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

from . import bricks, llm, review, runner, semantic, taskfs
from .db import Attempt, BrickEvent, SessionLocal, Task, TaskVersion, get_setting

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

def ref_key(version: TaskVersion, python: str, deps: str = "") -> str:
    return hashlib.sha1(f"{python}\0{version.content_hash}\0{deps}".encode()).hexdigest()[:16]


def suite(db, task: Task, files: dict, assembly: dict, mine: dict) -> tuple[dict, dict]:
    """(код для прогона, тесты): мои файлы + кирпичики (bricks/, slots/) + тесты задачи и контрактные тесты слота."""
    code, lib = bricks.assemble(db, task, files, assembly, mine)
    # task.json — в папку прогона: тест-запрет читает из него список запрещённых имён ("forbidden")
    meta = {"task.json": files["task.json"]} if "task.json" in files else {}
    return {**lib, **code}, {**taskfs.test_files(files), **bricks.contract_tests(db, files), **meta}


def reference_results(task: Task, version: TaskVersion, python: str, job=None, force=False) -> dict:
    """Тесты на эталоне (все зависимости — эталоны) — из кэша версии или свежий прогон.
    Ключ кэша учитывает эталоны зависимостей: поменялся эталон кирпичика — тесты перепрогоняются."""
    files = json.loads(version.files)
    with SessionLocal() as db:
        t = db.get(Task, task.id)
        try:
            code, tests = suite(db, t, files, {}, taskfs.reference_files(files))
        except bricks.DepError as e:
            return {"fatal": f"сборка не удалась: {e}", "tests": {}, "collection_errors": [], "ms": 0}
        key = ref_key(version, python, bricks.deps_key(db, t, files))
    cached = json.loads(version.ref_results or "{}")
    if not force and key in cached:
        if job:
            job.note("эталон: результаты тестов из кэша (версия, зависимости и окружение не менялись)\n", "stdout")
        return cached[key]
    if job:
        job.note("=== тесты на эталоне ===\n", "stdout")
    d = taskfs.run_dir(task.name, code, tests)
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


def _run_one(task: Task, version: TaskVersion, code: dict, tests: dict, python: str, job, broken_note: str = "") -> dict:
    ref = reference_results(task, version, python, job)
    if ref.get("fatal"):
        job.note(f"\n{ref['fatal']}\n")
        return {"fatal": ref["fatal"], "tests": []}
    job.note(f"\n=== тесты на вашем коде: {task.title} ===\n", "stdout")
    d = taskfs.run_dir(task.name, code, tests)
    try:
        mine = runner.run_pytest(python, d, task.timeout, job)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    out = compare(ref, mine)
    if broken_note:
        for t in out:
            if t["status"] == "broken":
                t["message"] = f"{broken_note} · {t['message']}"
    return {"tests": out, "fatal": mine.get("fatal"), "timeout": mine.get("timeout"), "ms": mine["ms"]}


def run_tests(task: Task, version: TaskVersion, code: dict, python: str, job, assembly: dict | None = None) -> dict:
    """Проверка с учётом кирпичиков: сначала собственные тесты кирпичиков «пишу сам» (глубокие первыми),
    потом тесты задачи на собранном коде. Итог по каждому тесту; у тестов кирпичика — поле brick."""
    assembly = assembly or {}
    files = json.loads(version.files)
    all_tests, fatal, timeout, ms, summary = [], None, None, 0, []
    with SessionLocal() as db:
        t = db.get(Task, task.id)
        try:
            nodes = bricks.tree(db, t, assembly, files)
            merged, tests = suite(db, t, files, assembly, code)
        except bricks.DepError as e:
            return {"fatal": f"сборка не удалась: {e}", "tests": [], "passed": 0, "total": 0, "broken": 0}
        own = []  # кирпичики «пишу сам»: их собственные тесты на моём коде кирпичика
        for n in sorted((n for n in nodes if bricks.source_of(assembly, n) == "self"), key=lambda n: -n["depth"]):
            bt = db.get(Task, n["task_id"])
            bfiles = json.loads(bt.current.files)
            bmine = {n["main"]: merged.get(n["module"], ""), **{p: c for p, c in code.items() if p.startswith("bricks/")}}
            try:
                bcode, btests = suite(db, bt, bfiles, assembly, bmine)
            except bricks.DepError as e:
                own.append((n, None, None, None, str(e)))
                continue
            own.append((n, bt, bt.current, (bcode, btests), ""))
        broken_note = f"сломано зависимостью: {t.broken}" if t.broken else ""
    for n, bt, bv, pack, err in own:
        if err:
            all_tests.append({"id": f"brick:{n['name']}", "name": f"сборка кирпичика {n['name']}", "file": n["module"],
                              "status": "error", "message": err, "text": "", "time": 0, "brick": n["name"], "brick_title": n["title"]})
            summary.append({"name": n["name"], "title": n["title"], "passed": 0, "total": 1})
            continue
        r = _run_one(bt, bv, pack[0], pack[1], python, job)
        tests_b = [{**x, "brick": n["name"], "brick_title": n["title"], "id": f"{n['name']}::{x['id']}"} for x in r["tests"]]
        if r.get("fatal") and not tests_b:
            tests_b = [{"id": f"brick:{n['name']}", "name": f"тесты кирпичика {n['name']}", "file": n["module"], "status": "error",
                        "message": r["fatal"], "text": "", "time": 0, "brick": n["name"], "brick_title": n["title"]}]
        counted = [x for x in tests_b if x["status"] not in ("broken", "skip")]
        summary.append({"name": n["name"], "title": n["title"], "task_id": bt.id,
                        "passed": sum(x["status"] == "pass" for x in counted), "total": len(counted)})
        all_tests += tests_b
        ms += r.get("ms") or 0
    r = _run_one(task, version, merged, tests, python, job, broken_note)
    all_tests += r["tests"]
    fatal, timeout, ms = r.get("fatal"), r.get("timeout"), ms + (r.get("ms") or 0)
    counted = [t for t in all_tests if t["status"] not in ("broken", "skip")]
    return {"tests": all_tests, "passed": sum(t["status"] == "pass" for t in counted), "total": len(counted),
            "broken": sum(t["status"] == "broken" for t in all_tests), "bricks": summary,
            "fatal": fatal, "timeout": timeout, "ms": ms, "checked_at": datetime.now().isoformat(timespec="seconds")}


def run_check(attempt_id: int, job) -> dict:
    """«Проверить» / «Сдать»: тесты на файлах попытки."""
    with SessionLocal() as db:
        a = db.get(Attempt, attempt_id)
        task, version = a.task, db.get(TaskVersion, a.version_id)
        code = json.loads(a.files)
        assembly = json.loads(a.assembly or "{}")
        python = taskfs.resolve_python(task.python)
    return run_tests(task, version, code, python, job, assembly)


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
        assembly = json.loads(a.assembly or "{}")
        mine = json.loads(a.files)
        sc = score_attempt(db, a, result)
        try:
            ref_code = bricks.reference_code(db, a.task, files, assembly)
            written = bricks.written_paths(db, a.task, files, assembly)
        except bricks.DepError:
            ref_code = taskfs.reference_files(files)
            written = sorted(f for f in set(ref_code) | set(mine) if roles.get(f, "write") == "write")
        brick_events(db, a, result, mine)
        diffs = {f: semantic.unified(ref_code.get(f, ""), mine.get(f, ""), f) for f in written}  # по смыслу
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


def brick_events(db, a: Attempt, result: dict, mine: dict):
    """Кирпичики «пишу сам» в составной задаче -> событие повторения у самого кирпичика:
    его тесты прошли — «нормально», упали — «забыл» (и строка в «Сегодня»)."""
    files = json.loads(db.get(TaskVersion, a.version_id).files)
    try:
        nodes = {n["name"]: n for n in bricks.tree(db, a.task, json.loads(a.assembly or "{}"), files)}
    except bricks.DepError:
        return
    for b in result.get("bricks") or []:
        n = nodes.get(b["name"])
        if not n:
            continue
        ok = bool(b["total"]) and b["passed"] == b["total"]
        bad = [t for t in result.get("tests", []) if t.get("brick") == b["name"] and t["status"] in ("fail", "error")]
        note = "; ".join(f"{t['name']}: {(t['message'] or t['status']).strip().splitlines()[0][:120]}" for t in bad[:3])
        db.add(BrickEvent(task_id=n["task_id"], parent_task_id=a.task_id, attempt_id=a.id, dep_name=b["name"],
                          at=a.finished_at, passed=int(ok), grade=3 if ok else 1, code=mine.get(n["module"], ""), note=note))
        db.flush()
        review.replay(db, db.get(Task, n["task_id"]))


def set_manual_grade(db, a: Attempt, grade: int | None):
    """«Не согласен с оценкой»: ручной уровень (None — вернуть автоматический)."""
    if grade is None:
        a.grade_manual, a.grade = 0, a.grade_auto
    else:
        a.grade_manual, a.grade = 1, grade
    review.replay(db, a.task)
    db.commit()
