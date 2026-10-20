"""FastAPI-приложение CODE RECALL: задачи как на LeetCode, но свои и с ML."""
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Response, UploadFile
from fastapi.staticfiles import StaticFiles

from . import attempts, backup, checking, llm, review, runner, stats, tasks
from .db import Attempt, SessionLocal, get_setting, init_db, set_setting

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
    backup.start_daily_thread()
    runner.start_reaper()
    yield
    runner.stop_all()


app = FastAPI(title="CODE RECALL", lifespan=lifespan)


def get_db():
    with SessionLocal() as db:
        yield db


@app.get("/api/today")
def today(db=Depends(get_db)):
    return review.today_lists(db)


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


app.include_router(tasks.router)
app.include_router(tasks.file_router)
app.include_router(attempts.router)
app.include_router(attempts.file_router)
app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
