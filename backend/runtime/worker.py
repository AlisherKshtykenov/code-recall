"""Процесс выполнения кода CODE RECALL (вместо Jupyter): один на попытку.

Команды приходят JSON-строками в stdin:
    {"id": 1, "op": "run", "path": "train.py"}   выполнить файл как __main__ (новое пространство имён)
    {"id": 2, "op": "exec", "code": "df.head()"}  строка консоли в том же пространстве имён
Ответы — JSON-строки в исходный stdout (протокол):
    {"t": "ready"} · {"t": "out", "s": "stdout"|"stderr", "text": ...} · {"t": "done", "id", "status", "ms"}
Вывод программы (включая вывод C-библиотек) идёт через пайпы на fd 1/2 и пересылается сюда же,
поэтому порядок print и show() сохраняется. Совместимо с Python 3.8+."""
import ast
import codecs
import json
import os
import signal
import sys
import threading
import time
import traceback

PROTO = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
_send_lock = threading.Lock()
SYNC = "\x1dSYNC\x1d"
_synced = {"stdout": threading.Event(), "stderr": threading.Event()}


def send(obj):
    with _send_lock:
        PROTO.write(json.dumps(obj, ensure_ascii=False) + "\n")
        PROTO.flush()


def _pump(fd, name):
    dec = codecs.getincrementaldecoder("utf-8")("replace")
    pending = ""
    while True:
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            break
        if not chunk:
            break
        pending += dec.decode(chunk)
        while True:
            i = pending.find(SYNC)
            if i < 0:
                break
            if i:
                send({"t": "out", "s": name, "text": pending[:i]})
            pending = pending[i + len(SYNC):]
            _synced[name].set()
        # хвост может быть началом SYNC — придержим его
        keep = 0
        for k in range(1, len(SYNC)):
            if pending.endswith(SYNC[:k]):
                keep = k
        if len(pending) > keep:
            send({"t": "out", "s": name, "text": pending[:len(pending) - keep]})
            pending = pending[len(pending) - keep:]


def _redirect(fd, name):
    r, w = os.pipe()
    os.dup2(w, fd)
    os.close(w)
    threading.Thread(target=_pump, args=(r, name), daemon=True).start()


_redirect(1, "stdout")
_redirect(2, "stderr")
sys.stdout = open(1, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False)
sys.stderr = open(2, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False)


def sync_output():
    """Дождаться, пока весь вывод команды ушёл в протокол, — только потом «done»."""
    for f in (sys.stdout, sys.stderr):
        try:
            f.flush()
        except Exception:
            pass
    for name, fd in (("stdout", 1), ("stderr", 2)):
        _synced[name].clear()
        os.write(fd, SYNC.encode())
    for e in _synced.values():
        e.wait(5)


CWD = os.getcwd()
if CWD not in sys.path:
    sys.path.insert(0, CWD)
USER = {"__name__": "__main__", "__builtins__": __builtins__}


def purge_task_modules():
    """Модули из папки задачи выгружаем перед запуском — правки в model.py видны сразу."""
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None) or ""
        if f and os.path.abspath(f).startswith(CWD + os.sep) and name not in ("__main__",):
            del sys.modules[name]


def print_error():
    """Traceback без кадров самого исполнителя."""
    etype, value, tb = sys.exc_info()
    me = os.path.abspath(__file__)
    while tb is not None and os.path.abspath(tb.tb_frame.f_code.co_filename) == me:
        tb = tb.tb_next
    sys.stderr.write("".join(traceback.format_exception(etype, value, tb)))


def run_file(path):
    global USER
    purge_task_modules()
    full = os.path.join(CWD, path)
    with open(full, encoding="utf-8") as f:
        src = f.read()
    USER = {"__name__": "__main__", "__file__": full, "__builtins__": __builtins__}
    sys.argv = [path]
    exec(compile(src, full, "exec"), USER)


def exec_line(code):
    """Как IPython: значение последнего выражения показываем (DataFrame — таблицей)."""
    import recall
    tree = ast.parse(code, "<консоль>", "exec")
    last = None
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last = ast.Expression(tree.body.pop().value)
    exec(compile(tree, "<консоль>", "exec"), USER)
    if last is not None:
        value = eval(compile(last, "<консоль>", "eval"), USER)
        if value is not None:
            USER["_"] = value
        recall.display_value(value)
    recall._show_all_figures()  # нарисованное в консоли без plt.show() тоже показываем


def main():
    signal.signal(signal.SIGINT, signal.default_int_handler)
    send({"t": "ready", "python": sys.version.split()[0], "executable": sys.executable})
    for line in iter(sys.stdin.readline, ""):
        try:
            cmd = json.loads(line)
        except ValueError:
            continue
        t0 = time.time()
        status = "ok"
        try:
            if cmd.get("op") == "run":
                run_file(cmd["path"])
            elif cmd.get("op") == "exec":
                exec_line(cmd.get("code", ""))
        except KeyboardInterrupt:
            status = "interrupted"
            sys.stderr.write("\nKeyboardInterrupt — выполнение остановлено\n")
        except SystemExit as e:
            if e.code not in (None, 0):
                status = "error"
                sys.stderr.write(f"SystemExit: {e.code}\n")
        except BaseException:
            status = "error"
            print_error()
        try:
            sync_output()
        except KeyboardInterrupt:
            pass
        send({"t": "done", "id": cmd.get("id"), "status": status, "ms": int((time.time() - t0) * 1000)})


if __name__ == "__main__":
    while True:
        try:
            main()
            break
        except KeyboardInterrupt:  # «Остановить», когда ничего не выполняется
            continue
