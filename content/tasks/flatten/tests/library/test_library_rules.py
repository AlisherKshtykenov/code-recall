"""Проверки режима «Библиотека» (одинаковые для всех задач): нужная функция библиотеки действительно применена,
важные параметры переданы. Что проверять — в task.json: library_function, required_names, required_kwargs."""
import ast
import json
from pathlib import Path

META = json.loads(Path("task.json").read_text(encoding="utf-8"))
MAIN = Path(META.get("main", "solution.py"))
REQUIRED = META.get("required_names", [])
KWARGS = META.get("required_kwargs", {})  # {имя функции: [параметры, которые нужно передать явно]}
LIBRARY = META.get("library_function", "")


def tree():
    return ast.parse(MAIN.read_text(encoding="utf-8"))


def aliases():
    """Локальные имена, под которыми импортированы нужные функции: from sklearn.metrics import recall_score as r -> r."""
    out = {}
    for node in ast.walk(tree()):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name in REQUIRED:
                    out[a.asname or a.name] = a.name
    return out


def called_name(func, alias):
    """Имя вызываемой функции: recall_score(…), metrics.recall_score(…), r(…) после import … as r."""
    if isinstance(func, ast.Name):
        return alias.get(func.id)  # голое имя — только если импортировано из библиотеки (своя def с тем же именем не в счёт)
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def usages():
    """{имя: [вызовы]} + имена, применённые как базовый класс или присвоенные (Adam = torch.optim.Adam)."""
    alias, calls, other = aliases(), {}, set()
    for node in ast.walk(tree()):
        if isinstance(node, ast.Call):
            name = called_name(node.func, alias)
            if name in REQUIRED:
                calls.setdefault(name, []).append(node)
        elif isinstance(node, ast.ClassDef):
            other |= {called_name(b, alias) for b in node.bases}
        elif isinstance(node, ast.Assign):
            other.add(called_name(node.value, alias))
    return calls, other


def test_required_function_is_called():
    calls, other = usages()
    missing = [n for n in REQUIRED if n not in calls and n not in other]
    hint = f" — в режиме «Библиотека» примените {LIBRARY}" if LIBRARY else ""
    assert not missing, f"нужная функция не вызвана: {', '.join(missing)}{hint}"


def test_required_kwargs_are_passed():
    calls, _ = usages()
    for name, kws in KWARGS.items():
        found = calls.get(name, [])
        if not found:
            continue  # отсутствие самой функции ловит предыдущий тест
        ok = any(set(kws) <= {k.arg for k in c.keywords if k.arg} for c in found)
        assert ok, f"в вызове {name}(…) передайте явно: {', '.join(f'{k}=…' for k in kws)}"
