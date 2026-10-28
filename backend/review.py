"""Интервальное повторение (FSRS-4.5) по задачам, статусы задач, «Сегодня».

Расписание не хранится «накопительно», а каждый раз пересчитывается по истории сданных
попыток — поэтому ручная смена уровня («не согласен») сразу корректно сдвигает дату."""
import math
from datetime import datetime, timedelta

import json
from types import SimpleNamespace

from .db import Attempt, BrickEvent, ReviewSession, Task

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


def _replay_mode(db, task: Task, mode: str):
    """FSRS одного режима по его истории -> dict(due_at, fsrs_s, fsrs_d, last_review, reps, lapses) или None."""
    rows = [a for a in db.query(Attempt).filter(Attempt.task_id == task.id, Attempt.status.in_(("submitted", "abandoned")),
                                                Attempt.grade.isnot(None), Attempt.finished_at.isnot(None)).all()
            if (a.mode or "scratch") == mode]
    # кирпичик, написанный внутри составной задачи, — повторение кирпичика в том режиме, в котором его написали
    rows += [SimpleNamespace(grade=e.grade, finished_at=e.at, brick_failed=not e.passed)
             for e in db.query(BrickEvent).filter_by(task_id=task.id).all() if (e.mode or "scratch") == mode]
    rows.sort(key=lambda x: x.finished_at)
    sessions = sorted((r for r in db.query(ReviewSession).filter(ReviewSession.task_id == task.id,
                                                                 ReviewSession.status.in_(("passed", "failed"))).all()
                       if (r.attempt.mode or "scratch") == mode), key=lambda r: r.finished_at)
    state, last, lapses = None, None, 0
    for a in rows:
        state = fsrs_step(state, a.grade, (a.finished_at - last).total_seconds() / 86400 if last else 0)
        lapses += a.grade == 1
        last = a.finished_at
    if state is None:
        return None
    days = max(1, round(interval_days(state["s"])))
    due = datetime.combine((last + timedelta(days=days)).date(), datetime.min.time())
    if getattr(rows[-1], "brick_failed", False):  # кирпичик упал внутри составной задачи — повторить его сегодня
        due = datetime.combine(last.date(), datetime.min.time())
    after = [s for s in sessions if s.finished_at > last]
    if after:  # последнее событие — работа над ошибками: её итог задаёт дату повтора
        day = after[-1].finished_at.date() + timedelta(days=1 if after[-1].status == "passed" else 0)
        due = datetime.combine(day, datetime.min.time())
    return {"due_at": due, "fsrs_s": state["s"], "fsrs_d": state["d"], "last_review": last, "reps": len(rows), "lapses": lapses}


def replay(db, task: Task):
    """FSRS по истории — отдельно для каждого режима (строки Schedule). В самой задаче — сводка:
    ближайшая дата повтора среди режимов (для списков и счётчиков «пора повторить»)."""
    from .db import Schedule
    found = {}
    for mode in ("library", "scratch"):
        st = _replay_mode(db, task, mode)
        row = db.get(Schedule, (task.id, mode))
        if st is None:
            if row is not None:
                db.delete(row)
            continue
        if row is None:
            row = Schedule(task_id=task.id, mode=mode)
            db.add(row)
        for k, v in st.items():
            setattr(row, k, v)
        found[mode] = st
    if not found:
        task.fsrs_s = task.fsrs_d = task.last_review = task.due_at = None
        task.reps = task.lapses = 0
        return
    first = min(found.values(), key=lambda st: st["due_at"])  # ближайший повтор
    task.due_at, task.fsrs_s, task.fsrs_d = first["due_at"], first["fsrs_s"], first["fsrs_d"]
    task.last_review = max(st["last_review"] for st in found.values())
    task.reps, task.lapses = sum(st["reps"] for st in found.values()), sum(st["lapses"] for st in found.values())


def schedules(db, task: Task) -> dict:
    """{режим: Schedule} — только режимы, в которых уже были повторения."""
    from .db import Schedule
    return {r.mode: r for r in db.query(Schedule).filter_by(task_id=task.id).all()}


def mode_summary(t: Task, modes: list, sched: dict, today=None) -> dict:
    """По каждому режиму: лучшая и последняя оценка, повторов, срыв, следующий, просрочка, медиана времени сданных попыток."""
    today = today or datetime.now().date()
    out = {}
    for m in modes:
        done = sorted((a for a in t.attempts if a.status == "submitted" and (a.mode or "scratch") == m), key=lambda a: a.finished_at)
        scores = [a.score for a in done if a.score is not None]
        times = sorted(a.total_ms for a in done if a.total_ms)
        row = sched.get(m)
        due = row.due_at.date() if row and row.due_at else None
        out[m] = {"best": max(scores, default=None), "last": scores[-1] if scores else None, "reps": row.reps if row else 0,
                  "lapses": row.lapses if row else 0, "due_at": due.isoformat() if due else None,
                  "overdue_days": (today - due).days if due and due < today else 0,
                  "median_ms": times[len(times) // 2] if times else None, "attempts": len(done)}
    return out


def mode_status(row) -> str:
    """new — в этом режиме ещё не решал; due — пора повторить; solved — повтор позже."""
    if row is None or row.due_at is None:
        return "new"
    return "due" if row.due_at.date() <= datetime.now().date() else "solved"


def score_grade(score) -> int:
    return next(g for t, g in THRESHOLDS if (score or 0) >= t)


def task_status(t: Task) -> str:
    """new — ещё не решал; due — пора повторить; solved — решено, повтор позже."""
    if t.due_at is None:
        return "new"
    return "due" if t.due_at.date() <= datetime.now().date() else "solved"


def weak_bricks(db, t: Task, by_name: dict, today) -> list[str]:
    """Прямые кирпичики составной задачи, которые сами пора повторить или которые в последний раз упали."""
    from . import bricks  # bricks -> db; review импортируется раньше bricks, поэтому здесь
    try:
        nodes = bricks.tree(db, t, json.loads(t.last_assembly or "{}"))
    except bricks.DepError:
        return []
    out = []
    for n in nodes:
        if n["depth"] != 0:
            continue
        b = db.get(Task, n["task_id"])
        last_ev = db.query(BrickEvent).filter_by(task_id=b.id).order_by(BrickEvent.at.desc()).first()
        if (b.due_at and b.due_at.date() <= today) or (last_ev and not last_ev.passed):
            out.append(b.title)
    return out


def _reason(db, t: Task, mode: str, last, today) -> str:
    """Почему эта пара (задача, режим) сегодня в списке."""
    ago = (today - last.finished_at.date()).days
    lastrev = max((rv for at in t.attempts if (at.mode or "scratch") == mode for rv in at.reviews if rv.status in ("passed", "failed")),
                  key=lambda r: r.finished_at, default=None)
    if last.status == "brick":
        parent = db.get(Task, last.event.parent_task_id)
        return (f"{t.title}: ошибка в задаче «{parent.title if parent else '?'}»" + (f" — {last.event.note}" if last.event.note else "")
                if not last.event.passed else f"написан в задаче «{parent.title if parent else '?'}» — тесты прошли")
    if lastrev and lastrev.finished_at > last.finished_at:
        return ("работа над ошибками пройдена — закрепляем на следующий день" if lastrev.status == "passed"
                else "работа над ошибками не пройдена — повторить сегодня")
    if last.status == "abandoned":
        return "прошлая попытка брошена"
    if last.grade <= 2:
        return f"прошлый раз ошибся: «{GRADES[last.grade]}», оценка {last.score}"
    return f"давно не повторял: {ago} дн."


def today_lists(db) -> dict:
    """Списки «Сегодня» по парам (задача, режим): «recall · библиотека» и «recall · с нуля» — разные строки."""
    from . import taskfs
    from .bricks import level_of
    from .builder import category_of
    today = datetime.now().date()
    overdue, due, new, upcoming, reviews = [], [], [], [], []
    for r in db.query(ReviewSession).filter_by(status="active").all():
        t = db.get(Task, r.task_id)
        mode = r.attempt.mode or "scratch"
        reviews.append({"id": r.id, "task_id": t.id, "title": t.title, "kind": t.kind, "tag": t.tag, "step": r.step,
                        "mode": mode, "mode_name": taskfs.MODE_NAME[mode],
                        "attempt_id": r.attempt_id, "started_at": r.started_at.isoformat(timespec="minutes"),
                        "reason": f"работа над ошибками не закончена: шаг {r.step} из 3"})
    events = {}
    for e in db.query(BrickEvent).order_by(BrickEvent.at).all():
        events.setdefault((e.task_id, e.mode or "scratch"), []).append(e)
    tasks = db.query(Task).all()
    by_name = {t.name: t for t in tasks}
    for t in tasks:
        files = json.loads(t.current.files) if t.current else {}
        modes = taskfs.modes_of(files)
        if not modes:
            continue  # концепт — только README, в повторения не входит
        sched = schedules(db, t)
        started = [m for m in modes if m in sched]
        library_done = any(a.status == "submitted" and (a.mode or "scratch") == "library" for a in t.attempts)
        for mode in modes:
            done = sorted((a for a in t.attempts if a.status in ("submitted", "abandoned") and a.grade is not None
                           and (a.mode or "scratch") == mode), key=lambda a: a.finished_at)
            last = done[-1] if done else None
            ev = events.get((t.id, mode), [])
            if ev and (not last or ev[-1].at > last.finished_at):
                last = SimpleNamespace(finished_at=ev[-1].at, grade=ev[-1].grade, score=None, status="brick", event=ev[-1])
            row = sched.get(mode)
            summ = mode_summary(t, [mode], sched, today)[mode]
            item = {"id": t.id, "name": t.name, "title": t.title, "kind": t.kind, "tag": t.tag, "mode": mode, "mode_name": taskfs.MODE_NAME[mode],
                    "level": level_of(files), "category": category_of(db, t), "median_ms": summ["median_ms"], "last_score": summ["last"],
                    "weak_brick": bool(last and getattr(last, "status", "") == "brick" and not last.event.passed),
                    "modes": modes, "due_at": row.due_at.date().isoformat() if row and row.due_at else None,
                    "best_score": max((a.score for a in done if a.score is not None), default=None),
                    "last_grade": GRADES[last.grade] if last else None,
                    "active_attempt": next((a.id for a in reversed(t.attempts) if a.status == "active" and (a.mode or "scratch") == mode), None)}
            if not last or row is None:
                # новая: сначала предлагаем «Библиотеку»; «С нуля» — отдельной строкой, когда библиотека уже начата
                if mode == "scratch" and "library" in modes and "library" not in started:
                    continue
                item["reason"] = (f"ещё не решал (добавлена {t.created_at.date().isoformat()})" if not started
                                  else f"«{taskfs.MODE_NAME[started[0]]}» уже начата — теперь «{taskfs.MODE_NAME[mode]}»")
                new.append(item)
                continue
            reason = _reason(db, t, mode, last, today)
            if mode == "scratch" and "library" in modes and not library_done:
                reason += " · сначала освой применение («Библиотека» ещё ни разу не сдана)"
            weak = weak_bricks(db, t, by_name, today)
            if weak:
                reason += " · сначала повтори кирпичик " + ", ".join(f"«{w}»" for w in weak)
            if t.broken:
                reason += f" · сломано зависимостью: {t.broken}"
            d = row.due_at.date()
            if d < today:
                item["reason"] = f"просрочено на {(today - d).days} дн. · {reason}"
                overdue.append(item)
            elif d == today:
                item["reason"] = reason
                due.append(item)
            elif d <= today + timedelta(days=7):
                item["reason"] = f"последний раз: «{GRADES[last.grade]}», {(today - last.finished_at.date()).days} дн. назад"
                upcoming.append(item)
    overdue.sort(key=lambda x: x["due_at"])
    upcoming.sort(key=lambda x: x["due_at"])
    return {"overdue": overdue, "due": due, "new": new, "upcoming": upcoming, "reviews": reviews}
