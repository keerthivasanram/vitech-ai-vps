"""FastAPI app — the ATS Engineering Assistant backend.

Pipeline per query:  question -> understand -> retrieve -> analyze -> LLM -> answer

This module is now only the application: middleware, startup and router
registration. The endpoints live under `app/api/`, one module per concern —
see `app/api/__init__.py` for why, and `tests_api_contract.py` for the
fingerprints that prove the split changed no response by a single byte.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .api import (admin, bom, data, documents, drawing, health, ingest,
                  package, query, session, tools, uploads)

app = FastAPI(title="ATS Engineering Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Optional API-key auth --------------------------------------------------
# Off by default (config.API_KEY == "") so a trusted LAN/pod is unaffected. When
# set, every /api request must carry the key (X-API-Key or Bearer); health and
# CORS preflight stay open. This is the wired seam for exposure beyond the LAN.
_AUTH_OPEN = {"/api/health"}


@app.middleware("http")
async def _api_key_guard(request, call_next):
    if config.API_KEY and request.method != "OPTIONS":
        path = request.url.path
        if path.startswith("/api/") and path not in _AUTH_OPEN:
            provided = request.headers.get("x-api-key") or ""
            auth = request.headers.get("authorization") or ""
            if auth.lower().startswith("bearer "):
                provided = provided or auth[7:].strip()
            if provided != config.API_KEY:
                from fastapi.responses import JSONResponse
                return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)


@app.on_event("startup")
def _warm_llm():
    """Pre-load the model in the background so the first query isn't slow."""
    import threading
    from .ollama_client import warmup
    threading.Thread(target=warmup, daemon=True).start()


# REGISTRATION ORDER IS PART OF THE CONTRACT. FastAPI matches routes in the
# order they are added, so `data` (which owns the literal
# `/api/offers/by-source/...` path) must be registered before anything that
# could capture it as `/api/offers/{offer_id}`. The order below reproduces the
# order the single-module version declared its routes in.
for _router in (health, session, ingest, query, documents, data, tools,
                drawing, bom, package, uploads, admin):
    app.include_router(_router.router)
