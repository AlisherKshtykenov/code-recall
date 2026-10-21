"""Сравнение кода «по смыслу»: без пробелов, пустых строк, комментариев, docstring и разницы кавычек.

1. Если обе версии парсятся, равенство проверяется через ast.parse -> ast.unparse (без docstring).
2. Для подсветки код режется на логические строки (tokenize): COMMENT, NL и пробелы выкидываются,
   строковые и числовые литералы приводятся к одному виду. Логические строки сравниваются difflib-ом,
   результат переводится обратно в номера МОИХ исходных строк — показываем то, что я написал,
   а подсвечиваем только строки, где отличается сам код.
3. Код не токенизируется (недописанная попытка) — запасной вариант: построчно, без комментариев и пробелов."""
import ast
import difflib
import io
import re
import tokenize


def _strip_docstrings(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return tree


def canonical(code: str) -> str | None:
    """ast.unparse без docstring; None — не парсится."""
    try:
        return ast.unparse(_strip_docstrings(ast.parse(code)))
    except (SyntaxError, ValueError, RecursionError):
        return None


def _norm_token(tok) -> str:
    if tok.type == tokenize.STRING:
        try:
            return repr(ast.literal_eval(tok.string))  # 'a' и "a" — одно и то же
        except (ValueError, SyntaxError):
            return tok.string
    if tok.type == tokenize.NUMBER:
        try:
            return repr(ast.literal_eval(tok.string))  # 1_000 и 1000
        except (ValueError, SyntaxError):
            return tok.string
    return tok.string


def logical_lines(code: str) -> list[dict]:
    """[{norm, start, end, kind}] — kind: code | comment (строка только с комментарием)."""
    out, cur, start = [], [], None
    comments = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(code).readline):
            if tok.type == tokenize.COMMENT:
                comments.append(tok.start[0])
                continue
            if tok.type in (tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER):
                continue
            if tok.type == tokenize.NEWLINE:
                if cur:
                    out.append({"toks": cur, "start": start, "end": tok.start[0]})
                cur, start = [], None
                continue
            if start is None:
                start = tok.start[0]
            cur.append(tok)
        if cur:
            out.append({"toks": cur, "start": start, "end": cur[-1].end[0]})
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return _fallback_lines(code)
    res = []
    for ln in out:
        toks = ln["toks"]
        # одиночная строка-литерал как оператор — docstring (или ничего не делающий код)
        if len(toks) == 1 and toks[0].type == tokenize.STRING:
            continue
        res.append({"norm": _join(toks), "start": ln["start"], "end": ln["end"], "kind": "code"})
    code_lines = {i for ln in res for i in range(ln["start"], ln["end"] + 1)}
    res += [{"norm": None, "start": c, "end": c, "kind": "comment"} for c in comments if c not in code_lines]
    return sorted(res, key=lambda x: x["start"])


def _join(toks) -> str:
    """Токены через пробел только там, где без него слова слиплись бы (def f, not in …)."""
    out = ""
    for t in toks:
        s = _norm_token(t)
        if out and (out[-1].isalnum() or out[-1] == "_") and (s[:1].isalnum() or s[:1] == "_"):
            out += " "
        out += s
    return out


def _fallback_lines(code: str) -> list[dict]:
    res = []
    for i, line in enumerate(code.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            res.append({"norm": None, "start": i, "end": i, "kind": "comment"})
            continue
        no_comment = re.sub(r"\s+#.*$", "", stripped) if "'" not in stripped and '"' not in stripped else stripped
        norm = re.sub(r"\s+", " ", no_comment)
        norm = re.sub(r"\s*([^\w\s])\s*", r"\1", norm)  # пробелы вокруг операторов и скобок
        res.append({"norm": norm, "start": i, "end": i, "kind": "code"})
    return res


def compare(mine: str, ref: str) -> dict:
    """Что подсветить «по смыслу».

    mine.changed / ref.changed — номера строк (с 1), где отличается сам код;
    *.same — совпавшие строки; *.comments — строки-комментарии (серые, не отличие).
    similarity — доля совпавших логических строк, 0..100."""
    equal_ast = None
    a, b = canonical(mine), canonical(ref)
    if a is not None and b is not None:
        equal_ast = a == b
    la = [x for x in logical_lines(mine) if x["kind"] == "code"]
    lb = [x for x in logical_lines(ref) if x["kind"] == "code"]
    sm = difflib.SequenceMatcher(None, [x["norm"] for x in la], [x["norm"] for x in lb], autojunk=False)
    m_changed, r_changed, m_same, r_same = set(), set(), set(), set()

    def span(lines, i1, i2, target):
        for x in lines[i1:i2]:
            target.update(range(x["start"], x["end"] + 1))

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            span(la, i1, i2, m_same)
            span(lb, j1, j2, r_same)
        else:
            span(la, i1, i2, m_changed)
            span(lb, j1, j2, r_changed)
    matched = sum(i2 - i1 for op, i1, i2, _, _ in sm.get_opcodes() if op == "equal")
    total = max(len(la), len(lb)) or 1
    equal = equal_ast if equal_ast is not None else (not m_changed and not r_changed)
    if equal:  # по AST совпали — значит отличий нет, даже если строки разбиты по-разному
        m_changed, r_changed = set(), set()
    return {"equal": bool(equal), "parsed": equal_ast is not None,
            "similarity": 100 if equal else round(100 * matched / total),
            "mine": {"changed": sorted(m_changed), "same": sorted(m_same),
                     "comments": [x["start"] for x in logical_lines(mine) if x["kind"] == "comment"]},
            "ref": {"changed": sorted(r_changed), "same": sorted(r_same),
                    "comments": [x["start"] for x in logical_lines(ref) if x["kind"] == "comment"]}}


def unified(ref: str, mine: str, name: str) -> str:
    """Построчный diff нормализованного кода (для текстового отчёта): пусто, если по смыслу равны."""
    a, b = canonical(ref), canonical(mine)
    if a is None or b is None:
        a = "\n".join(x["norm"] for x in logical_lines(ref) if x["kind"] == "code")
        b = "\n".join(x["norm"] for x in logical_lines(mine) if x["kind"] == "code")
    if a == b:
        return ""
    return "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), f"эталон/{name}", f"моё/{name}", n=2))


