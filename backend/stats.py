"""Статистика: серия дней, календарь, слабые тесты и темы."""
import json
from collections import defaultdict
from datetime import date, timedelta

from .db import Attempt, Task

KINDS = {"algo": "алгоритм", "ml": "ML"}


def streak(days: set, today: date) -> dict:
    # серия считается и если сегодня ещё не занимались, но вчера — да
    cur, d = 0, today if today in days else today - timedelta(days=1)
    while d in days:
        cur += 1
        d -= timedelta(days=1)
    best, run, prev = 0, 0, None
    for d in sorted(days):
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        best, prev = max(best, run), d
    return {"current": cur, "best": best, "today_done": today in days}


def overview(db) -> dict:
    today = date.today()
    rows = db.query(Attempt).filter_by(status="submitted").order_by(Attempt.finished_at).all()
    tasks = {t.id: t for t in db.query(Task).all()}
    days = {a.finished_at.date() for a in rows}

    tests = defaultdict(lambda: {"n": 0, "fails": 0, "last_error": ""})
    tags = defaultdict(lambda: {"attempts": 0, "score_sum": 0, "scored": 0, "tests": 0, "fails": 0})
    for a in rows:
        t = tasks.get(a.task_id)
        if not t or not a.report:
            continue
        rep = json.loads(a.report)
        tag = t.tag or KINDS.get(t.kind, t.kind)
        g = tags[tag]
        g["attempts"] += 1
        if a.score is not None:
            g["score_sum"] += a.score
            g["scored"] += 1
        for r in (rep.get("result") or {}).get("tests", []):
            if r["status"] in ("broken", "skip"):
                continue
            st = tests[(t.id, r["id"])]
            st["n"] += 1
            g["tests"] += 1
            if r["status"] != "pass":
                st["fails"] += 1
                g["fails"] += 1
                st["last_error"] = (r.get("message") or r["status"]).strip().splitlines()[0][:200] if (r.get("message") or "").strip() else r["status"]
    weak_tests = sorted(
        ({"task_id": tid, "task": tasks[tid].title, "test": test.split("::")[-1], "file": test.split("::")[0],
          "n": s["n"], "fails": s["fails"], "fail_rate": s["fails"] / s["n"], "last_error": s["last_error"]}
         for (tid, test), s in tests.items() if s["fails"] and tid in tasks),
        key=lambda x: (-x["fail_rate"], -x["fails"]))[:20]
    weak_tags = sorted(
        ({"tag": k, "attempts": s["attempts"], "avg_score": round(s["score_sum"] / s["scored"]) if s["scored"] else None,
          "tests": s["tests"], "fails": s["fails"], "fail_rate": s["fails"] / s["tests"] if s["tests"] else 0}
         for k, s in tags.items()),
        key=lambda x: (-x["fail_rate"], x["avg_score"] if x["avg_score"] is not None else 101))
    cal_start = today - timedelta(days=today.weekday(), weeks=11)  # 12 недель с понедельника
    per_day = defaultdict(int)
    for a in rows:
        per_day[a.finished_at.date()] += 1
    calendar = [{"date": (cal_start + timedelta(days=i)).isoformat(), "count": per_day.get(cal_start + timedelta(days=i), 0)}
                for i in range((today - cal_start).days + 1)]
    return {"streak": streak(days, today), "attempts": len(rows), "days_active": len(days),
            "tasks": len(tasks), "weak_tests": weak_tests, "weak_tags": weak_tags, "calendar": calendar}
