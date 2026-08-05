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
from .api import (admin, auth, bom, data, documents, drawing, health, ingest,
                  package, query, session, tools, uploads)
from .auth.middleware import auth_middleware

app = FastAPI(title="ATS Engineering Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Authentication, authorization and audit --------------------------------
# One middleware for every route, so a route added later without a thought for
# access control is still covered — `auth/policy.py` defaults an unclassified
# path to administrator. The coarse `VITECH_API_KEY` guard this replaces was
# all-or-nothing and, because the variable was never set, never engaged at all.
app.middleware("http")(auth_middleware)


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
for _router in (health, auth, session, ingest, query, documents, data, tools,
                drawing, bom, package, uploads, admin):
    app.include_router(_router.router)
