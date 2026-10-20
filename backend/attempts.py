"""Задания и ноутбук: попытка = своё Jupyter-ядро + черновик ячеек + подсказки."""
import json
import random
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import checking, kernels, review, workspace
from .db import Attempt, Reference, RefVersion, SessionLocal, get_setting

router = APIRouter(prefix="/api")
MODES = {"scratch": "полностью с нуля", "cells": "по ячейкам", "gaps": "восстанови пропуск",
         "block": "повторить блок"}


def get_db():
    with SessionLocal() as db:
        yield db


def load(db, aid) -> Attempt:
    a = db.get(Attempt, aid)
    if a is None:
        raise HTTPException(404, "попытка не найдена")
    return a


def active(db, aid) -> Attempt:
    a = load(db, aid)
    if a.status != "active":
        raise HTTPException(409, "попытка уже завершена")
    return a


def kernel_args(a: Attempt) -> dict:
    """Ядро попытки: Python эталона, рабочая папка results/attempts/<id> с data/ эталона."""
    return {"python": workspace.resolve_python(a.reference.python or ""),
            "cwd": str(workspace.attempt_dir(a.reference_id, a.id))}


def build_task(ref: Reference, mode: str, seed: int, target: int | None = None) -> dict:
    cells = ref.current.cells
    code_idx = [i for i, c in enumerate(cells) if c.kind != "markdown"]
    given = set()
    if mode == "gaps" and len(code_idx) > 1:
        # Импорты даём всегда, из остальных — примерно половину; писать хотя бы один блок.
        rest = [i for i in code_idx if cells[i].kind != "imports"]
        given = {i for i in code_idx if cells[i].kind == "imports"}
        rng = random.Random(seed)
        given |= set(rng.sample(rest, len(rest) // 2))
        if given >= set(code_idx):
            given.discard(rng.choice(rest))
    if mode == "block":
        # Повтор одного блока: всё до него дано и выполняется само, блоки после — не показываем.
        given = {i for i in code_idx if i < target}
    blocks = []
    for i, c in enumerate(cells):
        if mode == "block" and i > target:
            break
        md = c.kind == "markdown"
        b = {"index": i, "kind": c.kind, "title": c.title, "description": c.description,
             "given": md or i in given, "md": md}
        if md or i in given:
            b["code"] = c.code
        blocks.append(b)
    task = {"title": ref.title, "tag": ref.tag, "mode": mode, "task": ref.task,
            "notes": ref.notes, "blocks": blocks, "hints": {}}
    if mode == "block":
        task.update(target=target, target_title=cells[target].title, auto_run=True)
    return task


def public(a: Attempt, db) -> dict:
    task = json.loads(a.task)
    if a.mode == "scratch" and "plan" not in task["hints"]:
        task["blocks"] = []  # в режиме «с нуля» структура скрыта, пока не открыт план
    return {"id": a.id, "reference_id": a.reference_id, "mode": a.mode,
            "mode_name": MODES[a.mode] + (f": «{task['target_title']}»" if a.mode == "block" else ""),
            "status": a.status, "kernel_key": f"a{a.id}",
            "started_at": a.started_at.isoformat(timespec="seconds"),
            "total_ms": a.total_ms, "cells": json.loads(a.cells), "task": task,
            "score": a.score, "report": json.loads(a.report) if a.report else None,
            "grade": a.grade, "grade_auto": a.grade_auto, "grade_manual": bool(a.grade_manual),
            "grade_name": review.GRADES.get(a.grade), "grades": review.GRADES,
            "due_at": a.reference.due_at.date().isoformat() if a.reference.due_at else None,
            "kernel": kernels.state(f"a{a.id}"),
            "cell_timeout": int(get_setting(db, "cell_timeout", "60"))}


def initial_cells(task: dict) -> list[dict]:
    if task["mode"] == "scratch":
        return [{"block": None, "given": False, "code": "", "time_ms": 0}]
    return [{"block": b["index"], "given": b["given"], "md": b.get("md", False),
             "code": b.get("code", ""), "time_ms": 0} for b in task["blocks"]]


class StartIn(BaseModel):
    reference_id: int
    mode: str = "cells"
    block: int | None = None  # для mode=block — номер блока в текущей версии


@router.post("/attempts")
def start_attempt(body: StartIn, db=Depends(get_db)):
    if body.mode not in MODES:
        raise HTTPException(400, "неизвестный режим")
    ref = db.get(Reference, body.reference_id)
    if ref is None or not ref.current or not any(c.kind != "markdown" for c in ref.current.cells):
        raise HTTPException(404, "в эталоне нет блоков кода")
    if body.mode == "block":
        cells = ref.current.cells
        if body.block is None or not 0 <= body.block < len(cells) or cells[body.block].kind == "markdown":
            raise HTTPException(400, "укажите блок кода")
    a = Attempt(reference_id=ref.id, version_id=ref.current.id, mode=body.mode)
    db.add(a)
    db.flush()
    task = build_task(ref, body.mode, seed=a.id, target=body.block)
    a.task = json.dumps(task, ensure_ascii=False)
    a.cells = json.dumps(initial_cells(task), ensure_ascii=False)
    db.commit()
    try:
        kernels.start(f"a{a.id}", **kernel_args(a))
    except ValueError as e:  # окружение эталона не найдено — ядро не стартует, но попытка есть
        print("ядро не запущено:", e)
    return public(a, db)


@router.get("/attempts/{aid}")
def get_attempt(aid: int, db=Depends(get_db)):
    a = load(db, aid)
    if a.status == "active":
        try:
            kernels.start(f"a{a.id}", **kernel_args(a))  # после ухода со страницы — новое ядро
        except ValueError:
            pass
    return public(a, db)


@router.get("/references/{rid}/attempts")
def list_attempts(rid: int, db=Depends(get_db)):
    rows = db.query(Attempt).filter_by(reference_id=rid).order_by(Attempt.started_at.desc()).all()
    out = []
    for a in rows:
        task = json.loads(a.task)
        out.append({"id": a.id, "mode": a.mode,
                    "mode_name": MODES[a.mode] + (f": {task.get('target_title')}" if a.mode == "block" else ""),
                    "status": a.status, "started_at": a.started_at.isoformat(timespec="minutes"),
                    "total_ms": a.total_ms, "score": a.score,
                    "grade": review.GRADES.get(a.grade), "grade_manual": bool(a.grade_manual),
                    "conflicts": json.loads(a.report).get("conflicts", 0) if a.report else 0,
                    "hints": len(task.get("hints", {}))})
    return out


@router.get("/attempts/{aid}/autorun")
def autorun_plan(aid: int, db=Depends(get_db)):
    """Что выполнится перед повтором блока и сколько это займёт по прошлым запускам.
    Тяжёлый блок с действительным кэшем — загрузка кэша; без кэша — пропуск (можно включить)."""
    from . import cache
    a = load(db, aid)
    task = json.loads(a.task)
    ref = a.reference
    version = db.get(RefVersion, a.version_id)
    heavy = set(json.loads(ref.heavy or "[]"))
    times = json.loads(ref.block_times or "{}")
    try:
        py = workspace.resolve_python(ref.python or "")
    except ValueError:
        py = ""
    items = []
    for b in task["blocks"]:
        if b.get("md") or not b["given"]:
            continue
        i, title = b["index"], b["title"]
        item = {"index": i, "title": title, "heavy": title in heavy, "est_ms": times.get(title)}
        if title in heavy:
            st = cache.status(ref.id, version.cells, i, py) if py else {"valid": False}
            if st.get("valid"):
                item.update(action="cache", cache=st, est_ms=None)
            else:
                item.update(action="skip", reason="тяжёлый блок, кэша нет" + (" (устарел — код или окружение изменились)"
                                                                              if st.get("exists") else ""))
        else:
            item["action"] = "run"
        items.append(item)
    known = [x["est_ms"] for x in items if x["action"] == "run" and x["est_ms"] is not None]
    return {"items": items, "total_ms": sum(known),
            "unknown": sum(1 for x in items if x["action"] == "run" and x["est_ms"] is None)}


class GradeIn(BaseModel):
    grade: int | None = None  # 1..4; None — вернуть автоматический


@router.post("/attempts/{aid}/grade")
def set_grade(aid: int, body: GradeIn, db=Depends(get_db)):
    """«Не согласен с оценкой»: ручной уровень сразу пересчитывает расписание."""
    a = load(db, aid)
    if a.status != "submitted" or a.grade_auto is None:
        raise HTTPException(409, "уровень можно менять только у проверенной попытки")
    if body.grade is not None and body.grade not in review.GRADES:
        raise HTTPException(400, "уровень 1..4")
    review.set_manual_grade(db, a, body.grade)
    return public(a, db)


class DraftIn(BaseModel):
    cells: list[dict]
    total_ms: int


@router.put("/attempts/{aid}/draft")
def save_draft(aid: int, body: DraftIn, close: bool = False, db=Depends(get_db)):
    """Автосохранение. close=true — пользователь ушёл со страницы: ядро гасим,
    при возвращении поднимется новое (черновик и таймеры сохранены)."""
    a = active(db, aid)
    a.cells = json.dumps(body.cells, ensure_ascii=False)
    a.total_ms = body.total_ms
    db.commit()
    if close:
        kernels.stop(f"a{aid}")
    return {"ok": True}


class HintIn(BaseModel):
    key: str  # "plan" или номер блока


@router.post("/attempts/{aid}/hint")
def hint(aid: int, body: HintIn, db=Depends(get_db)):
    """Открыть подсказку можно только так — факт использования сохраняется."""
    a = active(db, aid)
    task = json.loads(a.task)
    cells = db.get(RefVersion, a.version_id).cells
    if body.key == "plan":
        code = [c for c in cells if c.kind != "markdown"]
        text = "\n".join(f"{i + 1}. [{c.kind}] {c.title}" + (f" — {c.description}" if c.description else "")
                         for i, c in enumerate(code))
    else:
        i = int(body.key)
        if not 0 <= i < len(cells) or cells[i].kind == "markdown":
            raise HTTPException(400, "подсказка есть только у блоков кода")
        lines = [l for l in cells[i].code.splitlines() if l.strip() and not l.strip().startswith("#")]
        text = "\n".join(lines[:2]) + ("\n…" if len(lines) > 2 else "")
    task["hints"][body.key] = text
    a.task = json.dumps(task, ensure_ascii=False)
    db.commit()
    return public(a, db)


@router.post("/attempts/{aid}/submit")
def submit(aid: int, body: DraftIn, db=Depends(get_db)):
    """Сохраняем ответ, гасим ядро ноутбука и запускаем проверку в фоне."""
    a = active(db, aid)
    a.cells = json.dumps(body.cells, ensure_ascii=False)
    a.total_ms = body.total_ms
    a.status = "checking"
    a.finished_at = datetime.now()
    a.report = json.dumps({"progress": "в очереди"}, ensure_ascii=False)
    db.commit()
    kernels.stop(f"a{aid}")
    checking.start_check(aid)
    return public(a, db)


@router.post("/attempts/{aid}/recheck")
def recheck(aid: int, db=Depends(get_db)):
    """Повторная проверка — например, после запуска Ollama."""
    a = load(db, aid)
    if a.status not in ("submitted",):
        raise HTTPException(409, "проверять можно только сданную попытку")
    a.status = "checking"
    a.report = json.dumps({"progress": "в очереди"}, ensure_ascii=False)
    db.commit()
    checking.start_check(aid)
    return public(a, db)


@router.post("/attempts/{aid}/abandon")
def abandon(aid: int, db=Depends(get_db)):
    a = active(db, aid)
    a.status = "abandoned"
    a.finished_at = datetime.now()
    db.commit()
    kernels.stop(f"a{aid}")
    return {"ok": True}
