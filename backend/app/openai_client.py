"""OpenAI HTTP transport — the specification narrative's model server.

Deliberately mirrors `ollama_client`: same call signatures (`messages`,
`options`) and the same return shapes, so `llm.py` can swap one for the other
without knowing which is behind it. Like that module it carries no answer logic
and no new dependency — httpx only, the same client the rest of the app uses.

SCOPE: this exists for the *specification narrative* only (see
`config.SPEC_LLM_PROVIDER`). It writes prose around numbers the engine already
computed. It never produces a number — golden rule #2 is unaffected by which
model writes the sentences, and nothing here is wired into the calculation,
pricing, lookup or analytics paths.
"""
import json
from typing import Iterator

import httpx

from . import config
from .observability import trace as _obs


class OpenAIUnavailable(RuntimeError):
    """Raised when OpenAI is unconfigured or refuses the request, so the caller
    can fall back to the local model instead of losing the specification."""


def _headers() -> dict[str, str]:
    if not config.OPENAI_API_KEY:
        raise OpenAIUnavailable("OPENAI_API_KEY is not set")
    return {"Authorization": f"Bearer {config.OPENAI_API_KEY}",
            "Content-Type": "application/json"}


def _body(messages: list[dict[str, str]], options: dict | None, stream: bool) -> dict:
    """Translate our Ollama-shaped options to the OpenAI chat-completions body.

    `repeat_penalty` is deliberately NOT mapped: Ollama's is a multiplicative
    logit penalty (~1.0-1.3) and OpenAI's `frequency_penalty` is an additive
    -2..2 scale. There is no honest conversion, and guessing one would quietly
    change the prose. We drop it and let the model's own defaults apply.
    """
    o = options or {}
    body: dict = {
        "model": config.OPENAI_MODEL,
        "messages": messages,
        "stream": stream,
        "temperature": o.get("temperature", config.LLM_TEMPERATURE),
        "top_p": o.get("top_p", config.LLM_TOP_P),
    }
    n_predict = o.get("num_predict", config.SPEC_NUM_PREDICT)
    if n_predict:
        body[config.OPENAI_MAX_TOKENS_FIELD] = int(n_predict)
    return body


def _post(body: dict, stream: bool):
    """POST to chat/completions, retrying once across the max_tokens rename.

    Reasoning-era models reject `max_tokens` and require `max_completion_tokens`;
    older ones reject the new name. Rather than make the operator discover that
    through a 400, we detect the complaint and retry with the other spelling
    (and remember it for the process, so it costs one request, once).
    """
    url = f"{config.OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    try:
        return _send(url, body, stream)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 400:
            raise
        detail = exc.response.text or ""
        swapped = _swap_max_tokens(body, detail)
        if swapped is None:
            raise
        return _send(url, swapped, stream)


def _swap_max_tokens(body: dict, detail: str) -> dict | None:
    """Return a copy of `body` using the other max-tokens field, or None if the
    400 was about something else entirely (a bad model name, a bad key, ...)."""
    if "max_tokens" not in detail and "max_completion_tokens" not in detail:
        return None
    old = config.OPENAI_MAX_TOKENS_FIELD
    new = "max_completion_tokens" if old == "max_tokens" else "max_tokens"
    if old not in body:
        return None
    out = dict(body)
    out[new] = out.pop(old)
    config.OPENAI_MAX_TOKENS_FIELD = new     # stick, so we pay this once
    return out


def _send(url: str, body: dict, stream: bool):
    if stream:
        ctx = httpx.stream("POST", url, json=body, headers=_headers(),
                           timeout=config.OPENAI_TIMEOUT)
        r = ctx.__enter__()
        try:
            r.raise_for_status()
        except Exception:
            ctx.__exit__(None, None, None)
            raise
        return ctx, r
    resp = httpx.post(url, json=body, headers=_headers(), timeout=config.OPENAI_TIMEOUT)
    resp.raise_for_status()
    return resp


def _openai_chat(messages: list[dict[str, str]], options: dict | None = None) -> str:
    with _obs.span("llm.chat", "llm") as _s:
        _s.detail(model=config.OPENAI_MODEL, provider="openai", streamed=False,
                  messages=len(messages or []))
        try:
            resp = _post(_body(messages, options, stream=False), stream=False)
        except httpx.HTTPStatusError as exc:
            raise OpenAIUnavailable(
                f"OpenAI {exc.response.status_code}: {exc.response.text[:200]}") from exc
        except httpx.HTTPError as exc:
            raise OpenAIUnavailable(f"OpenAI unreachable: {exc}") from exc
        choices = resp.json().get("choices") or []
        if not choices:
            raise OpenAIUnavailable("OpenAI returned no choices")
        return (choices[0].get("message", {}).get("content") or "").strip()


def _openai_stream(messages: list[dict[str, str]],
                   options: dict | None = None) -> Iterator[str]:
    """Yield content deltas as the model generates them (OpenAI SSE)."""
    try:
        ctx, r = _post(_body(messages, options, stream=True), stream=True)
    except httpx.HTTPStatusError as exc:
        raise OpenAIUnavailable(
            f"OpenAI {exc.response.status_code}: {exc.response.text[:200]}") from exc
    except httpx.HTTPError as exc:
        raise OpenAIUnavailable(f"OpenAI unreachable: {exc}") from exc
    try:
        for line in r.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            for ch in obj.get("choices") or []:
                piece = (ch.get("delta") or {}).get("content")
                if piece:
                    yield piece
    finally:
        ctx.__exit__(None, None, None)


def available() -> bool:
    """Whether a spec may be routed to OpenAI at all (key configured)."""
    return bool(config.OPENAI_API_KEY)
