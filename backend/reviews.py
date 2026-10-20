"""«Работа над ошибками» по попытке — три шага по каждому выбранному файлу:

1. Смотрю: эталон и мой код из попытки рядом, с подсветкой отличий. «Понял, дальше».
2. Переписываю с подглядыванием: эталон рядом, редактор пустой, вставка запрещена.
   Шаг закрыт, когда тесты прошли.
3. По памяти: эталон скрыт (подсмотреть можно — отмечается), пишу заново и сдаю тестами.
   Пройден, если тесты прошли без подглядывания.

Остальные файлы задачи во время шагов 2–3 берутся из эталона, чтобы тесты могли пройти.
На FSRS влияет только итог шага 3 (см. review.replay): пройден по всем файлам — повтор завтра,
нет — задача сегодня же снова в «Сегодня»."""
import json
import shutil
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import checking, files_api, review, runner, taskfs
from .db import Attempt, ReviewSession, SessionLocal, TaskVersion

router = APIRouter(prefix="/api")
STEPS = {1: "смотрю", 2: "переписываю с подглядыванием", 3: "по памяти"}


def get_db():
    with SessionLocal() as db:
        yield db


def load(db, rid) -> ReviewSession:
    r = db.get(ReviewSession, rid)
    if r is None:
        raise HTTPException(404, "работа над ошибками не найдена")
    return r


def active(db, rid) -> ReviewSession:
    r = load(db, rid)
    if r.status != "active":
        raise HTTPException(409, "работа над ошибками уже закончена")
    return r


def rdir(r: ReviewSession):
    p = taskfs.task_dir(r.attempt.task.name) / ".reviews" / str(r.id)
    (p / "results").mkdir(parents=True, exist_ok=True)
    taskfs._link(p / "data", taskfs.task_dir(r.attempt.task.name) / "data")
    return p


def version_files(db, r):
    v = db.get(TaskVersion, r.version_id)
    return json.loads(v.files), json.loads(v.roles or "{}")


def current_file(r) -> str:
    files = json.loads(r.files)
    return files[min(r.idx, len(files) - 1)]


def write_workdir(db, r: ReviewSession):
    """Рабочая папка шагов 2–3: переписываемый файл — из редактора, остальные — эталон."""
    files, _ = version_files(db, r)
    code = dict(taskfs.reference_files(files))
    work = json.loads(r.work or "{}")
    target = current_file(r)
    code[target] = work.get(target, "")
    taskfs.write_code(rdir(r), code)


def public(db, r: ReviewSession) -> dict:
    files, roles = version_files(db, r)
    a, t = r.attempt, r.attempt.task
    target = current_file(r)
    ref = taskfs.reference_files(files)
    out = {"id": r.id, "attempt_id": a.id, "task_id": t.id, "title": t.title, "kind": t.kind,
           "description": files.get("description.md", ""), "status": r.status, "step": r.step,
           "step_name": STEPS.get(r.step), "files": json.loads(r.files), "idx": r.idx, "file": target,
           "roles": roles, "all_files": sorted(ref), "peeked": bool(r.peeked), "checks": r.checks,
           "log": json.loads(r.log or "[]"), "started_at": r.started_at.isoformat(timespec="seconds"),
           "step_started": r.step_started.isoformat(timespec="seconds"), "timeout": t.timeout,
           "finished_at": r.finished_at.isoformat(timespec="minutes") if r.finished_at else None,
           "due_at": t.due_at.date().isoformat() if t.due_at else None, "data_link": taskfs.data_link(t.name),
           "mine": json.loads(a.files).get(target, "")}
    # эталон отдаём на шагах 1–2, на шаге 3 — только после «подсмотреть», и всегда после окончания
    if r.status != "active" or r.step in (1, 2) or r.peeked:
        out["reference"] = ref.get(target, "")
    return out


REVIEW_STATUS = {"active": "в процессе", "passed": "пройдена", "failed": "не пройдена", "abandoned": "брошена"}


def journal_row(r: ReviewSession, task) -> dict:
    log = json.loads(r.log or "[]")
    return {"type": "review", "id": r.id, "attempt_id": r.attempt_id, "task_id": task.id, "task": task.title,
            "kind": task.kind, "status": r.status, "status_name": REVIEW_STATUS.get(r.status, r.status),
            "date": (r.finished_at or r.started_at).isoformat(timespec="minutes"),
            "started_at": r.started_at.isoformat(timespec="minutes"), "step": r.step,
            "files": json.loads(r.files), "total_ms": sum(x["ms"] for x in log), "log": log,
            "checks": sum(x["checks"] for x in log), "ref_opened": any(x["peeked"] for x in log)}


class StartIn(BaseModel):
    files: list[str] | None = None  # None — все файлы «пишу сам» подряд


@router.post("/attempts/{aid}/reviews")
def start(aid: int, body: StartIn, db=Depends(get_db)):
    a = db.get(Attempt, aid)
    if a is None:
        raise HTTPException(404, "попытка не найдена")
    if a.status == "active":
        raise HTTPException(409, "сначала закончите попытку (сдайте или сбросьте)")
    open_ = next((r for r in a.reviews if r.status == "active"), None)
    if open_:
        return public(db, open_)  # незакрытая работа — продолжаем её
    v = db.get(TaskVersion, a.version_id)
    roles = json.loads(v.roles or "{}")
    written = sorted(f for f in taskfs.reference_files(json.loads(v.files)) if roles.get(f, "write") == "write")
    files = [f for f in (body.files or written) if f in written]
    if not files:
        raise HTTPException(400, "нет файлов «пишу сам»")
    r = ReviewSession(attempt_id=a.id, task_id=a.task_id, version_id=a.version_id, files=json.dumps(files))
    db.add(r)
    db.commit()
    return public(db, r)


@router.get("/reviews/{rid}")
def get(rid: int, db=Depends(get_db)):
    r = load(db, rid)
    if r.status == "active" and r.step > 1:
        write_workdir(db, r)
    return public(db, r)


def log_step(r: ReviewSession, passed: bool):
    log = json.loads(r.log or "[]")
    log.append({"file": current_file(r), "step": r.step, "passed": passed, "peeked": bool(r.peeked),
                "checks": r.checks, "ms": int((datetime.now() - r.step_started).total_seconds() * 1000)})
    r.log = json.dumps(log, ensure_ascii=False)


def next_step(db, r: ReviewSession):
    r.step += 1
    r.step_started, r.checks, r.peeked = datetime.now(), 0, 0
    if r.step in (2, 3):  # каждый шаг 2 и 3 начинается с пустого редактора
        work = json.loads(r.work or "{}")
        work[current_file(r)] = ""
        r.work = json.dumps(work, ensure_ascii=False)
    db.commit()
    write_workdir(db, r)


@router.post("/reviews/{rid}/next")
def step_next(rid: int, db=Depends(get_db)):
    """Шаг 1 -> 2 («понял, дальше»)."""
    r = active(db, rid)
    if r.step != 1:
        raise HTTPException(409, "дальше с этого шага — только через тесты")
    log_step(r, True)
    next_step(db, r)
    return public(db, r)


@router.post("/reviews/{rid}/peek")
def peek(rid: int, db=Depends(get_db)):
    """Подсмотреть эталон на шаге 3 — отмечается: шаг тогда не засчитывается."""
    r = active(db, rid)
    if r.step == 3:
        r.peeked = 1
        db.commit()
    return public(db, r)


def finish(db, r: ReviewSession, status: str):
    r.status = status
    r.finished_at = datetime.now()
    review.replay(db, r.attempt.task)
    db.commit()
    runner.stop(f"w{r.id}")
    shutil.rmtree(rdir(r), ignore_errors=True)


@router.post("/reviews/{rid}/check")
def check(rid: int, db=Depends(get_db)):
    """Тесты на текущем коде (шаги 2–3). Шаг 2 закрывается, как только тесты прошли.
    На шаге 3 это и есть «сдать»: прошли без подглядывания — файл пройден."""
    r = active(db, rid)
    if r.step == 1:
        raise HTTPException(409, "на шаге 1 тесты не нужны")
    r.checks += 1
    db.commit()
    job = runner.new_job("check")
    job.owner = f"w{rid}"
    job.state = "running"

    def go():
        with SessionLocal() as db2:
            rr = db2.get(ReviewSession, rid)
            files, _ = version_files(db2, rr)
            task = rr.attempt.task
            code = dict(taskfs.reference_files(files))
            code[current_file(rr)] = json.loads(rr.work or "{}").get(current_file(rr), "")
            python = taskfs.resolve_python(task.python)
            version = db2.get(TaskVersion, rr.version_id)
        try:
            res = checking.run_tests(task, version, code, python, job)
        except Exception as e:
            res = {"fatal": f"проверка упала: {e}", "tests": [], "passed": 0, "total": 0, "broken": 0}
        ok = bool(res.get("total")) and res["passed"] == res["total"]
        with SessionLocal() as db2:
            rr = db2.get(ReviewSession, rid)
            outcome = None
            if ok and rr.step == 2:
                log_step(rr, True)
                next_step(db2, rr)
                outcome = "step2_passed"
            elif rr.step == 3:
                passed = ok and not rr.peeked
                log_step(rr, passed)
                if not passed:
                    finish(db2, rr, "failed")
                    outcome = "failed"
                elif rr.idx + 1 < len(json.loads(rr.files)):
                    rr.idx += 1  # следующий файл — снова с шага 1
                    rr.step = 0
                    next_step(db2, rr)
                    outcome = "next_file"
                else:
                    finish(db2, rr, "passed")
                    outcome = "passed"
            db2.commit()
        job.finish({"status": "ok", "check": res, "outcome": outcome})

    threading.Thread(target=go, daemon=True).start()
    return {"job": job.id}


@router.post("/reviews/{rid}/abandon")
def abandon(rid: int, db=Depends(get_db)):
    r = load(db, rid)
    if r.status == "active":
        log_step(r, False)
        finish(db, r, "abandoned")
    return {"ok": True}


# ---------- запуск и консоль на шагах 2–3 ----------

class RunIn(BaseModel):
    path: str


class ExecIn(BaseModel):
    code: str


def worker_args(r: ReviewSession) -> dict:
    try:
        py = taskfs.resolve_python(r.attempt.task.python)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"key": f"w{r.id}", "python": py, "cwd": str(rdir(r)), "task_id": r.task_id}


def need_editor(db, rid):
    r = active(db, rid)
    if r.step == 1:
        raise HTTPException(409, "на шаге 1 код не запускается")
    return r


@router.post("/reviews/{rid}/run")
def run(rid: int, body: RunIn, db=Depends(get_db)):
    r = need_editor(db, rid)
    write_workdir(db, r)
    return {"job": runner.submit(**worker_args(r), cmd={"op": "run", "path": body.path}, timeout=r.attempt.task.timeout)}


@router.post("/reviews/{rid}/exec")
def exec_code(rid: int, body: ExecIn, db=Depends(get_db)):
    r = need_editor(db, rid)
    return {"job": runner.submit(**worker_args(r), cmd={"op": "exec", "code": body.code}, timeout=r.attempt.task.timeout)}


@router.post("/reviews/{rid}/stop")
def stop(rid: int):
    runner.interrupt(f"w{rid}")
    return {"ok": True}


def _review_files(rid, db, write):
    r = db.get(ReviewSession, rid)
    if r is None:
        raise ValueError("работа над ошибками не найдена")
    if write and (r.status != "active" or r.step == 1):
        raise ValueError("сейчас файлы только для чтения")

    def on_change(db2, rel):
        rr = db2.get(ReviewSession, rid)
        target = current_file(rr)
        if rel == target:  # в базу пишем только переписываемый файл
            p = rdir(rr) / target
            work = json.loads(rr.work or "{}")
            work[target] = p.read_text(encoding="utf-8") if p.exists() else ""
            rr.work = json.dumps(work, ensure_ascii=False)
            db2.commit()
    return rdir(r), on_change


file_router = files_api.make_router("/api/reviews", _review_files)
