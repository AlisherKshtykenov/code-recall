"""Разовые миграции данных при старте (флаги — в settings)."""
from .db import Attempt, BrickEvent, SessionLocal, Task, get_setting, set_setting


def migrate_modes():
    """Режимы «Библиотека / С нуля»: старые попытки и события кирпичиков — режим «с нуля»,
    расписание пересчитывается отдельно по каждому режиму (таблица schedules)."""
    from . import review
    with SessionLocal() as db:
        if get_setting(db, "modes_migrated") == "1":
            return
        for a in db.query(Attempt).filter(Attempt.mode.is_(None)):
            a.mode = "scratch"
        for e in db.query(BrickEvent).filter(BrickEvent.mode.is_(None)):
            e.mode = "scratch"
        db.flush()
        for t in db.query(Task).all():
            review.replay(db, t)
        set_setting(db, "modes_migrated", "1")
        db.commit()
        print("CODE RECALL: режимы — старые попытки отнесены к «с нуля», расписание пересчитано по режимам")
