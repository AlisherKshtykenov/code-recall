"""Статистика: серия дней, слабые места по блокам и темам."""
import json
from collections import defaultdict
from datetime import date, timedelta

from .db import Attempt, Reference

ERROR_SCORE = 70  # блок с оценкой ниже — «с ошибкой»


def block_has_error(b: dict) -> bool:
    j = b.get("judge") or {}
    return ((b.get("score") or 0) < ERROR_SCORE or not b.get("exec_ok")
            or (j.get("available") and j.get("verdict") != "верно")
            or any(t["status"] in ("fail", "error") for t in b.get("tests", [])))


def streak(days: set[date], today: date) -> dict:
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
    refs = {r.id: r for r in db.query(Reference).all()}
    days = {a.finished_at.date() for a in rows}

    blocks = defaultdict(lambda: {"n": 0, "errors": 0, "score_sum": 0, "last_error": ""})
    tags = defaultdict(lambda: {"attempts": 0, "score_sum": 0, "blocks": 0, "errors": 0})
    for a in rows:
        ref = refs.get(a.reference_id)
        if not ref or not a.report:
            continue
        rep = json.loads(a.report)
        tag = ref.tag or "без темы"
        tags[tag]["attempts"] += 1
        tags[tag]["score_sum"] += a.score or 0
        for b in rep.get("blocks", []):
            if b.get("given") or b.get("score") is None:
                continue
            title = b["title"] if b.get("index") is not None else "весь код («с нуля»)"
            k = (ref.id, title)
            err = block_has_error(b)
            st = blocks[k]
            st["n"] += 1
            st["errors"] += err
            st["score_sum"] += b["score"]
            tags[tag]["blocks"] += 1
            tags[tag]["errors"] += err
            if err:
                j = b.get("judge") or {}
                st["last_error"] = ((j.get("errors") or [None])[0] or (b.get("exec_errors") or [None])[0]
                                    or next((f"тест «{t['name']}» не прошёл" for t in b.get("tests", [])
                                             if t["status"] in ("fail", "error")), "")
                                    or f"оценка {b['score']}")

    weak_blocks = sorted(
        ({"reference_id": rid, "reference": refs[rid].title, "tag": refs[rid].tag, "block": t,
          "n": s["n"], "errors": s["errors"], "error_rate": s["errors"] / s["n"],
          "avg_score": round(s["score_sum"] / s["n"]), "last_error": s["last_error"]}
         for (rid, t), s in blocks.items() if s["errors"]),
        key=lambda x: (-x["error_rate"], -x["errors"], x["avg_score"]))[:20]
    weak_tags = sorted(
        ({"tag": t, "attempts": s["attempts"], "avg_score": round(s["score_sum"] / s["attempts"]),
          "blocks": s["blocks"], "errors": s["errors"],
          "error_rate": s["errors"] / s["blocks"] if s["blocks"] else 0}
         for t, s in tags.items()),
        key=lambda x: (-x["error_rate"], x["avg_score"]))

    # календарь: 12 недель, начиная с понедельника
    cal_start = today - timedelta(days=today.weekday(), weeks=11)
    per_day = defaultdict(int)
    for a in rows:
        per_day[a.finished_at.date()] += 1
    calendar = [{"date": (cal_start + timedelta(days=i)).isoformat(),
                 "count": per_day.get(cal_start + timedelta(days=i), 0)}
                for i in range((today - cal_start).days + 1)]
    return {"streak": streak(days, today), "attempts": len(rows), "days_active": len(days),
            "references": len(refs), "weak_blocks": weak_blocks, "weak_tags": weak_tags,
            "calendar": calendar}
