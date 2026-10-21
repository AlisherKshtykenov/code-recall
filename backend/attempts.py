"""Попытка решения задачи — мини-IDE: файлы, «Запустить», консоль, «Проверить», «Сдать»."""
import json
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import checking, files_api, review, reviews, runner, taskfs
from .db import Attempt, SessionLocal, Task, TaskVersion

router = APIRouter(prefix="/api")


def get_db():
    with SessionLocal() as db:
        yield db


def load(db, aid) -> Attempt:
    a = db.get(Attempt, aid)
    if a is None:
        raise HTTPException(404, "попытка не найдена")
    return a


def active(db, aid) -> Attempt:
    a = load(db, aid)
    if a.status != "active":
        raise HTTPException(409, "попытка уже сдана")
    return a


def adir(a: Attempt):
    return taskfs.attempt_dir(a.task.name, a.id)


def public(a: Attempt, db) -> dict:
    t = a.task
    v = db.get(TaskVersion, a.version_id)
    files = json.loads(v.files)
    roles = json.loads(v.roles or "{}")
    rep = json.loads(a.report) if a.report else None
    try:
        py = taskfs.resolve_python(t.python)
    except ValueError as e:
        py = f"ошибка: {e}"
    main = t.main_file if t.main_file in roles else next(
        (f for f in ("main.py", "train.py", "solution.py") if f in roles), sorted(roles)[0] if roles else "")
    return {"id": a.id, "task_id": t.id, "title": t.title, "kind": t.kind, "tag": t.tag, "outcome": outcome(a),
            "last_check": json.loads(a.last_check) if a.last_check else None,
            "last_output": json.loads(a.last_output) if a.last_output else None,
            "finished_at": a.finished_at.isoformat(timespec="seconds") if a.finished_at else None,
            "reviews": [review_short(r) for r in a.reviews],
            "version": v.number, "description": files.get("description.md", ""), "status": a.status,
            "started_at": a.started_at.isoformat(timespec="seconds"), "total_ms": a.total_ms,
            "files": sorted(json.loads(a.files)), "roles": roles, "main_file": main,
            "checks": a.checks, "ref_opened": bool(a.ref_opened), "timeout": t.timeout, "python": py,
            "score": a.score, "grade": a.grade, "grade_auto": a.grade_auto, "grade_manual": bool(a.grade_manual),
            "grade_name": review.GRADES.get(a.grade), "grades": review.GRADES, "report": rep,
            "due_at": t.due_at.date().isoformat() if t.due_at else None,
            "data_link": taskfs.data_link(t.name), "worker": runner.state(f"a{a.id}")}


OUTCOME = {"active": "в процессе", "checking": "проверяется", "abandoned": "брошена",
           "passed": "сдана", "partial": "тесты частично"}


def outcome(a: Attempt) -> str:
    """Статус для журнала: брошена / сдана (все тесты) / тесты частично."""
    if a.status != "submitted":
        return a.status
    res = (json.loads(a.report) if a.report else {}).get("result") or {}
    return "passed" if res.get("total") and res.get("passed") == res.get("total") else "partial"


def review_short(r) -> dict:
    return {"id": r.id, "status": r.status, "step": r.step, "idx": r.idx, "files": json.loads(r.files),
            "started_at": r.started_at.isoformat(timespec="minutes"), **reviews.progress(r)}


def journal_row(a: Attempt) -> dict:
    o = outcome(a)
    return {"type": "attempt", "id": a.id, "task_id": a.task_id, "task": a.task.title, "kind": a.task.kind,
            "status": o, "status_name": OUTCOME.get(o, o),
            "date": (a.finished_at or a.started_at).isoformat(timespec="minutes"),
            "started_at": a.started_at.isoformat(timespec="minutes"),
            "finished_at": a.finished_at.isoformat(timespec="minutes") if a.finished_at else None,
            "total_ms": a.total_ms, "score": a.score, "grade": review.GRADES.get(a.grade),
            "grade_manual": bool(a.grade_manual), "checks": a.checks, "ref_opened": bool(a.ref_opened),
            "reviews": [review_short(r) for r in a.reviews]}


def touch(a: Attempt):
    a.touched_at = datetime.now()


@router.post("/tasks/{tid}/attempts")
def start_attempt(tid: int, db=Depends(get_db)):
    t = db.get(Task, tid)
    if t is None:
        raise HTTPException(404, "задача не найдена")
    existing = next((a for a in reversed(t.attempts) if a.status == "active"), None)
    if existing:
        return public(existing, db)  # незаконченная попытка — продолжаем её
    v = t.current
    files = json.loads(v.files)
    start = taskfs.attempt_start_files(files, json.loads(v.roles or "{}"))
    a = Attempt(task_id=t.id, version_id=v.id, files=json.dumps(start, ensure_ascii=False))
    db.add(a)
    db.commit()
    taskfs.write_code(adir(a), start)
    return public(a, db)


@router.get("/attempts/{aid}")
def get_attempt(aid: int, db=Depends(get_db)):
    a = load(db, aid)
    if a.status == "active":
        taskfs.write_code(adir(a), json.loads(a.files))  # папка совпадает с черновиком
    return public(a, db)


@router.get("/tasks/{tid}/attempts")
def list_attempts(tid: int, db=Depends(get_db)):
    rows = db.query(Attempt).filter_by(task_id=tid).order_by(Attempt.started_at.desc()).all()
    return [journal_row(a) for a in rows]


class TimeIn(BaseModel):
    total_ms: int


@router.put("/attempts/{aid}/time")
def save_time(aid: int, body: TimeIn, db=Depends(get_db)):
    a = active(db, aid)
    a.total_ms = max(a.total_ms, body.total_ms)
    touch(a)
    db.commit()
    return {"ok": True}


# ---------- файлы попытки ----------

def sync_files(db, a: Attempt):
    """Файлы кода попытки в базе = .py в папке попытки (кроме data/ и results/)."""
    base = adir(a)
    files = {}
    for p in sorted(base.rglob("*.py")):
        rel = p.relative_to(base).as_posix()
        if rel.split("/")[0] in ("data", "results") or "__pycache__" in rel:
            continue
        files[rel] = p.read_text(encoding="utf-8", errors="replace")
    a.files = json.dumps(files, ensure_ascii=False)
    touch(a)
    db.commit()


def _attempt_files(aid, db, write):
    a = db.get(Attempt, aid)
    if a is None:
        raise ValueError("попытка не найдена")
    if write and a.status != "active":
        raise ValueError("попытка сдана — файлы только для чтения")

    def on_change(db2, rel):
        if rel.endswith(".py") or "." not in rel.split("/")[-1]:
            sync_files(db2, db2.get(Attempt, aid))
    return adir(a), on_change


file_router = files_api.make_router("/api/attempts", _attempt_files)


class ResetIn(BaseModel):
    path: str


@router.post("/attempts/{aid}/reset")
def reset_file(aid: int, body: ResetIn, db=Depends(get_db)):
    """«Сбросить файл»: вернуть заготовку (или пустой файл; «дан» — как в эталоне)."""
    a = active(db, aid)
    v = db.get(TaskVersion, a.version_id)
    start = taskfs.attempt_start_files(json.loads(v.files), json.loads(v.roles or "{}"))
    if body.path not in start:
        raise HTTPException(400, "этого файла нет в задаче")
    files = json.loads(a.files)
    files[body.path] = start[body.path]
    a.files = json.dumps(files, ensure_ascii=False)
    db.commit()
    (adir(a) / body.path).write_text(start[body.path], encoding="utf-8")
    return {"content": start[body.path]}


# ---------- запуск и консоль ----------

class RunIn(BaseModel):
    path: str


class ExecIn(BaseModel):
    code: str


def worker_args(a: Attempt) -> dict:
    try:
        py = taskfs.resolve_python(a.task.python)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"key": f"a{a.id}", "python": py, "cwd": str(adir(a)), "task_id": a.task_id}


@router.post("/attempts/{aid}/run")
def run_file(aid: int, body: RunIn, db=Depends(get_db)):
    a = active(db, aid)
    if not (adir(a) / body.path).is_file():
        raise HTTPException(404, "файла нет")
    touch(a)
    db.commit()
    return {"job": runner.submit(**worker_args(a), cmd={"op": "run", "path": body.path}, timeout=a.task.timeout,
                                 on_done=lambda job: remember_output(aid, body.path, job))}


def remember_output(aid: int, path: str, job):
    """Вывод последнего «Запустить» — чтобы он был виден и в журнале у брошенной попытки."""
    outs = runner.outputs_snapshot(job)
    with SessionLocal() as db:
        a = db.get(Attempt, aid)
        if a:
            a.last_output = json.dumps({"path": path, "outputs": outs, "result": job.result,
                                        "at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False)
            db.commit()


@router.post("/attempts/{aid}/exec")
def exec_code(aid: int, body: ExecIn, db=Depends(get_db)):
    a = active(db, aid)
    return {"job": runner.submit(**worker_args(a), cmd={"op": "exec", "code": body.code}, timeout=a.task.timeout)}


@router.post("/attempts/{aid}/stop")
def stop(aid: int):
    runner.interrupt(f"a{aid}")
    return {"ok": True}


@router.post("/attempts/{aid}/restart")
def restart(aid: int):
    runner.stop(f"a{aid}")  # новый процесс поднимется при следующем запуске
    return {"ok": True}


@router.get("/attempts/{aid}/worker")
def worker_state(aid: int):
    return runner.state(f"a{aid}")


@router.get("/jobs/{job}")
def poll(job: str, have: int = 0, rev: int = 0):
    j = runner.JOBS.get(job)
    if j is None:
        return {"state": "lost"}
    return j.poll(have, rev)


# ---------- проверка и сдача ----------

def _check_job(aid: int, final: bool) -> str:
    job = runner.new_job("submit" if final else "check")
    job.owner = f"a{aid}"
    job.state = "running"

    def go():
        try:
            res = checking.run_check(aid, job)
        except Exception as e:
            job.note(f"проверка упала: {e}\n")
            res = {"fatal": f"проверка упала: {e}", "tests": [], "passed": 0, "total": 0, "broken": 0}
        with SessionLocal() as db:  # последний результат тестов — виден и у брошенной попытки
            a = db.get(Attempt, aid)
            a.last_check = json.dumps(res, ensure_ascii=False)
            db.commit()
        if final:
            try:
                checking.finish_submit(aid, res)
            except Exception as e:
                job.note(f"не удалось сохранить отчёт: {e}\n")
                with SessionLocal() as db:
                    a = db.get(Attempt, aid)
                    a.status = "submitted"
                    a.report = json.dumps({"result": res, "fatal": str(e)}, ensure_ascii=False)
                    db.commit()
        job.finish({"status": "ok", "check": res})

    threading.Thread(target=go, daemon=True).start()
    return job.id


@router.post("/attempts/{aid}/check")
def check(aid: int, db=Depends(get_db)):
    """«Проверить»: тесты без оценки, сколько угодно раз (влияет на оценку только числом нажатий)."""
    a = active(db, aid)
    a.checks += 1
    db.commit()
    return {"job": _check_job(aid, final=False), "checks": a.checks}


@router.post("/attempts/{aid}/submit")
def submit(aid: int, body: TimeIn, db=Depends(get_db)):
    """«Сдать»: финальный прогон, оценка, время, сдвиг расписания."""
    a = active(db, aid)
    a.total_ms = max(a.total_ms, body.total_ms)
    a.status = "checking"
    a.finished_at = datetime.now()
    db.commit()
    runner.stop(f"a{aid}")
    return {"job": _check_job(aid, final=True)}


class AbandonIn(BaseModel):
    total_ms: int = 0


@router.post("/attempts/{aid}/abandon")
def abandon(aid: int, body: AbandonIn | None = None, db=Depends(get_db)):
    """«Сбросить» или уход со страницы: попытка в историю как «брошена» с кодом всех файлов на этот
    момент и временем. В FSRS — как «забыл»."""
    a = load(db, aid)
    if a.status != "active":
        return {"ok": True, "status": a.status}  # повторный сигнал (например, при закрытии вкладки)
    sync_files(db, a)
    abandon_attempt(db, a, body.total_ms if body else 0)
    runner.stop(f"a{aid}")
    return {"ok": True, "status": a.status}


def abandon_attempt(db, a: Attempt, total_ms: int = 0):
    a.total_ms = max(a.total_ms, total_ms or 0)
    a.status = "abandoned"
    a.finished_at = datetime.now()
    a.grade = a.grade_auto = 1
    review.replay(db, a.task)
    db.commit()


@router.post("/attempts/{aid}/reference")
def open_reference(aid: int, db=Depends(get_db)):
    """Эталон. До сдачи — только с отметкой «открыт» (снижает оценку)."""
    a = load(db, aid)  # у сданной и брошенной эталон открыт без штрафа
    if a.status == "active" and not a.ref_opened:
        a.ref_opened = 1
        db.commit()
    v = db.get(TaskVersion, a.version_id)
    files = json.loads(v.files)
    return {"files": taskfs.reference_files(files), "tests": taskfs.test_files(files),
            "roles": json.loads(v.roles or "{}")}


class GradeIn(BaseModel):
    grade: int | None = None


@router.post("/attempts/{aid}/grade")
def set_grade(aid: int, body: GradeIn, db=Depends(get_db)):
    """«Не согласен с оценкой»: ручной уровень сразу пересчитывает расписание."""
    a = load(db, aid)
    if a.status != "submitted":
        raise HTTPException(409, "уровень можно менять только у сданной попытки")
    if body.grade is not None and body.grade not in review.GRADES:
        raise HTTPException(400, "уровень 1..4")
    checking.set_manual_grade(db, a, body.grade)
    return public(a, db)


# ---------- запуск эталона в редакторе задачи ----------

def dev_args(t: Task) -> dict:
    try:
        py = taskfs.resolve_python(t.python)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"key": f"t{t.id}", "python": py, "cwd": str(taskfs.dev_dir(t.name)), "task_id": t.id}


@router.post("/tasks/{tid}/run")
def task_run(tid: int, body: RunIn, db=Depends(get_db)):
    """Запуск файла эталона (reference/x.py) из редактора задачи: код лежит в корне .dev/."""
    t = db.get(Task, tid)
    if t is None:
        raise HTTPException(404, "задача не найдена")
    path = body.path[len("reference/"):] if body.path.startswith("reference/") else body.path
    args = dev_args(t)
    if not (taskfs.dev_dir(t.name) / path).is_file():
        raise HTTPException(400, "запускать можно файлы из reference/")
    return {"job": runner.submit(**args, cmd={"op": "run", "path": path}, timeout=t.timeout)}


@router.post("/tasks/{tid}/exec")
def task_exec(tid: int, body: ExecIn, db=Depends(get_db)):
    t = db.get(Task, tid)
    if t is None:
        raise HTTPException(404, "задача не найдена")
    return {"job": runner.submit(**dev_args(t), cmd={"op": "exec", "code": body.code}, timeout=t.timeout)}


@router.post("/tasks/{tid}/stop")
def task_stop(tid: int):
    runner.interrupt(f"t{tid}")
    return {"ok": True}


@router.post("/tasks/{tid}/check")
def task_check(tid: int, db=Depends(get_db)):
    """Тесты на эталоне из текущей папки задачи (до сохранения версии) — проверить сами тесты."""
    t = db.get(Task, tid)
    if t is None:
        raise HTTPException(404, "задача не найдена")
    job = runner.new_job("check")
    job.owner = f"t{tid}"
    job.state = "running"
    name, timeout = t.name, t.timeout
    py = dev_args(t)["python"]

    def go():
        import shutil
        files = taskfs.snapshot(name)
        d = taskfs.run_dir(name, taskfs.reference_files(files), taskfs.test_files(files))
        try:
            res = runner.run_pytest(py, d, timeout, job)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        tests = [{**x, "status": x["status"]} for x in res.get("tests", {}).values()]
        for e in res.get("collection_errors", []):
            tests.append({"id": e["file"], "name": e["file"], "file": e["file"], "status": "error", "time": 0,
                          "message": e["message"], "text": e["text"]})
        job.finish({"status": "ok", "check": {"tests": tests, "fatal": res.get("fatal"),
                                               "passed": sum(x["status"] == "pass" for x in tests), "total": len(tests)}})

    threading.Thread(target=go, daemon=True).start()
    return {"job": job.id}
