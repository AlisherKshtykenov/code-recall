"""FastAPI-приложение CODE RECALL: задачи как на LeetCode, но свои и с ML."""
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Response, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import attempts, backup, builder, checking, library, llm, mapview, migrations, review, reviews, runner, semantic, stats, tasks
from .db import Attempt, ReviewSession, SessionLocal, Task, get_setting, init_db, set_setting

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
init_db()


@asynccontextmanager
async def lifespan(app):
    with SessionLocal() as db:  # проверки, прерванные перезапуском сервера, — в «сдано» без оценки
        for a in db.query(Attempt).filter_by(status="checking"):
            a.status = "active"
            a.finished_at = None
        db.commit()
    migrations.migrate_modes()  # разово: режимы «Библиотека / С нуля»
    backup.start_daily_thread()
    runner.start_reaper()
    start_stale_reaper()
    yield
    runner.stop_all()


app = FastAPI(title="CODE RECALL", lifespan=lifespan)


@app.middleware("http")
async def no_stale_html(request, call_next):
    """index.html — всегда свежая (в ней версии скриптов ?v=N), сами скрипты кэшируются по версии."""
    resp = await call_next(request)
    if request.url.path in ("/", "/index.html"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp
STALE_HOURS = 2


def start_stale_reaper():
    """Попытка, о которой сервер не слышал STALE_HOURS (вкладку закрыли, компьютер уснул), —
    в историю как брошенная, с тем кодом, что был сохранён."""
    import threading
    import time
    from datetime import timedelta

    def loop():
        while True:
            try:
                with SessionLocal() as db:
                    limit = datetime.now() - timedelta(hours=STALE_HOURS)
                    for a in db.query(Attempt).filter_by(status="active").all():
                        if (a.touched_at or a.started_at) < limit:
                            attempts.abandon_attempt(db, a)
                            runner.stop(f"a{a.id}")
            except Exception as e:
                print("stale reaper:", e)
            time.sleep(600)
    threading.Thread(target=loop, daemon=True).start()


def get_db():
    with SessionLocal() as db:
        yield db


@app.get("/api/today")
def today(db=Depends(get_db)):
    return review.today_lists(db)


@app.get("/api/journal")
def journal(filter: str = "", task_id: int | None = None, db=Depends(get_db)):
    """Журнал: попытки и «работа над ошибками». filter: abandoned | errors | reviews."""
    rows = []
    q = db.query(Attempt)
    if task_id:
        q = q.filter_by(task_id=task_id)
    for a in q.all():
        rows.append(attempts.journal_row(a))
    sq = db.query(ReviewSession)
    if task_id:
        sq = sq.filter_by(task_id=task_id)
    for r in sq.all():
        rows.append(reviews.journal_row(r, db.get(Task, r.task_id)))
    if filter == "abandoned":
        rows = [x for x in rows if x["status"] == "abandoned"]
    elif filter == "errors":
        rows = [x for x in rows if x["status"] in ("abandoned", "partial", "failed")]
    elif filter == "reviews":
        rows = [x for x in rows if x["type"] == "review"]
    return sorted(rows, key=lambda x: x["date"], reverse=True)


class CompareIn(BaseModel):
    mine: str = ""
    ref: str = ""


@app.post("/api/compare")
def compare(body: CompareIn):
    """Сравнение по смыслу: какие мои строки отличаются от эталона, без учёта оформления."""
    return semantic.compare(body.mine, body.ref)


@app.get("/api/stats")
def get_stats(db=Depends(get_db)):
    return stats.overview(db)


# ---------- бэкап ----------

@app.get("/api/backup/export")
def export_backup():
    data = backup.export_zip()
    name = f"code-recall-{datetime.now():%Y-%m-%d}.zip"
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.post("/api/backup/import")
async def import_backup(file: UploadFile):
    runner.stop_all()  # открытые попытки относятся к старой базе
    try:
        res = backup.import_zip(await file.read())
    except ValueError as e:
        raise HTTPException(400, str(e))
    init_db()
    return res


@app.get("/api/backup/list")
def list_backups():
    return backup.list_backups()


@app.post("/api/backup/now")
def backup_now():
    made = backup.daily_backup()
    return {"made": made.name if made else None, "backups": backup.list_backups()}


# ---------- настройки ----------

@app.get("/api/settings")
def get_settings(db=Depends(get_db)):
    s = {k: get_setting(db, k, d) for k, d in llm.DEFAULTS.items()}
    s.update(checking.score_settings(db))
    s["groq_key_set"] = bool(os.getenv("GROQ_API_KEY"))
    return s


@app.put("/api/settings")
def put_settings(body: dict, db=Depends(get_db)):
    for k in [*llm.DEFAULTS, *checking.SCORE_DEFAULTS]:
        if k in body:
            set_setting(db, k, str(body[k]))
    db.commit()
    return get_settings(db)


@app.post("/api/settings/test")
def test_llm():
    try:
        return {"ok": True, **llm.ping()}
    except llm.LLMError as e:
        return {"ok": False, "answer": str(e)}


app.include_router(library.router)
app.include_router(builder.router)
app.include_router(mapview.router)
app.include_router(tasks.router)
app.include_router(tasks.file_router)
app.include_router(attempts.router)
app.include_router(attempts.file_router)
app.include_router(reviews.router)
app.include_router(reviews.file_router)
app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
