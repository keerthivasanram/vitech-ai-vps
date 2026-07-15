"""Central configuration, driven by environment variables (.env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Where extracted engineering records live. Swap this for your real data.
# DATA_SOURCE may be a single JSON file OR a directory of .json files
# (one record or an array per file) — that's how thousands of CAD/PDF
# extractions get fed in.
DATA_FILE = Path(os.getenv("DATA_FILE", BASE_DIR / "data" / "sample_documents.json"))
# A directory of per-category offer files (given_data + technical_details).
DATA_SOURCE = Path(os.getenv("DATA_SOURCE", BASE_DIR / "data" / "offers"))

# How many records to embed + write to Chroma per batch. This is the knob
# that lets ingestion scale to thousands of files without loading everything
# into memory or blowing past Chroma's max batch size.
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "256"))

# Chroma persistent store location.
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", BASE_DIR / "chroma_store"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "engineering_knowledge")

# Retrieval
TOP_K = int(os.getenv("TOP_K", "6"))
# Minimum similarity for a retrieved document to count as "relevant" to a
# conversational question. Below this, the assistant answers from general
# knowledge instead of forcing in off-topic company documents.
RELEVANCE_THRESHOLD = float(os.getenv("RELEVANCE_THRESHOLD", "0.4"))

# Local LLM (Ollama HTTP API). If unreachable, the app falls back to a
# templated answer assembled directly from retrieved data.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
# CPU inference is slow; allow generous time and keep the model warm.
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "300"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
# Conversational answers: allow longer, fuller replies and tune sampling so the
# small local model produces natural, well-structured prose (not terse/generic).
LLM_NUM_PREDICT = int(os.getenv("LLM_NUM_PREDICT", "1024"))
# Conversational (Q&A) answers get a tighter budget than specs — a small local
# model is slow on CPU, and shorter, punchier answers are both faster and clearer.
CHAT_NUM_PREDICT = int(os.getenv("CHAT_NUM_PREDICT", "500"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.55"))
LLM_TOP_P = float(os.getenv("LLM_TOP_P", "0.9"))
LLM_REPEAT_PENALTY = float(os.getenv("LLM_REPEAT_PENALTY", "1.1"))
# Spec narrative: the LLM frames the deterministic table. Lower temperature +
# shorter budget keeps it tight and faithful to the computed values.
SPEC_NUM_PREDICT = int(os.getenv("SPEC_NUM_PREDICT", "420"))
SPEC_TEMPERATURE = float(os.getenv("SPEC_TEMPERATURE", "0.2"))
# Soft bar for pulling company project data INTO a conversational answer as
# grounding context (lower than RELEVANCE_THRESHOLD, which gates the "grounded"
# badge). The model is told to use it only where it is actually relevant.
GROUNDING_THRESHOLD = float(os.getenv("GROUNDING_THRESHOLD", "0.22"))
# Hard cap on how many company documents are fed to the LLM as grounding context
# for one conversational answer. Stops a broad query from dumping the whole
# corpus into the prompt (slow on a small local model, and it blends unrelated
# records). Named-client lookups are already scoped to that client's records.
MAX_GROUNDING_DOCS = int(os.getenv("MAX_GROUNDING_DOCS", "6"))

# Hybrid routing: a spec request with at least this fraction of its expected
# inputs (and the essential sizing input present) is built by the Quotation
# Engineer (history + rules + validation). Below it, the Consulting Engineer
# asks for the missing information instead of guessing.
HYBRID_THRESHOLD = float(os.getenv("HYBRID_THRESHOLD", "0.6"))

# Query understanding: use the LLM (JSON mode) for intent/entity extraction.
# Set to 0/false to use only the fast regex fallback (no extra LLM call).
USE_LLM_UNDERSTANDING = os.getenv("USE_LLM_UNDERSTANDING", "1").lower() not in ("0", "false", "no")
UNDERSTAND_NUM_PREDICT = int(os.getenv("UNDERSTAND_NUM_PREDICT", "200"))

# Session memory (Redis). Falls back to in-process memory if Redis is unreachable.
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SESSION_TTL = int(os.getenv("SESSION_TTL", "86400"))        # keep a session 1 day
SESSION_HISTORY = int(os.getenv("SESSION_HISTORY", "12"))   # messages kept for context
