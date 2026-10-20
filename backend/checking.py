"""Проверка сданной попытки в три слоя:
1) выполнение: ваш код целиком в НОВОМ ядре;
2) тесты: те же тесты на эталоне (своё ядро) и на вашем коде, результаты сравниваются;
3) LLM-судья по каждому блоку, строгий JSON.
Работает в фоновом потоке; прогресс пишется в attempt.report."""
import json
import math
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import llm, review, workspace
from .db import Attempt, RefVersion, SessionLocal, Test, get_setting
from .kernels import Kernel
from .review import normalize

MARK = "__CR_RESULT__"

# Определяется в каждом ядре: выполнить тест, вернуть значение последнего выражения
# в каноническом JSON-виде (тензоры/массивы -> {shape, values}), чтобы сравнивать между ядрами.
HELPER = r'''
def __cr_canon(v, depth=0):
    import math as _m
    if depth > 6:
        return repr(v)[:200]
    try:
        import numpy as _np
    except ImportError:
        _np = None
    if hasattr(v, "detach") and hasattr(v, "cpu"):  # torch.Tensor
        v = v.detach().cpu().numpy()
    if _np is not None and isinstance(v, _np.generic):
        v = v.item()
    if _np is not None and isinstance(v, _np.ndarray) and v.ndim == 0:
        v = v.item()
    if _np is not None and isinstance(v, _np.ndarray):
        flat = v.astype(float).ravel() if v.dtype.kind in "biuf" else None
        if flat is None:
            return {"__array__": list(v.shape), "repr": repr(v)[:500]}
        if flat.size > 5000:
            return {"__array__": list(v.shape), "stats": [float(flat.mean()), float(flat.std()), float(flat.sum())]}
        return {"__array__": list(v.shape), "values": [float(x) for x in flat]}
    if isinstance(v, bool) or v is None or isinstance(v, (int, str)):
        return v
    if isinstance(v, float):
        return v if _m.isfinite(v) else repr(v)
    if isinstance(v, dict):
        return {str(k): __cr_canon(x, depth + 1) for k, x in v.items()}
    if isinstance(v, (list, tuple, set, frozenset)) or type(v).__name__ == "Size":
        items = sorted(v, key=repr) if isinstance(v, (set, frozenset)) else v
        return [__cr_canon(x, depth + 1) for x in items]
    return {"__repr__": repr(v)[:500]}

def __cr_run(src):
    import ast as _ast, json as _json
    tree = _ast.parse(src)
    g = globals()
    last = None
    if tree.body and isinstance(tree.body[-1], _ast.Expr):
        expr = _ast.Expression(tree.body.pop().value)
        exec(compile(tree, "<test>", "exec"), g)
        last = eval(compile(expr, "<test>", "eval"), g)
    else:
        exec(compile(tree, "<test>", "exec"), g)
    print("__CR_RESULT__" + _json.dumps(__cr_canon(last)))
'''


# ---------- выполнение и тесты ----------

def first_error(res: dict) -> str | None:
    for o in res["outputs"]:
        if o["type"] == "error":
            return f"{o['ename']}: {o['evalue']}"
    return None


def run_program(k: Kernel, cells: list[str], timeout: float) -> list[dict]:
    """Выполняет ячейки по порядку; после первой упавшей продолжаем — так видно больше."""
    out = []
    for code in cells:
        if not code.strip():
            out.append({"status": "empty", "error": None})
            continue
        r = k.execute(code, timeout=timeout)
        out.append({"status": "ok" if r["status"] == "ok" else "error", "error": first_error(r)})
    return out


def run_test(k: Kernel, code: str, timeout: float) -> dict:
    r = k.execute(f"__cr_run({json.dumps(code)})", timeout=timeout)
    err = first_error(r)
    if err:
        return {"ok": False, "error": err}
    text = "".join(o.get("text", "") for o in r["outputs"] if o["type"] == "stream")
    line = next((l for l in reversed(text.splitlines()) if l.startswith(MARK)), None)
    if line is None:
        return {"ok": False, "error": "тест не вернул результат"}
    return {"ok": True, "value": json.loads(line[len(MARK):])}


def same(a, b) -> bool:
    """Сравнение с допуском для чисел с плавающей точкой."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-4, abs_tol=1e-6)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    return a == b


def short(v, n=200) -> str:
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "…"


def run_side(cells: list[str], tests, timeout: float, ref_id: int, python: str) -> dict:
    """Одна «сторона» проверки (эталон или вы) в своём свежем ядре и своей временной папке
    (data/ — ссылка на данные эталона), чтобы файлы сторон не перезатирали друг друга."""
    run_dir = workspace.temp_run_dir(ref_id)
    k = Kernel(python, str(run_dir))
    try:
        k.execute(HELPER, timeout=30)
        exec_res = run_program(k, cells, timeout)
        test_res = {t.id: run_test(k, t.code, timeout) for t in tests}
        return {"exec": exec_res, "tests": test_res}
    finally:
        k.shutdown()
        shutil.rmtree(run_dir, ignore_errors=True)


def compare_tests(tests, ref: dict, user: dict, ref_broken_exec: str | None) -> list[dict]:
    out = []
    for t in tests:
        r, u = ref[t.id], user[t.id]
        item = {"id": t.id, "name": t.name or f"тест #{t.id}", "block": t.block, "mode": t.mode,
                "ref_value": short(r.get("value")) if r["ok"] else None,
                "user_value": short(u.get("value")) if u["ok"] else None,
                "error": None}
        # Тест сломан, если не проходит на самом эталоне — это не ваша ошибка.
        if not r["ok"]:
            item.update(status="broken", error="на эталоне: " + (r["error"] or "")
                        + (f" (эталон не выполнился: {ref_broken_exec})" if ref_broken_exec else ""))
        elif t.mode == "assert" and r["value"] is not True:
            item.update(status="broken", error=f"на эталоне assert дал {short(r['value'], 80)}, а не True")
        elif not u["ok"]:
            item.update(status="error", error=u["error"])
        elif t.mode == "assert":
            item["status"] = "pass" if u["value"] is True else "fail"
        else:
            item["status"] = "pass" if same(r["value"], u["value"]) else "fail"
        out.append(item)
    return out


# ---------- LLM-судья ----------

VERDICTS = {"верно", "частично", "неверно"}
JUDGE_KEYS = {"verdict", "errors", "logic_differences", "comment"}


def validate_judge(d) -> tuple[dict | None, str]:
    """Строгая проверка ответа судьи. Возвращает (ответ, '') или (None, причина)."""
    if not isinstance(d, dict):
        return None, "ответ не JSON-объект"
    missing = JUDGE_KEYS - d.keys()
    if missing:
        return None, f"нет полей: {', '.join(sorted(missing))}"
    v = d["verdict"]
    if not isinstance(v, str) or v.strip().lower() not in VERDICTS:
        return None, f"verdict должен быть одним из: верно / частично / неверно (получено {v!r})"
    for key in ("errors", "logic_differences"):
        if not isinstance(d[key], list) or not all(isinstance(x, str) for x in d[key]):
            return None, f"{key} должен быть списком строк"
    if not isinstance(d["comment"], str):
        return None, "comment должен быть строкой"
    return {"verdict": v.strip().lower(), "errors": d["errors"],
            "logic_differences": d["logic_differences"], "comment": d["comment"]}, ""


def judge_prompt(task: str, ref_code: str, user_code: str, facts: str) -> str:
    return (
        "Ты проверяешь код, написанный по памяти, против эталона. Сравнивай ЛОГИКУ, а не текст.\n"
        "Правила вердикта:\n"
        "- «верно»: результат и поведение те же. Другие имена переменных, другой стиль, лишние "
        "промежуточные переменные, другой порядок независимых строк — это «верно», а не «частично».\n"
        "- «частично»: основная идея есть, но есть хотя бы одна настоящая ошибка или пропуск, "
        "который меняет поведение (пропущен шаг, не та формула, не то условие).\n"
        "- «неверно»: не работает или делает другое.\n"
        "Если в errors пусто — вердикт обязан быть «верно». Если вердикт «верно» — errors пустой.\n"
        "В errors — только настоящие ошибки, коротко и конкретно (что не так и как должно быть). "
        "Переименования и стиль в errors НЕ пиши — их место в logic_differences.\n"
        "Пример (не из твоей задачи): эталон `celsius = (f - 32) * 5 / 9` и ученик "
        "`c = 5 * (fahrenheit - 32) / 9` → «верно», errors []. Ученик `c = (f - 32) * 9 / 5` → «частично», "
        "errors [\"перепутан коэффициент: нужно 5/9, а не 9/5\"].\n"
        'Ответь СТРОГО JSON без текста вокруг: {"verdict": "верно|частично|неверно", '
        '"errors": ["..."], "logic_differences": ["..."], "comment": "..."}. Пиши по-русски.\n\n'
        f"ЗАДАЧА: {task}\n\nЭТАЛОН:\n```python\n{ref_code}\n```\n\n"
        f"КОД УЧЕНИКА:\n```python\n{user_code or '# (пусто)'}\n```\n\n"
        f"ФАКТЫ ПРОВЕРКИ (выполнение и тесты):\n{facts}")


def make_consistent(j: dict) -> dict:
    """Вердикт должен соответствовать списку ошибок самого судьи (маленькие модели путаются).
    Поправку видно в отчёте (поле adjusted)."""
    if j["verdict"] != "верно" and not j["errors"]:
        return {**j, "verdict": "верно",
                "adjusted": f"судья сказал «{j['verdict']}», но ошибок не назвал — засчитано как «верно»"}
    if j["verdict"] == "верно" and j["errors"]:
        return {**j, "verdict": "частично",
                "adjusted": "судья сказал «верно», но перечислил ошибки — засчитано как «частично»"}
    return j


class JudgeDown(Exception):
    pass


def judge(prompt: str) -> dict:
    """Один повтор при кривом JSON. Нет связи с LLM -> JudgeDown (дальше судью не зовём)."""
    messages = [{"role": "user", "content": prompt}]
    reason = ""
    for attempt in range(2):
        try:
            text = llm.chat(messages, want_json=True, timeout=240)
        except llm.LLMError as e:
            raise JudgeDown(str(e))
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data, reason = None, "ответ не разбирается как JSON"
        if data is not None:
            ok, reason = validate_judge(data)
            if ok:
                return {"available": True, **make_consistent(ok), "retried": attempt > 0}
        messages += [{"role": "assistant", "content": text[:4000]},
                     {"role": "user", "content": f"Ответ не прошёл проверку: {reason}. "
                      "Повтори строго в формате JSON с полями verdict, errors, logic_differences, comment."}]
    return {"available": False, "error": f"кривой ответ после повтора: {reason}"}


# ---------- оценка ----------

JUDGE_SCORE = {"верно": 1.0, "частично": 0.5, "неверно": 0.0}
# Веса и штрафы (в процентах) — редактируются в настройках.
SCORE_DEFAULTS = {"w_exec": 20, "w_tests": 30, "w_judge": 50,
                  "hint_penalty": 15, "plan_penalty": 10, "slower_pct": 10}


def score_settings(db) -> dict:
    out = {}
    for k, v in SCORE_DEFAULTS.items():
        try:
            out[k] = max(0.0, float(get_setting(db, k, str(v))))
        except ValueError:
            out[k] = float(v)
    return out


def block_parts(exec_ok: bool | None, tests: list[dict], jud: dict | None) -> dict:
    """Слои оценки блока, каждый 0..1 или None (слой недоступен)."""
    counted = [t for t in tests if t["status"] != "broken"]
    return {"exec": None if exec_ok is None else float(exec_ok),
            "tests": sum(t["status"] == "pass" for t in counted) / len(counted) if counted else None,
            "tests_n": len(counted),
            "judge": JUDGE_SCORE[jud["verdict"]] if jud and jud.get("available") else None}


def combine(parts: dict, w: dict) -> float:
    """Взвешенное среднее доступных слоёв: Σ(вес·значение) / Σ(вес)."""
    pairs = [(w["w_exec"], parts["exec"]), (w["w_tests"], parts["tests"]), (w["w_judge"], parts["judge"])]
    pairs = [(wt, v) for wt, v in pairs if v is not None]
    total = sum(wt for wt, _ in pairs)
    return sum(wt * v for wt, v in pairs) / total if total else 0.0


def find_conflict(parts: dict, jud: dict | None) -> str | None:
    """Слои противоречат друг другу — показываем явно, а не прячем в среднем."""
    verdict = jud["verdict"] if jud and jud.get("available") else None
    if verdict is None:
        return None
    if parts["tests"] == 1.0 and verdict == "неверно":
        return f"все тесты ({parts['tests_n']}) прошли, а судья считает «неверно»"
    if parts["tests"] == 0.0 and verdict == "верно":
        return f"судья считает «верно», а тесты ({parts['tests_n']}) не прошли"
    if parts["exec"] == 0.0 and verdict == "верно":
        return "судья считает «верно», а код падает при выполнении"
    return None


# ---------- основной сценарий ----------

def save_partial(aid: int, report: dict):
    """Промежуточный отчёт: тесты уже есть, судья дописывает блоки по мере готовности."""
    with SessionLocal() as db:
        a = db.get(Attempt, aid)
        a.report = json.dumps(report, ensure_ascii=False)
        db.commit()


def set_progress(aid: int, text: str):
    with SessionLocal() as db:
        a = db.get(Attempt, aid)
        a.report = json.dumps({"progress": text}, ensure_ascii=False)
        db.commit()


def check_attempt(aid: int):
    try:
        _check(aid)
    except Exception as e:  # проверка не должна оставлять попытку в «checking» навсегда
        with SessionLocal() as db:
            a = db.get(Attempt, aid)
            a.status = "submitted"
            a.report = json.dumps({"fatal": f"проверка упала: {e}"}, ensure_ascii=False)
            db.commit()


def _check(aid: int):
    with SessionLocal() as db:
        a = db.get(Attempt, aid)
        version = db.get(RefVersion, a.version_id)
        ref = a.reference
        user_cells = json.loads(a.cells)
        task = json.loads(a.task)
        # markdown не выполняется; в режиме «повторить блок» эталон — только до целевого блока
        last = task.get("target", len(version.cells) - 1) if a.mode == "block" else len(version.cells) - 1
        ref_cells = ["" if c.kind == "markdown" else c.code for c in version.cells[:last + 1]]
        blocks = [{"title": c.title, "kind": c.kind, "code": c.code} for c in version.cells]
        titles = {c.title for c in version.cells}
        # тесты «без блока» и неподтверждённые LLM-предложения не гоняем;
        # при повторе блока — только тесты этого блока
        tests = [t for t in ref.tests if t.approved and (not t.block or t.block in titles)]
        if a.mode == "block":
            tests = [t for t in tests if t.block == task["target_title"]]
        ref_id = ref.id
        python = workspace.resolve_python(ref.python or "")
        mode = a.mode
        timeout = float(get_setting(db, "cell_timeout", "60"))
        weights = score_settings(db)
        settings = llm.settings()
        task_text = ref.task or ref.title

    provider = settings["llm_provider"]
    model = settings["groq_model"] if provider == "groq" else settings["ollama_model"]

    set_progress(aid, "запускаю эталон и ваш код в двух отдельных ядрах")
    with ThreadPoolExecutor(2) as pool:
        f_ref = pool.submit(run_side, ref_cells, tests, timeout, ref_id, python)
        f_user = pool.submit(run_side, ["" if c.get("md") else c["code"] for c in user_cells], tests,
                             timeout, ref_id, python)
        ref_side, user_side = f_ref.result(), f_user.result()

    ref_err = next((e["error"] for e in ref_side["exec"] if e["status"] == "error"), None)
    test_results = compare_tests(tests, ref_side["tests"], user_side["tests"], ref_err)

    # Ваш код по блокам: ячейка без блока относится к предыдущему блоку.
    per_block = {i: {"code": [], "exec": [], "time_ms": 0} for i in range(len(blocks))}
    if mode != "scratch":
        cur = None
        for c, ex in zip(user_cells, user_side["exec"]):
            cur = c["block"] if c.get("block") is not None else cur
            if cur is not None:
                per_block[cur]["code"].append(c["code"])
                per_block[cur]["exec"].append(ex)
                per_block[cur]["time_ms"] += c.get("time_ms", 0)
    exec_errors = [{"cell": i, "error": ex["error"]} for i, ex in enumerate(user_side["exec"])
                   if ex["status"] == "error"]

    judge_info = {"provider": provider, "model": model, "available": True, "error": None}
    hints = task.get("hints", {})

    def facts_for(block_tests, errs):
        lines = [f"- ошибка выполнения: {e}" for e in errs if e] or ["- выполняется без ошибок"]
        for t in block_tests:
            if t["status"] != "broken":
                lines.append(f"- тест «{t['name']}»: {t['status']} (эталон {t['ref_value']}, ученик {t['user_value']})")
        return "\n".join(lines)

    def call_judge(prompt):
        if not judge_info["available"]:
            return None
        try:
            return judge(prompt)
        except JudgeDown as e:
            judge_info.update(available=False, error=f"нет связи с LLM: {e}")
            return None

    # --- фаза 1: блоки с выполнением и тестами — сразу в отчёт, судья ещё не смотрел ---
    report_blocks = []
    ref_code_all = "\n\n".join(b["code"] for b in blocks if b["kind"] != "markdown")
    if mode == "scratch":
        user_code = "\n\n".join(c["code"] for c in user_cells if not c.get("md"))
        report_blocks.append({"index": None, "title": "весь код", "given": False,
                              "user_code": user_code, "ref_code": ref_code_all,
                              "exec_ok": not exec_errors, "exec_errors": [e["error"] for e in exec_errors],
                              "tests": test_results, "judge": None, "hint": "plan" in hints,
                              "parts": None, "conflict": None, "score": None, "pending": bool(user_code.strip()),
                              "time_ms": sum(c.get("time_ms", 0) for c in user_cells),
                              "task_text": task_text})
    else:
        in_task = {tb["index"]: tb for tb in task["blocks"]}
        for i, b in enumerate(blocks):
            if b["kind"] == "markdown" or i not in in_task:
                continue  # текст не оценивается; при повторе блока — блоки после него не в задании
            given = in_task[i]["given"]
            pb = per_block[i]
            errs = [e["error"] for e in pb["exec"] if e["status"] == "error"]
            ran = [e for e in pb["exec"] if e["status"] != "empty"]
            user_code = "\n\n".join(pb["code"])
            report_blocks.append({
                "index": i, "title": b["title"], "given": given, "user_code": user_code,
                "ref_code": b["code"], "exec_ok": (not errs) if ran else False, "exec_errors": errs,
                "tests": [t for t in test_results if t["block"] == b["title"]],
                "judge": None, "hint": str(i) in hints, "score": None, "parts": None, "conflict": None,
                "time_ms": pb["time_ms"], "pending": not given and bool(user_code.strip()),
                "task_text": f"{task_text}. Блок «{b['title']}»"})

    def report_now(partial: bool, progress: str = "") -> dict:
        judge_used = any(b["judge"] and b["judge"].get("available") and not b["judge"].get("exact")
                         for b in report_blocks)
        return {"partial": partial, "progress": progress,
                "judge": {**judge_info, "used": judge_used},
                "reference_ok": ref_err is None, "reference_error": ref_err,
                "exec_errors": exec_errors, "tests": test_results,
                "broken_tests": [t["id"] for t in test_results if t["status"] == "broken"],
                "blocks": [{k: v for k, v in b.items() if k != "task_text"} for b in report_blocks],
                "weights": weights}

    pending = [b for b in report_blocks if b["pending"]]
    save_partial(aid, report_now(True, f"тесты готовы · судья ({provider}: {model}): 0/{len(pending)}"))

    # --- фаза 2: судья по блокам в фоне; отчёт обновляется после каждого блока ---
    for n, b in enumerate(pending, 1):
        if normalize(b["user_code"]) == normalize(b["ref_code"]):
            # код совпал с эталоном (без пробелов и комментариев) — судья не нужен
            b["judge"] = {"available": True, "verdict": "верно", "errors": [], "logic_differences": [],
                          "comment": "код совпадает с эталоном (без учёта пробелов и комментариев) — судья не вызывался",
                          "exact": True}
        else:
            b["judge"] = call_judge(judge_prompt(b["task_text"], b["ref_code"], b["user_code"],
                                                 facts_for(b["tests"], b["exec_errors"])))
        b["pending"] = False
        b["parts"] = block_parts(b["exec_ok"], b["tests"], b["judge"])
        b["conflict"] = find_conflict(b["parts"], b["judge"])
        save_partial(aid, report_now(True, f"судья ({provider}: {model}): {n}/{len(pending)}"))

    # --- фаза 3: оценки ---
    scores = []
    for b in report_blocks:
        if b["given"]:
            continue
        s = combine(b["parts"], weights) if b["parts"] else 0.0  # пустой блок = 0
        if b["hint"]:
            s *= 1 - (weights["plan_penalty"] if mode == "scratch" else weights["hint_penalty"]) / 100
        b["score"] = round(s * 100)
        scores.append(s)
    if mode != "scratch":
        # Тесты на весь код (без блока) — как ещё один «блок» в среднем.
        common = [t for t in test_results if not t["block"] and t["status"] != "broken"]
        if common:
            scores.append(sum(t["status"] == "pass" for t in common) / len(common))
    overall = sum(scores) / len(scores) if scores else 0.0

    if judge_info["available"] and any(b["judge"] and not b["judge"]["available"] for b in report_blocks):
        judge_info["error"] = "часть ответов судьи не прошла проверку JSON даже после повтора"
    report = report_now(False)
    llm_used, exact = report["judge"]["used"], any(b["judge"] and b["judge"].get("exact") for b in report_blocks)
    report.update({
        "score": round(overall * 100),
        "conflicts": sum(1 for b in report_blocks if b["conflict"]),
        "basis": ("тесты + выполнение + LLM-судья" if llm_used else
                  "тесты + выполнение (код совпал с эталоном, судья не понадобился)" if exact else
                  "только выполнение и тесты (судья недоступен)"),
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    })
    with SessionLocal() as db:
        a = db.get(Attempt, aid)
        a.report = json.dumps(report, ensure_ascii=False)
        a.score = report["score"]
        a.status = "submitted"
        # отмечаем сломанные тесты, чтобы это было видно на вкладке «тесты»
        for t in test_results:
            row = db.get(Test, t["id"])
            if row:
                row.broken = t["error"] if t["status"] == "broken" else ""
        db.commit()
        review.finalize(db, a)


def start_check(aid: int):
    threading.Thread(target=check_attempt, args=(aid,), daemon=True).start()


def run_reference_tests(ref) -> list[dict]:
    """Прогон тестов только на эталоне (вкладка «тесты»): видно значения и сломанные тесты."""
    with SessionLocal() as db:
        timeout = float(get_setting(db, "cell_timeout", "60"))
    cells = ref.current.cells
    titles = {c.title for c in cells}
    tests = [t for t in ref.tests if not t.block or t.block in titles]
    side = run_side(["" if c.kind == "markdown" else c.code for c in cells], tests, timeout,
                    ref.id, workspace.resolve_python(ref.python or ""))
    ref_err = next((e["error"] for e in side["exec"] if e["status"] == "error"), None)
    out = []
    for t in tests:
        r = side["tests"][t.id]
        if not r["ok"]:
            broken = "на эталоне: " + r["error"] + (f" (эталон не выполнился: {ref_err})" if ref_err else "")
        elif t.mode == "assert" and r["value"] is not True:
            broken = f"на эталоне assert дал {short(r['value'], 80)}, а не True"
        else:
            broken = ""
        out.append({"id": t.id, "value": short(r.get("value")) if r["ok"] else None, "broken": broken})
    return out
