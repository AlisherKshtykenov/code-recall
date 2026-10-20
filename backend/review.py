"""Интервальное повторение (FSRS-4.5) и итог попытки: уровень, предупреждения, расписание.

Расписание эталона не хранится «накопительно», а каждый раз пересчитывается по всей истории
сданных попыток. Поэтому ручная смена уровня («не согласен») сразу корректно меняет даты."""
import json
import math
import re
from datetime import datetime, timedelta

from .db import Attempt, Reference

GRADES = {1: "забыл", 2: "трудно", 3: "нормально", 4: "легко"}
# оценка 0–100 -> уровень
THRESHOLDS = [(90, 4), (70, 3), (50, 2), (0, 1)]

# ---------- FSRS-4.5, параметры по умолчанию ----------
W = [0.4872, 1.4003, 3.7145, 13.8206, 5.1618, 1.2298, 0.8975, 0.031, 1.6474, 0.1367,
     1.0461, 2.1072, 0.0793, 0.3246, 1.587, 0.2272, 2.8755]
W_SHORT = (0.5034, 0.6567)  # FSRS-5: повтор в тот же день (меньше суток)
DECAY, FACTOR = -0.5, 19 / 81
RETENTION = 0.9  # желаемая вероятность вспомнить к дате повторения


def clamp_d(d):
    return min(10.0, max(1.0, d))


def retrievability(days: float, s: float) -> float:
    return (1 + FACTOR * days / s) ** DECAY


def interval_days(s: float) -> float:
    return s / FACTOR * (RETENTION ** (1 / DECAY) - 1)


def fsrs_step(state: dict | None, grade: int, days: float) -> dict:
    """state = {s, d} или None для первого повторения."""
    if state is None:
        return {"s": W[grade - 1], "d": clamp_d(W[4] - (grade - 3) * W[5])}
    s, d = state["s"], state["d"]
    r = retrievability(max(days, 0.0), s)
    d0_good = W[4]
    new_d = clamp_d(W[7] * d0_good + (1 - W[7]) * (d - W[6] * (grade - 3)))
    if days < 1:
        # повтор в тот же день: стабильность меняется по краткосрочной формуле FSRS-5
        new_s = s * math.exp(W_SHORT[0] * (grade - 3 + W_SHORT[1]))
    elif grade == 1:
        new_s = W[11] * d ** -W[12] * ((s + 1) ** W[13] - 1) * math.exp(W[14] * (1 - r))
    else:
        bonus = W[15] if grade == 2 else W[16] if grade == 4 else 1.0
        new_s = s * (math.exp(W[8]) * (11 - d) * s ** -W[9] * (math.exp(W[10] * (1 - r)) - 1) * bonus + 1)
    return {"s": max(new_s, 0.1), "d": new_d}


def score_grade(score) -> int:
    return next(g for t, g in THRESHOLDS if (score or 0) >= t)


def block_grades(a: Attempt, version_cells, report: dict) -> dict:
    """Уровень каждого блока в попытке: {название: уровень}. Данные блоки и текст не считаются."""
    if a.mode == "scratch":
        # «с нуля» нет оценок по блокам — уровень попытки идёт всем блокам кода
        return {c.title: a.grade for c in version_cells if c.kind != "markdown"}
    written = [b for b in report.get("blocks", [])
               if not b.get("given") and b.get("index") is not None and b.get("score") is not None]
    if a.grade_manual:
        # ручной уровень — решение пользователя на всю попытку (только для блоков, которые он писал)
        return {b["title"]: a.grade for b in written}
    penalty = 1 if report.get("slower") else 0
    return {b["title"]: max(1, score_grade(b["score"]) - penalty - (1 if b.get("hint") else 0))
            for b in written}


def replay(db, ref: Reference):
    """Пересчитать расписание по истории попыток — ПО БЛОКАМ.

    Прогресс блока текущей версии складывается только из попыток, где этот блок был
    тем же самым (то же название и тот же код без учёта комментариев и пробелов).
    Поэтому после загрузки новой версии неизменённые блоки сохраняют прогресс,
    а изменённые и новые начинают с нуля. Дата эталона = самая ранняя дата среди блоков;
    блок без истории — «новый» и делает эталон доступным для повторения сразу."""
    # markdown-ячейки — текст, а не блоки для заучивания: в расписании не участвуют
    cur = ({c.title: normalize(c.code) for c in ref.current.cells if c.kind != "markdown"}
           if ref.current else {})
    rows = (db.query(Attempt).filter_by(reference_id=ref.id, status="submitted")
            .filter(Attempt.grade.isnot(None)).order_by(Attempt.finished_at).all())
    versions = {v.id: v for v in ref.versions}
    hist = {t: [] for t in cur}  # название -> [(время, уровень)]
    lapses = 0
    for a in rows:
        v = versions.get(a.version_id)
        if v is None or not a.report:
            continue
        same = {c.title for c in v.cells if c.title in cur and normalize(c.code) == cur[c.title]}
        for title, g in block_grades(a, v.cells, json.loads(a.report)).items():
            if title in same:
                hist[title].append((a.finished_at, g))
        lapses += a.grade == 1

    states = {}
    for title, events in hist.items():
        if not events:
            states[title] = {"status": "new", "due": None, "reps": 0}
            continue
        state, last = None, None
        for when, g in events:
            state = fsrs_step(state, g, (when - last).total_seconds() / 86400 if last else 0)
            last = when
        days = max(1, round(interval_days(state["s"])))
        due = datetime.combine((last + timedelta(days=days)).date(), datetime.min.time())
        states[title] = {"status": "learned", "s": round(state["s"], 2), "d": round(state["d"], 2),
                         "due": due.isoformat(), "reps": len(events), "last": last.isoformat(),
                         "last_grade": events[-1][1]}

    learned = [x for x in states.values() if x["status"] == "learned"]
    ref.block_states = json.dumps(states, ensure_ascii=False)
    ref.reps, ref.lapses = len(rows), lapses
    if not learned:
        ref.fsrs_s = ref.fsrs_d = ref.last_review = ref.due_at = None
        return
    ref.fsrs_s = min(x["s"] for x in learned)
    ref.fsrs_d = max(x["d"] for x in learned)
    ref.last_review = max(datetime.fromisoformat(x["last"]) for x in learned)
    if len(learned) < len(states):
        # есть новые/изменённые блоки — эталон пора повторить сейчас
        ref.due_at = datetime.combine(datetime.now().date(), datetime.min.time())
    else:
        ref.due_at = min(datetime.fromisoformat(x["due"]) for x in learned)


# ---------- уровень попытки ----------

def previous(db, a: Attempt) -> Attempt | None:
    """Прошлая сданная попытка того же эталона в том же режиме (время сравниваем честно).
    Для «повторить блок» — прошлый повтор того же блока."""
    rows = (db.query(Attempt)
            .filter(Attempt.reference_id == a.reference_id, Attempt.mode == a.mode,
                    Attempt.status == "submitted", Attempt.id != a.id,
                    Attempt.finished_at < a.finished_at)
            .order_by(Attempt.finished_at.desc()).all())
    if a.mode != "block":
        return rows[0] if rows else None
    target = json.loads(a.task).get("target_title")
    return next((p for p in rows if json.loads(p.task).get("target_title") == target), None)


def fmt_ms(ms) -> str:
    s = int((ms or 0) / 1000)
    return f"{s // 60:02d}:{s % 60:02d}"


def auto_grade(score: int, hints: int, total_ms: int, prev: Attempt | None, slower_pct: float):
    base = next(g for t, g in THRESHOLDS if score >= t)
    reasons = [f"оценка {score} → {GRADES[base]}"]
    g = base
    if hints:
        g -= 1
        reasons.append(f"подсказки ({hints}): −1 уровень")
    if prev and prev.total_ms and total_ms > prev.total_ms * (1 + slower_pct / 100):
        g -= 1
        reasons.append(f"время {fmt_ms(total_ms)} дольше прошлого ({fmt_ms(prev.total_ms)}): −1 уровень")
    g = max(1, g)
    if len(reasons) > 1:
        reasons.append(f"итог: {GRADES[g]}" + (" (ниже некуда)" if g == base == 1 else ""))
    return g, reasons


# ---------- предупреждения в отчёте ----------

def normalize(code: str) -> str:
    code = re.sub(r"#.*", "", code)
    return re.sub(r"\s+", "", code)


def warnings(report: dict, a: Attempt, prev: Attempt | None) -> list[dict]:
    """Короткие строки: {level: ok|warn|err, text}."""
    out = []
    if prev:
        diff = a.total_ms - prev.total_ms
        lvl = "warn" if diff > 0 else "ok"
        out.append({"level": lvl, "text": f"Написал за {fmt_ms(a.total_ms)} (прошлый раз {fmt_ms(prev.total_ms)}, "
                                          f"{'+' if diff > 0 else '−'}{fmt_ms(abs(diff))})"})
    else:
        out.append({"level": "ok", "text": f"Написал за {fmt_ms(a.total_ms)} (первая попытка в этом режиме)"})
    for b in report["blocks"]:
        if b["given"]:
            continue
        name = f"Блок {b['index'] + 1} «{b['title']}»" if b["index"] is not None else "Код"
        j = b["judge"] if b["judge"] and b["judge"].get("available") else None
        failed = [t for t in b["tests"] if t["status"] in ("fail", "error")]
        if not b["user_code"].strip():
            out.append({"level": "err", "text": f"{name}: не написан"})
            continue
        if b["conflict"]:
            out.append({"level": "warn", "text": f"{name}: КОНФЛИКТ — {b['conflict']}"})
        if b["exec_errors"]:
            out.append({"level": "err", "text": f"{name}: падает — {b['exec_errors'][0]}"})
        for t in failed[:2]:
            out.append({"level": "err", "text": f"{name}: тест «{t['name']}» "
                        + ("не совпал" if t["status"] == "fail" else "упал")})
        if j and j["errors"]:
            out.append({"level": "err", "text": f"{name}: {j['errors'][0]}"})
        tests_ok = b["parts"] and b["parts"]["tests"] == 1.0
        if (not b["exec_errors"] and not failed and (tests_ok or (j and j["verdict"] == "верно"))
                and normalize(b["user_code"]) != normalize(b["ref_code"]) and not b["conflict"]):
            out.append({"level": "ok", "text": f"{name}: написано иначе (другие имена/порядок), результат верный"})
        if b["hint"]:
            out.append({"level": "warn", "text": f"{name}: использована подсказка"})
    if report.get("broken_tests"):
        out.append({"level": "warn", "text": f"Сломанных тестов: {len(report['broken_tests'])} — не учитывались"})
    if not report["judge"]["used"]:
        out.append({"level": "warn", "text": "Судья недоступен — оценка только по выполнению и тестам"})
    return out


def finalize(db, a: Attempt):
    """После проверки: уровень, предупреждения, время блоков против прошлого раза, расписание."""
    report = json.loads(a.report)
    prev = previous(db, a)
    prev_blocks = {}
    if prev and prev.report:
        prev_blocks = {b["title"]: b.get("time_ms") for b in json.loads(prev.report).get("blocks", [])}
    for b in report["blocks"]:
        b["prev_time_ms"] = prev_blocks.get(b["title"])
    hints = len(json.loads(a.task).get("hints", {}))
    g, reasons = auto_grade(a.score, hints, a.total_ms, prev, report["weights"]["slower_pct"])
    a.grade_auto = g
    if not a.grade_manual:
        a.grade = g
    report["grade_reasons"] = reasons
    report["slower"] = any("дольше прошлого" in r for r in reasons)
    report["prev_attempt"] = ({"id": prev.id, "total_ms": prev.total_ms, "score": prev.score,
                               "date": prev.finished_at.isoformat(timespec="minutes")} if prev else None)
    report["warnings"] = warnings(report, a, prev)
    a.report = json.dumps(report, ensure_ascii=False)
    replay(db, a.reference)
    db.commit()


def set_manual_grade(db, a: Attempt, grade: int | None):
    """«Не согласен с оценкой»: ручной уровень (None — вернуть автоматический)."""
    if grade is None:
        a.grade_manual, a.grade = 0, a.grade_auto
    else:
        a.grade_manual, a.grade = 1, grade
    replay(db, a.reference)
    db.commit()


# ---------- экран «Сегодня» ----------

def block_reason(st: dict, today) -> str:
    if st["status"] == "new":
        return "ещё не повторялся (новый блок, изменён в новой версии или ещё не попадал в задания)"
    ago = (today - datetime.fromisoformat(st["last"]).date()).days
    if st["last_grade"] <= 2:
        return f"прошлый раз ошибся: «{GRADES[st['last_grade']]}»"
    return f"давно не повторял: {ago} дн."


def today_lists(db) -> dict:
    """Целые эталоны — когда к повторению подошли все их блоки; иначе — отдельные блоки."""
    today = datetime.now().date()
    overdue, due, new, upcoming, blocks = [], [], [], [], []
    for r in db.query(Reference).all():
        if not r.current or not any(c.kind != "markdown" for c in r.current.cells):
            continue
        done = sorted((a for a in r.attempts if a.status == "submitted" and a.grade is not None),
                      key=lambda a: a.finished_at)
        last = done[-1] if done else None
        code_cells = [(i, c) for i, c in enumerate(r.current.cells) if c.kind != "markdown"]
        item = {"id": r.id, "title": r.title, "tag": r.tag, "blocks": len(code_cells),
                "due_at": r.due_at.date().isoformat() if r.due_at else None,
                "last_grade": GRADES[last.grade] if last else None,
                "last_score": last.score if last else None,
                "last_date": last.finished_at.date().isoformat() if last else None,
                "reps": r.reps or 0, "lapses": r.lapses or 0,
                "mode": recommend_mode(done)}
        bs = json.loads(r.block_states or "{}")
        if not last or not any(x["status"] == "learned" for x in bs.values()):
            item["reason"] = f"ещё не решал (добавлен {r.created_at.date().isoformat()})"
            new.append(item)
            continue
        due_now = []
        for i, c in code_cells:
            st = bs.get(c.title, {"status": "new"})
            d = datetime.fromisoformat(st["due"]).date() if st.get("due") else today
            if st["status"] == "new" or d <= today:
                due_now.append((i, c, st, d))
        ago = (today - last.finished_at.date()).days
        if due_now and len(due_now) == len(code_cells):
            d = min(x[3] for x in due_now)
            reason = (f"прошлый раз ошибся: «{GRADES[last.grade]}», оценка {last.score}" if last.grade <= 2
                      else f"давно не повторял: {ago} дн. с последнего раза")
            if d < today:
                item["reason"] = f"просрочено на {(today - d).days} дн. · {reason}"
                item["due_at"] = d.isoformat()
                overdue.append(item)
            else:
                item["reason"] = reason
                due.append(item)
            continue
        for i, c, st, d in due_now:
            late = (today - d).days
            blocks.append({"id": r.id, "title": r.title, "tag": r.tag, "block": c.title, "index": i,
                           "due_at": d.isoformat() if st["status"] == "learned" else None,
                           "overdue": late > 0 and st["status"] == "learned",
                           "reason": (f"просрочен на {late} дн. · " if late > 0 and st["status"] == "learned" else "")
                           + block_reason(st, today)})
        if not due_now and r.due_at and r.due_at.date() <= today + timedelta(days=7):
            item["reason"] = f"последний раз: «{GRADES[last.grade]}», {ago} дн. назад"
            upcoming.append(item)
    overdue.sort(key=lambda x: x["due_at"])
    upcoming.sort(key=lambda x: x["due_at"])
    blocks.sort(key=lambda x: (not x["overdue"], x["due_at"] or "", x["title"]))
    return {"overdue": overdue, "due": due, "blocks": blocks, "new": new, "upcoming": upcoming}


MODE_ORDER = ["cells", "gaps", "scratch"]


def recommend_mode(done: list[Attempt]) -> str:
    """Новый эталон — по ячейкам; успех (нормально/легко) — режим сложнее; провал — проще."""
    done = [a for a in done if a.mode in MODE_ORDER]  # повтор одного блока не в счёт
    if not done:
        return "cells"
    last = done[-1]
    i = MODE_ORDER.index(last.mode)
    if last.grade >= 3:
        i = min(i + 1, len(MODE_ORDER) - 1)
    elif last.grade == 1:
        i = max(i - 1, 0)
    return MODE_ORDER[i]
