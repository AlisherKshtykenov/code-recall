"""«Карта навыков»: импорт combinations.csv, дерево тем по карте, статусы кирпичиков для матрицы.

Импорт и переимпорт: новые строки и кирпичики добавляются, у существующих дополняются строки и категории;
задачи (Task) не создаются и не трогаются, узел кирпичика, который вы перенесли руками, не меняется."""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from . import bricks, skillmap, taskfs
from .db import BrickEvent, MapBrick, MapRow, SessionLocal, Task, Topic, set_setting
from .tasks import topic_path

router = APIRouter(prefix="/api")


def get_db():
    with SessionLocal() as db:
        yield db


def merge(a: list, b: list) -> list:
    return a + [x for x in b if x not in a]


def import_map(db, text: str) -> dict:
    try:
        parsed = skillmap.parse_csv(text)
    except (KeyError, IndexError, ValueError) as e:
        raise HTTPException(400, f"не разобрал CSV: {e}")
    if not parsed["rows"]:
        raise HTTPException(400, "в CSV нет строк (первая строка — заголовок: задача,модели,preprocessing,…)")
    stats = {"rows_new": 0, "rows_updated": 0, "bricks_new": 0, "bricks_updated": 0}
    for cat in skillmap.CATEGORIES:  # узлы категорий — всегда, даже если в CSV их пока нет
        topic_path(db, skillmap.TOPIC_OF[cat])
    projects = topic_path(db, skillmap.PROJECTS_TOPIC)
    titles = {}
    for r in parsed["rows"]:
        titles[r["title"]] = titles.get(r["title"], 0) + 1
    for pos, r in enumerate(parsed["rows"]):
        row = db.get(MapRow, r["key"])
        # одинаковые названия строк («classification» дважды) различаем по первой модели
        first_model = next((it["name"] for it in r["cells"].get("models", [])), "")
        node_name = r["title"] if titles[r["title"]] == 1 else f"{r['title']} · {first_model}"
        if row is None:
            node = db.query(Topic).filter_by(name=node_name, parent_id=projects).first() or Topic(name=node_name, parent_id=projects, position=pos)
            db.add(node)
            db.flush()
            row = MapRow(key=r["key"], title=r["title"], topic_id=node.id)
            db.add(row)
            stats["rows_new"] += 1
        else:
            stats["rows_updated"] += 1
        row.position, row.cells = pos, json.dumps(r["cells"], ensure_ascii=False)
    for name, b in parsed["bricks"].items():
        mb = db.get(MapBrick, name)
        if mb is None:
            mb = MapBrick(name=name, kind=b["kind"], note=skillmap.NOTES.get(name, ""),
                          related=json.dumps(skillmap.RELATED.get(name, []), ensure_ascii=False))
            mb.topic_id = topic_path(db, skillmap.TOPIC_OF[b["categories"][0]])
            db.add(mb)
            stats["bricks_new"] += 1
        else:
            stats["bricks_updated"] += 1
        mb.categories = json.dumps(merge(taskfs.json_list(mb.categories), b["categories"]), ensure_ascii=False)
        mb.rows = json.dumps(merge(taskfs.json_list(mb.rows), b["rows"]), ensure_ascii=False)
        mb.raw = json.dumps(merge(taskfs.json_list(mb.raw), b["raw"]), ensure_ascii=False)
    set_setting(db, "map_imported_at", datetime.now().isoformat(timespec="minutes"))
    db.commit()
    return {**stats, "rows": len(parsed["rows"]), "bricks": len(parsed["bricks"])}


@router.post("/map/import")
async def map_import(file: UploadFile, db=Depends(get_db)):
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "CSV должен быть в UTF-8")
    return import_map(db, text)


@router.post("/map/preview")
async def map_preview(file: UploadFile, db=Depends(get_db)):
    """Ничего не сохраняет: сколько строк и кирпичиков добавится."""
    try:
        parsed = skillmap.parse_csv((await file.read()).decode("utf-8-sig"))
    except (UnicodeDecodeError, KeyError, IndexError, ValueError) as e:
        raise HTTPException(400, f"не разобрал CSV: {e}")
    have_rows = {r.key for r in db.query(MapRow).all()}
    have_bricks = {b.name for b in db.query(MapBrick).all()}
    return {"rows": len(parsed["rows"]), "rows_new": [r["title"] for r in parsed["rows"] if r["key"] not in have_rows],
            "bricks": len(parsed["bricks"]), "bricks_new": sorted(set(parsed["bricks"]) - have_bricks)}


def brick_status(db, t: Task | None, kind: str) -> str:
    """planned — задачи нет; concept — только README; new / learned / due / weak — по повторениям."""
    if t is None:
        return "planned"
    if kind == "concept":
        return "concept"
    if t.broken:
        return "weak"
    last_ev = db.query(BrickEvent).filter_by(task_id=t.id).order_by(BrickEvent.at.desc()).first()
    done = sorted((a for a in t.attempts if a.status in ("submitted", "abandoned") and a.grade is not None), key=lambda a: a.finished_at)
    last_grade, last_at = (done[-1].grade, done[-1].finished_at) if done else (None, None)
    if last_ev and (last_at is None or last_ev.at > last_at):
        last_grade = last_ev.grade
    if last_grade is None:
        return "new"
    if last_grade <= 2:
        return "weak"
    if t.due_at and t.due_at.date() <= datetime.now().date():
        return "due"
    return "learned"


def planned_list(db) -> list[dict]:
    """Кирпичики карты без задачи — для библиотеки (серые строки «запланировано»)."""
    names = {t.name for t in db.query(Task.name).all()}
    return [{"name": b.name, "kind": b.kind, "topic_id": b.topic_id, "categories": taskfs.json_list(b.categories),
             "rows": taskfs.json_list(b.rows), "note": b.note} for b in db.query(MapBrick).order_by(MapBrick.name) if b.name not in names]


@router.get("/map")
def get_map(db=Depends(get_db)):
    rows = db.query(MapRow).order_by(MapRow.position).all()
    tasks = {t.name: t for t in db.query(Task).all()}
    out_bricks = {}
    for b in db.query(MapBrick).all():
        t = tasks.get(b.name)
        out_bricks[b.name] = {"name": b.name, "kind": b.kind, "categories": taskfs.json_list(b.categories),
                              "rows": taskfs.json_list(b.rows), "reuse": len(taskfs.json_list(b.rows)), "note": b.note,
                              "related": taskfs.json_list(b.related), "topic_id": b.topic_id,
                              "task_id": t.id if t else None, "title": t.title if t else b.name,
                              "status": brick_status(db, t, b.kind)}
    countable = [b for b in out_bricks.values() if b["kind"] != "concept"]
    cov = {"total": len(countable), "created": sum(b["task_id"] is not None for b in countable),
           "learned": sum(b["status"] == "learned" for b in countable), "concepts": len(out_bricks) - len(countable)}
    return {"categories": [{"key": c, "title": skillmap.CATEGORY_TITLE[c], "slot": skillmap.SLOT_OF.get(c)} for c in skillmap.CATEGORIES],
            "rows": [{"key": r.key, "title": r.title, "topic_id": r.topic_id, "cells": taskfs.json_dict(r.cells)} for r in rows],
            "bricks": out_bricks, "coverage": cov}


@router.get("/map/planned")
def map_planned(db=Depends(get_db)):
    return planned_list(db)


def map_rows_of(db, name: str) -> list[dict]:
    """Строки карты, где используется кирпичик, — для README («в каких строках карты»)."""
    b = db.get(MapBrick, name)
    keys = taskfs.json_list(b.rows) if b else []
    return [{"key": r.key, "title": r.title} for r in db.query(MapRow).filter(MapRow.key.in_(keys)).order_by(MapRow.position)] if keys else []


@router.get("/map/brick/{name}")
def map_brick(name: str, db=Depends(get_db)):
    b = db.get(MapBrick, name)
    if b is None:
        raise HTTPException(404, "такого кирпичика на карте нет")
    t = bricks.find_task(db, name)
    return {"name": b.name, "kind": b.kind, "categories": taskfs.json_list(b.categories), "note": b.note,
            "rows": map_rows_of(db, name), "related": taskfs.json_list(b.related), "topic_id": b.topic_id,
            "task_id": t.id if t else None}
