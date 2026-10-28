"""Библиотека: дерево тем, слоты, граф «Состав», экран сборки, мастер «Новая задача»,
«Вынести в кирпичик», «Создать слот», «Дублировать», перепрогон зависимых («сломано зависимостью»)."""
import ast
import json
import re
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import bricks, checking, review, runner, taskfs
from .db import Attempt, BrickEvent, MapBrick, SessionLocal, Slot, Task, TaskVersion, Topic
from .tasks import commit_version, deps_ok, place, task_short

router = APIRouter(prefix="/api")


def get_db():
    with SessionLocal() as db:
        yield db


# ---------- дерево тем ----------

@router.get("/topics")
def topics(db=Depends(get_db)):
    """Плоский список узлов с числом задач и «пора повторить» (в узле и во всём поддереве)."""
    nodes = db.query(Topic).order_by(Topic.position, Topic.name).all()
    today = datetime.now().date()
    own = {n.id: [0, 0, 0] for n in nodes}  # задач, пора повторить, запланировано (кирпичики карты без задачи)
    names = set()
    for t in db.query(Task).all():
        names.add(t.name)
        if t.topic_id in own:
            own[t.topic_id][0] += 1
            own[t.topic_id][1] += bool(t.due_at and t.due_at.date() <= today)
    for b in db.query(MapBrick).all():
        if b.name not in names and b.topic_id in own:
            own[b.topic_id][2] += 1
    kids = {}
    for n in nodes:
        kids.setdefault(n.parent_id, []).append(n.id)

    def total(i):
        acc = list(own[i])
        for k in kids.get(i, []):
            acc = [x + y for x, y in zip(acc, total(k))]
        return acc
    out = []
    for n in nodes:
        tot = total(n.id)
        out.append({"id": n.id, "name": n.name, "parent_id": n.parent_id, "position": n.position, "tasks": own[n.id][0],
                    "due": own[n.id][1], "planned": own[n.id][2], "total": tot[0], "total_due": tot[1], "total_planned": tot[2]})
    return out


class TopicIn(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    position: int | None = None
    move: bool = False  # true — parent_id задан явно (в т.ч. None = в корень)


@router.post("/topics")
def create_topic(body: TopicIn, db=Depends(get_db)):
    if not (body.name or "").strip():
        raise HTTPException(400, "нужно имя")
    if body.parent_id and not db.get(Topic, body.parent_id):
        raise HTTPException(400, "нет родительского узла")
    t = Topic(name=body.name.strip(), parent_id=body.parent_id, position=body.position or 0)
    db.add(t)
    db.commit()
    return {"id": t.id}


@router.patch("/topics/{nid}")
def update_topic(nid: int, body: TopicIn, db=Depends(get_db)):
    """Переименовать и/или перенести (перетаскиванием). Узел нельзя положить в самого себя или в потомка."""
    n = db.get(Topic, nid)
    if n is None:
        raise HTTPException(404, "узел не найден")
    if body.name is not None and body.name.strip():
        n.name = body.name.strip()
    if body.move:
        p = body.parent_id
        while p is not None:
            if p == nid:
                raise HTTPException(400, "нельзя перенести узел внутрь самого себя")
            parent = db.get(Topic, p)
            if parent is None:
                raise HTTPException(400, "нет такого узла")
            p = parent.parent_id
        n.parent_id = body.parent_id
    if body.position is not None:
        n.position = body.position
    db.commit()
    return {"ok": True}


@router.delete("/topics/{nid}")
def delete_topic(nid: int, db=Depends(get_db)):
    """Удалить узел: его задачи и подузлы переходят к родителю (задачи не удаляются)."""
    n = db.get(Topic, nid)
    if n is None:
        raise HTTPException(404, "узел не найден")
    parent = n.parent_id
    for t in db.query(Task).filter_by(topic_id=nid):
        t.topic_id = parent if parent is not None else None
    for c in db.query(Topic).filter_by(parent_id=nid):
        c.parent_id = parent
    db.delete(n)
    db.flush()
    if parent is None:  # задачи без узла — в «Без темы»
        orphans = db.query(Task).filter_by(topic_id=None).all()
        if orphans:
            from .tasks import topic_path
            tid = topic_path(db, "Без темы")
            for t in orphans:
                t.topic_id = tid
    db.commit()
    return {"ok": True}


# ---------- слоты ----------

def slot_out(db, s: Slot) -> dict:
    return {"id": s.id, "name": s.name, "symbol": s.symbol or s.name, "title": s.title or s.name, "signature": s.signature,
            "description": s.description, "tests": taskfs.json_dict(s.tests), "default_impl": s.default_impl,
            "impls": [{"id": t.id, "name": t.name, "title": t.title, "status": review.task_status(t)} for t in bricks.impls(db, s.name)]}


@router.get("/slots")
def list_slots(db=Depends(get_db)):
    return [slot_out(db, s) for s in db.query(Slot).order_by(Slot.name).all()]


class SlotIn(BaseModel):
    name: str
    symbol: str = ""
    title: str = ""
    signature: str = ""
    description: str = ""
    tests: dict[str, str] = {}
    default_impl: str = ""


def save_slot(db, body: SlotIn) -> Slot:
    name = re.sub(r"\W+", "_", body.name.strip()).strip("_").lower()
    if not name:
        raise HTTPException(400, "имя слота — идентификатор Python, например loss")
    s = db.query(Slot).filter_by(name=name).first() or Slot(name=name)
    s.symbol = body.symbol or s.symbol or name
    s.title, s.signature, s.description = body.title or s.title or name, body.signature or s.signature, body.description or s.description
    tests = {k if k.startswith("tests/") else f"tests/{k}": v for k, v in body.tests.items()}
    if tests:
        s.tests = json.dumps(tests, ensure_ascii=False)
    if body.default_impl:
        s.default_impl = body.default_impl
    db.add(s)
    db.commit()
    return s


@router.post("/slots")
def create_slot(body: SlotIn, db=Depends(get_db)):
    return slot_out(db, save_slot(db, body))


@router.get("/slots/{name}")
def get_slot(name: str, db=Depends(get_db)):
    s = db.query(Slot).filter_by(name=name).first()
    if s is None:
        raise HTTPException(404, "слот не найден")
    return slot_out(db, s)


def upload_slot(db, folder: str, text: dict) -> dict:
    """Папка слота: slot.json {name, symbol, title, signature, description, default} + tests/ — контрактные тесты."""
    try:
        meta = json.loads(text["slot.json"])
    except ValueError as e:
        return {"folder": folder, "status": "error", "error": f"slot.json: {e}"}
    s = save_slot(db, SlotIn(name=meta.get("name") or folder, symbol=meta.get("symbol", ""), title=meta.get("title", ""),
                             signature=meta.get("signature", ""), description=meta.get("description") or text.get("description.md", ""),
                             tests=taskfs.all_test_files(text), default_impl=meta.get("default", "")))
    return {"folder": folder, "status": "slot", "slot": s.name, "tests": len(json.loads(s.tests or "{}"))}


# ---------- граф «Состав» ----------

def node_status(db, t: Task) -> str:
    if t.broken:
        return "broken"
    last = db.query(BrickEvent).filter_by(task_id=t.id).order_by(BrickEvent.at.desc()).first()
    if last and not last.passed and (not t.last_review or last.at >= t.last_review):
        return "failed"
    return review.task_status(t)


@router.get("/tasks/{tid}/graph")
def graph(tid: int, db=Depends(get_db)):
    """Вниз — из чего состоит (на любой глубине), вверх — где используется."""
    t = db.get(Task, tid)
    if t is None:
        raise HTTPException(404, "задача не найдена")
    asm = json.loads(t.last_assembly or "{}")
    try:
        down = bricks.tree(db, t, asm, None, taskfs.ref_mode(json.loads(t.current.files)))
        err = ""
    except bricks.DepError as e:
        down, err = [], str(e)
    for n in down:
        n["status"] = node_status(db, db.get(Task, n["task_id"]))
    up = []

    def walk_up(x: Task, depth: int, seen: set):
        for p in bricks.dependents(db, x):
            direct = any(n["task_id"] == x.id and n["depth"] == 0 for n in bricks.tree(db, p, {}))
            if p.id in seen or not direct:
                continue
            seen.add(p.id)
            up.append({"task_id": p.id, "title": p.title, "depth": depth, "child": x.id, "status": node_status(db, p)})
            walk_up(p, depth + 1, seen)
    walk_up(t, 0, {t.id})
    files = json.loads(t.current.files)
    return {"id": t.id, "title": t.title, "status": node_status(db, t), "implements": bricks.implements_of(files),
            "down": down, "up": up, "error": err}


# ---------- экран сборки ----------

@router.get("/tasks/{tid}/assembly")
def assembly_options(tid: int, asm: str = "", mode: str = "", db=Depends(get_db)):
    """Для каждой зависимости — варианты: пишу сам библиотекой / пишу сам с нуля / эталон / моя последняя версия;
    у слота — реализации. asm — текущий выбор (JSON): при смене реализации или режима меняется и поддерево.
    mode — режим самой задачи (какие зависимости ей нужны)."""
    t = db.get(Task, tid)
    if t is None:
        raise HTTPException(404, "задача не найдена")
    files = json.loads(t.current.files)
    mode = mode if mode in taskfs.modes_of(files) else taskfs.default_mode(files)
    last = json.loads(t.last_assembly or "{}")
    try:
        chosen = json.loads(asm) if asm else last
    except ValueError:
        chosen = last
    try:
        nodes = bricks.tree(db, t, chosen, files, mode)
    except bricks.DepError as e:
        raise HTTPException(400, str(e))
    from .mapview import brick_status
    out = []
    for n in nodes:
        bt = db.get(Task, n["task_id"])
        lg = bricks.last_good(db, bt)
        out.append({**n, "source": bricks.source_of(chosen, n), "node_mode": bricks.node_mode(chosen, n, db),
                    "last": {"from": lg["from"], "mode": lg["mode"]} if lg else None,
                    "status": node_status(db, bt), "statuses": brick_status(db, bt, "brick")[1]})
    return {"nodes": out, "last": last, "has_last": bool(last), "mode": mode, "modes": taskfs.modes_of(files)}


# ---------- «сломано зависимостью» ----------

def recheck_dependents_later(tid: int):
    threading.Thread(target=recheck_dependents, args=(tid,), daemon=True).start()


def recheck_dependents(tid: int):
    """Эталон кирпичика изменился: зависящие задачи перепрогоняют тесты на эталоне;
    упало — помечаются «сломано зависимостью» (с тем, что упало), прошло — пометка снимается."""
    with SessionLocal() as db:
        src = db.get(Task, tid)
        if src is None:
            return
        targets = [(t.id, t.name) for t in bricks.dependents(db, src)]
        label = f"{src.title} v{src.current.number}"
    for xid, _ in targets:
        with SessionLocal() as db:
            t = db.get(Task, xid)
            try:
                py = taskfs.resolve_python(t.python)
            except ValueError:
                continue
            version = t.current
        job = runner.new_job("recheck")
        bad, res = [], {}
        for m in taskfs.modes_of(json.loads(version.files)):  # каждый режим — на своём эталоне
            try:
                res = checking.reference_results(t, version, py, job, mode=m)
            except Exception as e:
                res = {"fatal": str(e)}
            bad += [f"{r['name']} ({taskfs.MODE_NAME[m]})" for r in (res.get("tests") or {}).values() if r["status"] in ("fail", "error")]
            bad += [e["file"] for e in res.get("collection_errors", [])]
        with SessionLocal() as db:
            t = db.get(Task, xid)
            t.broken = (f"{label} — упали: {', '.join(bad[:5])}" if bad else f"{label} — {res['fatal'][:200]}" if res.get("fatal") else "")
            db.commit()


@router.post("/tasks/{tid}/recheck")
def recheck(tid: int, db=Depends(get_db)):
    """Перепрогнать тесты на эталоне у самой задачи (и снять/поставить «сломано зависимостью»)."""
    t = db.get(Task, tid)
    if t is None:
        raise HTTPException(404, "задача не найдена")
    job = runner.new_job("check")
    job.state = "running"

    def go():
        py = taskfs.resolve_python(t.python)
        bad, res = [], {}
        for m in taskfs.modes_of(json.loads(t.current.files)):
            res = checking.reference_results(t, t.current, py, job, force=True, mode=m)
            bad += [f"{r['name']} ({taskfs.MODE_NAME[m]})" for r in (res.get("tests") or {}).values() if r["status"] in ("fail", "error")]
        with SessionLocal() as db2:
            tt = db2.get(Task, tid)
            if bricks.deps_of(json.loads(tt.current.files)):
                tt.broken = f"упали на эталоне: {', '.join(bad[:5])}" if bad else ""
            db2.commit()
        job.finish({"status": "ok", "bad": bad, "fatal": res.get("fatal")})
    threading.Thread(target=go, daemon=True).start()
    return {"job": job.id}


# ---------- «проверить со всеми реализациями слота» ----------

@router.post("/attempts/{aid}/check_slots")
def check_slots(aid: int, db=Depends(get_db)):
    """Мой код с каждой реализацией каждого слота (остальная сборка — как в попытке)."""
    a = db.get(Attempt, aid)
    if a is None:
        raise HTTPException(404, "попытка не найдена")
    asm = json.loads(a.assembly or "{}")
    v = db.get(TaskVersion, a.version_id)
    nodes = [n for n in bricks.tree(db, a.task, asm, json.loads(v.files), a.mode or "scratch") if n["kind"] == "slot"]
    if not nodes:
        raise HTTPException(400, "в этой задаче нет слотов")
    job = runner.new_job("check")
    job.owner = f"a{aid}"
    job.state = "running"
    task, code, py = a.task, json.loads(a.files), taskfs.resolve_python(a.task.python)
    plan = [(n, impl) for n in nodes for impl in n["impls"]]

    def go():
        rows = []
        for n, impl in plan:
            trial = {**asm, n["name"]: {**(asm.get(n["name"]) or {}), "impl": impl["name"],
                                        "source": (asm.get(n["name"]) or {}).get("source", "ref")}}
            job.note(f"\n### слот {n['slot']} → {impl['title']}\n", "stdout")
            try:
                res = checking.run_tests(task, v, code, py, job, trial, a.mode or "scratch")
            except Exception as e:
                res = {"fatal": str(e), "passed": 0, "total": 0}
            rows.append({"slot": n["slot"], "dep": n["name"], "impl": impl["name"], "title": impl["title"],
                         "current": impl["name"] == n["task_name"], "passed": res.get("passed", 0), "total": res.get("total", 0),
                         "fatal": res.get("fatal")})
        job.finish({"status": "ok", "slots": rows})
    threading.Thread(target=go, daemon=True).start()
    return {"job": job.id}


# ---------- мастер «Новая задача» ----------

class DepIn(BaseModel):
    name: str
    task: str | None = None
    slot: str | None = None


class WizardIn(BaseModel):
    title: str
    topic_id: int | None = None
    tags: list[str] = []
    kind: str = "algo"
    type: str = "plain"  # plain | slot | composite
    implements: str = ""
    files: dict[str, str] = {}  # {reference/x.py | tests/test_x.py | starter/x.py | description.md: текст}
    deps: list[DepIn] = []
    main: str = ""


def write_meta(files: dict, **kw) -> dict:
    meta = taskfs.read_meta(files)
    for k, v in kw.items():
        if v in (None, "", [], {}):
            meta.pop(k, None)
        else:
            meta[k] = v
    files["task.json"] = json.dumps(meta, ensure_ascii=False, indent=2) + "\n"
    return files


def make_task(db, title: str, files: dict, topic_id=None, tags=(), kind="algo") -> Task:
    name = taskfs.slug(title)
    base, i = name, 2
    while db.query(Task).filter_by(name=name).first():
        name, i = f"{base}_{i}", i + 1
    t = Task(name=name, title=title, kind=kind if kind in ("algo", "ml") else "algo", topic_id=topic_id,
             tags=json.dumps(list(tags), ensure_ascii=False))
    db.add(t)
    db.flush()
    err = deps_ok(db, t, files)
    if err:
        db.rollback()
        raise HTTPException(400, err)
    from .tasks import apply_meta
    apply_meta(t, taskfs.read_meta(files))
    if topic_id is None:
        place(db, t, taskfs.read_meta(files))
    commit_version(db, t, files)
    taskfs.materialize(name, files)
    db.commit()
    return t


@router.post("/tasks/wizard")
def wizard(body: WizardIn, db=Depends(get_db)):
    """Мастер: название, узел, теги → тип → файлы → зависимости → (дальше «проверить эталон» в редакторе)."""
    files = dict(body.files)
    if not taskfs.modes_of(files):
        raise HTTPException(400, "нужен хотя бы один файл эталона (reference/*.py)")
    if body.type == "slot" and not body.implements:
        raise HTTPException(400, "укажите слот, который реализует задача")
    if body.type == "composite" and not body.deps:
        raise HTTPException(400, "у составной задачи должна быть хотя бы одна зависимость")
    files.setdefault("description.md", f"# {body.title}\n")
    deps = [{"name": d.name, **({"task": d.task} if d.task else {"slot": d.slot})} for d in body.deps if d.task or d.slot]
    write_meta(files, title=body.title, kind=body.kind, tags=body.tags, main=body.main,
               implements=body.implements if body.type == "slot" else "", deps=deps if body.type == "composite" else [])
    t = make_task(db, body.title, files, body.topic_id, body.tags, body.kind)
    return {"id": t.id}


@router.post("/tasks/{tid}/duplicate")
def duplicate(tid: int, db=Depends(get_db)):
    t = db.get(Task, tid)
    if t is None:
        raise HTTPException(404, "задача не найдена")
    files = json.loads(t.current.files)
    title = f"{t.title} (копия)"
    write_meta(files, title=title)
    n = make_task(db, title, files, t.topic_id, taskfs.json_list(t.tags), t.kind)
    n.python, n.timeout, n.main_file = t.python, t.timeout, t.main_file
    db.commit()
    return {"id": n.id}


class ExtractIn(BaseModel):
    file: str  # reference/x.py
    symbol: str  # имя функции или класса
    title: str = ""
    dep_name: str = ""
    as_slot: bool = False  # «Создать слот» из функции вместо кирпичика


def find_def(code: str, symbol: str):
    tree = ast.parse(code)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol:
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            return node, start, node.end_lineno
    raise HTTPException(400, f"в файле нет функции или класса «{symbol}» на верхнем уровне")


def needed_imports(code: str, snippet: str) -> str:
    """Импорты исходного файла, имена из которых встречаются в вынесенном коде."""
    names = {n.id for n in ast.walk(ast.parse(snippet)) if isinstance(n, ast.Name)} | \
            {n.value.id for n in ast.walk(ast.parse(snippet)) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    out = []
    for node in ast.parse(code).body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if any((a.asname or a.name).split(".")[0] in names for a in node.names):
                out.append(ast.unparse(node))
    return "\n".join(out) + ("\n\n\n" if out else "")


@router.post("/tasks/{tid}/extract")
def extract(tid: int, body: ExtractIn, db=Depends(get_db)):
    """«Вынести в кирпичик»: функция или класс становится новой задачей (её эталон — этот код),
    в исходной задаче код заменяется на `from bricks.<имя> import <symbol>` и добавляется зависимость.
    as_slot — «Создать слот»: сигнатура и docstring функции становятся слотом, код — первой реализацией."""
    t = db.get(Task, tid)
    if t is None:
        raise HTTPException(404, "задача не найдена")
    files = taskfs.snapshot(t.name)  # с диска: могли быть несохранённые в версию правки
    rel = body.file if body.file.startswith("reference/") else f"reference/{body.file}"
    if rel not in files:
        raise HTTPException(400, "нет такого файла эталона")
    code = files[rel]
    node, start, end = find_def(code, body.symbol)
    lines = code.splitlines(True)
    snippet = "".join(lines[start - 1:end])
    dep = re.sub(r"\W+", "_", body.dep_name or body.symbol).strip("_").lower()
    title = body.title or body.symbol
    brick_files = {"reference/solution.py": needed_imports(code, snippet) + snippet.rstrip() + "\n",
                   "description.md": f"# {title}\n\nВынесено из задачи «{t.title}» ({rel[10:]}).\n",
                   "tests/test_solution.py": f"from solution import {body.symbol}\n\n\ndef test_exists():\n    assert callable({body.symbol})\n"}
    # вынесенный код сам импортирует кирпичики (from bricks.x / slots.y) — эти зависимости переходят в новую задачу
    imports = needed_imports(code, snippet)
    used = set(re.findall(r"from (?:bricks|slots)\.(\w+) import", imports))
    inherited = [d for d in (taskfs.read_meta(files).get("deps") or []) if isinstance(d, dict)
                 and re.sub(r"\W+", "_", str(d.get("name") or d.get("task") or d.get("slot"))).lower() in used]
    if inherited:
        write_meta(brick_files, deps=inherited)
    slot_name = ""
    if body.as_slot:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raise HTTPException(400, "слот создаётся из функции")
        slot_name = dep
        sig = lines[node.lineno - 1].strip().rstrip(":")
        save_slot(db, SlotIn(name=slot_name, symbol=body.symbol, title=title, signature=sig,
                             description=ast.get_docstring(node) or "",
                             tests={"test_contract.py": f"from slots.{slot_name} import {body.symbol}\n\n\n"
                                    f"def test_callable():\n    assert callable({body.symbol})\n"}))
        write_meta(brick_files, title=f"{title} (реализация)", implements=slot_name)
    else:
        write_meta(brick_files, title=title)
    b = make_task(db, title if not body.as_slot else f"{title} (реализация)", brick_files, t.topic_id, taskfs.json_list(t.tags), t.kind)
    if body.as_slot:
        s = db.query(Slot).filter_by(name=slot_name).first()
        s.default_impl = b.name
        db.commit()
    imp = f"from slots.{slot_name} import {body.symbol}\n" if body.as_slot else f"from bricks.{dep} import {body.symbol}\n"
    new_code = "".join(lines[:start - 1]) + imp + "".join(lines[end:])
    files[rel] = new_code
    deps = taskfs.read_meta(files).get("deps") or []
    deps.append({"name": dep, "slot": slot_name} if body.as_slot else {"name": dep, "task": b.name})
    write_meta(files, deps=deps)
    err = deps_ok(db, t, files)
    if err:
        raise HTTPException(400, err)
    taskfs.materialize(t.name, files)
    roles = json.loads(t.current.roles or "{}")
    commit_version(db, t, files, {f: roles.get(f, "write") for f in taskfs.reference_names(files)})
    db.commit()
    return {"brick_id": b.id, "dep": dep, "slot": slot_name, "import": imp.strip(), "task": task_short(t)}
