"""Ollama HTTP transport — the ONLY module that talks to the model server.

Kept deliberately thin and dependency-free (config + httpx only) so the answer
layer (`llm.py`) and any future caller share one client and one set of request
options. It carries no answer logic: it does not decide WHAT to ask, only how to
send it and stream it back.
"""
import json
from typing import Iterator

import httpx

from . import config


def _opts(options: dict | None) -> dict:
    o = {
        "num_predict": config.LLM_NUM_PREDICT,
        "temperature": config.LLM_TEMPERATURE,
        "top_p": config.LLM_TOP_P,
        "repeat_penalty": config.LLM_REPEAT_PENALTY,
    }
    if options:
        o.update(options)
    return o


def _ollama_chat(messages: list[dict[str, str]], options: dict | None = None) -> str:
    resp = httpx.post(
        f"{config.OLLAMA_HOST}/api/chat",
        json={"model": config.OLLAMA_MODEL, "messages": messages, "stream": False,
              "keep_alive": config.OLLAMA_KEEP_ALIVE, "options": _opts(options)},
        timeout=config.LLM_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def _ollama_stream(messages: list[dict[str, str]], options: dict | None = None) -> Iterator[str]:
    """Yield content deltas as the model generates them (Ollama stream=true)."""
    with httpx.stream(
        "POST", f"{config.OLLAMA_HOST}/api/chat",
        json={"model": config.OLLAMA_MODEL, "messages": messages, "stream": True,
              "keep_alive": config.OLLAMA_KEEP_ALIVE, "options": _opts(options)},
        timeout=config.LLM_TIMEOUT,
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            piece = (obj.get("message") or {}).get("content")
            if piece:
                yield piece
            if obj.get("done"):
                break


def warmup() -> bool:
    """Pre-load the model into memory so the first real query is fast."""
    try:
        httpx.post(
            f"{config.OLLAMA_HOST}/api/chat",
            json={"model": config.OLLAMA_MODEL,
                  "messages": [{"role": "user", "content": "ok"}],
                  "stream": False, "keep_alive": config.OLLAMA_KEEP_ALIVE,
                  "options": {"num_predict": 1}},
            timeout=config.LLM_TIMEOUT,
        ).raise_for_status()
        return True
    except Exception:
        return False
