"""Выполнение ячеек — одно API для эталона (ключ ядра "r<id>") и попытки ("a<id>").
Вывод идёт по мере выполнения: POST execute -> job, затем GET job опрашивается.

Если выполняется код блока ЭТАЛОНА (передан block и код совпадает с эталоном), запоминаем время
запуска, а у тяжёлого блока сохраняем кэш переменных (см. cache.py)."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import cache, kernels, workspace
from .attempts import kernel_args
from .db import Attempt, Reference, RefVersion, SessionLocal, get_setting
from .review import normalize

router = APIRouter(prefix="/api/kernels")


def get_db():
    with SessionLocal() as db:
        yield db


def resolve(key: str, db) -> dict:
    """Ключ -> python, рабочая папка, эталон и версия; заодно проверяем, что ядро можно запускать."""
    try:
        kind, num = key[0], int(key[1:])
    except (IndexError, ValueError):
        raise HTTPException(400, "плохой ключ ядра")
    try:
        if kind == "a":
            a = db.get(Attempt, num)
            if a is None or a.status != "active":
                raise HTTPException(409, "попытка завершена — ячейки больше не выполняются")
            return {**kernel_args(a), "ref": a.reference, "version": db.get(RefVersion, a.version_id)}
        if kind == "r":
            r = db.get(Reference, num)
            if r is None:
                raise HTTPException(404, "эталон не найден")
            return {"python": workspace.resolve_python(r.python or ""), "cwd": str(workspace.ws(r.id)),
                    "ref": r, "version": r.current}
    except ValueError as e:  # окружение эталона не найдено
        raise HTTPException(400, str(e))
    raise HTTPException(400, "плохой ключ ядра")


def find_block(version, title: str):
    for i, c in enumerate(version.cells):
        if c.title == title and c.kind != "markdown":
            return i, c
    return None, None


def make_post(ref_id: int, version_id: int, index: int, title: str, code: str, heavy: bool, python: str):
    """После ячейки эталона: время запуска; у тяжёлого блока — снимок переменных в кэш."""
    def post(k, res):
        with SessionLocal() as db:
            r = db.get(Reference, ref_id)
            times = json.loads(r.block_times or "{}")
            times[title] = res["elapsed_ms"]
            r.block_times = json.dumps(times, ensure_ascii=False)
            db.commit()
            cells = db.get(RefVersion, version_id).cells
            h = cache.prefix_hash(cells, index, python)
        if not heavy or res["status"] != "ok":
            return []
        path = cache.cache_path(ref_id, index, title)
        snap = k.execute(cache.snapshot_code(path, cache.names_in(code)), timeout=900, history=False)
        err = kernels.first_error(snap)
        if err:
            return [{"type": "stream", "name": "stderr", "text": f"кэш не сохранён: {err}\n"}]
        line = next((l for l in kernels.stream_text(snap).splitlines() if l.startswith(cache.MARK)), None)
        if not line:
            return [{"type": "stream", "name": "stderr", "text": "кэш не сохранён: нет ответа от ядра\n"}]
        info = json.loads(line[len(cache.MARK):])
        cache.save_meta(ref_id, index, title, info, h, res["elapsed_ms"])
        mb = info["bytes"] / 1048576
        text = (f"💾 кэш блока сохранён ({info['engine']}, {mb:.1f} МБ, {info['save_ms'] / 1000:.1f} с): "
                + ", ".join(info["names"]) + "\n")
        if info["skipped"]:
            text += "не сохранились (не сериализуются): " + ", ".join(info["skipped"]) + "\n"
        return [{"type": "stream", "name": "stdout", "text": text}]
    return post


class ExecIn(BaseModel):
    code: str = ""
    block: str | None = None  # название блока эталона, если выполняется его код
    cache_load: bool = False  # вместо кода — загрузить кэш блока


@router.post("/{key}/execute")
def execute(key: str, body: ExecIn, db=Depends(get_db)):
    ctx = resolve(key, db)
    ref, version = ctx["ref"], ctx["version"]
    timeout = float(get_setting(db, "cell_timeout", "60"))
    args = {"python": ctx["python"], "cwd": ctx["cwd"]}
    if body.cache_load:
        i, c = find_block(version, body.block or "")
        st = cache.status(ref.id, version.cells, i, ctx["python"]) if c else {"valid": False}
        if not st.get("valid"):
            raise HTTPException(409, "нет действительного кэша — выполните блок в эталоне")
        code = cache.restore_code(cache.cache_path(ref.id, i, c.title), st.get("engine", "pickle"))
        return {"job": kernels.submit(key, code, max(timeout, 600), **args)}
    post = None
    if body.block:
        i, c = find_block(version, body.block)
        if c and normalize(c.code) == normalize(body.code):  # учитываем только код эталона
            heavy = c.title in json.loads(ref.heavy or "[]")
            post = make_post(ref.id, version.id, i, c.title, c.code, heavy, ctx["python"])
            if heavy:
                timeout = max(timeout, 24 * 3600)  # обучение не обрываем по таймауту ячейки
    return {"job": kernels.submit(key, body.code, timeout, post=post, **args)}


@router.get("/{key}/jobs/{job}")
def poll(key: str, job: str, have: int = 0, rev: int = 0):
    return kernels.poll(job, have, rev)


@router.post("/{key}/start")
def start(key: str, db=Depends(get_db)):
    ctx = resolve(key, db)
    kernels.start(key, python=ctx["python"], cwd=ctx["cwd"])
    return {"kernel": kernels.state(key)}


@router.get("/{key}/state")
def state(key: str):
    return {"kernel": kernels.state(key), "idle_left": kernels.idle_left(key)}


@router.post("/{key}/interrupt")
def interrupt(key: str):
    kernels.interrupt(key)
    return {"ok": True}


@router.post("/{key}/restart")
def restart(key: str, db=Depends(get_db)):
    """Перезапуск = новое ядро: надёжнее, чем restart зависшего (идущая ячейка завершится ошибкой)."""
    ctx = resolve(key, db)
    kernels.stop(key)
    kernels.get(key, python=ctx["python"], cwd=ctx["cwd"])
    return {"kernel": kernels.state(key)}


@router.post("/{key}/stop")
def stop(key: str):
    kernels.stop(key)
    return {"ok": True}
