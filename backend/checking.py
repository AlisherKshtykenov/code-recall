"""Проверка: тесты задачи (pytest) на эталоне и на вашем коде, оценка, отчёт.

- Прогон идёт в копии рабочей папки: файлы кода + tests/ + conftest.py с фикстурами (device, seed,
  data_dir), data/ по ссылке. Рабочая директория — корень, как при «Запустить».
- Тесты сначала гоняются на эталоне (результат кэшируется по версии задачи и окружению).
  Тест упал на эталоне -> «сломан», на оценку не влияет.
- Оценка: доля прошедших тестов, минус штрафы за лишние «Проверить», открытый эталон и время
  дольше прошлой попытки. Веса — в настройках."""
import difflib
import hashlib
import json
import shutil
from datetime import datetime

from . import llm, review, runner, taskfs
from .db import Attempt, SessionLocal, Task, TaskVersion, get_setting

SCORE_DEFAULTS = {"free_checks": 2, "check_penalty": 3, "check_penalty_max": 15,
                  "ref_penalty": 30, "time_penalty": 10, "slower_pct": 20, "llm_judge": 0}


def score_settings(db) -> dict:
    out = {}
    for k, v in SCORE_DEFAULTS.items():
        try:
            out[k] = max(0, int(float(get_setting(db, k, str(v)))))
        except ValueError:
            out[k] = v
    return out


# ---------- прогоны ----------

def ref_key(version: TaskVersion, python: str) -> str:
    return hashlib.sha1(f"{python}\0{version.content_hash}".encode()).hexdigest()[:16]


def reference_results(task: Task, version: TaskVersion, python: str, job=None, force=False) -> dict:
    """Тесты на эталоне — из кэша версии или свежий прогон."""
    key = ref_key(version, python)
    cached = json.loads(version.ref_results or "{}")
    if not force and key in cached:
        if job:
            job.note("эталон: результаты тестов из кэша (версия и окружение не менялись)\n", "stdout")
        return cached[key]
    files = json.loads(version.files)
    if job:
        job.note("=== тесты на эталоне ===\n", "stdout")
    d = taskfs.run_dir(task.name, taskfs.reference_files(files), taskfs.test_files(files))
    try:
        res = runner.run_pytest(python, d, task.timeout, job)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    res.pop("output", None)
    if not res.get("fatal") and not res.get("timeout"):
        with SessionLocal() as db:
            v = db.get(TaskVersion, version.id)
            v.ref_results = json.dumps({key: res}, ensure_ascii=False)  # храним только последнее окружение
            db.commit()
    return res


def compare(ref: dict, mine: dict) -> list[dict]:
    """Итог по каждому тесту эталона: pass | fail | error | broken | skip."""
    out = []
    coll = {e["file"].split(".")[-1] + ".py": e for e in mine.get("collection_errors", [])}
    for e in ref.get("collection_errors", []):
        out.append({"id": e["file"], "name": e["file"], "file": e["file"], "status": "broken", "time": 0,
                    "message": "файл тестов не собирается даже на эталоне: " + e["message"], "text": e["text"]})
    for tid, r in ref.get("tests", {}).items():
        item = {"id": tid, "name": r["name"], "file": r["file"], "time": 0, "message": "", "text": "",
                "ref_time": r["time"]}
        if r["status"] in ("fail", "error"):
            item.update(status="broken", message="падает на эталоне: " + (r["message"] or r["status"]), text=r["text"])
        elif r["status"] == "skip":
            item["status"] = "skip"
        elif tid in mine.get("tests", {}):
            m = mine["tests"][tid]
            item.update(status=m["status"], time=m["time"], message=m["message"], text=m["text"])
        elif r["file"] in coll:
            e = coll[r["file"]]
            item.update(status="error", message="тесты не запустились: " + e["message"], text=e["text"])
        else:
            item.update(status="error", message="тест не выполнился" + (f": {mine['fatal']}" if mine.get("fatal") else ""))
        out.append(item)
    return out


def run_tests(task: Task, version: TaskVersion, code: dict, python: str, job) -> dict:
    """Тесты на эталоне (из кэша, если можно) и на переданных файлах кода; итог по каждому тесту."""
    files = json.loads(version.files)
    ref = reference_results(task, version, python, job)
    if ref.get("fatal"):
        job.note(f"\n{ref['fatal']}\n")
        return {"fatal": ref["fatal"], "tests": [], "passed": 0, "total": 0, "broken": 0}
    job.note("\n=== тесты на вашем коде ===\n", "stdout")
    d = taskfs.run_dir(task.name, code, taskfs.test_files(files))
    try:
        mine = runner.run_pytest(python, d, task.timeout, job)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    tests = compare(ref, mine)
    counted = [t for t in tests if t["status"] not in ("broken", "skip")]
    return {"tests": tests, "passed": sum(t["status"] == "pass" for t in counted), "total": len(counted),
            "broken": sum(t["status"] == "broken" for t in tests),
            "fatal": mine.get("fatal"), "timeout": mine.get("timeout"), "ms": mine["ms"],
            "checked_at": datetime.now().isoformat(timespec="seconds")}


def run_check(attempt_id: int, job) -> dict:
    """«Проверить» / «Сдать»: тесты на файлах попытки."""
    with SessionLocal() as db:
        a = db.get(Attempt, attempt_id)
        task, version = a.task, db.get(TaskVersion, a.version_id)
        code = json.loads(a.files)
        python = taskfs.resolve_python(task.python)
    return run_tests(task, version, code, python, job)


# ---------- оценка и отчёт ----------

def unified(a: str, b: str, name: str) -> str:
    return "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), f"эталон/{name}", f"моё/{name}", n=3))


def previous(db, a: Attempt):
    return (db.query(Attempt).filter(Attempt.task_id == a.task_id, Attempt.status == "submitted",
                                     Attempt.id != a.id, Attempt.finished_at < a.finished_at)
            .order_by(Attempt.finished_at.desc()).first())


def fmt_ms(ms) -> str:
    s = int((ms or 0) / 1000)
    return f"{s // 60:02d}:{s % 60:02d}"


def score_attempt(db, a: Attempt, result: dict) -> dict:
    """Оценка 0–100 и уровень. Формула видна в отчёте."""
    w = score_settings(db)
    prev = previous(db, a)
    parts, reasons = [], []
    base = None if result.get("fatal") or not result.get("total") else 100 * result["passed"] / result["total"]
    score, grade = base, None
    if base is not None:
        parts.append(f"тесты {result['passed']}/{result['total']} → {base:.0f}")
        extra = max(0, a.checks - w["free_checks"])
        if extra:
            p = min(w["check_penalty_max"], extra * w["check_penalty"])
            score -= p
            parts.append(f"«Проверить» {a.checks} раз (без штрафа {w['free_checks']}) → −{p}")
        if a.ref_opened:
            score -= w["ref_penalty"]
            parts.append(f"открыт эталон → −{w['ref_penalty']}")
        if prev and prev.total_ms and a.total_ms > prev.total_ms * (1 + w["slower_pct"] / 100):
            score -= w["time_penalty"]
            parts.append(f"время {fmt_ms(a.total_ms)} дольше прошлого ({fmt_ms(prev.total_ms)}) больше чем на "
                         f"{w['slower_pct']}% → −{w['time_penalty']}")
        score = max(0, min(100, round(score)))
        grade = review.score_grade(score)
        reasons.append(f"оценка {score} → {review.GRADES[grade]}")
        if a.ref_opened and grade > 1:
            grade -= 1
            reasons.append("эталон открыт до сдачи: −1 уровень")
    else:
        reasons.append("нет результатов тестов — поставьте уровень сами («не согласен»)")
    return {"score": score, "grade": grade, "parts": parts, "reasons": reasons, "weights": w,
            "prev": {"id": prev.id, "total_ms": prev.total_ms, "score": prev.score} if prev else None}


def warnings(a: Attempt, result: dict, sc: dict) -> list[dict]:
    out = []
    prev = sc["prev"]
    if prev:
        diff = a.total_ms - prev["total_ms"]
        out.append({"level": "warn" if diff > 0 else "ok",
                    "text": f"Решил за {fmt_ms(a.total_ms)} (прошлый раз {fmt_ms(prev['total_ms'])}, "
                            f"{'+' if diff > 0 else '−'}{fmt_ms(abs(diff))})"})
    else:
        out.append({"level": "ok", "text": f"Решил за {fmt_ms(a.total_ms)} — первая сданная попытка"})
    if result.get("fatal"):
        out.append({"level": "err", "text": result["fatal"]})
    for t in result.get("tests", []):
        if t["status"] in ("fail", "error"):
            first = (t["message"] or t["status"]).strip().splitlines() or [t["status"]]
            out.append({"level": "err", "text": f"{t['name']}: {first[0][:200]}"})
        elif t["status"] == "broken":
            out.append({"level": "warn", "text": f"{t['name']}: тест сломан на эталоне — не учитывался"})
    if result.get("total") and result["passed"] == result["total"]:
        out.append({"level": "ok", "text": f"Все тесты прошли ({result['total']})"})
    if a.checks:
        out.append({"level": "warn" if a.checks > sc["weights"]["free_checks"] else "ok",
                    "text": f"«Проверить» нажато {a.checks} раз"})
    if a.ref_opened:
        out.append({"level": "warn", "text": "Эталон открыт до сдачи"})
    return out


def finish_submit(attempt_id: int, result: dict):
    """После финального прогона: оценка, отчёт, расписание; затем (если включён) комментарий LLM."""
    with SessionLocal() as db:
        a = db.get(Attempt, attempt_id)
        version = db.get(TaskVersion, a.version_id)
        files = json.loads(version.files)
        roles = json.loads(version.roles or "{}")
        ref_code = taskfs.reference_files(files)
        mine = json.loads(a.files)
        sc = score_attempt(db, a, result)
        written = sorted(f for f in set(ref_code) | set(mine) if roles.get(f, "write") == "write")
        diffs = {f: unified(ref_code.get(f, ""), mine.get(f, ""), f) for f in written}
        history = [{"id": x.id, "date": x.finished_at.isoformat(timespec="minutes"), "score": x.score,
                    "total_ms": x.total_ms} for x in a.task.attempts if x.status == "submitted" and x.id != a.id]
        history.append({"id": a.id, "date": a.finished_at.isoformat(timespec="minutes"), "score": sc["score"],
                        "total_ms": a.total_ms})
        report = {"result": result, **sc, "diffs": diffs, "written": written, "history": history,
                  "warnings": warnings(a, result, sc), "judge": "pending" if sc["weights"]["llm_judge"] else None}
        a.score, a.grade_auto = sc["score"], sc["grade"]
        if not a.grade_manual:
            a.grade = sc["grade"]
        a.status = "submitted"
        a.report = json.dumps(report, ensure_ascii=False)
        review.replay(db, a.task)
        db.commit()
        title = a.task.title
    if not sc["weights"]["llm_judge"]:
        return
    s = llm.settings()
    model = s["groq_model"] if s["llm_provider"] == "groq" else s["ollama_model"]
    try:
        judge = {"ok": True, **llm.review_comment(title, {f: ref_code.get(f, "") for f in written},
                                                  {f: mine.get(f, "") for f in written})}
    except llm.LLMError as e:
        judge = {"ok": False, "error": str(e)}
    judge.update(provider=s["llm_provider"], model=model)
    with SessionLocal() as db:
        a = db.get(Attempt, attempt_id)
        rep = json.loads(a.report)
        rep["judge"] = judge
        a.report = json.dumps(rep, ensure_ascii=False)
        db.commit()


def set_manual_grade(db, a: Attempt, grade: int | None):
    """«Не согласен с оценкой»: ручной уровень (None — вернуть автоматический)."""
    if grade is None:
        a.grade_manual, a.grade = 0, a.grade_auto
    else:
        a.grade_manual, a.grade = 1, grade
    review.replay(db, a.task)
    db.commit()
