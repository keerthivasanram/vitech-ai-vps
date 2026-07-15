"""Deterministic metadata extraction for ingested documents.

Same principle as the rest of this product (see app/analysis.py): NEVER guess
a value with low confidence and present it as fact. Every field here comes
from one of three sources, tried in this priority order:

  1. explicit   - passed by the human running the ingest (most trustworthy)
  2. body       - regex-matched from the document's own text (a cover page
                  that says "Client: Acme Corp" is authoritative)
  3. filename   - best-effort parse of the source filename

If none of the three finds a field, it stays None - never invented. Every
merged field also records which source won, so a human reviewing the
ingest report can see exactly how much to trust it.

Filename parsing was reverse-engineered from the 33 real offer filenames in
backend/data/offers/*.json (source_file), e.g.:
    "MECCANOTECNICA_DCS_R4_240623.pdf"          -> customer, equipment, rev, date fused
    "Ascend R5 23.10.24.pdf"                    -> space-separated, dotted date
    "Offer - Valv Technologies -R6110124.pdf"   -> rev+date fused after customer
It is intentionally best-effort: Vitech's real filenames are not consistent,
so low-confidence splits (customer vs equipment text) are still returned but
should be corrected via explicit overrides for production ingests.
"""
import re
from datetime import datetime
from typing import Any, Optional

from app.classify import CONFIDENT, classify_equipment

FIELDS = ("customer", "project", "equipment_type", "doc_category",
          "revision", "offer_number", "date")

_DATE_FORMATS = (
    "%d%m%y", "%d%m%Y",
    "%d.%m.%y", "%d.%m.%Y", "%d-%m-%y", "%d-%m-%Y", "%d/%m/%y", "%d/%m/%Y",
)


def _try_parse_date(raw: str) -> Optional[str]:
    """Best-effort normalise to ISO YYYY-MM-DD. Returns None rather than
    guess when the string doesn't cleanly match a known format."""
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt)
            # 2-digit years: assume 2000s (this business's records start ~2018)
            if dt.year < 100:
                dt = dt.replace(year=dt.year + 2000)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


# --- filename parsing --------------------------------------------------

# Underscore is a word char, so \b fails between "_" and "R" — the real corpus
# is full of "_R4", so use explicit non-alnum lookarounds instead of \b.
_REV_TOKEN = re.compile(r"(?<![A-Za-z0-9])R(\d+)([A-Za-z])?(?![A-Za-z])")
_DOTTED_DATE = re.compile(r"\b(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})\b")
_FUSED_DATE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_NOISE_PREFIX = re.compile(r"^(offer|quotation)\s*[-:]\s*", re.I)
_SEP_RUN = re.compile(r"[\s_\-]+")


def parse_filename(filename: str) -> dict[str, Any]:
    """Best-effort split of a source filename into customer / equipment text
    / revision / date. Every field may be absent - a messy or unrecognised
    filename degrades to {} rather than a wrong guess."""
    stem = re.sub(r"\.(pdf|docx?|xlsx?|txt|md|json)$", "", filename, flags=re.I).strip()
    out: dict[str, Any] = {}

    # 1) Revision: "R" + digits, optionally a trailing letter (R3A). A long
    # digit run (>2) after R means the date is fused straight on ("R2201123"
    # = rev "2" + date "201123") - split there rather than swallow both as
    # one meaningless number.
    working = stem
    rev_match = _REV_TOKEN.search(working)
    fused_date_digits = None
    if rev_match:
        digits, letter = rev_match.group(1), rev_match.group(2) or ""
        if len(digits) > 2:
            out["revision"] = digits[0] + letter
            fused_date_digits = digits[1:]
        else:
            out["revision"] = digits + letter
        working = working[:rev_match.start()] + " " + working[rev_match.end():]

    # 2) Date: prefer the fused digits split off the revision token, else a
    # dotted/slashed date anywhere, else a standalone 6-digit run (DDMMYY).
    # Whichever forms appear, blank them ALL out of `working` so they can't
    # pollute the customer/equipment text below. A 5-digit or otherwise
    # irregular run is left unparsed rather than guessed at.
    date_raw = fused_date_digits if (fused_date_digits and len(fused_date_digits) == 6) else None
    m = _DOTTED_DATE.search(working)
    if m:
        date_raw = date_raw or m.group(1)
        working = _DOTTED_DATE.sub(" ", working)
    m = _FUSED_DATE.search(working)
    if m:
        date_raw = date_raw or m.group(1)
        working = _FUSED_DATE.sub(" ", working)
    if date_raw:
        out["date_raw"] = date_raw
        iso = _try_parse_date(date_raw)
        if iso:
            out["date"] = iso

    # 3) Customer / equipment text: derive BOTH from `working`, which now has
    # the revision and every date blanked out — so neither field carries that
    # noise. Underscore is the dominant delimiter in the real corpus; split on
    # the first one (customer before it, equipment description after).
    working = _NOISE_PREFIX.sub("", working.strip())
    seg = re.split(r"_+", working, maxsplit=1) if "_" in working else [working]
    customer_guess = _SEP_RUN.sub(" ", seg[0]).strip(" -_")
    equipment_guess = _SEP_RUN.sub(" ", seg[1]).strip(" -_") if len(seg) > 1 else None

    if customer_guess:
        out["customer"] = customer_guess
    if equipment_guess:
        out["equipment_text"] = equipment_guess

    guess_source = " ".join(filter(None, [customer_guess, equipment_guess]))
    category, score = classify_equipment(guess_source or stem)
    if score >= CONFIDENT:
        out["equipment_type"] = category

    return out


# --- body-text parsing ---------------------------------------------------

_BODY_PATTERNS = {
    "offer_number": re.compile(
        r"\b(?:Offer|Quotation|Ref(?:erence)?)\s*(?:No\.?|Number|#)?\s*[:\-]\s*"
        r"([A-Z][A-Z0-9\-/]{3,})", re.I),
    "revision": re.compile(r"\bRev(?:ision)?\.?\s*(?:No\.?)?\s*[:\-]\s*([A-Za-z0-9]{1,3})\b", re.I),
    "date": re.compile(
        r"\bDate\s*[:\-]\s*(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}|\d{1,2}\s+\w+\s+\d{4})", re.I),
    "customer": re.compile(
        r"(?:^|\n)\s*(?:M/s\.?|Client|Customer)\s*[:\-]\s*(.+)", re.I),
    "project": re.compile(r"(?:^|\n)\s*Project(?:\s*Name)?\s*[:\-]\s*(.+)", re.I),
}


def extract_body_metadata(text: str, *, window: int = 3000) -> dict[str, Any]:
    """Regex-scan the document's own text (header/cover-page region) for
    self-declared metadata - more trustworthy than the filename when present."""
    head = text[:window]
    out: dict[str, Any] = {}
    for field, pattern in _BODY_PATTERNS.items():
        m = pattern.search(head)
        if not m:
            continue
        value = m.group(1).strip().strip(".").strip()
        if not value:
            continue
        if field == "date":
            out["date_raw"] = value
            iso = _try_parse_date(re.sub(r"[./]", "-", value)) or _try_parse_date(value)
            out[field] = iso or value
        else:
            out[field] = value

    category, score = classify_equipment(head)
    if score >= CONFIDENT:
        out["equipment_type"] = category
    return out


# --- merge -----------------------------------------------------------------

def merge_metadata(*, explicit: dict[str, Any] | None = None,
                    body: dict[str, Any] | None = None,
                    filename: dict[str, Any] | None = None) -> dict[str, Any]:
    """Priority: explicit > body > filename. Returns the merged field values
    plus a `_meta_source` map of field -> which layer supplied it, so an
    ingest report can show confidence at a glance."""
    explicit, body, filename = explicit or {}, body or {}, filename or {}
    merged: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for field in FIELDS:
        for layer_name, layer in (("explicit", explicit), ("body", body), ("filename", filename)):
            if layer.get(field):
                merged[field] = layer[field]
                sources[field] = layer_name
                break
    if "date" not in merged:
        raw = explicit.get("date_raw") or body.get("date_raw") or filename.get("date_raw")
        if raw:
            merged["date_raw"] = raw
    merged["_meta_source"] = sources
    return merged
