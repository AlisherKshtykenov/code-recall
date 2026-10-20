"""API задач: загрузка папок, создание в интерфейсе, версии, роли файлов, данные, окружение."""
import difflib
import json
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from pydantic import BaseModel

from . import files_api, review, runner, taskfs
from .db import SessionLocal, Task, TaskVersion

router = APIRouter(prefix="/api")


def get_db():
    with SessionLocal() as db:
        yield db


def or_404(obj, what="задача не найдена"):
    if obj is None:
        raise HTTPException(404, what)
    return obj


def iso(dt):
    return dt.isoformat(timespec="minutes") if dt else None


# ---------- версии ----------

def commit_version(db, task: Task, files: dict, roles: dict | None = None) -> str:
    """Новая версия, если текст файлов или роли изменились. Возвращает created | new_version | unchanged."""
    if roles is None:
        roles = taskfs.default_roles(files, taskfs.read_meta(files))
    roles = {f: r for f, r in roles.items() if f in taskfs.reference_files(files)}
    h = taskfs.files_hash(files, roles)
    cur = task.current
    if cur and cur.content_hash == h:
        return "unchanged"
    v = TaskVersion(task=task, number=(cur.number + 1) if cur else 1, files=json.dumps(files, ensure_ascii=False),
                    roles=json.dumps(roles, ensure_ascii=False), content_hash=h)
    db.add(v)
    task.updated_at = datetime.now()
    return "new_version" if cur else "created"


def apply_meta(task: Task, meta: dict):
    """task.json -> поля задачи (только те, что заданы)."""
    if meta.get("title"):
        task.title = str(meta["title"])
    if meta.get("kind") in ("algo", "ml"):
        task.kind = meta["kind"]
    for k in ("tag", "notes"):
        if isinstance(meta.get(k), str):
            setattr(task, k, meta[k])
    if isinstance(meta.get("difficulty"), int):
        task.difficulty = max(1, min(5, meta["difficulty"]))
    if isinstance(meta.get("timeout"), int):
        task.timeout = max(5, meta["timeout"])
    if isinstance(meta.get("main"), str):
        task.main_file = meta["main"]


def version_out(v: TaskVersion) -> dict:
    files = json.loads(v.files)
    return {"id": v.id, "number": v.number, "created_at": iso(v.created_at),
            "files": sorted(files), "roles": json.loads(v.roles or "{}")}


# ---------- загрузка папки ----------

def group_upload(paths: list[str]) -> dict:
    """Пути вида <задача>/reference/x.py -> {задача: [(индекс, путь внутри задачи)]}."""
    groups = defaultdict(list)
    for i, p in enumerate(paths):
        parts = [x for x in p.replace("\\", "/").split("/") if x]
        if len(parts) < 2:
            continue  # файл вне папки задачи
        groups[parts[0]].append((i, "/".join(parts[1:])))
    return groups


async def read_upload(files, paths):
    if len(paths) != len(files):
        raise HTTPException(400, "пути и файлы не совпадают")
    groups = group_upload(paths)
    if not groups:
        raise HTTPException(400, "перетащите папку задачи (в ней reference/ и tests/), а не отдельные файлы")
    out = {}
    for folder, items in groups.items():
        text, data, skipped = {}, [], []
        for i, rel in items:
            if rel.startswith(("results/", ".")) or "/__pycache__/" in f"/{rel}" or "/." in rel:
                continue
            if rel == "README.md" and not any(r == "description.md" for _, r in items):
                rel = "description.md"
            if rel.startswith("data/"):
                data.append((i, rel))
            elif taskfs.is_version_file(rel):
                raw = await files[i].read()
                try:
                    text[rel] = raw.decode("utf-8")
                except UnicodeDecodeError:
                    skipped.append(rel)
            else:
                skipped.append(rel)
        out[folder] = {"text": text, "data": data, "skipped": skipped}
    return out


def unified(a: str, b: str, name: str) -> str:
    return "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), f"было/{name}", f"стало/{name}", n=2))


@router.post("/tasks/upload/preview")
async def upload_preview(files: list[UploadFile], paths: list[str] = Form(...), db=Depends(get_db)):
    """Ничего не сохраняет: что станет новой задачей, у какой появится новая версия и что поменяется."""
    res = []
    for folder, g in (await read_upload(files, paths)).items():
        name = taskfs.slug(folder)
        text = g["text"]
        item = {"folder": folder, "name": name, "data_files": len(g["data"]), "skipped": g["skipped"][:20]}
        if not taskfs.reference_files(text):
            res.append({**item, "status": "error", "error": "нет reference/*.py — эталона"})
            continue
        task = db.query(Task).filter_by(name=name).first()
        meta = taskfs.read_meta(text)
        roles = taskfs.default_roles(text, meta)
        if task is None:
            res.append({**item, "status": "new", "files": sorted(text), "tests": len(taskfs.test_files(text))})
            continue
        cur = json.loads(task.current.files)
        if taskfs.files_hash(text, roles) == task.current.content_hash:
            res.append({**item, "status": "unchanged", "id": task.id, "version": task.current.number})
            continue
        changed = [f for f in text if f in cur and cur[f] != text[f]]
        res.append({**item, "status": "changed", "id": task.id, "title": task.title, "version": task.current.number,
                    "added": [f for f in text if f not in cur], "removed": [f for f in cur if f not in text],
                    "changed": changed, "diff": {f: unified(cur[f], text[f], f) for f in changed}})
    return res


@router.post("/tasks/upload")
async def upload(files: list[UploadFile], paths: list[str] = Form(...), db=Depends(get_db)):
    """Сохранить: новая задача или новая версия существующей. Файлы из data/ кладутся в data/ задачи."""
    results = []
    for folder, g in (await read_upload(files, paths)).items():
        name, text = taskfs.slug(folder), g["text"]
        if not taskfs.reference_files(text):
            results.append({"folder": folder, "status": "error", "error": "нет reference/*.py"})
            continue
        meta = taskfs.read_meta(text)
        task = db.query(Task).filter_by(name=name).first()
        if task is None:
            task = Task(name=name, title=folder.replace("_", " "), kind="ml" if g["data"] else "algo")
            db.add(task)
        apply_meta(task, meta)
        status = commit_version(db, task, text)
        db.flush()
        taskfs.materialize(name, text)
        base = taskfs.task_dir(name)
        for i, rel in g["data"]:  # данные не версионируются: просто кладём в data/
            dst = taskfs.safe(base, rel)
            dst.parent.mkdir(parents=True, exist_ok=True)
            with open(dst, "wb") as out:
                await files[i].seek(0)
                while chunk := await files[i].read(1 << 20):
                    out.write(chunk)
        db.commit()
        results.append({"folder": folder, "status": status, "id": task.id, "version": task.current.number,
                        "data_files": len(g["data"])})
    return results


class NewTask(BaseModel):
    title: str
    kind: str = "algo"


STARTER_TEST = '''# Тесты импортируют ваш код по имени файла.
from solution import solve


def test_example():
    assert solve([3, 1, 2]) == [1, 2, 3]
'''


@router.post("/tasks")
def create_task(body: NewTask, db=Depends(get_db)):
    """Собрать задачу в интерфейсе: пустой эталон и пример теста, дальше — в редакторе задачи."""
    name = taskfs.slug(body.title)
    if db.query(Task).filter_by(name=name).first():
        raise HTTPException(409, "задача с таким именем уже есть")
    files = {"description.md": f"# {body.title}\n\nОпишите задачу.\n",
             "reference/solution.py": "def solve(xs):\n    return sorted(xs)\n",
             "tests/test_solution.py": STARTER_TEST}
    task = Task(name=name, title=body.title, kind=body.kind if body.kind in ("algo", "ml") else "algo")
    db.add(task)
    commit_version(db, task, files)
    taskfs.materialize(name, files)
    db.commit()
    return {"id": task.id}


# ---------- список и карточка ----------

def task_short(t: Task) -> dict:
    done = [a for a in t.attempts if a.status == "submitted"]
    scores = [a.score for a in done if a.score is not None]
    v = t.current
    files = json.loads(v.files) if v else {}
    return {"id": t.id, "name": t.name, "title": t.title, "kind": t.kind, "tag": t.tag,
            "difficulty": t.difficulty, "version": v.number if v else 0,
            "files": len(taskfs.reference_files(files)), "tests": len(taskfs.test_files(files)),
            "attempts": len(done), "best_score": max(scores, default=None),
            "best_time_ms": min((a.total_ms for a in done), default=None),
            "last_attempt": iso(max((a.finished_at for a in done), default=None)),
            "active_attempt": next((a.id for a in reversed(t.attempts) if a.status == "active"), None),
            "due_at": iso(t.due_at), "status": review.task_status(t), "updated_at": iso(t.updated_at)}


@router.get("/tasks")
def list_tasks(db=Depends(get_db)):
    return [task_short(t) for t in db.query(Task).order_by(Task.title).all()]


@router.get("/tasks/{tid}")
def get_task(tid: int, db=Depends(get_db)):
    t = or_404(db.get(Task, tid))
    v = t.current
    files = json.loads(v.files)
    try:
        py = taskfs.resolve_python(t.python)
    except ValueError as e:
        py = f"ошибка: {e}"
    return {**task_short(t), "notes": t.notes, "python": t.python, "python_resolved": py, "timeout": t.timeout,
            "main_file": t.main_file, "description": files.get("description.md", ""),
            "reference": sorted(taskfs.reference_files(files)), "roles": json.loads(v.roles or "{}"),
            "test_files": sorted(taskfs.test_files(files)), "versions": [version_out(x) for x in t.versions],
            "data_link": taskfs.data_link(t.name), "path": str(taskfs.task_dir(t.name)),
            "dirty": taskfs.files_hash(taskfs.snapshot(t.name), json.loads(v.roles or "{}")) != v.content_hash}


class TaskMeta(BaseModel):
    title: str | None = None
    kind: str | None = None
    tag: str | None = None
    difficulty: int | None = None
    notes: str | None = None
    python: str | None = None
    timeout: int | None = None
    main_file: str | None = None


@router.patch("/tasks/{tid}")
def update_task(tid: int, meta: TaskMeta, db=Depends(get_db)):
    t = or_404(db.get(Task, tid))
    data = meta.model_dump(exclude_none=True)
    if data.get("python"):
        try:
            info = taskfs.check_python(data["python"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        if not info["pytest"]:
            raise HTTPException(400, f"в этом окружении нет pytest — установите: {info['fix']}")
    if "kind" in data and data["kind"] not in ("algo", "ml"):
        raise HTTPException(400, "тип: algo или ml")
    if "timeout" in data:
        data["timeout"] = max(5, min(24 * 3600, data["timeout"]))
    for k, val in data.items():
        setattr(t, k, val)
    db.commit()
    if "python" in data:
        runner.stop_task_workers(t.id)  # консоли перезапустятся в новом окружении
    return task_short(t)


@router.delete("/tasks/{tid}")
def delete_task(tid: int, db=Depends(get_db)):
    t = or_404(db.get(Task, tid))
    name = t.name
    runner.stop_task_workers(t.id)
    db.delete(t)
    db.commit()
    # rmtree не раскрывает символические ссылки: привязанная data/ (ваши датасеты) не пострадает
    shutil.rmtree(taskfs.ROOT / name, ignore_errors=True)
    return {"ok": True}


class RolesIn(BaseModel):
    roles: dict[str, str]


@router.put("/tasks/{tid}/roles")
def set_roles(tid: int, body: RolesIn, db=Depends(get_db)):
    """Роли файлов эталона: write — пишу сам, given — дан как есть. Сохраняется новой версией."""
    t = or_404(db.get(Task, tid))
    files = json.loads(t.current.files)
    roles = {f: ("given" if body.roles.get(f) == "given" else "write") for f in taskfs.reference_files(files)}
    meta = taskfs.read_meta(files)
    meta["roles"] = {f: r for f, r in roles.items() if r == "given"}
    files["task.json"] = json.dumps(meta, ensure_ascii=False, indent=2) + "\n"
    taskfs.materialize(t.name, files)
    status = commit_version(db, t, files, roles)
    db.commit()
    return {"status": status, "version": t.current.number, "roles": roles}


@router.post("/tasks/{tid}/version")
def save_version(tid: int, db=Depends(get_db)):
    """Снимок папки задачи (после правок в редакторе) -> новая версия, если что-то поменялось."""
    t = or_404(db.get(Task, tid))
    files = taskfs.snapshot(t.name)
    if not taskfs.reference_files(files):
        raise HTTPException(400, "в reference/ нет ни одного .py")
    apply_meta(t, taskfs.read_meta(files))
    roles = json.loads(t.current.roles or "{}")
    roles = {f: roles.get(f, "write") for f in taskfs.reference_files(files)}
    status = commit_version(db, t, files, roles)
    db.commit()
    return {"status": status, "version": t.current.number}


@router.get("/tasks/{tid}/diff")
def version_diff(tid: int, a: int, b: int, db=Depends(get_db)):
    t = or_404(db.get(Task, tid))
    va = or_404(next((x for x in t.versions if x.number == a), None), "нет версии")
    vb = or_404(next((x for x in t.versions if x.number == b), None), "нет версии")
    fa, fb = json.loads(va.files), json.loads(vb.files)
    return {f: unified(fa.get(f, ""), fb.get(f, ""), f) for f in sorted(set(fa) | set(fb)) if fa.get(f) != fb.get(f)}


@router.get("/tasks/{tid}/versions/{n}")
def version_files(tid: int, n: int, db=Depends(get_db)):
    t = or_404(db.get(Task, tid))
    v = or_404(next((x for x in t.versions if x.number == n), None), "нет версии")
    return {"number": v.number, "files": json.loads(v.files), "roles": json.loads(v.roles or "{}")}


class PathIn(BaseModel):
    path: str = ""


@router.post("/tasks/{tid}/data/bind")
def data_bind(tid: int, body: PathIn, db=Depends(get_db)):
    t = or_404(db.get(Task, tid))
    try:
        taskfs.bind_data(t.name, body.path)
    except (ValueError, OSError) as e:
        raise HTTPException(400, str(e))
    return {"data_link": taskfs.data_link(t.name)}


@router.post("/tasks/{tid}/data/unbind")
def data_unbind(tid: int, db=Depends(get_db)):
    t = or_404(db.get(Task, tid))
    taskfs.unbind_data(t.name)
    return {"data_link": None}


@router.post("/python/check")
def python_check(body: PathIn):
    try:
        return taskfs.check_python(body.path)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------- файлы папки задачи (редактор задачи) ----------

def _task_files(tid, db, write):
    t = db.get(Task, tid)
    if t is None:
        raise ValueError("задача не найдена")
    return taskfs.task_dir(t.name), None


file_router = files_api.make_router("/api/tasks", _task_files)
