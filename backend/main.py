"""FastAPI-приложение CODE RECALL: библиотека эталонов, тесты, настройки."""
import difflib
import json
import shutil
import hashlib
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import backup, cache, checking, kernels, llm, notebook, parsing, review, stats, workspace
from .db import (Attempt, RefCell, Reference, RefVersion, SessionLocal, Test,
                 get_setting, init_db, set_setting)

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
init_db()


@asynccontextmanager
async def lifespan(app):
    # проверки, прерванные перезапуском сервера, запускаем заново
    with SessionLocal() as db:
        for a in db.query(Attempt).filter_by(status="checking"):
            checking.start_check(a.id)
    backup.start_daily_thread()
    kernels.start_reaper()
    with SessionLocal() as db:
        upgrade_notebooks(db)
    yield
    kernels.stop_all()


app = FastAPI(title="CODE RECALL", lifespan=lifespan)


def get_db():
    with SessionLocal() as db:
        yield db


def or_404(obj):
    if obj is None:
        raise HTTPException(404, "не найдено")
    return obj


# ---------- сериализация ----------

def cell_out(c: RefCell) -> dict:
    return {"id": c.id, "position": c.position, "kind": c.kind, "title": c.title,
            "code": c.code, "description": c.description}


def test_out(t: Test, titles: set) -> dict:
    return {"id": t.id, "block": t.block, "name": t.name, "code": t.code, "mode": t.mode,
            "approved": bool(t.approved), "broken": t.broken or "",
            "orphan": bool(t.block) and t.block not in titles}


def ref_short(r: Reference) -> dict:
    v = r.current
    titles = {c.title for c in v.cells} if v else set()
    done = [a for a in r.attempts if a.status == "submitted"]
    scores = [a.score for a in done if a.score is not None]
    return {"id": r.id, "title": r.title, "filename": r.filename, "tag": r.tag,
            "difficulty": r.difficulty, "notes": r.notes, "task": r.task,
            "version": v.number if v else 0,
            "blocks": sum(1 for c in v.cells if c.kind != "markdown") if v else 0,
            "python": r.python or "",
            "tests": len(r.tests),
            "orphan_tests": sum(1 for t in r.tests if t.block and t.block not in titles),
            "last_attempt": iso(max((a.finished_at for a in done), default=None)),
            "attempts": len(done),
            "best_score": max(scores, default=None),
            "best_time_ms": min((a.total_ms for a in done), default=None),
            "due_at": iso(r.due_at),
            "updated_at": iso(r.updated_at)}


def iso(dt):
    return dt.isoformat(timespec="minutes") if dt else None


# ---------- загрузка и версии ----------

def title_from_filename(name: str) -> str:
    """'cnn/simple_cnn.py' -> 'cnn / simple cnn'."""
    path = Path(name).with_suffix("").as_posix()
    return " / ".join(p.replace("_", " ").replace("-", " ").strip() for p in path.split("/"))


def file_text(name: str, raw: str) -> str:
    """Текст для diff: у .ipynb сравниваем код ячеек, а не JSON с метаданными."""
    if name.endswith(".ipynb"):
        return "\n\n".join(f"# --- [{c['title']}]\n{c['code']}" for c in parsing.parse_file(name, raw))
    return raw


def unified(a: str, b: str, a_name="было", b_name="стало") -> str:
    return "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True),
                                        a_name, b_name, n=2))


def compare_blocks(old_cells, new_cells, tests) -> dict:
    """Что станет с блоками и тестами после загрузки новой версии.
    Код сравнивается без комментариев и пробелов — так же, как при переносе прогресса."""
    old = {c.title: review.normalize(c.code) for c in old_cells}
    new = {c["title"]: review.normalize(c["code"]) for c in new_cells}
    return {
        "added": [t for t in new if t not in old],
        "removed": [t for t in old if t not in new],
        "changed": [t for t in new if t in old and old[t] != new[t]],
        "same": [t for t in new if t in old and old[t] == new[t]],
        "progress_reset": [t for t in new if t not in old or old[t] != new[t]],
        "orphaned_tests": [t.name or f"тест #{t.id}" for t in tests
                           if t.block and t.block in old and t.block not in new],
    }


async def read_uploads(files, paths=None):
    """paths — относительные пути при загрузке папки (имя эталона = путь внутри папки)."""
    for i, f in enumerate(files):
        name = (paths[i] if paths and i < len(paths) and paths[i] else f.filename) or "file.py"
        raw = (await f.read()).decode("utf-8", errors="replace")
        yield name, raw, hashlib.sha256(raw.encode()).hexdigest()


@app.post("/api/upload/preview")
async def upload_preview(files: list[UploadFile], paths: list[str] | None = Form(None),
                         db=Depends(get_db)):
    """Ничего не сохраняет: показывает, что будет создано / какой diff у новой версии."""
    res = []
    async for name, raw, h in read_uploads(files, paths):
        item = {"filename": name}
        if not name.endswith((".py", ".ipynb")):
            res.append({**item, "status": "skipped", "error": "только .py / .ipynb"})
            continue
        try:
            new_cells = parsing.parse_file(name, raw)
        except Exception as e:
            res.append({**item, "status": "error", "error": f"не разобрать: {e}"})
            continue
        ref = db.query(Reference).filter_by(filename=name).first()
        if ref is None:
            res.append({**item, "status": "new", "blocks": len(new_cells)})
        elif ref.current.content_hash == h:
            res.append({**item, "status": "unchanged", "id": ref.id, "version": ref.current.number})
        else:
            cur = ref.current
            res.append({**item, "status": "changed", "id": ref.id, "title": ref.title,
                        "version": cur.number,
                        "diff": unified(file_text(name, cur.source), file_text(name, raw),
                                        f"v{cur.number}", f"v{cur.number + 1}"),
                        "blocks": compare_blocks(cur.cells, new_cells, ref.tests)})
    return res


def add_version(db, ref: Reference, raw: str, h: str) -> RefVersion:
    prev = ref.current
    v = RefVersion(reference=ref, number=(prev.number + 1) if prev else 1,
                   source=raw, content_hash=h)
    old = {c.title: c for c in prev.cells} if prev else {}
    for i, c in enumerate(parsing.parse_file(ref.filename, raw)):
        # Описание переносим из прошлой версии, если блок с тем же названием.
        # Тесты привязаны к названию блока и переносятся сами.
        if c["title"] in old and not c["description"]:
            c["description"] = old[c["title"]].description
        v.cells.append(RefCell(position=i, **c))
    db.add(v)
    return v


@app.post("/api/upload")
async def upload(files: list[UploadFile], paths: list[str] | None = Form(None),
                 db=Depends(get_db)):
    """Сохраняет присланные файлы: новый эталон или новую версию существующего."""
    results = []
    async for name, raw, h in read_uploads(files, paths):
        if not name.endswith((".py", ".ipynb")):
            continue
        ref = db.query(Reference).filter_by(filename=name).first()
        try:
            if ref is None:
                ref = Reference(title=title_from_filename(name), filename=name)
                db.add(ref)
                add_version(db, ref, raw, h)
                status = "created"
            elif ref.current.content_hash == h:
                status = "unchanged"
            else:
                add_version(db, ref, raw, h)
                ref.updated_at = datetime.now()
                status = "new_version"
            db.commit()
        except Exception as e:
            db.rollback()
            results.append({"filename": name, "status": "error", "error": str(e)})
            continue
        if status == "new_version":
            review.replay(db, ref)  # изменённые блоки начинают прогресс заново
            db.commit()
        results.append({"filename": name, "status": status, "id": ref.id,
                        "version": ref.current.number})
    return results


# ---------- эталоны ----------

@app.get("/api/references")
def list_references(db=Depends(get_db)):
    return [ref_short(r) for r in db.query(Reference).all()]


@app.get("/api/references/{rid}")
def get_reference(rid: int, version: int | None = None, db=Depends(get_db)):
    r = or_404(db.get(Reference, rid))
    v = next((x for x in r.versions if x.number == version), r.current)
    titles = {c.title for c in r.current.cells}
    return {**ref_short(r),
            "versions": [{"id": x.id, "number": x.number, "created_at": iso(x.created_at),
                          "blocks": len(x.cells)} for x in r.versions],
            "shown_version": {"id": v.id, "number": v.number, "source": v.source,
                              "cells": [cell_out(c) for c in v.cells]},
            "test_list": [test_out(t, titles) for t in r.tests],
            "block_states": json.loads(r.block_states or "{}"),
            "heavy": json.loads(r.heavy or "[]"),
            "block_times": json.loads(r.block_times or "{}"),
            "caches": block_caches(r, v),
            "kernel": kernels.state(f"r{r.id}")}


def block_caches(r: Reference, v) -> dict:
    """Состояние кэша тяжёлых блоков: {название: {...}}."""
    heavy = set(json.loads(r.heavy or "[]"))
    try:
        py = workspace.resolve_python(r.python or "")
    except ValueError:
        return {}
    return {c.title: cache.status(r.id, v.cells, i, py)
            for i, c in enumerate(v.cells) if c.title in heavy and c.kind != "markdown"}


class HeavyIn(BaseModel):
    title: str
    heavy: bool


@app.post("/api/references/{rid}/heavy")
def set_heavy(rid: int, body: HeavyIn, db=Depends(get_db)):
    """Пометка «тяжёлый блок»: при «повторить блок» не выполняется заново, а берётся из кэша."""
    r = or_404(db.get(Reference, rid))
    heavy = set(json.loads(r.heavy or "[]"))
    (heavy.add if body.heavy else heavy.discard)(body.title)
    r.heavy = json.dumps(sorted(heavy), ensure_ascii=False)
    db.commit()
    return {"heavy": sorted(heavy), "caches": block_caches(r, r.current)}


@app.delete("/api/references/{rid}/cache/{index}")
def drop_cache(rid: int, index: int, db=Depends(get_db)):
    r = or_404(db.get(Reference, rid))
    cells = r.current.cells
    if not 0 <= index < len(cells):
        raise HTTPException(404, "нет такого блока")
    cache.drop(rid, index, cells[index].title)
    return {"caches": block_caches(r, r.current)}


@app.get("/api/references/{rid}/diff")
def version_diff(rid: int, a: int, b: int, db=Depends(get_db)):
    r = or_404(db.get(Reference, rid))
    va = or_404(next((x for x in r.versions if x.number == a), None))
    vb = or_404(next((x for x in r.versions if x.number == b), None))
    return {"diff": unified(file_text(r.filename, va.source), file_text(r.filename, vb.source),
                            f"v{a}", f"v{b}")}


class RefMeta(BaseModel):
    title: str | None = None
    tag: str | None = None
    difficulty: int | None = None
    notes: str | None = None
    task: str | None = None
    python: str | None = None  # окружение для ядра; "" — окружение приложения


@app.patch("/api/references/{rid}")
def update_reference(rid: int, meta: RefMeta, db=Depends(get_db)):
    r = or_404(db.get(Reference, rid))
    data = meta.model_dump(exclude_none=True)
    if data.get("python"):
        try:
            info = workspace.check_python(data["python"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        if not info["ipykernel"]:
            raise HTTPException(400, f"в этом окружении нет ipykernel — установите: {info['fix']}")
    for k, val in data.items():
        setattr(r, k, val)
    db.commit()
    if "python" in data:
        kernels.stop(f"r{rid}")  # ядро эталона перезапустится уже в новом окружении
    return ref_short(r)


@app.delete("/api/references/{rid}")
def delete_reference(rid: int, db=Depends(get_db)):
    db.delete(or_404(db.get(Reference, rid)))
    db.commit()
    kernels.stop(f"r{rid}")
    # папку эталона удаляем; привязанная data/ — ссылка, rmtree её не раскрывает и чужие файлы не трогает
    shutil.rmtree(workspace.ROOT / f"ref-{rid}", ignore_errors=True)
    return {"ok": True}


class CellIn(BaseModel):
    id: int | None = None  # id блока до правки — чтобы отследить переименование
    kind: str = "code"
    title: str = ""
    code: str = ""
    description: str = ""


@app.put("/api/references/{rid}/cells")
def save_cells(rid: int, cells: list[CellIn], db=Depends(get_db)):
    """Ручная правка разбиения текущей версии: присылается весь список блоков."""
    r = or_404(db.get(Reference, rid))
    v = r.current
    old_titles = {c.id: c.title for c in v.cells}
    data = parsing.unique_titles([c.model_dump(exclude={"id"}) for c in cells])
    # Переименованный блок: тесты едут за ним.
    renames = {old_titles[c.id]: d["title"] for c, d in zip(cells, data)
               if c.id in old_titles and old_titles[c.id] != d["title"]}
    for t in r.tests:
        if t.block in renames:
            t.block = renames[t.block]
    v.cells.clear()
    db.flush()
    for i, d in enumerate(data):
        v.cells.append(RefCell(position=i, **d))
    db.flush()
    review.replay(db, r)
    db.commit()
    sync_tests(r)
    return get_reference(rid, db=db)


class ResplitIn(BaseModel):
    mode: str = "ast"  # ast | llm


@app.post("/api/references/{rid}/resplit")
def resplit(rid: int, body: ResplitIn, db=Depends(get_db)):
    """Предлагает новое разбиение текущей версии (не сохраняет)."""
    r = or_404(db.get(Reference, rid))
    src = r.current.source
    if body.mode == "llm":
        if r.filename.endswith(".ipynb"):
            raise HTTPException(400, "LLM-разбиение только для .py")
        try:
            cells = parsing.cells_from_line_ranges(src, llm.suggest_split(src))
        except llm.LLMError as e:
            raise HTTPException(502, str(e))
        cells = parsing.unique_titles(cells)
    else:
        cells = parsing.parse_file(r.filename, src)
    old = {c.title: c.description for c in r.current.cells}
    for c in cells:
        c["description"] = c["description"] or old.get(c["title"], "")
    return cells


@app.post("/api/references/{rid}/describe")
def describe(rid: int, overwrite: bool = False, db=Depends(get_db)):
    """LLM пишет словесные описания блоков и задачи целиком (без кода)."""
    r = or_404(db.get(Reference, rid))
    cells = [c for c in r.current.cells if c.kind != "markdown"]
    try:
        data = llm.describe_blocks(r.title, [(c.title, c.code) for c in cells])
    except llm.LLMError as e:
        raise HTTPException(502, str(e))
    descs = data.get("blocks", [])
    for c, d in zip(cells, descs):
        if overwrite or not c.description:
            c.description = str(d).strip()
    if overwrite or not r.task:
        r.task = str(data.get("task", "")).strip()
    db.commit()
    return get_reference(rid, db=db)


# ---------- тесты ----------

class TestIn(BaseModel):
    block: str | None = None
    name: str | None = None
    code: str | None = None
    mode: str | None = None
    approved: bool | None = None


@app.post("/api/references/{rid}/tests")
def add_test(rid: int, body: TestIn, db=Depends(get_db)):
    r = or_404(db.get(Reference, rid))
    t = Test(reference=r, **{k: v for k, v in body.model_dump().items() if v is not None})
    db.add(t)
    db.commit()
    sync_tests(r)
    return test_out(t, {c.title for c in r.current.cells})


@app.patch("/api/tests/{tid}")
def update_test(tid: int, body: TestIn, db=Depends(get_db)):
    """В том числе ручная привязка теста «без блока» к новому блоку (поле block)."""
    t = or_404(db.get(Test, tid))
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(t, k, int(v) if k == "approved" else v)
    if body.code is not None:
        t.broken = ""  # тест поправили — пусть проверится заново
    db.commit()
    sync_tests(t.reference)
    return test_out(t, {c.title for c in t.reference.current.cells})


@app.post("/api/references/{rid}/tests/run")
def run_tests_on_reference(rid: int, db=Depends(get_db)):
    """Прогнать тесты на эталоне: значения + отметка сломанных."""
    r = or_404(db.get(Reference, rid))
    res = checking.run_reference_tests(r)
    for item in res:
        db.get(Test, item["id"]).broken = item["broken"]
    db.commit()
    sync_tests(r)
    return res


@app.post("/api/references/{rid}/tests/suggest")
def suggest_tests(rid: int, db=Depends(get_db)):
    """LLM предлагает тесты; они сохраняются неподтверждёнными и не участвуют в проверке."""
    r = or_404(db.get(Reference, rid))
    code = [c for c in r.current.cells if c.kind != "markdown"]
    titles = [c.title for c in code]
    try:
        items = llm.suggest_tests(r.title, [(c.title, c.code) for c in code])
    except llm.LLMError as e:
        raise HTTPException(502, str(e))
    for it in items:
        if not isinstance(it, dict) or not isinstance(it.get("code"), str) or not it["code"].strip():
            continue
        block = it.get("block") if it.get("block") in titles else ""
        mode = it.get("mode") if it.get("mode") in ("match", "assert") else "match"
        db.add(Test(reference=r, block=block, name=str(it.get("name", ""))[:200],
                    code=it["code"], mode=mode, approved=0))
    db.commit()
    sync_tests(r)
    return get_reference(rid, db=db)


@app.delete("/api/tests/{tid}")
def delete_test(tid: int, db=Depends(get_db)):
    t = or_404(db.get(Test, tid))
    ref = t.reference
    db.delete(t)
    db.commit()
    sync_tests(ref)
    return {"ok": True}


def sync_tests(ref: Reference):
    """Зеркало тестов в tests/ папки эталона: файл на блок."""
    try:
        workspace.write_tests(ref.id, [c.title for c in ref.current.cells if c.kind != "markdown"], ref.tests)
    except OSError as e:
        print("не записал tests/:", e)


# ---------- папка эталона ----------

@app.get("/api/references/{rid}/workspace")
def workspace_info(rid: int, db=Depends(get_db)):
    r = or_404(db.get(Reference, rid))
    sync_tests(r)
    return {"path": str(workspace.ws(rid)), "data_link": workspace.data_link(rid),
            "python": r.python or "", "python_resolved": _python_or_error(r.python or ""),
            "kernel": kernels.state(f"r{rid}")}


def _python_or_error(path: str) -> str:
    try:
        return workspace.resolve_python(path)
    except ValueError as e:
        return f"ошибка: {e}"


class PathIn(BaseModel):
    path: str = ""


@app.post("/api/python/check")
def python_check(body: PathIn):
    try:
        return workspace.check_python(body.path)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/references/{rid}/files")
def files_list(rid: int, path: str = "", db=Depends(get_db)):
    or_404(db.get(Reference, rid))
    try:
        return workspace.listing(rid, path)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/references/{rid}/raw/{path:path}")
def files_raw(rid: int, path: str, download: bool = False):
    try:
        p = workspace.safe_path(rid, path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not p.is_file():
        raise HTTPException(404, "файла нет")
    # FileResponse отдаёт Range-запросы — видео перематывается
    return FileResponse(p, filename=p.name if download else None,
                        content_disposition_type="attachment" if download else "inline")


@app.post("/api/references/{rid}/files")
async def files_upload(rid: int, files: list[UploadFile], folder: str = Form("data"), db=Depends(get_db)):
    or_404(db.get(Reference, rid))
    saved = []
    for f in files:
        try:
            saved.append(workspace.save_upload(rid, folder, f.filename or "file", await f.read()))
        except (ValueError, OSError) as e:
            raise HTTPException(400, str(e))
    return {"saved": saved}


@app.delete("/api/references/{rid}/files")
def files_delete(rid: int, path: str, db=Depends(get_db)):
    or_404(db.get(Reference, rid))
    try:
        workspace.delete(rid, path)
    except (ValueError, OSError) as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/references/{rid}/data/bind")
def data_bind(rid: int, body: PathIn, db=Depends(get_db)):
    or_404(db.get(Reference, rid))
    try:
        workspace.bind_data(rid, body.path)
    except (ValueError, OSError) as e:
        raise HTTPException(400, str(e))
    return {"data_link": workspace.data_link(rid)}


@app.post("/api/references/{rid}/data/unbind")
def data_unbind(rid: int, db=Depends(get_db)):
    or_404(db.get(Reference, rid))
    workspace.unbind_data(rid)
    return {"data_link": None}


def upgrade_notebooks(db):
    """Разовый переход: .ipynb, разобранные до появления markdown-ячеек, получают их.
    Только если ячейки не правились вручную (совпадают со старым разбором) и по версии нет попыток —
    иначе сдвинулись бы номера блоков в старых попытках. Описания и тесты сохраняются."""
    for r in db.query(Reference).all():
        v = r.current
        if not v or not r.filename.endswith(".ipynb") or any(c.kind == "markdown" for c in v.cells):
            continue
        if any(a.version_id == v.id for a in r.attempts):
            continue
        try:
            new = parsing.parse_file(r.filename, v.source)
        except Exception:
            continue
        if not any(c["kind"] == "markdown" for c in new):
            continue
        old_sig = [(c.kind, c.title, c.code.strip()) for c in v.cells]
        new_sig = [(c["kind"], c["title"], c["code"].strip()) for c in new if c["kind"] != "markdown"]
        if old_sig != new_sig:
            continue  # разбиение правили руками — не трогаем, можно нажать «заново по AST»
        desc = {c.title: c.description for c in v.cells}
        v.cells.clear()
        db.flush()
        for i, c in enumerate(new):
            if c["kind"] != "markdown" and desc.get(c["title"]):
                c["description"] = desc[c["title"]]
            v.cells.append(RefCell(position=i, **c))
        db.flush()
        review.replay(db, r)
        print(f"markdown-ячейки добавлены: {r.filename}")
    db.commit()


# ---------- сегодня ----------

@app.get("/api/today")
def today(db=Depends(get_db)):
    return review.today_lists(db)


@app.get("/api/stats")
def get_stats(db=Depends(get_db)):
    return stats.overview(db)


# ---------- бэкап ----------

@app.get("/api/backup/export")
def export_backup():
    data = backup.export_zip()
    name = f"code-recall-{datetime.now():%Y-%m-%d}.zip"
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.post("/api/backup/import")
async def import_backup(file: UploadFile):
    kernels.stop_all()  # открытые попытки относятся к старой базе
    try:
        res = backup.import_zip(await file.read())
    except ValueError as e:
        raise HTTPException(400, str(e))
    init_db()  # архив из более старой версии приложения — добавим новые колонки
    return res


@app.get("/api/backup/list")
def list_backups():
    return backup.list_backups()


@app.post("/api/backup/now")
def backup_now():
    """Сделать сегодняшнюю автокопию сразу (если её ещё нет)."""
    made = backup.daily_backup()
    return {"made": made.name if made else None, "backups": backup.list_backups()}


# ---------- настройки ----------

@app.get("/api/settings")
def get_settings(db=Depends(get_db)):
    s = {k: get_setting(db, k, d) for k, d in llm.DEFAULTS.items()}
    s["cell_timeout"] = get_setting(db, "cell_timeout", "60")
    s.update({k: int(v) if float(v).is_integer() else v for k, v in checking.score_settings(db).items()})
    s["groq_key_set"] = bool(os.getenv("GROQ_API_KEY"))
    return s


@app.put("/api/settings")
def put_settings(body: dict, db=Depends(get_db)):
    for k in [*llm.DEFAULTS, "cell_timeout", *checking.SCORE_DEFAULTS]:
        if k in body:
            set_setting(db, k, str(body[k]))
    db.commit()
    return get_settings(db)


@app.post("/api/settings/test")
def test_llm():
    try:
        return {"ok": True, **llm.ping()}
    except llm.LLMError as e:
        return {"ok": False, "answer": str(e)}


from . import attempts  # noqa: E402  (эндпоинты заданий / ноутбука)

app.include_router(attempts.router)
app.include_router(notebook.router)
app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
