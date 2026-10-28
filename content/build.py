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
        (task / "tests" / "test_rules.py").unlink(missing_ok=True)  # старое место проверки «С нуля»
        for mode, rules in (("scratch", "test_rules.py"), ("library", "test_library_rules.py")):
            if mode in modes(task):  # проверки режима — только если у задачи есть этот режим
                (task / "tests" / mode).mkdir(exist_ok=True)
                shutil.copy(ROOT / "common" / rules, task / "tests" / mode / rules)
            else:
                shutil.rmtree(task / "tests" / mode, ignore_errors=True)
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


def modes(task: Path) -> list:
    """Режимы задачи: library и/или scratch — по папкам reference/<режим>/ (плоский reference/ — scratch)."""
    found = [m for m in ("library", "scratch") if (task / "reference" / m).is_dir()]
    return found or (["scratch"] if list((task / "reference").glob("*.py")) else [])


def ref_dir(task: Path, mode: str | None = None) -> Path:
    mode = mode or ("scratch" if "scratch" in modes(task) else modes(task)[0])
    return task / "reference" / mode if (task / "reference" / mode).is_dir() else task / "reference"


def main_of(task: Path) -> str:
    return meta(task).get("main", "solution.py")


def assemble(task: Path, out: Path, mode: str):
    """Код задачи режима mode в корень + зависимости этого режима (эталоны — с нуля, если есть) в bricks/ + slots/."""
    for f in ref_dir(task, mode).glob("*.py"):
        shutil.copy(f, out / f.name)
    add_deps(task, out, set(), mode)


def add_deps(task: Path, out: Path, seen: set, mode: str):
    for d in meta(task).get("deps", []):
        if isinstance(d.get("modes"), list) and mode not in d["modes"]:
            continue  # зависимость нужна только другому режиму
        dep = TASKS / d["task"] if d.get("task") else default_impl(d["slot"])
        mod = d["name"] if d.get("task") else dep.name
        (out / "bricks").mkdir(exist_ok=True)
        dep_mode = "scratch" if "scratch" in modes(dep) else modes(dep)[0]  # скрытый эталон — с нуля, как в приложении
        shutil.copy(ref_dir(dep, dep_mode) / main_of(dep), out / "bricks" / f"{mod}.py")
        if d.get("slot"):
            slot_shim(out, d["slot"], f"bricks.{mod}")
        if dep.name not in seen:
            seen.add(dep.name)
            add_deps(dep, out, seen, dep_mode)


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


def copy_tests(task: Path, out: Path, mode: str):
    """Общие тесты + тесты режима, плоско как tests/test_<режим>__<имя> (так же раскладывает приложение)."""
    (out / "tests").mkdir()
    for f in (task / "tests").iterdir():
        if f.is_file():
            shutil.copy(f, out / "tests" / f.name)
    for f in (task / "tests" / mode).glob("*") if (task / "tests" / mode).is_dir() else []:
        name = f"test_{mode}__{f.name[5:]}" if f.name.startswith("test_") else f.name
        shutil.copy(f, out / "tests" / name)


def run(name: str, mode: str | None = None) -> bool:
    task = TASKS / name
    if mode is None:
        return all([run(name, m) for m in modes(task)])
    out = Path(tempfile.mkdtemp(prefix=f"content-{name}-"))
    assemble(task, out, mode)
    copy_tests(task, out, mode)
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
    print(f"{name:24} {mode:8} {last}")
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
        ok = [run(*n.split(":")) for n in names]  # recall или recall:library
        sys.exit(0 if all(ok) else 1)
