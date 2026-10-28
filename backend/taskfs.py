"""Файлы задачи на диске.

data/tasks/<name>/
  description.md   описание (markdown + формулы), необязательно
  task.json        метаданные: title, kind, tag, timeout, main, roles {файл: write|given}
  reference/       эталон: .py, которые я учу
  starter/         заготовки для файлов «пишу сам» (то же имя, что в reference/), необязательно
  tests/           test_*.py (pytest)
  data/            датасеты — файлы или символическая ссылка на папку на диске
  results/         что сохраняет код эталона
  .attempts/<id>/  рабочая папка попытки: мои файлы в корне, data/ -> ../../data, свой results/
  .dev/            запуск эталона из редактора задачи: копия reference/ в корне

Рабочая директория любого запуска — «корень задачи» (файлы кода в корне, рядом data/ и results/),
поэтому pd.read_csv("data/x.csv") и `from model import Net` работают одинаково в коде и в тестах."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .db import DATA_DIR

ROOT = DATA_DIR / "tasks"
TEXT_DIRS = ("reference", "starter", "tests")
MAX_TEXT = 2_000_000  # байт: больше — не текстовый файл задачи, а данные


def slug(s: str) -> str:
    s = re.sub(r"[^\w.-]+", "_", s.strip(), flags=re.U).strip("._")
    return s[:80] or "task"


def task_dir(name: str) -> Path:
    p = ROOT / name
    for d in ("reference", "tests", "results"):
        (p / d).mkdir(parents=True, exist_ok=True)
    if not (p / "data").exists() and not (p / "data").is_symlink():
        (p / "data").mkdir()
    return p


# ---------- версии: текстовые файлы задачи ----------

def is_version_file(rel: str) -> bool:
    """Что входит в версию задачи (и в базу): описание, метаданные, эталон, заготовки, тесты."""
    parts = Path(rel).parts
    if not parts or any(p.startswith(".") or p == "__pycache__" for p in parts):
        return False
    if rel in ("description.md", "task.json"):
        return True
    if parts[0] in ("reference", "starter"):
        return rel.endswith(".py")
    if parts[0] == "tests":
        return rel.endswith((".py", ".json", ".txt", ".csv", ".yaml", ".yml"))
    return False


def files_hash(files: dict, roles: dict) -> str:
    h = hashlib.sha1()
    for k in sorted(files):
        h.update(k.encode() + b"\0" + files[k].encode() + b"\0")
    h.update(json.dumps(roles, sort_keys=True).encode())
    return h.hexdigest()


def snapshot(name: str) -> dict:
    """Текстовые файлы задачи с диска -> {путь: текст}."""
    base = task_dir(name)
    out = {}
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base).as_posix()
        if p.is_file() and not p.is_symlink() and is_version_file(rel) and p.stat().st_size <= MAX_TEXT:
            try:
                out[rel] = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                pass
    return out


def materialize(name: str, files: dict):
    """Записать версию на диск: reference/, starter/, tests/, description.md, task.json.
    data/ и results/ не трогаем."""
    base = task_dir(name)
    for d in TEXT_DIRS:
        for p in sorted((base / d).rglob("*"), reverse=True) if (base / d).exists() else []:
            rel = p.relative_to(base).as_posix()
            if p.is_file() and is_version_file(rel) and rel not in files:
                p.unlink()
    for f in ("description.md", "task.json"):
        if f not in files and (base / f).exists():
            (base / f).unlink()
    for rel, text in files.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists() or p.read_text(encoding="utf-8", errors="replace") != text:
            p.write_text(text, encoding="utf-8")


MODES = ("library", "scratch")  # «Библиотека» — через готовую функцию; «С нуля» — своими руками
MODE_NAME = {"library": "библиотека", "scratch": "с нуля"}


def _nested(files: dict) -> bool:
    """Новая раскладка reference/library/, reference/scratch/ (а не плоский reference/*.py)."""
    return any(k.startswith(("reference/library/", "reference/scratch/")) for k in files)


def modes_of(files: dict) -> list[str]:
    """Режимы задачи по эталонам: [library, scratch], один из них или [] (концепт). Плоский reference/ — это scratch."""
    if _nested(files):
        return [m for m in MODES if any(k.startswith(f"reference/{m}/") for k in files)]
    return ["scratch"] if any(k.startswith("reference/") for k in files) else []


def default_mode(files: dict) -> str:
    """Какой режим предлагать первым: «Библиотека», если она есть (сначала — как применять)."""
    ms = modes_of(files)
    return "library" if "library" in ms else (ms[0] if ms else "scratch")


def ref_mode(files: dict) -> str:
    """Чей эталон подключать скрыто, когда кирпичик «эталоном»: свой (с нуля), если есть."""
    ms = modes_of(files)
    return "scratch" if "scratch" in ms else (ms[0] if ms else "scratch")


def reference_files(files: dict, mode: str | None = None) -> dict:
    """{имя файла: текст} эталона режима (без префикса reference/<режим>/)."""
    mode = mode or ref_mode(files)
    if _nested(files):
        prefix = f"reference/{mode}/"
        return {k[len(prefix):]: v for k, v in files.items() if k.startswith(prefix)}
    if mode != "scratch":
        return {}
    return {k[len("reference/"):]: v for k, v in files.items() if k.startswith("reference/")}


def reference_names(files: dict) -> list[str]:
    """Имена файлов эталона по всем режимам (они одинаковые в обоих режимах)."""
    return sorted({n for m in modes_of(files) for n in reference_files(files, m)})


def test_files(files: dict, mode: str | None = None) -> dict:
    """Общие тесты tests/* + тесты режима tests/<mode>/* (кладутся плоско как tests/test_<mode>__<имя>,
    чтобы одноимённые файлы разных режимов не мешали pytest). mode=None — только общие."""
    out = {k: v for k, v in files.items() if k.startswith("tests/") and not k.startswith(("tests/library/", "tests/scratch/"))}
    if mode:
        prefix = f"tests/{mode}/"
        for k, v in files.items():
            if k.startswith(prefix):
                rest = k[len(prefix):]
                name = f"tests/test_{mode}__{rest[5:]}" if rest.startswith("test_") and "/" not in rest else f"tests/{rest}"
                out[name] = v
    return out


def all_test_files(files: dict) -> dict:
    return {k: v for k, v in files.items() if k.startswith("tests/")}


def default_roles(files: dict, meta: dict | None = None) -> dict:
    """Роль каждого файла эталона: write (пишу сам) или given (дан как есть). По умолчанию — write."""
    given = (meta or {}).get("roles", {})
    return {f: ("given" if given.get(f) == "given" else "write") for f in reference_names(files)}


def json_list(text) -> list:
    """Список из JSON-колонки: NULL, пустая строка или битый JSON -> []."""
    try:
        v = json.loads(text or "[]")
    except (ValueError, TypeError):
        return []
    return v if isinstance(v, list) else []


def json_dict(text) -> dict:
    try:
        v = json.loads(text or "{}")
    except (ValueError, TypeError):
        return {}
    return v if isinstance(v, dict) else {}


def read_meta(files: dict) -> dict:
    return json_dict(files.get("task.json"))


def attempt_start_files(files: dict, roles: dict, mode: str | None = None) -> dict:
    """Файлы новой попытки режима: «дан» — как в эталоне, «пишу сам» — заготовка (starter/<режим>/ или starter/) или пусто."""
    mode = mode or default_mode(files)
    out = {}
    for f, text in reference_files(files, mode).items():
        out[f] = text if roles.get(f) == "given" else files.get(f"starter/{mode}/{f}", files.get(f"starter/{f}", ""))
    return out


# ---------- данные ----------

def data_link(name: str) -> str | None:
    d = task_dir(name) / "data"
    return os.readlink(d) if d.is_symlink() else None


def bind_data(name: str, target: str):
    """Привязать существующую папку как data/ (символическая ссылка, без копирования)."""
    t = Path(target).expanduser()
    if not t.is_absolute():
        raise ValueError("нужен абсолютный путь к папке")
    if not t.is_dir():
        raise ValueError(f"папки нет: {t}")
    d = task_dir(name) / "data"
    if d.is_symlink():
        d.unlink()
    elif d.exists():
        if any(d.iterdir()):
            raise ValueError("в data/ уже есть файлы — удалите их, прежде чем подключать папку")
        d.rmdir()
    d.symlink_to(t, target_is_directory=True)


def unbind_data(name: str):
    d = task_dir(name) / "data"
    if d.is_symlink():
        d.unlink()  # удаляется только ссылка, файлы в привязанной папке на месте
    d.mkdir(exist_ok=True)


# ---------- рабочие папки ----------

def _link(dst: Path, src: Path):
    """Ссылка на data/ (или results/) задачи. Относительная: если data/ задачи потом
    привяжут к другой папке, ссылки попыток и прогонов пойдут туда же."""
    want = os.path.relpath(src, dst.parent)
    if dst.is_symlink():
        if os.readlink(dst) == want:
            return
        dst.unlink()
    elif dst.exists():
        return
    try:
        dst.symlink_to(want, target_is_directory=True)
    except FileExistsError:  # параллельный запрос успел создать её же
        pass


def write_code(root: Path, code: dict):
    """Положить .py в корень рабочей папки; лишние .py, которых больше нет, убрать."""
    root.mkdir(parents=True, exist_ok=True)
    for p in root.rglob("*.py"):
        rel = p.relative_to(root).as_posix()
        if rel.split("/")[0] in ("data", "results", "tests", ".lib") or rel == "conftest.py":
            continue
        if rel not in code:
            p.unlink()
    for rel, text in code.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists() or p.read_text(encoding="utf-8", errors="replace") != text:
            p.write_text(text, encoding="utf-8")


def attempt_dir(name: str, attempt_id: int) -> Path:
    p = task_dir(name) / ".attempts" / str(attempt_id)
    (p / "results").mkdir(parents=True, exist_ok=True)
    _link(p / "data", task_dir(name) / "data")
    return p


def dev_dir(name: str, files: dict | None = None, mode: str | None = None) -> Path:
    """Запуск эталона из редактора задачи: копия reference/<режим>/ в корне, data/ и results/ задачи."""
    base = task_dir(name)
    p = base / ".dev"
    p.mkdir(exist_ok=True)
    _link(p / "data", base / "data")
    _link(p / "results", base / "results")
    write_code(p, reference_files(files if files is not None else snapshot(name), mode))
    return p


def run_dir(name: str, code: dict, tests: dict) -> Path:
    """Изолированная папка для прогона тестов: код + tests/ + conftest.py, data/ по ссылке."""
    tmp = DATA_DIR / "tmp"
    tmp.mkdir(exist_ok=True)
    p = Path(tempfile.mkdtemp(prefix=f"run-{name[:20]}-", dir=tmp))
    write_code(p, code)
    for rel, text in tests.items():
        f = p / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    shutil.copy(Path(__file__).parent / "runtime" / "conftest_recall.py", p / "conftest.py")
    _link(p / "data", task_dir(name) / "data")
    (p / "results").mkdir(exist_ok=True)
    return p


# ---------- дерево и файлы ----------

def safe(base: Path, rel: str) -> Path:
    """Путь внутри base: проверяем логический путь (до раскрытия ссылок), чтобы привязанная
    data/ работала, а выйти через '..' было нельзя."""
    rel = (rel or "").strip("/")
    norm = os.path.normpath(os.path.join(str(base), rel))
    if norm != str(base) and not norm.startswith(str(base) + os.sep):
        raise ValueError("путь вне папки задачи")
    return Path(norm)


KIND = {".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image", ".svg": "image", ".webp": "image",
        ".mp4": "video", ".webm": "video", ".mov": "video", ".mp3": "audio", ".wav": "audio", ".ogg": "audio",
        ".m4a": "audio", ".flac": "audio", ".py": "python", ".md": "markdown",
        ".csv": "table", ".tsv": "table", ".parquet": "table", ".xlsx": "table", ".xls": "table", ".json": "json"}
TEXTISH = {".txt", ".log", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".sh", ".sql", ".html", ".xml"}


def kind_of(p: Path) -> str:
    ext = p.suffix.lower()
    return KIND.get(ext) or ("text" if ext in TEXTISH else "file")


def listing(base: Path, rel: str = "", hide: tuple = ()) -> list[dict]:
    p = safe(base, rel)
    if not p.is_dir():
        raise ValueError("это не папка")
    out = []
    try:
        entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        raise ValueError("нет доступа к папке")
    for e in entries[:3000]:
        r = os.path.relpath(e, base)
        if e.name.startswith(".") or e.name == "__pycache__" or r in hide:
            continue
        try:
            st = e.stat()
        except OSError:
            out.append({"name": e.name, "path": r, "dir": False, "kind": "broken", "size": 0})
            continue
        out.append({"name": e.name, "path": r, "dir": e.is_dir(), "size": None if e.is_dir() else st.st_size,
                    "kind": "dir" if e.is_dir() else kind_of(e),
                    "link": os.readlink(e) if e.is_symlink() else None, "mtime": int(st.st_mtime)})
    return out


def protected(base: Path, p: Path) -> bool:
    return p == base or (p.parent == base and p.name in ("data", "results", "reference", "tests"))


def delete(base: Path, rel: str):
    p = safe(base, rel)
    if protected(base, p):
        raise ValueError("эту папку удалить нельзя (data/ можно отключить)")
    data = str(base / "data")
    if p.is_symlink():
        p.unlink()
    elif p.is_dir():
        if str(p).startswith(data + os.sep):
            raise ValueError("папки внутри data/ удаляются только вручную — это могут быть ваши датасеты")
        shutil.rmtree(p)
    elif p.exists():
        p.unlink()
    else:
        raise ValueError("файла нет")


def rename(base: Path, rel: str, new_rel: str) -> str:
    src, dst = safe(base, rel), safe(base, new_rel)
    if protected(base, src):
        raise ValueError("эту папку переименовать нельзя")
    if dst.exists():
        raise ValueError("файл с таким именем уже есть")
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return os.path.relpath(dst, base)


def table_preview(p: Path, limit: int = 200) -> dict:
    """Превью таблицы: первые строки, размер, типы колонок."""
    import pandas as pd
    ext = p.suffix.lower()
    total = None
    if ext in (".csv", ".tsv"):
        sep = "\t" if ext == ".tsv" else ","
        df = pd.read_csv(p, sep=sep, nrows=limit)
        with open(p, "rb") as f:  # число строк без чтения всего файла в память
            total = max(0, sum(chunk.count(b"\n") for chunk in iter(lambda: f.read(1 << 20), b"")) - 1)
        cols = len(df.columns)
    elif ext == ".parquet":
        import pyarrow.parquet as pq
        pf = pq.ParquetFile(p)
        total, cols = pf.metadata.num_rows, pf.metadata.num_columns
        df = next(pf.iter_batches(batch_size=limit)).to_pandas() if total else pd.DataFrame()
    elif ext in (".xlsx", ".xls"):
        df_all = pd.read_excel(p)
        total, cols = len(df_all), len(df_all.columns)
        df = df_all.head(limit)
    elif ext == ".json":
        try:
            df_all = pd.read_json(p)
        except ValueError:
            df_all = pd.read_json(p, lines=True)
        total, cols = len(df_all), len(df_all.columns)
        df = df_all.head(limit)
    else:
        raise ValueError("не таблица")
    return {"columns": [str(c) for c in df.columns], "dtypes": [str(t) for t in df.dtypes],
            "rows": [[None if pd.isna(v) else _cell(v) for v in row] for row in df.head(limit).itertuples(index=False)],
            "n_rows": total if total is not None else len(df), "n_cols": cols if total is not None else len(df.columns)}


def _cell(v):
    s = str(v)
    return s if len(s) <= 200 else s[:200] + "…"


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
    """Версия Python и пакеты; для проверки нужен pytest."""
    py = resolve_python(path)
    mods = ["pytest", "numpy", "pandas", "matplotlib", "torch", "sklearn", "xgboost", "mlflow", "transformers", "dill"]
    dist = {"sklearn": "scikit-learn"}
    code = ("import sys, importlib.util as u, importlib.metadata as md, json; print(sys.version.split()[0]); "
            f"print(' '.join(m for m in {mods!r} if u.find_spec(m)))\n"
            "def v(m):\n    try: return md.version(" + repr(dist) + ".get(m, m))\n    except Exception: return ''\n"
            f"print(json.dumps({{m: v(m) for m in {mods!r} if u.find_spec(m)}}))")
    try:
        r = subprocess.run([py, "-c", code], capture_output=True, text=True, timeout=30)
    except Exception as e:
        raise ValueError(f"не запускается {py}: {e}")
    if r.returncode != 0:
        raise ValueError(f"{py}: {r.stderr.strip()[:300]}")
    version, found, vers = (r.stdout.strip().splitlines() + ["", "", "{}"])[:3]
    found = found.split()
    try:
        versions = json.loads(vers)
    except ValueError:
        versions = {}
    return {"python": py, "version": version, "packages": found, "versions": versions, "pytest": "pytest" in found,
            "fix": None if "pytest" in found else f"{py} -m pip install pytest"}
