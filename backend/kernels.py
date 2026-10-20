"""Jupyter-ядра. Ключ ядра — строка: "a12" (попытка 12) или "r3" (эталон 3).
Каждое ядро запускается в рабочей папке эталона и на выбранном для эталона Python
(по умолчанию — Python самого приложения)."""
import hashlib
import json
import os
import queue
import re
import sys
import threading
import time
import uuid

from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager

from .db import DATA_DIR

SPEC_DIR = DATA_DIR / "kernelspec"
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
IDLE_LIMIT = {"r": 15 * 60, "a": 30 * 60}  # ядро эталона гасим после 15 мин простоя, попытки — 30
MAX_STREAM = 2_000_000  # символов stdout на ячейку — дальше обрезаем

# MIME-типы, которые отдаём фронтенду (application/javascript не исполняем — небезопасно)
MIMES = ("application/vnd.plotly.v1+json", "text/html", "image/svg+xml", "image/png", "image/jpeg",
         "image/gif", "text/markdown", "text/latex", "application/json", "text/plain")


def spec_name(python: str) -> str:
    """Отдельный kernelspec на каждый интерпретатор."""
    name = "cr-" + hashlib.sha1(python.encode()).hexdigest()[:10]
    d = SPEC_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "kernel.json").write_text(json.dumps({
        "argv": [python, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": f"CODE RECALL ({python})", "language": "python"}))
    return name


def plain(text: str) -> str:
    return ANSI.sub("", text or "")


class Kernel:
    def __init__(self, python: str | None = None, cwd: str | None = None):
        python = python or sys.executable
        self.python, self.cwd = python, cwd
        name = spec_name(python)
        self.km = KernelManager(kernel_name=name,
                                kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(SPEC_DIR)],
                                                                      ensure_native_kernel=False))
        env = {**os.environ,
               "PLOTLY_RENDERER": "plotly_mimetype",  # plotly -> JSON, рисуем на фронте
               "MPLBACKEND": "module://matplotlib_inline.backend_inline",
               "PYTHONUNBUFFERED": "1"}
        env.pop("PYTHONPATH", None)  # не подмешиваем пакеты приложения в чужой venv
        self.km.start_kernel(cwd=cwd, env=env)
        self.kc = self.km.client()
        self.kc.start_channels()
        self.kc.wait_for_ready(timeout=90)
        self.lock = threading.Lock()
        self.seq = threading.Lock()  # очередь заданий из ноутбука: ячейка + её пост-обработка подряд
        self.last_used = time.time()
        self.count = 0

    def execute(self, code: str, timeout: float = 60, sink=None, history: bool = True) -> dict:
        """Выполнить код. sink(outputs, changed_all) вызывается при каждом новом выводе —
        так фронтенд видит вывод, пока ячейка ещё работает."""
        with self.lock:
            self.last_used = time.time()
            if history:
                self.count += 1
            msg_id = self.kc.execute(code, store_history=history)
            outputs, status, stream_len = [], "ok", 0
            pending_clear = False  # clear_output(wait=True): очистить перед следующим выводом
            t0 = time.time()
            deadline = t0 + timeout

            def push(out, rewrite=False):
                nonlocal pending_clear
                if pending_clear:
                    outputs.clear()
                    pending_clear, rewrite = False, True
                if out["type"] == "stream" and outputs and outputs[-1]["type"] == "stream" \
                        and outputs[-1]["name"] == out["name"]:
                    outputs[-1]["text"] += out["text"]  # склеиваем stdout, как Jupyter
                    rewrite = True
                else:
                    outputs.append(out)
                if sink:
                    sink(outputs, rewrite)

            while True:
                left = deadline - time.time()
                if left <= 0:
                    self.km.interrupt_kernel()
                    text = f"ячейка выполнялась дольше {timeout:.0f} с — прервано"
                    if not self._drain(msg_id, 5):
                        # код глушит KeyboardInterrupt или висит в C — ядро не ответило
                        self.km.restart_kernel(now=True)
                        self.kc.wait_for_ready(timeout=90)
                        self.count = 0
                        text += "; ядро не ответило на прерывание и перезапущено (переменные сброшены)"
                    push({"type": "error", "ename": "TimeoutError", "evalue": text, "traceback": ""})
                    status = "timeout"
                    break
                try:
                    msg = self.kc.get_iopub_msg(timeout=min(left, 0.5))
                except queue.Empty:
                    continue
                if msg["parent_header"].get("msg_id") != msg_id:
                    continue
                t, c = msg["msg_type"], msg["content"]
                if t == "status" and c["execution_state"] == "idle":
                    break
                if t == "clear_output":
                    if c.get("wait"):
                        pending_clear = True
                    else:
                        outputs.clear()
                        if sink:
                            sink(outputs, True)
                    continue
                if t == "update_display_data":
                    did = c.get("transient", {}).get("display_id")
                    for i, o in enumerate(outputs):
                        if did and o.get("display_id") == did:
                            outputs[i] = {**self._display(c), "display_id": did}
                            if sink:
                                sink(outputs, True)
                    continue
                if t == "stream":
                    if stream_len > MAX_STREAM:
                        continue
                    stream_len += len(c["text"])
                    text = c["text"] if stream_len <= MAX_STREAM else c["text"] + "\n… вывод обрезан\n"
                    push({"type": "stream", "name": c["name"], "text": text})
                elif t in ("execute_result", "display_data"):
                    out = self._display(c)
                    if t == "execute_result":
                        out["count"] = c.get("execution_count")
                    did = c.get("transient", {}).get("display_id")
                    if did:
                        out["display_id"] = did
                    push(out)
                elif t == "error":
                    status = "error"
                    # traceback с ANSI-цветами — фронтенд раскрашивает, как Jupyter
                    push({"type": "error", "ename": c["ename"], "evalue": plain(c["evalue"]),
                          "traceback": "\n".join(c["traceback"])})
            self.last_used = time.time()
            return {"count": self.count, "outputs": outputs, "status": status,
                    "elapsed_ms": int((time.time() - t0) * 1000)}

    @staticmethod
    def _display(c) -> dict:
        data = c.get("data", {})
        keep = {m: data[m] for m in MIMES if m in data}
        return {"type": "display", "data": keep}

    def _drain(self, msg_id, timeout):
        end = time.time() + timeout
        while time.time() < end:
            try:
                msg = self.kc.get_iopub_msg(timeout=0.5)
            except queue.Empty:
                continue
            if (msg["parent_header"].get("msg_id") == msg_id and msg["msg_type"] == "status"
                    and msg["content"]["execution_state"] == "idle"):
                return True
        return False

    def interrupt(self):
        self.km.interrupt_kernel()

    def restart(self):
        self.km.restart_kernel(now=True)
        self.kc.wait_for_ready(timeout=90)
        self.count = 0

    def shutdown(self):
        try:
            self.kc.stop_channels()
            self.km.shutdown_kernel(now=True)
        except Exception:
            pass


def first_error(res: dict) -> str | None:
    for o in res["outputs"]:
        if o["type"] == "error":
            return f"{o['ename']}: {o['evalue']}"
    return None


def stream_text(res: dict) -> str:
    return "".join(o.get("text", "") for o in res["outputs"] if o["type"] == "stream")


# ---------- реестр ядер ----------
_kernels: dict[str, Kernel] = {}
_starting: dict[str, threading.Event] = {}
_errors: dict[str, str] = {}
_cancelled: set[str] = set()  # stop() пришёл, пока ядро ещё запускалось
_reg_lock = threading.Lock()


def start(key: str, python: str | None = None, cwd: str | None = None):
    """Запуск ядра в фоне: пользователь уже читает задание, пока ядро стартует."""
    reap_idle()
    with _reg_lock:
        _cancelled.discard(key)
        if key in _kernels or key in _starting:
            return
        ev = _starting[key] = threading.Event()

    def run():
        try:
            k = Kernel(python, cwd)
            if key in _cancelled:
                _cancelled.discard(key)
                k.shutdown()
            else:
                _kernels[key] = k
        except Exception as e:
            _errors[key] = str(e)
        finally:
            _starting.pop(key, None)
            ev.set()

    threading.Thread(target=run, daemon=True).start()


def get(key: str, python: str | None = None, cwd: str | None = None, wait: float = 120) -> Kernel:
    if key not in _kernels and key not in _starting:
        start(key, python, cwd)
    ev = _starting.get(key)
    if ev:
        ev.wait(wait)
    if key in _errors:
        raise RuntimeError("ядро не запустилось: " + _errors.pop(key))
    return _kernels[key]


def state(key: str) -> str:
    if key in _starting:
        return "starting"
    k = _kernels.get(key)
    if not k:
        return "off"
    return "busy" if k.lock.locked() or k.seq.locked() else "idle"


def interrupt(key: str):
    k = _kernels.get(key)
    if k:
        k.interrupt()


def stop(key: str):
    with _reg_lock:
        if key in _starting:
            _cancelled.add(key)
    k = _kernels.pop(key, None)
    if k:
        k.shutdown()


def stop_all():
    _cancelled.update(_starting)
    for key in list(_kernels):
        stop(key)


def idle_left(key: str) -> int | None:
    """Сколько секунд осталось до автоматического выключения ядра."""
    k = _kernels.get(key)
    if not k:
        return None
    return max(0, int(IDLE_LIMIT.get(key[0], 1800) - (time.time() - k.last_used)))


def reap_idle():
    now = time.time()
    for key, k in list(_kernels.items()):
        if now - k.last_used > IDLE_LIMIT.get(key[0], 1800) and not k.lock.locked() and not k.seq.locked():
            stop(key)


def start_reaper():
    def loop():
        while True:
            time.sleep(60)
            try:
                reap_idle()
            except Exception as e:
                print("reaper:", e)
    threading.Thread(target=loop, daemon=True).start()


# ---------- выполнение с выводом по мере работы ----------
_jobs: dict[str, dict] = {}


def submit(key: str, code: str, timeout: float, python=None, cwd=None, post=None) -> str:
    """Запустить ячейку в фоне. Ячейки одного ядра выполняются по очереди (как в Jupyter).
    post(kernel, result) -> [выводы] выполняется сразу после ячейки, до следующей в очереди."""
    job_id = uuid.uuid4().hex[:12]
    job = {"key": key, "state": "queued", "outputs": [], "rev": 0, "result": None, "created": time.time()}
    _jobs[job_id] = job

    def sink(outputs, rewrite):
        job["outputs"] = [dict(o) for o in outputs]
        job["rev"] += 1 if rewrite else 0
        job["state"] = "running"

    def run():
        try:
            k = get(key, python, cwd)
            with k.seq:
                job["state"] = "running"
                res = k.execute(code, timeout=timeout, sink=sink)
                extra = []
                if post:
                    try:
                        extra = post(k, res) or []
                    except Exception as e:
                        extra = [{"type": "stream", "name": "stderr", "text": f"пост-обработка не удалась: {e}\n"}]
                k.last_used = time.time()
            job["outputs"], job["result"] = res["outputs"] + extra, {"count": res["count"], "status": res["status"],
                                                                     "elapsed_ms": res["elapsed_ms"]}
        except Exception as e:
            job["outputs"] = [{"type": "error", "ename": "KernelError", "evalue": str(e), "traceback": ""}]
            job["result"] = {"count": None, "status": "error", "elapsed_ms": 0}
        job["rev"] += 1
        job["state"] = "done"
        _gc_jobs()

    threading.Thread(target=run, daemon=True).start()
    return job_id


def poll(job_id: str, have: int, rev: int) -> dict:
    """have — сколько выводов уже есть у клиента, rev — версия списка у клиента.
    Если список переписан (clear_output, склейка stdout), отдаём его целиком."""
    job = _jobs.get(job_id)
    if job is None:
        return {"state": "lost"}
    outs = job["outputs"]
    full = job["rev"] != rev or have > len(outs)
    return {"state": job["state"], "rev": job["rev"], "reset": full,
            "outputs": outs if full else outs[have:], "result": job["result"]}


def _gc_jobs():
    now = time.time()
    for jid, j in list(_jobs.items()):
        if j["state"] == "done" and now - j["created"] > 600:
            _jobs.pop(jid, None)
