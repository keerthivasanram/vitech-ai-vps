"""Local LLM client (Ollama HTTP API) with graceful fallback.

One planner (`plan_answer`) decides HOW to answer; both the non-streaming
(`generate_answer`) and streaming (`stream_answer`) paths run that plan, so they
stay perfectly consistent.
"""
import json
import re
from typing import Any, Iterator

import httpx

from . import config
from .analytics import deterministic_analytics, record_detail
from .prompt import (build_messages, fallback_answer, knowledge_spec_messages,
                     small_talk, spec_messages, spec_summary, spec_writeup,
                     verify_messages)

_STRUCTURED = {"specification", "quotation"}


# --- Ollama transport -------------------------------------------------------

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


# --- anti-hallucination helpers ---------------------------------------------

def _chat_temperature(analysis: dict) -> float:
    """Lower temperature for factual work, warmer for open conversation."""
    if analysis.get("data_lookup"):
        return 0.2                                   # quoting stored facts
    if analysis.get("mode") in ("analytical", "comparison"):
        return 0.25                                  # compute / tabulate over data
    if analysis.get("intent") in ("concept", "comparison", "search"):
        return 0.4                                   # technical explanation
    return 0.6                                        # general chat


def _verify(question: str, hits: list[dict[str, Any]], draft: str) -> str:
    """Second pass: strip/repair any claim the retrieved data doesn't support.
    Best-effort — if the model is slow or down, keep the draft."""
    try:
        return _ollama_chat(
            verify_messages(question, hits, draft),
            {"temperature": 0.0, "num_predict": config.LLM_NUM_PREDICT},
        )
    except Exception:
        return draft


_WORD = re.compile(r"\S+\s*")


def _word_chunks(text: str, group: int = 5) -> Iterator[str]:
    """Break a ready string into small multi-word pieces for a fast typing effect
    (grouping keeps the SSE event count — and render cost — low)."""
    toks = _WORD.findall(text or "")
    for i in range(0, len(toks), group):
        yield "".join(toks[i:i + group])


# --- the planner ------------------------------------------------------------

def plan_answer(question, hits, analysis, history=None) -> dict[str, Any]:
    """Decide how to answer. Returns a plan dict:
      kind="static": {text, extra}                — no LLM, send as-is
      kind="stream": {messages, options, verify, extra} — LLM generates it
    """
    intent = analysis.get("intent")

    if intent in _STRUCTURED:
        if analysis.get("spec_mode") == "knowledge":
            return {"kind": "stream",
                    "messages": knowledge_spec_messages(question, analysis),
                    # low temperature: a consulting framework, not creative invention
                    "options": {"num_predict": config.LLM_NUM_PREDICT, "temperature": 0.25},
                    "verify": False, "extra": {"spec_mode": "knowledge"}}
        # Data-mode spec is rendered DETERMINISTICALLY (no LLM narrative), so the
        # prose can never drift from the analysed numbers, and it reads as a clean
        # ChatGPT-style write-up rather than a dense table panel.
        if not analysis.get("technical_details"):       # no close project found
            return {"kind": "static", "text": spec_summary(analysis),
                    "extra": {"deterministic": True, "spec_mode": "data"}}
        return {"kind": "static", "text": spec_writeup(analysis),
                "extra": {"deterministic": True, "spec_mode": "data"}}

    canned = small_talk(question)
    if canned is not None:
        return {"kind": "static", "text": canned,
                "extra": {"deterministic": True, "small_talk": True}}

    # A NAMED record's data ("given data of C2C") is rendered EXACTLY from the
    # stored fields — no LLM, no hijack by the corpus analytics below.
    detail = record_detail(question)
    if detail is not None:
        return {"kind": "static", "text": detail,
                "extra": {"deterministic": True, "mode": "lookup"}}

    # Count / list / breakdown / client questions are answered EXACTLY from the
    # records — the LLM miscounts a corpus. Open-ended analytics fall through.
    analytics = deterministic_analytics(question)
    if analytics is not None:
        return {"kind": "static", "text": analytics,
                "extra": {"deterministic": True, "mode": "analytical"}}

    return {"kind": "stream",
            "messages": build_messages(question, hits, analysis, history),
            "options": {"temperature": _chat_temperature(analysis),
                        "num_predict": config.CHAT_NUM_PREDICT},
            # verify only direct data-lookups (where claims are checkable),
            # not general/technical answers that legitimately use world knowledge.
            "verify": bool(analysis.get("data_lookup")),
            "extra": {}}


def _spec_fallback_text(question, hits, analysis, extra) -> str:
    if analysis.get("intent") in _STRUCTURED:
        if extra.get("spec_mode") == "knowledge":
            return ("The local model isn't reachable right now, so I can't design "
                    "the specification. Start Ollama and try again.")
        return spec_summary(analysis)
    return fallback_answer(question, hits, analysis)


# --- non-streaming answer (used by /api/query) ------------------------------

def generate_answer(question, hits, analysis, history=None) -> dict[str, Any]:
    plan = plan_answer(question, hits, analysis, history)
    extra = plan["extra"]
    res: dict[str, Any] = {"llm": None, "fallback": False, "deterministic": False}
    res.update(extra)

    if plan["kind"] == "static":
        res["answer"] = plan["text"]
        res["deterministic"] = extra.get("deterministic", False)
        return res

    try:
        answer = _ollama_chat(plan["messages"], plan["options"])
        if plan.get("verify"):
            answer = _verify(question, hits, answer)
        res["answer"] = answer
        res["llm"] = config.OLLAMA_MODEL
        return res
    except Exception as exc:
        res["answer"] = _spec_fallback_text(question, hits, analysis, extra)
        res["fallback"] = True
        res["deterministic"] = extra.get("spec_mode") == "data"
        res["llm_error"] = str(exc)
        return res


# --- streaming answer (used by /api/query/stream) ---------------------------

def stream_answer(question, hits, analysis, history=None) -> Iterator[dict[str, Any]]:
    """Yield {"type":"token","v":...} pieces, then one {"type":"final", ...}
    carrying the complete answer plus the same flags generate_answer returns."""
    plan = plan_answer(question, hits, analysis, history)
    extra = plan["extra"]
    final: dict[str, Any] = {"type": "final", "llm": None, "fallback": False,
                             "deterministic": False}
    final.update(extra)
    parts: list[str] = []

    # static — emit the ready text as a typing effect
    if plan["kind"] == "static":
        for ch in _word_chunks(plan["text"]):
            yield {"type": "token", "v": ch}
        final["answer"] = plan["text"]
        final["deterministic"] = extra.get("deterministic", False)
        yield final
        return

    try:
        if plan.get("verify"):
            # generate, fact-check, THEN reveal (can't stream a not-yet-checked draft)
            draft = _ollama_chat(plan["messages"], plan["options"])
            text = _verify(question, hits, draft)
            for ch in _word_chunks(text):
                yield {"type": "token", "v": ch}
            final["answer"] = text
            final["llm"] = config.OLLAMA_MODEL
            final["verified"] = True
        else:
            for delta in _ollama_stream(plan["messages"], plan["options"]):
                parts.append(delta)
                yield {"type": "token", "v": delta}
            final["answer"] = "".join(parts)
            final["llm"] = config.OLLAMA_MODEL
        yield final
    except Exception as exc:
        final["fallback"] = True
        final["llm_error"] = str(exc)
        if parts:                                   # keep whatever already streamed
            final["answer"] = "".join(parts)
        else:
            text = _spec_fallback_text(question, hits, analysis, extra)
            for ch in _word_chunks(text):
                yield {"type": "token", "v": ch}
            final["answer"] = text
            final["deterministic"] = extra.get("spec_mode") == "data"
        yield final
