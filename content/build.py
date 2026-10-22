"""Сборка контента задач (content/tasks/*, content/slots/*).

python content/build.py prepare           — в каждую задачу: общий тест-запрет tests/test_rules.py
                                            и раздел README «Где используется на карте» (из combinations.csv)
python content/build.py run recall f1     — прогнать тесты на эталоне локально, как это делает приложение:
                                            зависимости -> bricks/<имя>.py, слот -> slots/<слот>.py, контрактные тесты
python content/build.py run all"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from backend import skillmap  # noqa: E402

TASKS, SLOTS = ROOT / "tasks", ROOT / "slots"
START, END = "<!-- map:start -->", "<!-- map:end -->"


def meta(task: Path) -> dict:
    return json.loads((task / "task.json").read_text(encoding="utf-8"))


def map_section(name: str, parsed: dict) -> str:
    b = parsed["bricks"].get(name)
    titles = {r["key"]: r["title"] for r in parsed["rows"]}
    notes = meta(TASKS / name).get("map_notes", {})
    if not b:  # блок не из CSV (conv_block, train_one_epoch…): строки — те, где он нужен по цепочке
        return "".join(f"- [{titles.get(k, k)}](#/map) — {v}\n" for k, v in notes.items()) or "- на карте пока нет\n"
    return "".join(f"- [{titles[k]}](#/map/{name})" + (f" — {notes[k]}" if k in notes else "") + "\n" for k in b["rows"])


def prepare():
    parsed = skillmap.parse_csv((ROOT.parent / "combinations.csv").read_text(encoding="utf-8"))
    for task in sorted(p for p in TASKS.iterdir() if (p / "task.json").exists()):
        (task / "tests").mkdir(exist_ok=True)
        shutil.copy(ROOT / "common" / "test_rules.py", task / "tests" / "test_rules.py")
        shutil.copy(ROOT / "common" / "likelib.py", task / "tests" / "likelib.py")
        if meta(task).get("implements") == "optimizer":
            shutil.copy(ROOT / "common" / "optimlib.py", task / "tests" / "optimlib.py")
        readme = task / "description.md"
        text = readme.read_text(encoding="utf-8")
        if START in text:
            head, rest = text.split(START, 1)
            tail = rest.split(END, 1)[1]
            readme.write_text(f"{head}{START}\n{map_section(task.name, parsed)}{END}{tail}", encoding="utf-8")
        print("prepared", task.name)


def main_of(task: Path) -> str:
    return meta(task).get("main", "solution.py")


def assemble(task: Path, out: Path):
    """Код задачи в корень + все зависимости (эталоны) в bricks/ + slots/ — на любой глубине."""
    for f in (task / "reference").glob("*.py"):
        shutil.copy(f, out / f.name)
    add_deps(task, out, set())


def add_deps(task: Path, out: Path, seen: set):
    for d in meta(task).get("deps", []):
        dep = TASKS / d["task"] if d.get("task") else default_impl(d["slot"])
        mod = d["name"] if d.get("task") else dep.name
        (out / "bricks").mkdir(exist_ok=True)
        shutil.copy(dep / "reference" / main_of(dep), out / "bricks" / f"{mod}.py")
        if d.get("slot"):
            slot_shim(out, d["slot"], f"bricks.{mod}")
        if dep.name not in seen:
            seen.add(dep.name)
            add_deps(dep, out, seen)


def slot_meta(slot: str) -> dict:
    return json.loads((SLOTS / f"slot_{slot}" / "slot.json").read_text(encoding="utf-8"))


def default_impl(slot: str) -> Path:
    want = slot_meta(slot).get("default")
    if want and (TASKS / want).exists():
        return TASKS / want
    return next(p for p in sorted(TASKS.iterdir()) if (p / "task.json").exists() and meta(p).get("implements") == slot)


def slot_shim(out: Path, slot: str, module: str):
    (out / "slots").mkdir(exist_ok=True)
    sym = slot_meta(slot).get("symbol", slot)
    (out / "slots" / f"{slot}.py").write_text(f"from {module} import *  # noqa\nfrom {module} import {sym}  # noqa\n", encoding="utf-8")


def run(name: str) -> bool:
    task = TASKS / name
    out = Path(tempfile.mkdtemp(prefix=f"content-{name}-"))
    assemble(task, out)
    shutil.copytree(task / "tests", out / "tests")
    shutil.copy(task / "task.json", out / "task.json")
    shutil.copy(ROOT.parent / "backend" / "runtime" / "conftest_recall.py", out / "conftest.py")
    if (task / "data").exists():
        shutil.copytree(task / "data", out / "data")
    impl = meta(task).get("implements")
    if impl:
        slot_shim(out, impl, main_of(task)[:-3])
        for t in (SLOTS / f"slot_{impl}" / "tests").glob("test_*.py"):
            shutil.copy(t, out / "tests" / f"test_contract_{impl}_{t.name[5:]}")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"], cwd=out, capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or ["?"])[-1]
    print(f"{name:24} {last}")
    if r.returncode:
        print("\n".join([line for line in r.stdout.splitlines() if line.startswith(("FAILED", "ERROR", "E "))][:40]))
    shutil.rmtree(out, ignore_errors=True)
    return r.returncode == 0


if __name__ == "__main__":
    cmd, *names = sys.argv[1:] or ["prepare"]
    if cmd == "prepare":
        prepare()
    elif cmd == "run":
        names = [p.name for p in sorted(TASKS.iterdir()) if (p / "task.json").exists()] if names in ([], ["all"]) else names
        ok = [run(n) for n in names]
        sys.exit(0 if all(ok) else 1)
