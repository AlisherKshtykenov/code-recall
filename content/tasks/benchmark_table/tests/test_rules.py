"""Правила задачи (одинаковые для всех задач): эталон пишется своими руками.
Список запрещённого — в task.json: "forbidden": {"modules": [...], "names": [...]}."""
import ast
import json
from pathlib import Path

META = json.loads(Path("task.json").read_text(encoding="utf-8"))
MAIN = Path(META.get("main", "solution.py"))
FORBIDDEN = META.get("forbidden", {})


def tree():
    return ast.parse(MAIN.read_text(encoding="utf-8"))


def test_no_forbidden_imports():
    banned = tuple(FORBIDDEN.get("modules", []))
    found = []
    for node in ast.walk(tree()):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] in banned or a.name in banned]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in banned or node.module in banned:
                found.append(node.module)
    assert not found, f"в {MAIN} нельзя импортировать {', '.join(sorted(set(found)))} — напишите это своими руками"


def test_no_forbidden_names():
    banned = set(FORBIDDEN.get("names", []))
    used, imported = set(), set()
    for node in ast.walk(tree()):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in banned:
            used.add(node.func.id)  # вызов по имени: recall_score(...); переменная std = ... — не нарушение
        elif isinstance(node, ast.Attribute) and node.attr in banned:  # torch.std, x.std(), TF.normalize
            used.add(node.attr)
        elif isinstance(node, ast.alias) and (node.name.split(".")[-1] in banned or (node.asname or "") in banned):
            imported.add(node.name.split(".")[-1])  # и «import recall_score as r» — по настоящему имени
    defined = {n.name for n in ast.walk(tree()) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    bad = (used - defined) | imported  # своя функция с тем же именем — это и есть задача; импорт — никогда
    assert not bad, f"в {MAIN} нельзя вызывать или импортировать {', '.join(sorted(bad))} (это та самая функция или её прямой аналог)"
