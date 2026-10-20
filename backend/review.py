"""Интервальное повторение (FSRS-4.5) по задачам, статусы задач, «Сегодня».

Расписание не хранится «накопительно», а каждый раз пересчитывается по истории сданных
попыток — поэтому ручная смена уровня («не согласен») сразу корректно сдвигает дату."""
import math
from datetime import datetime, timedelta

from .db import Attempt, ReviewSession, Task

GRADES = {1: "забыл", 2: "трудно", 3: "нормально", 4: "легко"}
THRESHOLDS = [(90, 4), (70, 3), (50, 2), (0, 1)]

# FSRS-4.5, параметры по умолчанию; повтор в тот же день — краткосрочная формула FSRS-5
W = [0.4872, 1.4003, 3.7145, 13.8206, 5.1618, 1.2298, 0.8975, 0.031, 1.6474, 0.1367,
     1.0461, 2.1072, 0.0793, 0.3246, 1.587, 0.2272, 2.8755]
W_SHORT = (0.5034, 0.6567)
DECAY, FACTOR = -0.5, 19 / 81
RETENTION = 0.9


def clamp_d(d):
    return min(10.0, max(1.0, d))


def fsrs_step(state, grade: int, days: float) -> dict:
    if state is None:
        return {"s": W[grade - 1], "d": clamp_d(W[4] - (grade - 3) * W[5])}
    s, d = state["s"], state["d"]
    r = (1 + FACTOR * max(days, 0.0) / s) ** DECAY
    new_d = clamp_d(W[7] * W[4] + (1 - W[7]) * (d - W[6] * (grade - 3)))
    if days < 1:
        new_s = s * math.exp(W_SHORT[0] * (grade - 3 + W_SHORT[1]))
    elif grade == 1:
        new_s = W[11] * d ** -W[12] * ((s + 1) ** W[13] - 1) * math.exp(W[14] * (1 - r))
    else:
        bonus = W[15] if grade == 2 else W[16] if grade == 4 else 1.0
        new_s = s * (math.exp(W[8]) * (11 - d) * s ** -W[9] * (math.exp(W[10] * (1 - r)) - 1) * bonus + 1)
    return {"s": max(new_s, 0.1), "d": new_d}


def interval_days(s: float) -> float:
    return s / FACTOR * (RETENTION ** (1 / DECAY) - 1)


def replay(db, task: Task):
    """FSRS по истории: сданные попытки (уровень по оценке или вручную) и брошенные («забыл»).
    Работа над ошибками на стабильность не влияет, но двигает дату: шаг 3 пройден без подглядывания —
    повтор завтра (не дольше), не пройден — сегодня же."""
    rows = (db.query(Attempt).filter(Attempt.task_id == task.id, Attempt.status.in_(("submitted", "abandoned")),
                                     Attempt.grade.isnot(None), Attempt.finished_at.isnot(None))
            .order_by(Attempt.finished_at).all())
    sessions = (db.query(ReviewSession).filter(ReviewSession.task_id == task.id,
                                               ReviewSession.status.in_(("passed", "failed")))
                .order_by(ReviewSession.finished_at).all())
    state, last, lapses = None, None, 0
    for a in rows:
        state = fsrs_step(state, a.grade, (a.finished_at - last).total_seconds() / 86400 if last else 0)
        lapses += a.grade == 1
        last = a.finished_at
    task.reps, task.lapses = len(rows), lapses
    if state is None:
        task.fsrs_s = task.fsrs_d = task.last_review = task.due_at = None
        return
    task.fsrs_s, task.fsrs_d, task.last_review = state["s"], state["d"], last
    days = max(1, round(interval_days(state["s"])))
    task.due_at = datetime.combine((last + timedelta(days=days)).date(), datetime.min.time())
    after = [s for s in sessions if s.finished_at > last]
    if after:  # последнее событие — работа над ошибками: её итог задаёт дату повтора
        s = after[-1]
        day = s.finished_at.date() + timedelta(days=1 if s.status == "passed" else 0)
        task.due_at = datetime.combine(day, datetime.min.time())


def score_grade(score) -> int:
    return next(g for t, g in THRESHOLDS if (score or 0) >= t)


def task_status(t: Task) -> str:
    """new — ещё не решал; due — пора повторить; solved — решено, повтор позже."""
    if t.due_at is None:
        return "new"
    return "due" if t.due_at.date() <= datetime.now().date() else "solved"


def today_lists(db) -> dict:
    today = datetime.now().date()
    overdue, due, new, upcoming, reviews = [], [], [], [], []
    for r in db.query(ReviewSession).filter_by(status="active").all():
        t = db.get(Task, r.task_id)
        reviews.append({"id": r.id, "task_id": t.id, "title": t.title, "kind": t.kind, "tag": t.tag, "step": r.step,
                        "attempt_id": r.attempt_id, "started_at": r.started_at.isoformat(timespec="minutes"),
                        "reason": f"работа над ошибками не закончена: шаг {r.step} из 3"})
    for t in db.query(Task).all():
        done = sorted((a for a in t.attempts if a.status in ("submitted", "abandoned") and a.grade is not None),
                      key=lambda a: a.finished_at)
        last = done[-1] if done else None
        item = {"id": t.id, "title": t.title, "kind": t.kind, "tag": t.tag,
                "due_at": t.due_at.date().isoformat() if t.due_at else None,
                "best_score": max((a.score for a in done if a.score is not None), default=None),
                "last_grade": GRADES[last.grade] if last else None,
                "active_attempt": next((a.id for a in reversed(t.attempts) if a.status == "active"), None)}
        if not last:
            item["reason"] = f"ещё не решал (добавлена {t.created_at.date().isoformat()})"
            new.append(item)
            continue
        ago = (today - last.finished_at.date()).days
        lastrev = max((rv for at in t.attempts for rv in at.reviews if rv.status in ("passed", "failed")),
                      key=lambda r: r.finished_at, default=None)
        if lastrev and lastrev.finished_at > last.finished_at:
            reason = ("работа над ошибками пройдена — закрепляем на следующий день" if lastrev.status == "passed"
                      else "работа над ошибками не пройдена — повторить сегодня")
        elif last.status == "abandoned":
            reason = "прошлая попытка брошена"
        elif last.grade <= 2:
            reason = f"прошлый раз ошибся: «{GRADES[last.grade]}», оценка {last.score}"
        else:
            reason = f"давно не повторял: {ago} дн."
        d = t.due_at.date()
        if d < today:
            item["reason"] = f"просрочено на {(today - d).days} дн. · {reason}"
            overdue.append(item)
        elif d == today:
            item["reason"] = reason
            due.append(item)
        elif d <= today + timedelta(days=7):
            item["reason"] = f"последний раз: «{GRADES[last.grade]}», {ago} дн. назад"
            upcoming.append(item)
    overdue.sort(key=lambda x: x["due_at"])
    upcoming.sort(key=lambda x: x["due_at"])
    return {"overdue": overdue, "due": due, "new": new, "upcoming": upcoming, "reviews": reviews}
