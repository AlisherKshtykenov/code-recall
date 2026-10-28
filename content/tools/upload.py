"""Загрузить папки задач в приложение тем же API, что «Загрузить папки» (multipart: files + paths).
python content/tools/upload.py [--base http://127.0.0.1:8000/api] content/tasks/recall content/slots/slot_metric …"""
import argparse
import json
import os
import urllib.request as u
import uuid

BASE = "http://127.0.0.1:8000/api"


def upload(dirs, base=BASE, preview=False):
    bnd, body = uuid.uuid4().hex, b""
    for d in dirs:
        root = os.path.dirname(os.path.abspath(d))
        for r, _, names in os.walk(d):
            if "__pycache__" in r:
                continue
            for n in names:
                if n.startswith("."):
                    continue
                full = os.path.join(r, n)
                rel = os.path.relpath(full, root)
                body += f'--{bnd}\r\nContent-Disposition: form-data; name="paths"\r\n\r\n{rel}\r\n'.encode()
                body += (f'--{bnd}\r\nContent-Disposition: form-data; name="files"; filename="{n}"\r\n'
                         "Content-Type: application/octet-stream\r\n\r\n").encode() + open(full, "rb").read() + b"\r\n"
    body += f"--{bnd}--\r\n".encode()
    req = u.Request(base + ("/tasks/upload/preview" if preview else "/tasks/upload"), data=body, method="POST",
                    headers={"Content-Type": f"multipart/form-data; boundary={bnd}"})
    return json.load(u.urlopen(req))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--preview", action="store_true")
    a = ap.parse_args()
    for r in upload(a.dirs, a.base, a.preview):
        print(r.get("folder"), r.get("status"), r.get("version", ""), r.get("error", ""))
