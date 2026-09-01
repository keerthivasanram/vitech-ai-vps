"""Guards for the customer-facing PDF renderers.

These 1,119 lines produce the documents that actually leave the building - the
quotation a customer is quoted from, the specification an engineer signs, the
enquiry data sheets. Until 2026-09-01 they had NO tests at all, which the
production-readiness review called out: a renderer could drop an engineering
value, or start printing confidence on a customer quotation, and every other
suite would stay green.

WHAT IS ASSERTED, and why these and not pixels:

  * **Every engineering number that goes in comes out.** A PDF that renders
    beautifully while silently dropping the airflow is the failure that matters,
    and it is invisible to a "does it produce bytes" check. The text is read
    back out of the rendered PDF and searched.
  * **Confidence NEVER appears on a customer quotation.** That is a deliberate
    product rule (the markdown's customer-facing stance and the agent's own
    rule); a regression here misrepresents a draft as a certainty.
  * **Determinism.** The same input renders the same bytes, so "is the platform
    still deterministic?" stays answerable, and so the artifact digests in
    `data/jobs/` mean something.
  * **Latin-1 safety.** fpdf2's core fonts are latin-1 only; an em-dash or a
    rupee sign reaching a renderer used to raise. Every renderer is fed text
    that would break it if the folding regressed.

Run after any change to `*_pdf.py` or `vitech_letterhead.py`.
"""
import re
import sys

from app.datasheet_pdf import FORMS, render_datasheet_pdf
from app.quotation_pdf import render_quotation_pdf
from app.specification_pdf import render_specification_pdf

FAILS: list[str] = []


def check(cond, label):
    print(("OK   " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


def text_of(pdf_bytes: bytes) -> str:
    """Extract the rendered text, so an assertion is about what a READER sees."""
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return "\n".join(page.get_text() for page in doc)


def pages(pdf_bytes: bytes) -> int:
    import fitz
    return fitz.open(stream=pdf_bytes, filetype="pdf").page_count


def norm(pdf_bytes: bytes) -> bytes:
    """Strip the parts fpdf2 varies per run (creation date, file id) so two
    renders of the same input can be compared for real equality."""
    out = re.sub(rb"/CreationDate\s*\(([^)]*)\)", b"/CreationDate()", pdf_bytes)
    return re.sub(rb"/ID\s*\[[^\]]*\]", b"/ID[]", out)


# --------------------------------------------------------------- fixtures ---
# THE FIXTURES ARE BUILT BY THE ENGINE, not hand-written. A hand-made dict drifts
# from the real shape the moment a field is added, and then the suite passes
# while the renderer is fed something it never sees in production - which is
# exactly how a renderer with "tests" still drops a value.
from app.quotation import build_quotation
from app.resolver import ATS, resolve
from app.retriever import retrieve
from app.understand import understand


def _resolved(question: str, intent: str) -> dict:
    u = understand(question)
    u.intent = intent
    hits = retrieve(question, top_k=8, where={"category": u.category} if u.category else None)
    a = resolve(question, hits, u, ATS)
    a["spec_mode"] = "data"
    return a, dict(u.parameters)


_SCRUBBER = "wet scrubber 800 cfm 750mm tower 4 nos"
_BOOTH = "paint booth 5m x 3m x 4m liquid"

_a, _params = _resolved(_SCRUBBER, "quotation")
QUOTE = build_quotation(_a, _params)
SPEC, _ = _resolved(_BOOTH, "specification")

# ------------------------------------------------------------- quotation ----
q = render_quotation_pdf(QUOTE)
check(q[:4] == b"%PDF", "quotation renders a PDF")
check(len(q) > 3000, f"quotation PDF is substantial ({len(q)} bytes)")
qt = text_of(q)

check("VITECH ENVIRO SYSTEMS" in qt.upper(), "quotation carries the Vitech letterhead")
check(QUOTE.get("ref", "@@") in qt, "quotation prints its own reference")
check("Wet Scrubber" in qt or "Scrubber" in qt, "quotation names the equipment")
_price = (QUOTE.get("price_display") or "").replace("\u20b9", "").strip()
check(_price and _price in qt.replace("\u20b9", ""),
      f"quotation prints its own headline price ({_price})")
check("800" in qt, "quotation prints the airflow the customer stated")
check("750" in qt, "quotation prints the tower diameter the customer stated")

# THE PRODUCT RULE: a customer quotation never shows how sure we are.
check("confidence" not in qt.lower(), "quotation NEVER shows confidence to a customer")
check("87%" not in qt, "quotation shows no confidence percentage")

check(norm(render_quotation_pdf(QUOTE)) == norm(q), "quotation rendering is deterministic")

# --------------------------------------------------------- specification ----
s = render_specification_pdf(SPEC)
check(s[:4] == b"%PDF", "specification renders a PDF")
st = text_of(s)
check("VITECH ENVIRO SYSTEMS" in st.upper(), "specification carries the letterhead")
_rows = SPEC.get("technical_details") or []
_computed = [r for r in _rows if str(r.get("value", "")).strip()
             and str(r.get("value")).lower() != "to be determined"]
_missing = [r["label"] for r in _computed
            if str(r["value"]).split()[0] not in st and str(r["value"])[:14] not in st]
check(not _missing, f"every resolved value reaches the page; missing: {_missing[:4]}")
check("21600" in st, "the computed exhaust airflow is printed")

# THE HONEST-GAP CONTRACT, in the printed document rather than only the JSON.
check("To be determined" in st,
      "a TBD row survives into the PDF - a gap is shown AS a gap to the reader")
check("liquid" in st.lower(), "specification echoes the customer's own paint process")
check(norm(render_specification_pdf(SPEC)) == norm(s), "specification rendering is deterministic")

# ------------------------------------------------------------ data sheets ---
check(len(FORMS) >= 3, f"data-sheet forms are declared as data ({len(FORMS)} forms)")
for key in FORMS:
    blank = render_datasheet_pdf(key)
    check(blank[:4] == b"%PDF", f"data sheet '{key}' renders blank")
    check(pages(blank) >= 1, f"data sheet '{key}' has at least one page")

first = sorted(FORMS)[0]
check(norm(render_datasheet_pdf(first)) == norm(render_datasheet_pdf(first)),
      "data-sheet rendering is deterministic")

# --------------------------------------------------- latin-1 / unicode -------
# fpdf2 core fonts are latin-1 only. Every one of these characters has reached a
# renderer in real data: the rupee sign from `inr_display`, the em-dash from
# reused offer prose, the degree sign from an oven temperature.
hostile = dict(QUOTE)
hostile["customer"] = "M/s Test — ₹ Ltd °C ‘quoted’"
hostile["headline"] = "Wet Scrubber — 800 CFM ‘heavy duty’ 220°C"
try:
    h = render_quotation_pdf(hostile)
    check(h[:4] == b"%PDF", "a quotation survives em-dash, rupee, degree and curly quotes")
except Exception as exc:                                    # pragma: no cover
    check(False, f"unicode in a quotation raised {type(exc).__name__}: {exc}")

hostile_spec = dict(SPEC)
hostile_spec["technical_details"] = list(SPEC.get("technical_details") or []) + [
    {"label": "Operating temperature", "value": "220°C — LPG fired",
     "origin": "reused", "reason": "from OFF-SURFACE-OVEN-356R3"}]
try:
    hs = render_specification_pdf(hostile_spec)
    check(hs[:4] == b"%PDF", "a specification survives the same characters")
except Exception as exc:                                    # pragma: no cover
    check(False, f"unicode in a specification raised {type(exc).__name__}: {exc}")

# ------------------------------------------------------------ degenerate ----
# A renderer must not crash on the honest-gap cases the engine really produces.
try:
    bare = render_specification_pdf({"equipment": "Wet Scrubber", "category": "wet_scrubber",
                                     "given_data": [], "technical_details": []})
    check(bare[:4] == b"%PDF", "a specification with no resolved rows still renders")
except Exception as exc:                                    # pragma: no cover
    check(False, f"an empty specification raised {type(exc).__name__}: {exc}")

print()
if FAILS:
    print(f"{len(FAILS)} PDF TEST FAIL")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL PDF TESTS PASS")
