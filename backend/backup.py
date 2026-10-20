"""Бэкап: экспорт/импорт архива и автокопия SQLite раз в день (храним 7 последних)."""
import io
import json
import sqlite3
import threading
import time
import zipfile
from datetime import date, datetime
from pathlib import Path

from .db import DATA_DIR, engine

DB_PATH = DATA_DIR / "recall.db"
BACKUP_DIR = DATA_DIR / "backups"
KEEP = 7
REQUIRED_TABLES = {"references", "ref_versions", "ref_cells", "tests", "attempts", "settings"}


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
    for old in sorted(BACKUP_DIR.glob("recall-????-??-??.db"))[:-KEEP]:
        old.unlink()
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
    return [{"name": p.name, "size": p.stat().st_size,
             "created": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="minutes")}
            for p in sorted(BACKUP_DIR.glob("*.db"), reverse=True)]


def export_zip() -> bytes:
    """Архив: recall.db + исходники всех версий эталонов (для чтения глазами) + manifest."""
    buf = io.BytesIO()
    tmp = DATA_DIR / "export-tmp.db"
    snapshot(tmp)
    try:
        con = sqlite3.connect(tmp)
        rows = con.execute('SELECT r.id, r.filename, r.title, v.number, v.source FROM "references" r '
                           "JOIN ref_versions v ON v.reference_id = r.id ORDER BY r.id, v.number").fetchall()
        counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in REQUIRED_TABLES}
        con.close()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmp, "recall.db")
            for rid, filename, title, num, src in rows:
                name = Path(filename)
                z.writestr(f"references/{rid:03d}_{name.stem}/v{num}{name.suffix}", src)
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
        refs = con.execute('SELECT COUNT(*) FROM "references"').fetchone()[0]
        con.close()
    except sqlite3.DatabaseError:
        incoming.unlink(missing_ok=True)
        raise ValueError("recall.db в архиве — не SQLite-база")
    except ValueError:
        incoming.unlink(missing_ok=True)
        raise
    BACKUP_DIR.mkdir(exist_ok=True)
    saved = BACKUP_DIR / f"before-import-{datetime.now():%Y-%m-%d_%H-%M-%S}.db"
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
    return {"references": refs, "previous_saved_as": saved.name}
