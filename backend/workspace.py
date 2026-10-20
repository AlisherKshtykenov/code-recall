"""Папка эталона: data/workspaces/ref-<id>/{data,tests,results}.

- data/    — данные: загруженные файлы или символическая ссылка на папку на диске (без копирования);
- tests/   — тесты, по файлу на блок (зеркало базы, пишется автоматически);
- results/ — всё, что сохраняют ячейки. Попытки пишут в results/attempts/<id>/, чтобы не
             перезатирать файлы эталона.
Ядро эталона работает с cwd = папка эталона, поэтому pd.read_csv("data/x.csv") и
savefig("results/…") работают без правки путей."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .db import DATA_DIR

ROOT = DATA_DIR / "workspaces"
SUBDIRS = ("data", "tests", "results")


def ws(ref_id: int) -> Path:
    p = ROOT / f"ref-{ref_id}"
    for d in SUBDIRS:
        sub = p / d
        if not sub.exists() and not sub.is_symlink():
            sub.mkdir(parents=True, exist_ok=True)
    return p


def data_link(ref_id: int) -> str | None:
    """Куда указывает data/, если это ссылка на внешнюю папку."""
    d = ws(ref_id) / "data"
    return os.readlink(d) if d.is_symlink() else None


def bind_data(ref_id: int, target: str):
    """Привязать существующую папку как data/ (символическая ссылка, без копирования)."""
    t = Path(target).expanduser()
    if not t.is_absolute():
        raise ValueError("нужен абсолютный путь к папке")
    if not t.is_dir():
        raise ValueError(f"папки нет: {t}")
    d = ws(ref_id) / "data"
    if d.is_symlink():
        d.unlink()
    elif d.exists():
        if any(d.iterdir()):
            raise ValueError("в data/ уже есть файлы — удалите их или отвяжите, прежде чем привязывать папку")
        d.rmdir()
    d.symlink_to(t, target_is_directory=True)


def unbind_data(ref_id: int):
    d = ws(ref_id) / "data"
    if d.is_symlink():
        d.unlink()  # удаляется только ссылка, файлы в привязанной папке не трогаем
    d.mkdir(exist_ok=True)


def safe_path(ref_id: int, rel: str) -> Path:
    """Путь внутри папки эталона. Проверяем логический путь (до раскрытия ссылок),
    чтобы привязанная data/ работала, но выйти через '..' было нельзя."""
    base = ws(ref_id)
    rel = (rel or "").strip("/")
    norm = os.path.normpath(os.path.join(str(base), rel))
    if norm != str(base) and not norm.startswith(str(base) + os.sep):
        raise ValueError("путь вне папки эталона")
    return Path(norm)


def in_data(ref_id: int, p: Path) -> bool:
    data = str(ws(ref_id) / "data")
    return str(p) == data or str(p).startswith(data + os.sep)


KIND = {".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image", ".svg": "image", ".webp": "image",
        ".mp4": "video", ".webm": "video", ".mov": "video", ".mp3": "audio", ".wav": "audio", ".ogg": "audio",
        ".m4a": "audio", ".flac": "audio"}
TEXT = {".txt", ".csv", ".tsv", ".json", ".py", ".md", ".yaml", ".yml", ".log", ".ini", ".cfg", ".toml", ".xml",
        ".html", ".ipynb", ".sql", ".sh"}


def kind_of(p: Path) -> str:
    ext = p.suffix.lower()
    return KIND.get(ext) or ("text" if ext in TEXT else "file")


def listing(ref_id: int, rel: str = "") -> list[dict]:
    p = safe_path(ref_id, rel)
    if not p.is_dir():
        raise ValueError("это не папка")
    out = []
    try:
        entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        raise ValueError("нет доступа к папке")
    for e in entries[:2000]:
        if e.name.startswith(".") and e.name not in (".gitkeep",):
            continue
        r = os.path.relpath(e, ws(ref_id))
        try:
            st = e.stat()
        except OSError:  # битая ссылка
            out.append({"name": e.name, "path": r, "dir": False, "kind": "broken", "size": 0})
            continue
        out.append({"name": e.name, "path": r, "dir": e.is_dir(), "size": st.st_size if e.is_file() else None,
                    "kind": "dir" if e.is_dir() else kind_of(e), "link": os.readlink(e) if e.is_symlink() else None,
                    "mtime": int(st.st_mtime)})
    return out


def delete(ref_id: int, rel: str):
    p = safe_path(ref_id, rel)
    base = ws(ref_id)
    if p == base or p.parent == base and p.name in SUBDIRS:
        raise ValueError("корневые папки data/, tests/, results/ удалить нельзя (data можно отвязать)")
    if p.is_symlink():
        p.unlink()
    elif p.is_dir():
        if in_data(ref_id, p):
            raise ValueError("папки внутри data/ удаляются только вручную — это могут быть ваши датасеты")
        shutil.rmtree(p)
    elif p.exists():
        p.unlink()
    else:
        raise ValueError("файла нет")


def save_upload(ref_id: int, folder: str, name: str, content: bytes) -> str:
    d = safe_path(ref_id, folder)
    d.mkdir(parents=True, exist_ok=True)
    name = Path(name).name  # без путей из имени файла
    target = safe_path(ref_id, os.path.join(folder, name))
    target.write_bytes(content)
    return os.path.relpath(target, ws(ref_id))


# ---------- рабочие папки для попыток и проверки ----------

def _link_data(dst: Path, ref_id: int):
    """В отдельной рабочей папке data/ — ссылка на data/ эталона (данные не копируются)."""
    src = (ws(ref_id) / "data").resolve()
    d = dst / "data"
    if not d.exists() and not d.is_symlink():
        d.symlink_to(src, target_is_directory=True)
    (dst / "results").mkdir(exist_ok=True)


def attempt_dir(ref_id: int, attempt_id: int) -> Path:
    p = ws(ref_id) / "results" / "attempts" / str(attempt_id)
    p.mkdir(parents=True, exist_ok=True)
    _link_data(p, ref_id)
    return p


def temp_run_dir(ref_id: int) -> Path:
    """Изолированная папка для одной стороны проверки (эталон / ваш код)."""
    tmp = DATA_DIR / "tmp"
    tmp.mkdir(exist_ok=True)
    p = Path(tempfile.mkdtemp(prefix=f"check-{ref_id}-", dir=tmp))
    _link_data(p, ref_id)
    return p


# ---------- тесты — по файлу на блок ----------

def slug(s: str) -> str:
    s = re.sub(r"[^\w]+", "_", s.lower(), flags=re.U).strip("_")
    return s[:50] or "block"


def write_tests(ref_id: int, blocks: list[str], tests) -> None:
    """Зеркало тестов в tests/: файл на блок. Источник правды — база (правьте тесты в приложении)."""
    d = ws(ref_id) / "tests"
    for old in d.glob("*.py"):
        old.unlink()
    groups = {}
    for t in tests:
        groups.setdefault(t.block, []).append(t)
    order = {b: i for i, b in enumerate(blocks)}
    for block, items in groups.items():
        num = f"{order[block] + 1:02d}" if block in order else ("00" if not block else "xx")
        name = f"{num}_{slug(block) if block else 'whole_code'}.py"
        lines = [f"# Тесты блока «{block or 'весь код'}». Файл создаёт CODE RECALL — правьте тесты в приложении.",
                 "# Результат теста — значение последнего выражения.", ""]
        for t in items:
            mode = "assert: должно быть True" if t.mode == "assert" else "= результат эталона"
            flags = (" [не подтверждён]" if not t.approved else "") + (" [сломан]" if t.broken else "")
            lines += [f"# --- {t.name or f'тест #{t.id}'} ({mode}){flags}", t.code.rstrip(), ""]
        (d / name).write_text("\n".join(lines), encoding="utf-8")


# ---------- окружение Python ----------

def resolve_python(path: str) -> str:
    """Путь к .venv, к папке проекта с .venv или к самому python -> исполняемый python."""
    if not path:
        return sys.executable
    p = Path(path).expanduser()
    for cand in (p, p / "bin" / "python", p / ".venv" / "bin" / "python", p / "venv" / "bin" / "python",
                 p / "Scripts" / "python.exe"):
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    raise ValueError(f"не нашёл python в {p} (ожидается .venv, папка проекта с .venv или путь к python)")


def check_python(path: str) -> dict:
    """Проверка окружения: версия Python и есть ли ipykernel (без него ядро не запустится)."""
    py = resolve_python(path)
    code = ("import sys, importlib.util as u; print(sys.version.split()[0]); "
            "print(' '.join(m for m in ['ipykernel','numpy','pandas','torch','sklearn','matplotlib','plotly',"
            "'mlflow','xgboost','transformers'] if u.find_spec(m)))")
    try:
        r = subprocess.run([py, "-c", code], capture_output=True, text=True, timeout=30)
    except Exception as e:
        raise ValueError(f"не запускается {py}: {e}")
    if r.returncode != 0:
        raise ValueError(f"{py}: {r.stderr.strip()[:300]}")
    version, mods = (r.stdout.strip().splitlines() + ["", ""])[:2]
    mods = mods.split()
    return {"python": py, "version": version, "packages": mods, "ipykernel": "ipykernel" in mods,
            "fix": None if "ipykernel" in mods else f"{py} -m pip install ipykernel"}
