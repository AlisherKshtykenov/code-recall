"""Кэш тяжёлых блоков (обучение, загрузка больших датасетов).

После успешного выполнения тяжёлого блока ЭТАЛОНА сохраняем переменные, которые блок
создаёт или меняет, в results/cache/<NN>_<блок>.pkl (dill, если есть в окружении, иначе pickle).
При «повторить блок» обычные блоки до цели выполняются заново (импорты, определения функций и
классов — быстро), а тяжёлый — заменяется загрузкой кэша.

Кэш действителен, пока не поменялся код блоков до тяжёлого включительно и окружение Python
(хеш в метаданных)."""
import ast
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from . import workspace
from .review import normalize

MARK = "__CR_CACHE__"


def cache_path(ref_id: int, index: int, title: str) -> Path:
    return workspace.ws(ref_id) / "results" / "cache" / f"{index + 1:02d}_{workspace.slug(title)}.pkl"


def prefix_hash(cells, index: int, python: str) -> str:
    """Хеш кода блоков до index включительно (без комментариев и пробелов) + окружение."""
    h = hashlib.sha1(python.encode())
    for c in cells[:index + 1]:
        if c.kind != "markdown":
            h.update(normalize(c.code).encode())
            h.update(b"\0")
    return h.hexdigest()[:16]


def meta(ref_id: int, index: int, title: str) -> dict | None:
    p = cache_path(ref_id, index, title).with_suffix(".json")
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def status(ref_id: int, cells, index: int, python: str) -> dict:
    """Есть ли действительный кэш блока: {exists, valid, size, created, names, skipped, engine}."""
    c = cells[index]
    m = meta(ref_id, index, c.title)
    p = cache_path(ref_id, index, c.title)
    if not m or not p.exists():
        return {"exists": False, "valid": False}
    return {**m, "exists": True, "valid": m.get("hash") == prefix_hash(cells, index, python),
            "size": p.stat().st_size}


def names_in(code: str) -> list[str]:
    """Имена, которые блок использует или присваивает: их и сохраняем
    (обучение меняет модель «на месте», поэтому одних новых переменных мало)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add((node.asname or node.name).split(".")[0])
    return sorted(names)


def snapshot_code(path: Path, names: list[str]) -> str:
    """Код, который выполняется в ядре сразу после тяжёлого блока."""
    return f'''
def __cr_snapshot(path, names):
    import json, os, pickle, types, time
    try:
        import dill as pk; engine = "dill"
    except ImportError:
        pk = pickle; engine = "pickle"
    t0 = time.time()
    g = get_ipython().user_ns
    def ok(n):
        if n not in g or n.startswith("_") or n in ("In", "Out", "exit", "quit", "get_ipython"):
            return False
        v = g[n]
        if isinstance(v, types.ModuleType):
            return False
        # функции и классы ноутбука pickle сохраняет только ссылкой: их заново определят блоки до этого
        if engine == "pickle" and isinstance(v, (types.FunctionType, type)) and getattr(v, "__module__", "") == "__main__":
            return False
        return True
    data = {{n: g[n] for n in names if ok(n)}}
    skipped = []
    try:
        blob = pk.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)  # одним дампом: общие ссылки сохраняются
    except Exception:
        for n in list(data):
            try:
                pk.dumps(data[n], protocol=pickle.HIGHEST_PROTOCOL)
            except Exception as e:
                skipped.append(f"{{n}} ({{type(e).__name__}})")
                data.pop(n)
        blob = pk.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "wb") as f:
        f.write(blob)
    os.replace(path + ".tmp", path)
    print("{MARK}" + json.dumps({{"names": sorted(data), "skipped": skipped, "engine": engine,
                                   "bytes": len(blob), "save_ms": int((time.time() - t0) * 1000)}}))
__cr_snapshot({str(path)!r}, {names!r})
del __cr_snapshot
'''


def restore_code(path: Path, engine: str) -> str:
    return f'''
def __cr_restore(path, engine):
    import pickle, time
    t0 = time.time()
    if engine == "dill":
        try:
            import dill as pk
        except ImportError:
            raise RuntimeError("кэш сохранён через dill, а в этом окружении dill нет: pip install dill")
    else:
        pk = pickle
    with open(path, "rb") as f:
        data = pk.load(f)
    get_ipython().user_ns.update(data)
    print(f"кэш загружен за {{time.time() - t0:.1f}} с: " + ", ".join(sorted(data)))
__cr_restore({str(path)!r}, {engine!r})
del __cr_restore
'''


def save_meta(ref_id: int, index: int, title: str, info: dict, hash_: str, run_ms: int):
    p = cache_path(ref_id, index, title).with_suffix(".json")
    p.write_text(json.dumps({**info, "hash": hash_, "run_ms": run_ms, "title": title,
                             "created": datetime.now().isoformat(timespec="minutes")}, ensure_ascii=False))


def drop(ref_id: int, index: int, title: str):
    p = cache_path(ref_id, index, title)
    for f in (p, p.with_suffix(".json")):
        if f.exists():
            os.remove(f)
