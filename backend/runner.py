"""Запуск кода и тестов.

Worker — процесс runtime/worker.py в рабочей папке (попытки или редактора задачи): «Запустить» и
строки «Консоли» выполняются в нём, переменные скрипта остаются доступны в консоли.
Тесты — отдельный процесс `python -m pytest` в изолированной копии папки.
Вывод любых запусков идёт заданиями (job): клиент опрашивает job и получает вывод по мере появления."""
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

RUNTIME = Path(__file__).parent / "runtime"
MARK = "\x1eRECALL"
IDLE_LIMIT = 30 * 60
MAX_OUTPUT = 3_000_000  # символов вывода на одно задание


def child_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    env.update(PYTHONPATH=str(RUNTIME), MPLBACKEND="Agg", PYTHONUNBUFFERED="1",
               PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    return env


# ---------- задания: вывод по мере выполнения ----------

class Job:
    def __init__(self, kind: str):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.state = "queued"  # queued | running | done
        self.outputs: list[dict] = []
        self.rev = 0  # растёт, когда уже отданный вывод переписан (склейка текста)
        self.result = None
        self.created = time.time()
        self._partial = {"stdout": "", "stderr": ""}
        self._size = 0
        self.lock = threading.Lock()

    def _push_text(self, stream: str, text: str):
        if not text:
            return
        if self._size > MAX_OUTPUT:
            return
        self._size += len(text)
        if self._size > MAX_OUTPUT:
            text += "\n… вывод обрезан (слишком много)\n"
        last = self.outputs[-1] if self.outputs else None
        if last and last["type"] == "stream" and last["name"] == stream:
            last["text"] += text
            self.rev += 1
        else:
            self.outputs.append({"type": "stream", "name": stream, "text": text})

    def add(self, stream: str, text: str):
        """Текст процесса; строки «\\x1eRECALL{json}» — события show() (таблица, картинка)."""
        with self.lock:
            buf = self._partial[stream] + text
            while True:
                i = buf.find(MARK)
                if i < 0:
                    break
                self._push_text(stream, buf[:i])
                j = buf.find("\n", i)
                if j < 0:
                    buf = buf[i:]
                    self._partial[stream] = buf
                    return
                try:
                    self.outputs.append({"type": "rich", **json.loads(buf[i + len(MARK):j])})
                except ValueError:
                    self._push_text(stream, buf[i:j + 1])
                buf = buf[j + 1:]
            keep = next((k for k in range(len(MARK) - 1, 0, -1) if buf.endswith(MARK[:k])), 0)
            self._push_text(stream, buf[:len(buf) - keep] if keep else buf)
            self._partial[stream] = buf[len(buf) - keep:] if keep else ""

    def note(self, text: str, stream: str = "stderr"):
        with self.lock:
            self._push_text(stream, text)

    def finish(self, result: dict):
        with self.lock:
            for s, rest in self._partial.items():
                self._push_text(s, rest)
            self.result = result
            self.state = "done"
            self.rev += 1

    def poll(self, have: int, rev: int) -> dict:
        with self.lock:
            full = rev != self.rev or have > len(self.outputs)
            outs = self.outputs if full else self.outputs[have:]
            return {"state": self.state, "rev": self.rev, "reset": full,
                    "outputs": [dict(o) for o in outs], "result": self.result}


JOBS: dict[str, Job] = {}


def new_job(kind: str) -> Job:
    now = time.time()
    for jid, j in list(JOBS.items()):
        if j.state == "done" and now - j.created > 900:
            JOBS.pop(jid, None)
    job = Job(kind)
    JOBS[job.id] = job
    return job


# ---------- процесс выполнения (консоль + «Запустить») ----------

class Worker:
    def __init__(self, key: str, python: str, cwd: str, task_id: int):
        self.key, self.python, self.cwd, self.task_id = key, python, cwd, task_id
        self.seq = threading.Lock()  # команды выполняются по одной, как в консоли
        self.current: Job | None = None
        self.done = threading.Event()
        self.done_msg = None
        self.ready = threading.Event()
        self.last_used = time.time()
        self.info = {}
        self.cmd_id = 0
        self.proc = subprocess.Popen(
            [python, "-u", "-X", "utf8", str(RUNTIME / "worker.py")], cwd=cwd, env=child_env(),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", bufsize=1, start_new_session=True)
        threading.Thread(target=self._read_proto, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_proto(self):
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            t = msg.get("t")
            if t == "ready":
                self.info = msg
                self.ready.set()
            elif t == "out" and self.current:
                self.current.add(msg["s"], msg["text"])
            elif t == "done":
                self.done_msg = msg
                self.done.set()
        self.ready.set()
        self.done.set()  # процесс умер — никого не ждём вечно

    def _read_stderr(self):
        """Ошибки до перенаправления вывода (например, нет такого python)."""
        for line in self.proc.stderr:
            if self.current:
                self.current.note(line)

    def alive(self) -> bool:
        return self.proc.poll() is None

    def run(self, job: Job, cmd: dict, timeout: float):
        with self.seq:
            self.last_used = time.time()
            job.state = "running"
            if not self.ready.wait(30) or not self.alive():
                job.note("процесс выполнения не запустился (проверьте окружение Python задачи)\n")
                job.finish({"status": "error", "ms": 0})
                return
            self.cmd_id += 1
            self.current, self.done_msg = job, None
            self.done.clear()
            t0 = time.time()
            try:
                self.proc.stdin.write(json.dumps({**cmd, "id": self.cmd_id}) + "\n")
                self.proc.stdin.flush()
            except OSError:
                job.note("процесс выполнения завершился\n")
            if not self.done.wait(timeout):
                job.note(f"\nпревышен лимит {timeout:.0f} с — останавливаю\n")
                self.interrupt()
                if not self.done.wait(5):
                    job.note("процесс не ответил на остановку и перезапущен (переменные сброшены)\n")
                    self.kill()
                status = "timeout"
            else:
                status = (self.done_msg or {}).get("status", "error") if self.alive() or self.done_msg else "error"
                if not self.done_msg:
                    job.note("процесс выполнения завершился (возможно, не хватило памяти)\n")
            self.current = None
            self.last_used = time.time()
            job.finish({"status": status, "ms": int((time.time() - t0) * 1000)})

    def interrupt(self):
        if self.alive():
            try:
                os.kill(self.proc.pid, signal.SIGINT)
            except OSError:
                pass

    def kill(self):
        if self.alive():
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except OSError:
                self.proc.kill()


WORKERS: dict[str, Worker] = {}
_reg = threading.Lock()


def get_worker(key: str, python: str, cwd: str, task_id: int) -> Worker:
    with _reg:
        w = WORKERS.get(key)
        if w and (not w.alive() or w.python != python or w.cwd != cwd):
            w.kill()
            w = None
        if w is None:
            w = WORKERS[key] = Worker(key, python, cwd, task_id)
        return w


def outputs_snapshot(job, tail=20000, limit=400_000) -> list[dict]:
    """Вывод задания для хранения в базе: хвост каждого текстового блока, не больше limit всего."""
    outs, size = [], 0
    for o in job.outputs:
        o = dict(o)
        if o.get("type") == "stream":
            o["text"] = o["text"][-tail:]
        size += len(json.dumps(o, ensure_ascii=False))
        if size > limit:
            break
        outs.append(o)
    return outs


def submit(key: str, python: str, cwd: str, task_id: int, cmd: dict, timeout: float, on_done=None) -> str:
    """on_done(job) — после завершения (например, запомнить вывод у попытки)."""
    job = new_job(cmd.get("op", "run"))

    def go():
        try:
            get_worker(key, python, cwd, task_id).run(job, cmd, timeout)
        except Exception as e:
            job.note(f"не удалось выполнить: {e}\n")
            job.finish({"status": "error", "ms": 0})
        if on_done:
            try:
                on_done(job)
            except Exception as e:
                print("on_done:", e)

    threading.Thread(target=go, daemon=True).start()
    return job.id


def interrupt(key: str):
    w = WORKERS.get(key)
    if w:
        w.interrupt()
    for job in JOBS.values():  # и прогон тестов этой попытки
        if job.state != "done" and getattr(job, "owner", None) == key and getattr(job, "proc", None):
            kill_tree(job.proc)


def stop(key: str):
    w = WORKERS.pop(key, None)
    if w:
        w.kill()


def stop_task_workers(task_id: int):
    for key, w in list(WORKERS.items()):
        if w.task_id == task_id:
            stop(key)


def state(key: str) -> dict:
    w = WORKERS.get(key)
    if not w or not w.alive():
        return {"state": "off"}
    return {"state": "busy" if w.seq.locked() else "idle", "python": w.info.get("python"),
            "idle_left": max(0, int(IDLE_LIMIT - (time.time() - w.last_used)))}


def stop_all():
    for key in list(WORKERS):
        stop(key)


def start_reaper():
    def loop():
        while True:
            time.sleep(60)
            now = time.time()
            for key, w in list(WORKERS.items()):
                if not w.seq.locked() and now - w.last_used > IDLE_LIMIT:
                    stop(key)
    threading.Thread(target=loop, daemon=True).start()


# ---------- pytest ----------

def kill_tree(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass


def run_pytest(python: str, run_dir: Path, timeout: float, job: Job | None = None) -> dict:
    """python -m pytest в папке прогона. Вывод — в job по мере появления; результат — из junit XML."""
    report = run_dir / ".recall_junit.xml"
    cmd = [python, "-m", "pytest", "tests", "-q", "-rN", "--tb=short", "--color=no", "-p", "no:cacheprovider",
           f"--junitxml={report}", "-o", "junit_family=xunit1"]
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=run_dir, env=child_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", bufsize=1, start_new_session=True)
    if job is not None:
        job.proc = proc
    out = []
    timer = threading.Timer(timeout, lambda: (out.append(f"\nпревышен лимит {timeout:.0f} с — прогон остановлен\n"),
                                               kill_tree(proc)))
    timer.start()
    try:
        for line in proc.stdout:
            out.append(line)
            if job is not None:
                job.add("stdout", line)
    finally:
        timer.cancel()
    proc.wait()
    timed_out = any("превышен лимит" in x for x in out[-2:])
    text = "".join(out)
    if timed_out and job is not None:
        job.note(out[-1])
    res = {"ms": int((time.time() - t0) * 1000), "exit": proc.returncode, "timeout": timed_out,
           "output": text[-20000:], "tests": {}, "collection_errors": []}
    if "No module named pytest" in text:
        res["fatal"] = f"в окружении нет pytest — установите: {python} -m pip install pytest"
        return res
    if not report.exists():
        res["fatal"] = "pytest не выдал отчёт" + (" (остановлен по лимиту времени)" if timed_out else "")
        return res
    for case in ET.parse(report).getroot().iter("testcase"):
        cls, name = case.get("classname", ""), case.get("name", "")
        file = (case.get("file") or cls.replace(".", "/") + ".py")
        failure, error, skipped = case.find("failure"), case.find("error"), case.find("skipped")
        if not cls and error is not None:  # ошибка сбора: тесты файла не запустились (импорт и т.п.)
            text = error.text or ""
            # «collection failure» ничего не говорит — берём настоящую причину из traceback
            reason = [l.strip().lstrip("E").strip() for l in text.splitlines() if "Error" in l or "error:" in l]
            res["collection_errors"].append({"file": name, "message": reason[-1] if reason else error.get("message", ""),
                                             "text": text[-4000:]})
            continue
        node = failure if failure is not None else error
        status = "fail" if failure is not None else "error" if error is not None else \
            "skip" if skipped is not None else "pass"
        tid = f"{Path(file).name}::{name}"
        res["tests"][tid] = {"id": tid, "file": Path(file).name, "name": name, "status": status,
                             "time": float(case.get("time") or 0), "message": (node.get("message") if node is not None else "") or "",
                             "text": ((node.text or "") if node is not None else "")[-4000:]}
    return res
