"""LLM-слой: два провайдера (Ollama локально, Groq API), один интерфейс chat()."""
import json
import os

import httpx

from .db import SessionLocal, get_setting

DEFAULTS = {
    "llm_provider": "ollama",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3.1:8b",
    "groq_model": "llama-3.3-70b-versatile",
}


def settings() -> dict:
    with SessionLocal() as db:
        return {k: get_setting(db, k, v) for k, v in DEFAULTS.items()}


class LLMError(Exception):
    pass


def chat(messages: list[dict], want_json=False, timeout=180) -> str:
    s = settings()
    try:
        if s["llm_provider"] == "groq":
            return _groq(s, messages, want_json, timeout)
        return _ollama(s, messages, want_json, timeout)
    except httpx.HTTPError as e:
        raise LLMError(f"{s['llm_provider']}: {e}") from e


def _ollama(s, messages, want_json, timeout):
    body = {"model": s["ollama_model"], "messages": messages, "stream": False,
            "options": {"temperature": 0.1}}
    if want_json:
        body["format"] = "json"
    r = httpx.post(f"{s['ollama_url'].rstrip('/')}/api/chat", json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()["message"]["content"]


def _groq(s, messages, want_json, timeout):
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        raise LLMError("GROQ_API_KEY не задан в .env")
    body = {"model": s["groq_model"], "messages": messages, "temperature": 0.1}
    if want_json:
        body["response_format"] = {"type": "json_object"}
    r = httpx.post("https://api.groq.com/openai/v1/chat/completions", json=body,
                   headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def review_comment(title: str, reference: dict, mine: dict) -> dict:
    """Комментарий после сдачи: стиль и отличия от эталона. На оценку не влияет.
    Строго JSON {comment: str, differences: [str]}; кривой ответ -> один повтор -> LLMError."""
    def block(files):
        return "\n\n".join(f"### {name}\n```python\n{code}\n```" for name, code in sorted(files.items()))
    prompt = (
        f"Задача «{title}». Ниже эталонное решение и решение ученика, написанное по памяти.\n"
        "Коротко по-русски (2–4 предложения) оцени стиль и читаемость кода ученика и назови отличия от "
        "эталона в подходе. Не пересказывай код. Правильность проверяют тесты — её не оценивай.\n"
        'Ответь строго JSON: {"comment": "...", "differences": ["...", ...]}\n\n'
        f"ЭТАЛОН:\n{block(reference)}\n\nУЧЕНИК:\n{block(mine)}")
    messages = [{"role": "user", "content": prompt}]
    for _ in range(2):
        text = chat(messages, want_json=True, timeout=240)
        try:
            data = json.loads(text)
            if isinstance(data.get("comment"), str) and isinstance(data.get("differences"), list) \
                    and all(isinstance(x, str) for x in data["differences"]):
                return {"comment": data["comment"], "differences": data["differences"]}
        except (ValueError, AttributeError):
            pass
        messages += [{"role": "assistant", "content": text[:3000]},
                     {"role": "user", "content": 'Нужен строго JSON {"comment": строка, "differences": [строки]}.'}]
    raise LLMError("модель вернула ответ не в нужном формате")


def ping() -> dict:
    """Короткий запрос: ответ, время и какая модель ответила."""
    import time
    s = settings()
    t0 = time.time()
    answer = chat([{"role": "user", "content": "Ответь одним словом: ok"}], timeout=120)
    model = s["groq_model"] if s["llm_provider"] == "groq" else s["ollama_model"]
    return {"answer": answer.strip()[:200], "ms": int((time.time() - t0) * 1000),
            "provider": s["llm_provider"], "model": model}
