"""Разбор загруженных файлов на ячейки.

.ipynb -> code-ячейки ноутбука (markdown перед ячейкой становится её описанием).
.py    -> если есть маркеры `# %%`, режем по ним; иначе по AST верхнего уровня:
          импорты одним блоком, каждый класс/функция отдельно, цикл обучения,
          `if __name__ == "__main__"`, прочий код группами.
"""
import ast
import json
import re

TRAIN_HINTS = ("backward", "optimizer", "epoch", "zero_grad", ".step(")


def cell(code, kind="code", title="", description=""):
    return {"kind": kind, "title": title, "code": code.strip("\n"),
            "description": description.strip()}


def parse_file(filename: str, raw: str) -> list[dict]:
    cells = parse_ipynb(raw) if filename.endswith(".ipynb") else parse_py(raw)
    return unique_titles(cells)


def unique_titles(cells: list[dict]) -> list[dict]:
    """Название блока — ключ привязки тестов, поэтому делаем его уникальным: код, код #2…"""
    seen = {}
    for c in cells:
        base = c["title"] or "блок"
        seen[base] = seen.get(base, 0) + 1
        c["title"] = base if seen[base] == 1 else f"{base} #{seen[base]}"
    return cells


def md_title(src: str) -> str:
    """Заголовок markdown-ячейки: первая непустая строка без разметки."""
    for line in src.splitlines():
        t = re.sub(r"[#*_`>\[\]$]+", "", line).strip()
        if t:
            return "текст: " + (t[:40] + "…" if len(t) > 40 else t)
    return "текст"


def parse_ipynb(raw: str) -> list[dict]:
    """Markdown — отдельная ячейка (kind=markdown) и одновременно описание следующего блока кода."""
    nb = json.loads(raw)
    cells, pending_md = [], []
    for c in nb.get("cells", []):
        src = c.get("source", "")
        src = "".join(src) if isinstance(src, list) else src
        if c.get("cell_type") == "markdown":
            if src.strip():
                cells.append(cell(src, "markdown", md_title(src)))
                pending_md.append(src)
            continue
        if c.get("cell_type") != "code" or not src.strip():
            continue
        kind, title = classify_code(src)
        cells.append(cell(src, kind, title, "\n\n".join(pending_md)))
        pending_md = []
    return cells


def parse_py(raw: str) -> list[dict]:
    if re.search(r"^# ?%%", raw, re.M):
        return split_by_markers(raw)
    try:
        tree = ast.parse(raw)
    except SyntaxError:
        return [cell(raw, "code", "весь файл")]
    return split_by_ast(raw, tree)


def split_by_markers(raw: str) -> list[dict]:
    parts = re.split(r"^# ?%%(.*)$", raw, flags=re.M)
    cells = []
    head = parts[0]
    if head.strip():
        kind, title = classify_code(head)
        cells.append(cell(head, kind, title))
    for i in range(1, len(parts), 2):
        marker_title, body = parts[i].strip(), parts[i + 1]
        if not body.strip():
            continue
        kind, title = classify_code(body)
        cells.append(cell(body, kind, marker_title.strip("[] ") or title))
    return cells


def node_kind(node) -> str:
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return "imports"
    if isinstance(node, ast.ClassDef):
        return "class"
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return "function"
    if isinstance(node, ast.If) and "__name__" in ast.unparse(node.test):
        return "main"
    if isinstance(node, (ast.For, ast.While)):
        text = ast.unparse(node)
        if any(h in text for h in TRAIN_HINTS):
            return "train"
    return "code"


def split_by_ast(raw: str, tree: ast.Module) -> list[dict]:
    lines = raw.splitlines()
    # Группы узлов: подряд идущие импорты и подряд идущий "прочий код" склеиваем.
    groups = []
    for node in tree.body:
        kind = node_kind(node)
        if groups and kind in ("imports", "code") and groups[-1][0] == kind:
            groups[-1][1].append(node)
        else:
            groups.append((kind, [node]))

    cells, prev_end = [], 0  # prev_end — индекс строки после предыдущего блока
    for kind, nodes in groups:
        end = nodes[-1].end_lineno
        # Комментарии между блоками прикрепляем к следующему блоку.
        cells.append(cell("\n".join(lines[prev_end:end]), kind,
                          block_title(kind, nodes)))
        prev_end = end
    # Хвост файла (комментарии после последнего узла)
    tail = "\n".join(lines[prev_end:])
    if tail.strip() and cells:
        cells[-1]["code"] += "\n" + tail.strip("\n")
    return [c for c in cells if c["code"].strip()]


def block_title(kind, nodes) -> str:
    n = nodes[0]
    if kind == "imports":
        return "импорты"
    if kind == "class":
        return f"class {n.name}"
    if kind == "function":
        return f"def {n.name}"
    if kind == "main":
        return "__main__"
    if kind == "train":
        return "цикл обучения"
    return "код"


def classify_code(src: str) -> tuple[str, str]:
    """Тип и заголовок для готового куска кода (ячейки ноутбука / `# %%`)."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return "code", "код"
    kinds = [node_kind(n) for n in tree.body]
    if not kinds:
        return "code", "код"
    for k in ("class", "function", "train", "main"):
        if k in kinds:
            node = tree.body[kinds.index(k)]
            return k, block_title(k, [node])
    if all(k == "imports" for k in kinds):
        return "imports", "импорты"
    return kinds[0], block_title(kinds[0], tree.body[:1])


def cells_from_line_ranges(raw: str, ranges: list[dict]) -> list[dict]:
    """Разбиение, предложенное LLM: [{title, kind, start_line, end_line}], строки с 1.
    Код берём из оригинала, чтобы LLM не мог его переписать."""
    lines = raw.splitlines()
    cells, covered = [], 0
    for r in sorted(ranges, key=lambda r: int(r["start_line"])):
        s = max(int(r["start_line"]) - 1, covered)
        e = min(int(r["end_line"]), len(lines))
        if e <= s:
            continue
        # Пропущенные LLM строки не теряем — приклеиваем к текущему блоку.
        code = "\n".join(lines[covered:e])
        covered = e
        cells.append(cell(code, r.get("kind", "code"), r.get("title", "")))
    if covered < len(lines) and cells:
        cells[-1]["code"] += "\n" + "\n".join(lines[covered:])
    return [c for c in cells if c["code"].strip()]
