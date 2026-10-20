"""Помощник для вывода таблиц и графиков без ноутбуков.

    from recall import show
    show(df)            # DataFrame / Series / 2D-массив -> таблица в выводе
    show(fig)           # matplotlib Figure (или plt) -> картинка, файл в results/
    show(img)           # PIL.Image -> картинка
    show(plotly_fig)    # plotly -> интерактивный график
    show(obj)           # всё остальное -> repr

plt.show() в скриптах перехватывается: каждая открытая фигура сохраняется в results/ и показывается.
Работает и при «Запустить», и в «Консоли». Вне CODE RECALL show() просто печатает объект."""
import json
import os
import sys
import time

MARK = "\x1eRECALL"
ROWS = 200
_n = [0]


def _emit(event: dict):
    out = sys.stdout
    out.flush()
    out.write(MARK + json.dumps(event, ensure_ascii=False, default=str) + "\n")
    out.flush()


def _results_path(prefix: str, ext: str) -> str:
    os.makedirs("results", exist_ok=True)
    _n[0] += 1
    return os.path.join("results", f"{prefix}_{time.strftime('%H%M%S')}_{_n[0]:02d}.{ext}")


def _cell(v):
    if v is None:
        return None
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return None
    except Exception:
        pass
    s = str(v)
    return s if len(s) <= 200 else s[:200] + "…"


def _table(df, title=None):
    import pandas as pd
    if isinstance(df, pd.Series):
        df = df.to_frame(name=df.name if df.name is not None else "value")
    head = df.head(ROWS)
    show_index = not isinstance(df.index, pd.RangeIndex)
    cols = ([str(df.index.name or "")] if show_index else []) + [str(c) for c in df.columns]
    dtypes = (["index"] if show_index else []) + [str(t) for t in df.dtypes]
    rows = []
    for idx, row in zip(head.index, head.itertuples(index=False)):
        vals = [_cell(v) for v in row]
        rows.append(([_cell(idx)] if show_index else []) + vals)
    _emit({"type": "table", "title": title, "columns": cols, "dtypes": dtypes, "rows": rows,
           "n_rows": int(df.shape[0]), "n_cols": int(df.shape[1])})


def _figure(fig, title=None):
    path = _results_path("figure", "png")
    fig.savefig(path, dpi=110, bbox_inches="tight")
    _emit({"type": "image", "path": path.replace(os.sep, "/"), "title": title})


def show(obj=None, title=None):
    """Показать объект в выводе CODE RECALL (таблица, картинка, график)."""
    mod = type(obj).__module__ or ""
    try:
        if obj is None or getattr(obj, "__name__", "") == "matplotlib.pyplot":
            import matplotlib.pyplot as plt
            for num in plt.get_fignums():
                _figure(plt.figure(num), title)
            plt.close("all")
            return
        if mod.startswith("pandas"):
            import pandas as pd
            if isinstance(obj, (pd.DataFrame, pd.Series)):
                return _table(obj, title)
        if mod.startswith("numpy") and getattr(obj, "ndim", 0) in (1, 2):
            import pandas as pd
            return _table(pd.DataFrame(obj), title)
        if mod.startswith("matplotlib"):
            fig = getattr(obj, "figure", None) or obj  # Figure, Axes и т.п.
            if hasattr(fig, "savefig"):
                _figure(fig, title)
                import matplotlib.pyplot as plt
                plt.close(fig)
                return
        if mod.startswith("PIL"):
            path = _results_path("image", "png")
            obj.save(path)
            return _emit({"type": "image", "path": path.replace(os.sep, "/"), "title": title})
        if mod.startswith("plotly"):
            return _emit({"type": "plotly", "figure": json.loads(obj.to_json()), "title": title})
    except ImportError:
        pass
    print(repr(obj))


def _show_all_figures():
    """plt.show() и конец команды в консоли: все открытые фигуры -> results/ и в вывод."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return
    for num in plt.get_fignums():
        _figure(plt.figure(num))
    plt.close("all")


def _patch_pyplot(pyplot):
    pyplot.show = lambda *a, **k: _show_all_figures()


def display_value(value):
    """Как в IPython: результат последнего выражения в консоли."""
    if value is None:
        return
    mod = type(value).__module__ or ""
    if mod.startswith(("pandas", "matplotlib", "PIL", "plotly")) or (mod.startswith("numpy") and getattr(value, "ndim", 0) == 2):
        show(value)
    else:
        print(repr(value))
