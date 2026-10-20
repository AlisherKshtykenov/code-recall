"""LLM-слой: два провайдера (Ollama локально, Groq API), один интерфейс chat()."""
import json
import os
import re

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


def chat_json(messages: list[dict], **kw) -> dict:
    text = chat(messages, want_json=True, **kw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)  # модель обернула JSON в текст
        if m:
            return json.loads(m.group(0))
        raise LLMError(f"LLM вернул не JSON: {text[:300]}")


def suggest_split(source: str) -> list[dict]:
    """Просим LLM разбить .py на логические блоки — только номерами строк."""
    numbered = "\n".join(f"{i + 1:4d}| {l}" for i, l in enumerate(source.splitlines()))
    prompt = (
        "Разбей Python-файл на логические блоки для заучивания: импорты, "
        "классы, функции, подготовка данных, цикл обучения, оценка и т.п. "
        "Каждый блок — цельный смысловой кусок. Блоки идут подряд и покрывают весь файл.\n"
        'Ответь строго JSON: {"blocks": [{"title": "...", "kind": '
        '"imports|class|function|train|code|main", "start_line": N, "end_line": M}]}\n\n'
        + numbered)
    data = chat_json([{"role": "user", "content": prompt}])
    return data.get("blocks", [])


def describe_blocks(title: str, blocks: list[tuple[str, str]]) -> dict:
    """Описания заданий словами, без кода: что должен делать каждый блок."""
    parts = "\n\n".join(f"### Блок {i + 1}: {t}\n```python\n{code}\n```"
                        for i, (t, code) in enumerate(blocks))
    prompt = (
        f"Ниже эталонный код «{title}», разбитый на блоки. Я буду писать его по памяти.\n"
        "Сформулируй задание СЛОВАМИ по-русски, без кода, без готовых строк и без "
        "подсказок по синтаксису. Можно называть, что блок должен сделать, какие "
        "сущности создать, какие входы/выходы и размерности, но не как это написать.\n"
        '1) "task": задача целиком в 2–4 предложениях;\n'
        '2) "blocks": список описаний, по одному на блок, в том же порядке (1–3 предложения).\n'
        'Ответь строго JSON: {"task": "...", "blocks": ["...", ...]}\n\n' + parts)
    return chat_json([{"role": "user", "content": prompt}])


def suggest_tests(title: str, blocks: list[tuple[str, str]]) -> list[dict]:
    parts = "\n\n".join(f"### Блок «{t}»\n```python\n{code}\n```" for t, code in blocks)
    prompt = (
        f"Ниже эталонный код «{title}» по блокам. Предложи 3–8 тестов результата.\n"
        "Тест — короткий Python-код, который выполняется ПОСЛЕ всего кода в том же пространстве имён; "
        "значение последнего выражения — результат. Тест не должен зависеть от имён локальных "
        "переменных внутри функций — только от публичных функций/классов/переменных верхнего уровня.\n"
        "mode=\"match\": результат сравнивается с эталоном (пример: quicksort([3,1,2]); "
        "tuple(SimpleCNN()(torch.randn(8,3,32,32)).shape); sum(p.numel() for p in model.parameters())).\n"
        "mode=\"assert\": результат должен быть True (пример: losses[-1] < losses[0]).\n"
        "Если есть случайность — фиксируй torch.manual_seed / np.random.seed внутри теста.\n"
        'Ответь строго JSON: {"tests": [{"block": "<название блока>", "name": "...", '
        '"code": "...", "mode": "match|assert"}]}\n\n' + parts)
    data = chat_json([{"role": "user", "content": prompt}])
    tests = data.get("tests", [])
    return tests if isinstance(tests, list) else []


def ping() -> dict:
    """Короткий запрос: ответ, время и какая модель ответила."""
    import time
    s = settings()
    t0 = time.time()
    answer = chat([{"role": "user", "content": "Ответь одним словом: ok"}], timeout=120)
    model = s["groq_model"] if s["llm_provider"] == "groq" else s["ollama_model"]
    return {"answer": answer.strip()[:200], "ms": int((time.time() - t0) * 1000),
            "provider": s["llm_provider"], "model": model}
