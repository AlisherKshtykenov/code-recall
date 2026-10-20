"""Файловое API для дерева в IDE — одно для папки задачи и для папки попытки.
make_router(prefix, resolve) -> APIRouter, где resolve(id, db) -> (base_dir, hooks)."""
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import taskfs
from .db import SessionLocal

TEXT_LIMIT = 1_000_000


def get_db():
    with SessionLocal() as db:
        yield db


class FileIn(BaseModel):
    path: str
    content: str = ""


class NewIn(BaseModel):
    path: str
    dir: bool = False


class RenameIn(BaseModel):
    path: str
    new_path: str


def make_router(prefix: str, resolve) -> APIRouter:
    """resolve(id, db, write: bool) -> (base: Path, on_change(db, rel) | None)."""
    r = APIRouter(prefix=prefix)

    def ctx(id_, db, write=False):
        try:
            return resolve(id_, db, write)
        except ValueError as e:
            raise HTTPException(400, str(e))

    def guard(fn):
        try:
            return fn()
        except (ValueError, OSError) as e:
            raise HTTPException(400, str(e))

    @r.get("/{id_}/files")
    def tree(id_: int, path: str = "", db=Depends(get_db)):
        base, _ = ctx(id_, db)
        return guard(lambda: taskfs.listing(base, path))

    @r.get("/{id_}/file")
    def read(id_: int, path: str, db=Depends(get_db)):
        base, _ = ctx(id_, db)
        p = guard(lambda: taskfs.safe(base, path))
        if not p.is_file():
            raise HTTPException(404, "файла нет")
        if p.stat().st_size > TEXT_LIMIT:
            raise HTTPException(413, "файл слишком большой для редактора — скачайте его")
        try:
            return {"path": path, "content": p.read_text(encoding="utf-8")}
        except UnicodeDecodeError:
            raise HTTPException(415, "это не текстовый файл")

    @r.put("/{id_}/file")
    def write(id_: int, body: FileIn, db=Depends(get_db)):
        base, on_change = ctx(id_, db, True)
        p = guard(lambda: taskfs.safe(base, body.path))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body.content, encoding="utf-8")
        if on_change:
            on_change(db, body.path)
        return {"ok": True}

    @r.post("/{id_}/new")
    def create(id_: int, body: NewIn, db=Depends(get_db)):
        base, on_change = ctx(id_, db, True)
        p = guard(lambda: taskfs.safe(base, body.path))
        if p.exists():
            raise HTTPException(409, "уже есть")
        if body.dir:
            p.mkdir(parents=True)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("", encoding="utf-8")
            if on_change:
                on_change(db, body.path)
        return {"ok": True}

    @r.post("/{id_}/rename")
    def ren(id_: int, body: RenameIn, db=Depends(get_db)):
        base, on_change = ctx(id_, db, True)
        new = guard(lambda: taskfs.rename(base, body.path, body.new_path))
        if on_change:
            on_change(db, body.path)
            on_change(db, new)
        return {"path": new}

    @r.delete("/{id_}/files")
    def remove(id_: int, path: str, db=Depends(get_db)):
        base, on_change = ctx(id_, db, True)
        guard(lambda: taskfs.delete(base, path))
        if on_change:
            on_change(db, path)
        return {"ok": True}

    @r.post("/{id_}/upload")
    async def upload(id_: int, files: list[UploadFile], folder: str = Form(""), db=Depends(get_db)):
        base, on_change = ctx(id_, db, True)
        saved = []
        for f in files:
            name = Path(f.filename or "file").name
            p = guard(lambda: taskfs.safe(base, f"{folder.strip('/')}/{name}" if folder.strip("/") else name))
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "wb") as out:
                while chunk := await f.read(1 << 20):
                    out.write(chunk)
            rel = str(p.relative_to(base))
            saved.append(rel)
            if on_change:
                on_change(db, rel)
        return {"saved": saved}

    @r.get("/{id_}/raw/{path:path}")
    def raw(id_: int, path: str, download: bool = False, db=Depends(get_db)):
        base, _ = ctx(id_, db)
        p = guard(lambda: taskfs.safe(base, path))
        if not p.is_file():
            raise HTTPException(404, "файла нет")
        mt = mimetypes.guess_type(p.name)[0]
        return FileResponse(p, media_type=mt, filename=p.name if download else None,
                            content_disposition_type="attachment" if download else "inline")

    @r.get("/{id_}/table")
    def table(id_: int, path: str, db=Depends(get_db)):
        base, _ = ctx(id_, db)
        p = guard(lambda: taskfs.safe(base, path))
        if not p.is_file():
            raise HTTPException(404, "файла нет")
        try:
            return taskfs.table_preview(p)
        except ImportError as e:
            raise HTTPException(400, f"для превью нужен пакет: {e.name}")
        except Exception as e:
            raise HTTPException(400, f"не прочитать таблицу: {e}")

    return r
