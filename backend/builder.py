"""Конструктор задач — визуальная доска: палитра, раскладка холста, сохранение (черновики -> задачи,
стрелки -> зависимости), «Собрать в блок», шаблоны новых задач для обоих режимов."""
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import bricks, taskfs
from .db import MapBrick, MapRow, SessionLocal, Slot, Task, Topic, get_setting, set_setting
from .library import make_task, write_meta
from .tasks import commit_version, deps_ok

router = APIRouter(prefix="/api/builder")
FREE_BOARD = "board:free"  # доска без задачи-корня («Новая задача»)


def get_db():
    with SessionLocal() as db:
        yield db


def ref_tests(version) -> dict:
    """{режим: [прошло, всего]} — из кэша тестов на эталоне (если эталон уже проверяли)."""
    out = {}
    for res in json.loads(version.ref_results or "{}").values():
        mode = res.get("_mode", "scratch")
        tests = list((res.get("tests") or {}).values())
        if tests or res.get("collection_errors"):
            total = len(tests) + len(res.get("collection_errors", []))
            out[mode] = [sum(t["status"] == "pass" for t in tests), total]
    return out


level_of = bricks.level_of



def category_of(db, t: Task) -> str:
    b = db.get(MapBrick, t.name)
    cats = taskfs.json_list(b.categories) if b else []
    if cats:
        return cats[0]
    topic = db.get(Topic, t.topic_id) if t.topic_id else None
    return (topic.name.lower() if topic else "") or "other"


def task_card(db, t: Task) -> dict:
    files = json.loads(t.current.files) if t.current else {}
    from .tasks import mode_statuses
    return {"id": t.id, "name": t.name, "title": t.title, "topic_id": t.topic_id, "tags": taskfs.json_list(t.tags),
            "modes": taskfs.modes_of(files), "statuses": mode_statuses(t, files), "implements": bricks.implements_of(files),
            "deps": bricks.deps_of(files), "level": level_of(files), "category": category_of(db, t), "main": taskfs.read_meta(files).get("main") or "",
            "tests": {**(ref_tests(t.current) if t.current else {}), **json.loads(get_setting(db, f"reftests:{t.id}", "{}") or "{}")},
            "broken": t.broken or ""}


@router.get("/palette")
def palette(db=Depends(get_db)):
    """Всё для левой панели: задачи (со статусами режимов и тестами эталона), слоты, дерево тем, строки карты."""
    tasks = [task_card(db, t) for t in db.query(Task).order_by(Task.title).all()]
    slots = [{"name": s.name, "title": s.title or s.name, "signature": s.signature, "symbol": s.symbol or s.name,
              "default_impl": s.default_impl, "impls": [x.name for x in bricks.impls(db, s.name)]} for s in db.query(Slot).order_by(Slot.name)]
    topics = [{"id": n.id, "name": n.name, "parent_id": n.parent_id} for n in db.query(Topic).order_by(Topic.position, Topic.name)]
    rows = [{"key": r.key, "title": r.title, "bricks": sorted({i["name"] for items in taskfs.json_dict(r.cells).values() for i in items})}
            for r in db.query(MapRow).order_by(MapRow.position)]
    return {"tasks": tasks, "slots": slots, "topics": topics, "map_rows": rows}


@router.get("/board")
def get_board(task_id: int | None = None, db=Depends(get_db)):
    """Раскладка доски: у задачи — сохранённая в задаче; без задачи — свободная доска."""
    if task_id:
        t = db.get(Task, task_id)
        if t is None:
            raise HTTPException(404, "задача не найдена")
        return {"task": task_card(db, t), "board": json.loads(t.board or "{}") or None}
    return {"task": None, "board": json.loads(get_setting(db, FREE_BOARD, "") or "{}") or None}


class BoardIn(BaseModel):
    task_id: int | None = None
    board: dict


@router.put("/board")
def put_board(body: BoardIn, db=Depends(get_db)):
    """Сохранить раскладку (позиции карточек, свёрнутые блоки). Версию задачи не создаёт."""
    text = json.dumps(body.board, ensure_ascii=False)
    if body.task_id:
        t = db.get(Task, body.task_id)
        if t is None:
            raise HTTPException(404, "задача не найдена")
        t.board = text
    else:
        set_setting(db, FREE_BOARD, text)
    db.commit()
    return {"ok": True}


# ---------- шаблоны новых задач (черновики на холсте) ----------

def _readme(title, apply, how):
    return f"# {title}\n\n**Что делает.** …\n\n## Как применять\n\n{apply}\n\n## Как работает\n\n{how}\n\n## Задача\n\n" \
           "**Режим «Библиотека»** — примените готовую функцию с той же сигнатурой.\n\n**Режим «С нуля»** — та же функция своими руками.\n"


TEMPLATES = {
    "sklearn_function": {
        "title": "новая функция (sklearn)", "level": "brick",
        "files": {
            "reference/library/solution.py": '"""Через sklearn."""\nfrom sklearn import metrics  # готовые функции\n\n\ndef solve(y_true, y_pred):\n'
                                             '    """Что делает — одной фразой."""\n    return metrics.accuracy_score(y_true, y_pred)  # замените на нужную функцию\n',
            "reference/scratch/solution.py": '"""Своими руками — та же сигнатура."""\nimport numpy as np\n\n\ndef solve(y_true, y_pred):\n'
                                             '    """Что делает — одной фразой."""\n    return float(np.mean(np.asarray(y_true) == np.asarray(y_pred)))  # шаги с комментариями\n',
            "tests/test_solution.py": 'import numpy as np\nfrom sklearn.metrics import accuracy_score\n\nfrom solution import solve\n\n\n'
                                      'def test_like_library():\n    y, p = [0, 1, 1, 0], [0, 1, 0, 0]\n'
                                      '    assert np.isclose(solve(y, p), accuracy_score(y, p)), "результат как у sklearn"\n',
        },
        "meta": {"library_function": "sklearn.metrics.accuracy_score", "required_names": ["accuracy_score"],
                 "forbidden_modules": ["sklearn"], "forbidden_names": ["accuracy_score"], "required_kwargs": {}, "kind": "ml"},
    },
    "torch_layer": {
        "title": "новый слой (torch)", "level": "brick",
        "files": {
            "reference/library/solution.py": '"""Через torch.nn.functional."""\nimport torch.nn.functional as F  # готовые слои\n\n\n'
                                             'def layer(input):\n    """Что делает слой."""\n    return F.gelu(input)  # замените на нужную функцию\n',
            "reference/scratch/solution.py": '"""Своими руками — та же сигнатура, тот же градиент."""\nimport math\n\nimport torch\n\n\n'
                                             'def layer(input):\n    """Что делает слой."""\n    return 0.5 * input * (1 + torch.erf(input / math.sqrt(2)))  # формула\n',
            "tests/test_solution.py": 'import torch\nimport torch.nn.functional as F\n\nfrom solution import layer\n\n\n'
                                      'def test_forward_and_grad_like_torch():\n    x = torch.randn(4, 5, dtype=torch.float64, requires_grad=True)\n'
                                      '    y = x.detach().clone().requires_grad_()\n    layer(x).sum().backward()\n    F.gelu(y).sum().backward()\n'
                                      '    assert torch.allclose(layer(x), F.gelu(y)) and torch.allclose(x.grad, y.grad), "выход и градиент как у torch"\n',
        },
        "meta": {"library_function": "torch.nn.functional.gelu", "required_names": ["gelu"], "forbidden_modules": ["torch.nn.functional"],
                 "forbidden_names": ["gelu"], "required_kwargs": {}, "kind": "ml"},
    },
    "metric": {
        "title": "новая метрика", "level": "brick", "implements": "metric",
        "files": {
            "reference/library/solution.py": '"""Метрика через sklearn."""\nfrom sklearn import metrics  # метрики\n\n\n'
                                             'def precision_score(y_true, y_pred, *, pos_label=1, zero_division="warn"):\n    """Точность: доля верных среди названных положительными."""\n'
                                             '    return metrics.precision_score(y_true, y_pred, pos_label=pos_label, zero_division=zero_division)\n\n\nmetric = precision_score  # слот metric\n',
            "reference/scratch/solution.py": '"""Метрика своими руками."""\nimport numpy as np\n\n\n'
                                             'def precision_score(y_true, y_pred, *, pos_label=1, zero_division="warn"):\n    """Точность: TP / (TP + FP)."""\n'
                                             '    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)\n    predicted = y_pred == pos_label  # названо положительным\n'
                                             '    if not predicted.any():\n        return 0.0 if zero_division == "warn" else float(zero_division)\n'
                                             '    return float((y_true[predicted] == pos_label).mean())  # из них — верно\n\n\nmetric = precision_score  # слот metric\n',
            "tests/test_solution.py": 'import numpy as np\nfrom sklearn.metrics import precision_score as sk\n\nfrom solution import precision_score\n\n\n'
                                      'def test_like_sklearn():\n    y, p = [0, 1, 1, 0, 1], [1, 1, 0, 0, 1]\n    assert np.isclose(precision_score(y, p), sk(y, p)), "как sklearn"\n',
        },
        "meta": {"library_function": "sklearn.metrics.precision_score", "required_names": ["precision_score"], "forbidden_modules": ["sklearn"],
                 "forbidden_names": ["precision_score"], "required_kwargs": {"precision_score": ["zero_division"]}, "kind": "ml"},
    },
    "wall": {
        "title": "новая стена (пайплайн)", "level": "wall", "main": "pipeline.py",
        "files": {
            "reference/scratch/pipeline.py": '"""Стена: цепочка из кирпичиков. Импорт — from bricks.<имя> import …"""\n\n\ndef run(data_root="data"):\n'
                                             '    """Загрузить данные -> подготовить -> обучить -> оценить. Вернуть словарь метрик."""\n    return {}\n',
            "tests/test_pipeline.py": 'from pipeline import run\n\n\ndef test_returns_metrics():\n    assert isinstance(run(), dict), "run() возвращает словарь метрик"\n',
        },
        "meta": {"tags": ["стена"], "kind": "ml", "level": "wall"},
    },
}


@router.get("/templates")
def templates():
    return {k: {"title": v["title"], "level": v["level"], "files": v["files"], "meta": v["meta"],
                "implements": v.get("implements", ""), "main": v.get("main", "solution.py")} for k, v in TEMPLATES.items()}


# ---------- сохранение доски ----------

class DraftIn(BaseModel):
    key: str  # временный id карточки на холсте
    title: str
    topic_id: int | None = None
    tags: list[str] = []
    files: dict[str, str] = {}
    meta: dict = {}
    main: str = "solution.py"
    implements: str = ""


class EdgeIn(BaseModel):
    source: str  # ключ карточки, которую используют (задача: "t:<id>", слот: "s:<имя>", черновик: "d:<ключ>")
    target: str  # ключ карточки, которая использует
    name: str = ""  # имя для импорта (from bricks.<name> …); пусто — имя задачи


class SaveIn(BaseModel):
    task_id: int | None = None
    drafts: list[DraftIn] = []
    edges: list[EdgeIn] = []
    board: dict = {}


def dep_name(s: str) -> str:
    return re.sub(r"\W+", "_", s).strip("_").lower() or "dep"


@router.post("/save")
def save(body: SaveIn, db=Depends(get_db)):
    """Черновики -> новые задачи; стрелки -> зависимости задач-получателей (новая версия, если изменилось).
    Циклы и неразрешимые зависимости отклоняются целиком — ничего не сохраняется."""
    created, keymap = {}, {}
    for d in body.drafts:
        files = dict(d.files)
        files.setdefault("description.md", f"# {d.title}\n")
        meta = {**d.meta, "title": d.title, "main": d.main, "tags": d.tags}
        if d.implements:
            meta["implements"] = d.implements
        write_meta(files, **meta)
        if not taskfs.modes_of(files):
            raise HTTPException(400, f"черновик «{d.title}»: нет эталона ни в reference/library/, ни в reference/scratch/")
        t = make_task(db, d.title, files, d.topic_id, d.tags, meta.get("kind", "ml"))
        created[d.key] = t.id
        keymap[f"d:{d.key}"] = t
    for key in {e.source for e in body.edges} | {e.target for e in body.edges}:
        if key.startswith("t:"):
            t = db.get(Task, int(key[2:]))
            if t is None:
                raise HTTPException(400, f"нет задачи {key}")
            keymap[key] = t
    wanted = {}  # задача-получатель -> её зависимости по стрелкам
    for e in body.edges:
        target = keymap.get(e.target)
        if target is None:
            raise HTTPException(400, "стрелка может вести только в задачу (не в слот)")
        if e.source.startswith("s:"):
            dep = {"name": dep_name(e.name or e.source[2:]), "slot": e.source[2:]}
        else:
            src = keymap[e.source]
            dep = {"name": dep_name(e.name or src.name), "task": src.name}
        wanted.setdefault(target.id, []).append(dep)
    changed = []
    for tid, deps in wanted.items():
        t = db.get(Task, tid)
        files = json.loads(t.current.files)
        old = taskfs.read_meta(files).get("deps") or []
        keep_modes = {d["name"]: d.get("modes") for d in old if isinstance(d, dict)}  # режимы зависимостей не теряем
        merged = []
        for d in deps:
            if keep_modes.get(d["name"]):
                d["modes"] = keep_modes[d["name"]]
            if d not in merged:
                merged.append(d)
        if sorted(json.dumps(x, sort_keys=True) for x in merged) == sorted(json.dumps(x, sort_keys=True) for x in old):
            continue
        write_meta(files, deps=merged)
        err = deps_ok(db, t, files)
        if err:
            db.rollback()
            raise HTTPException(400, err)
        taskfs.materialize(t.name, files)
        roles = json.loads(t.current.roles or "{}")
        commit_version(db, t, files, {f: roles.get(f, "write") for f in taskfs.reference_names(files)})
        changed.append(t.id)
    board = json.dumps(body.board, ensure_ascii=False)
    if body.task_id and db.get(Task, body.task_id):
        db.get(Task, body.task_id).board = board
    else:
        set_setting(db, FREE_BOARD, board)
    db.commit()
    return {"created": created, "changed": changed}


class BlockIn(BaseModel):
    title: str
    members: list[str]  # ключи карточек: "t:<id>" или "s:<слот>"
    topic_id: int | None = None
    tags: list[str] = []


@router.post("/block")
def make_block(body: BlockIn, db=Depends(get_db)):
    """«Собрать в блок»: новая задача-блок, выбранные карточки — её зависимости; файлы — заготовки обоих режимов."""
    deps, imports = [], []
    for key in body.members:
        if key.startswith("s:"):
            slot = db.query(Slot).filter_by(name=key[2:]).first()
            if slot is None:
                raise HTTPException(400, f"нет слота {key[2:]}")
            deps.append({"name": dep_name(slot.name), "slot": slot.name})
            imports.append(f"from slots.{slot.name} import {slot.symbol or slot.name}")
        elif key.startswith("t:"):
            t = db.get(Task, int(key[2:]))
            if t is None:
                raise HTTPException(400, f"нет задачи {key}")
            name = dep_name(t.name)
            deps.append({"name": name, "task": t.name})
            imports.append(f"from bricks.{name} import …  # {t.title}")
        else:
            raise HTTPException(400, "в блок собираются только сохранённые задачи и слоты (черновик сначала сохраните)")
    if not deps:
        raise HTTPException(400, "выберите хотя бы одну карточку")
    body_text = "\n".join(f"# {line}" for line in imports)
    scratch = f'"""{body.title}: блок из кирпичиков (с нуля — на своих кирпичиках)."""\n{body_text}\n\n\ndef run(x):\n    """Что делает блок."""\n    return x\n'
    library = f'"""{body.title}: блок через библиотеку (кирпичики подключаются так же, внутри — готовые функции)."""\n{body_text}\n\n\ndef run(x):\n    """Что делает блок."""\n    return x\n'
    files = {"reference/scratch/solution.py": scratch, "reference/library/solution.py": library,
             "tests/test_solution.py": "from solution import run\n\n\ndef test_runs():\n    assert run(1) == 1, \"заготовка: замените на тесты блока\"\n",
             "description.md": f"# {body.title}\n\n**Что делает.** Блок из: {', '.join(d['name'] for d in deps)}.\n\n## Как применять\n\n…\n\n## Как работает\n\n…\n\n## Задача\n\n…\n"}
    write_meta(files, title=body.title, deps=deps, tags=body.tags or ["блок"], main="solution.py", level="block")
    t = make_task(db, body.title, files, body.topic_id, body.tags or ["блок"], "ml")
    return task_card(db, t)
