"""Кирпичики: задачи, собранные из задач.

task.json задачи может объявить:
  "implements": "loss"                       — задача реализует слот loss (проходит его контрактные тесты)
  "deps": [{"name": "split", "task": "train_test_split"},   — зависимость от задачи
           {"name": "loss", "slot": "loss"}]                 — зависимость от слота (реализация выбирается)

Импорт в коде — по фиксированным именам:
  from bricks.split import train_test_split      bricks/<имя зависимости>.py — код кирпичика
  from slots.loss import loss                    slots/<слот>.py — реэкспорт выбранной реализации

Сборка (assembly) — для каждой зависимости (на любой глубине): source = self (пишу сам) | ref (эталон,
скрыт) | last (моя последняя версия, где все тесты прошли); для слота ещё impl — какая задача-реализация.
«Пишу сам» — файл bricks/<имя>.py лежит в папке попытки; эталонные — в скрытой .lib/ рядом
(bricks и slots — namespace-пакеты, части из корня и из .lib/ сливаются). Циклы запрещены."""
import hashlib
import json

from . import taskfs
from .db import Attempt, BrickEvent, Slot, Task

SOURCES = ("self", "ref", "last")


class DepError(ValueError):
    pass


def files_of(task: Task) -> dict:
    return json.loads(task.current.files) if task.current else {}


def deps_of(files: dict) -> list[dict]:
    """Зависимости из task.json: [{name, task} | {name, slot}]; name — имя модуля для импорта."""
    out = []
    deps = taskfs.read_meta(files).get("deps")
    for d in deps if isinstance(deps, list) else []:
        if not isinstance(d, dict) or not (d.get("task") or d.get("slot")):
            continue
        target = d.get("task") or d.get("slot")
        name = taskfs.slug(str(d.get("name") or target)).replace("-", "_").replace(".", "_").lower()
        out.append({"name": name, "task": d.get("task"), "slot": d.get("slot")} if d.get("task")
                   else {"name": name, "slot": d["slot"], "task": None})
    return out


def implements_of(files: dict) -> str:
    v = taskfs.read_meta(files).get("implements")
    return str(v) if v else ""


def main_module(task: Task, files: dict | None = None) -> str:
    """Файл кирпичика, который становится bricks/<имя>.py: главный файл задачи или единственный в reference/."""
    ref = taskfs.reference_files(files if files is not None else files_of(task))
    if task.main_file in ref:
        return task.main_file
    written = sorted(ref)
    if len(written) == 1:
        return written[0]
    return "solution.py" if "solution.py" in ref else (written[0] if written else "solution.py")


def find_task(db, name: str) -> Task | None:
    if not name:
        return None
    t = db.query(Task).filter_by(name=name).first()
    return t or db.query(Task).filter_by(name=taskfs.slug(name)).first()


def impls(db, slot: str) -> list[Task]:
    """Задачи, текущая версия которых объявляет «реализую слот slot»."""
    return [t for t in db.query(Task).order_by(Task.title).all() if t.current and implements_of(files_of(t)) == slot]


def module_name(task: Task) -> str:
    return taskfs.slug(task.name).replace("-", "_").replace(".", "_").lower()


def tree(db, task: Task, assembly: dict | None = None, files: dict | None = None) -> list[dict]:
    """Все зависимости задачи на любой глубине (сначала ближние), с выбранной реализацией слотов.
    Узел: {name, kind: task|slot, slot, task_id, title, module, depth, parent, impls}."""
    assembly = assembly or {}
    nodes, seen = [], {}

    def walk(t: Task, fl: dict, depth: int, parent: str | None, stack: list):
        for d in deps_of(fl):
            if d["slot"]:
                s = db.query(Slot).filter_by(name=d["slot"]).first()
                options = impls(db, d["slot"])
                want = (assembly.get(d["name"]) or {}).get("impl") or (s.default_impl if s else "")
                target = find_task(db, want) if want else None
                if target not in options:
                    target = options[0] if options else None
                if target is None:
                    raise DepError(f"у слота «{d['slot']}» нет ни одной реализации (задачи с \"implements\": \"{d['slot']}\")")
                node = {"name": d["name"], "kind": "slot", "slot": d["slot"], "symbol": (s.symbol if s and s.symbol else d["slot"]),
                        "slot_known": s is not None, "impls": [{"id": x.id, "name": x.name, "title": x.title} for x in options]}
                mod = module_name(target)
            else:
                target = find_task(db, d["task"])
                if target is None:
                    raise DepError(f"{t.title}: нет задачи «{d['task']}» (зависимость {d['name']})")
                node = {"name": d["name"], "kind": "task"}
                mod = d["name"]
            if target.id in stack:
                chain = " → ".join([db.get(Task, i).title for i in stack] + [target.title])
                raise DepError(f"цикл зависимостей: {chain}")
            key = d["name"]
            if key in seen:
                if seen[key]["task_id"] != target.id:
                    raise DepError(f"имя «{key}» занято двумя разными кирпичиками: {seen[key]['title']} и {target.title}")
                continue
            node.update(task_id=target.id, task_name=target.name, title=target.title, module=f"bricks/{mod}.py",
                        depth=depth, parent=parent, main=main_module(target))
            seen[key] = node
            nodes.append(node)
            walk(target, files_of(target), depth + 1, key, stack + [target.id])

    walk(task, files if files is not None else files_of(task), 0, None, [task.id])
    return nodes


def check_cycles(db, task: Task, files: dict):
    """Перед сохранением версии: зависимости разрешимы и без циклов."""
    tree(db, task, {}, files)


def source_of(assembly: dict, node: dict) -> str:
    s = (assembly.get(node["name"]) or {}).get("source", "ref")
    return s if s in SOURCES else "ref"


def last_good(db, task: Task) -> dict | None:
    """«Моя последняя версия»: последний код кирпичика, на котором прошли все его тесты —
    из сданной попытки самого кирпичика или из составной задачи."""
    main = main_module(task)
    best = None
    for a in db.query(Attempt).filter_by(task_id=task.id, status="submitted").all():
        res = (json.loads(a.report) if a.report else {}).get("result") or {}
        if res.get("total") and res.get("passed") == res.get("total"):
            code = json.loads(a.files).get(main)
            if code is not None and (best is None or a.finished_at > best["at"]):
                best = {"code": code, "at": a.finished_at, "from": f"попытка {a.finished_at:%Y-%m-%d}"}
    for e in db.query(BrickEvent).filter_by(task_id=task.id, passed=1).all():
        if best is None or e.at > best["at"]:
            parent = db.get(Task, e.parent_task_id)
            best = {"code": e.code, "at": e.at, "from": f"в задаче «{parent.title if parent else '?'}» {e.at:%Y-%m-%d}"}
    return best


def brick_ref(db, node: dict) -> str:
    t = db.get(Task, node["task_id"])
    return taskfs.reference_files(files_of(t)).get(node["main"], "")


def brick_starter(db, node: dict) -> str:
    t = db.get(Task, node["task_id"])
    return files_of(t).get(f"starter/{node['main']}", "")


def slot_shim(node: dict) -> str:
    mod = node["module"][len("bricks/"):-3]
    return (f"# слот {node['slot']}: реализация — {node['title']}\n"
            f"from bricks.{mod} import *  # noqa: F401,F403\nfrom bricks.{mod} import {node['symbol']}  # noqa: F401\n")


def self_paths(nodes: list[dict], assembly: dict) -> list[str]:
    return [n["module"] for n in nodes if source_of(assembly, n) == "self"]


def assemble(db, task: Task, files: dict, assembly: dict, mine: dict) -> tuple[dict, dict]:
    """(code, lib): code — мои файлы (свои + кирпичики «пишу сам»), lib — скрытое: кирпичики-эталоны,
    «моя последняя версия», slots/*.py. Для задачи без зависимостей lib пуст (кроме слота, который она реализует)."""
    nodes = tree(db, task, assembly, files)
    code, lib = dict(mine), {}
    for n in nodes:
        src = source_of(assembly, n)
        if src == "self":
            code.setdefault(n["module"], "")
        elif src == "last":
            lg = last_good(db, db.get(Task, n["task_id"]))
            lib[n["module"]] = lg["code"] if lg else brick_ref(db, n)
        else:
            lib[n["module"]] = brick_ref(db, n)
        if n["kind"] == "slot":
            lib[f"slots/{n['slot']}.py"] = slot_shim(n)
    impl = implements_of(files)
    if impl:  # сама задача реализует слот: контрактные тесты импортируют from slots.<слот> import …
        s = db.query(Slot).filter_by(name=impl).first()
        sym = s.symbol if s and s.symbol else impl
        mod = main_module(task, files)[:-3].replace("/", ".")
        lib.setdefault(f"slots/{impl}.py", f"# слот {impl}: реализация — эта задача\nfrom {mod} import *  # noqa\nfrom {mod} import {sym}  # noqa\n")
    return code, lib


def contract_tests(db, files: dict) -> dict:
    """Контрактные тесты слота, который реализует задача: tests/contract_<слот>/…"""
    impl = implements_of(files)
    if not impl:
        return {}
    s = db.query(Slot).filter_by(name=impl).first()
    if not s:
        return {}
    out = {}
    for rel, text in taskfs.json_dict(s.tests).items():
        base = rel.split("/")[-1]
        out[f"tests/test_contract_{impl}_{base[5:] if base.startswith('test_') else base}"] = text
    return out


def reference_code(db, task: Task, files: dict, assembly: dict) -> dict:
    """Эталон всего, что можно писать в этой сборке: свои файлы и кирпичики «пишу сам» (bricks/<имя>.py)."""
    out = dict(taskfs.reference_files(files))
    for n in tree(db, task, assembly, files):
        if source_of(assembly, n) == "self":
            out[n["module"]] = brick_ref(db, n)
    return out


def written_paths(db, task: Task, files: dict, assembly: dict) -> list[str]:
    """Что я пишу сам: свои файлы с ролью «пишу сам» + кирпичики «пишу сам»."""
    roles = taskfs.default_roles(files, taskfs.read_meta(files))
    own = [f for f in sorted(taskfs.reference_files(files)) if roles.get(f) != "given"]
    return own + self_paths(tree(db, task, assembly, files), assembly)


def brick_of(db, task: Task, files: dict, assembly: dict) -> dict:
    """{путь файла: узел кирпичика} — чтобы в отчётах писать «кирпичик split», а не путь."""
    return {n["module"]: n for n in tree(db, task, assembly, files)}


def deps_key(db, task: Task, files: dict, assembly: dict | None = None) -> str:
    """Отпечаток эталонов всех зависимостей — часть ключа кэша тестов на эталоне."""
    h = hashlib.sha1()
    try:
        for n in tree(db, task, assembly or {}, files):
            t = db.get(Task, n["task_id"])
            h.update(f"{n['name']}={t.name}@{t.current.content_hash};".encode())
        impl = implements_of(files)
        if impl:
            s = db.query(Slot).filter_by(name=impl).first()
            h.update((s.tests if s else "").encode())
    except DepError as e:
        h.update(str(e).encode())
    return h.hexdigest()[:12]


def dependents(db, task: Task) -> list[Task]:
    """Задачи, в дереве которых (на любой глубине, в т.ч. через слот) есть task."""
    out = []
    for t in db.query(Task).all():
        if t.id == task.id or not t.current:
            continue
        try:
            # эталонная сборка (реализации слотов по умолчанию) — та же, на которой гоняются тесты на эталоне
            if any(n["task_id"] == task.id for n in tree(db, t, {})):
                out.append(t)
        except DepError:
            continue
    return out


def write_lib(root, lib: dict):
    """Скрытая .lib/ рабочей папки: кирпичики-эталоны и slots/ (пустая, если зависимостей нет)."""
    taskfs.write_code(root / ".lib", lib)
