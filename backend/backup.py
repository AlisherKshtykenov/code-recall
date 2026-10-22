"""Бэкап: экспорт/импорт архива и автокопия SQLite раз в день (храним 7 последних).

data/backups/recall-ГГГГ-ММ-ДД.db — автокопии, ротация (KEEP последних) касается ТОЛЬКО их.
data/backups/manual/                — ручные и предмиграционные копии (перед импортом, миграцией, правками):
                                      не удаляются никогда. Прочие файлы в data/backups/ тоже не трогаются."""
import io
import json
import sqlite3
import threading
import time
import zipfile
from datetime import date, datetime
from pathlib import Path

from .db import DATA_DIR, DB_PATH, engine

BACKUP_DIR = DATA_DIR / "backups"
MANUAL_DIR = BACKUP_DIR / "manual"
AUTO_PATTERN = "recall-[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].db"
KEEP = 7
REQUIRED_TABLES = {"tasks", "task_versions", "attempts", "settings"}


def snapshot(dest: Path):
    """Согласованная копия живой базы через sqlite backup API (безопасно во время работы)."""
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()


def daily_backup() -> Path | None:
    BACKUP_DIR.mkdir(exist_ok=True)
    target = BACKUP_DIR / f"recall-{date.today().isoformat()}.db"
    if target.exists() or not DB_PATH.exists():
        return None
    snapshot(target)
    for old in sorted(BACKUP_DIR.glob(AUTO_PATTERN))[:-KEEP]:  # только автокопии; manual/ и остальное — никогда
        old.unlink()
    return target


def manual_backup(reason: str) -> Path:
    """Ручная / предмиграционная копия в backups/manual/ — вне ротации."""
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    target = MANUAL_DIR / f"{reason}-{datetime.now():%Y-%m-%d_%H-%M-%S}.db"
    snapshot(target)
    return target


def start_daily_thread():
    def loop():
        while True:
            try:
                daily_backup()
            except Exception as e:  # бэкап не должен ронять сервер
                print("автокопия не удалась:", e)
            time.sleep(3600)  # проверяем раз в час, копия — раз в сутки
    threading.Thread(target=loop, daemon=True).start()


def list_backups() -> list[dict]:
    BACKUP_DIR.mkdir(exist_ok=True)
    files = [*BACKUP_DIR.glob("*.db"), *(MANUAL_DIR.glob("*.db") if MANUAL_DIR.exists() else [])]
    return [{"name": p.relative_to(BACKUP_DIR).as_posix(), "size": p.stat().st_size, "auto": p.match(AUTO_PATTERN),
             "created": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="minutes")}
            for p in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)]


def export_zip() -> bytes:
    """Архив: recall.db + текстовые файлы текущих версий задач (для чтения глазами) + manifest.
    Датасеты из data/ в архив не входят — они бывают большими и часто привязаны к папкам на диске."""
    buf = io.BytesIO()
    tmp = DATA_DIR / "export-tmp.db"
    snapshot(tmp)
    try:
        con = sqlite3.connect(tmp)
        rows = con.execute("SELECT t.name, v.files FROM tasks t JOIN task_versions v ON v.task_id = t.id "
                           "WHERE v.number = (SELECT MAX(number) FROM task_versions WHERE task_id = t.id)").fetchall()
        counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in REQUIRED_TABLES}
        con.close()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmp, "recall.db")
            for name, files in rows:
                for rel, text in json.loads(files).items():
                    z.writestr(f"tasks/{name}/{rel}", text)
            z.writestr("manifest.json", json.dumps({
                "app": "CODE RECALL", "exported_at": datetime.now().isoformat(timespec="seconds"),
                "counts": counts}, ensure_ascii=False, indent=2))
    finally:
        tmp.unlink(missing_ok=True)
    return buf.getvalue()


def import_zip(data: bytes) -> dict:
    """Заменяет базу базой из архива. Текущая база перед этим копируется в backups/."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("это не zip-архив")
    if "recall.db" not in z.namelist():
        raise ValueError("в архиве нет recall.db — это не экспорт CODE RECALL")
    incoming = DATA_DIR / "import-tmp.db"
    incoming.write_bytes(z.read("recall.db"))
    try:
        con = sqlite3.connect(incoming)
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("база в архиве повреждена")
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = REQUIRED_TABLES - tables
        if missing:
            raise ValueError(f"в базе нет таблиц: {', '.join(sorted(missing))}")
        refs = con.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        con.close()
    except sqlite3.DatabaseError:
        incoming.unlink(missing_ok=True)
        raise ValueError("recall.db в архиве — не SQLite-база")
    except ValueError:
        incoming.unlink(missing_ok=True)
        raise
    BACKUP_DIR.mkdir(exist_ok=True)
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    saved = MANUAL_DIR / f"before-import-{datetime.now():%Y-%m-%d_%H-%M-%S}.db"  # вне ротации
    if DB_PATH.exists():
        snapshot(saved)
    # Пишем поверх через backup API: файл и соединения остаются прежними.
    engine.dispose()
    src = sqlite3.connect(incoming)
    dst = sqlite3.connect(DB_PATH)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()
    incoming.unlink(missing_ok=True)
    restore_task_folders()
    return {"tasks": refs, "previous_saved_as": saved.name}


def restore_task_folders():
    """Папки задач на диске = текущие версии из базы (data/ и results/ не трогаются)."""
    from . import taskfs
    con = sqlite3.connect(DB_PATH)
    rows = con.execute("SELECT t.name, v.files FROM tasks t JOIN task_versions v ON v.task_id = t.id "
                       "WHERE v.number = (SELECT MAX(number) FROM task_versions WHERE task_id = t.id)").fetchall()
    con.close()
    for name, files in rows:
        taskfs.materialize(name, json.loads(files))
