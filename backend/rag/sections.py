"""Engineering-section detection.

A Vitech offer is not flat prose — it is a sequence of recognisable sections
(scope, technical specification, terms, price schedule, ...). Tagging each
chunk with the section it came from lets the Engineering Agent retrieve, say,
only the "technical specification" of similar past projects and ignore the
commercial/terms boilerplate. Detection is heading-based and deterministic:
a line is a heading if it matches a known section's cue words and looks like a
heading (short, mostly title/upper case, often numbered).
"""
import re

# canonical section -> cue patterns that identify its heading line
_SECTION_CUES: list[tuple[str, re.Pattern]] = [
    ("scope", re.compile(r"\b(scope\s+of\s+(work|supply)|scope)\b", re.I)),
    ("technical_specification", re.compile(
        r"\b(technical\s+(specification|details?|data)|specification[s]?|"
        r"design\s+(basis|data|parameters)|equipment\s+details?)\b", re.I)),
    ("bill_of_materials", re.compile(
        r"\b(bill\s+of\s+materials?|bom|list\s+of\s+(materials|components)|"
        r"components?\s+list)\b", re.I)),
    ("construction", re.compile(
        r"\b(construction|material\s+of\s+construction|moc|fabrication)\b", re.I)),
    ("price_schedule", re.compile(
        r"\b(price\s+(schedule|list|break[\s-]*up)|commercial\s+(offer|terms)|"
        r"cost\s+(sheet|summary)|schedule\s+of\s+(prices|rates))\b", re.I)),
    ("terms_and_conditions", re.compile(
        r"\b(terms\s+(and|&)\s+conditions|payment\s+terms|delivery\s+terms|"
        r"warranty|general\s+conditions|exclusions?)\b", re.I)),
    ("scope_of_exclusion", re.compile(r"\b(scope\s+of\s+exclusion|not\s+in\s+our\s+scope)\b", re.I)),
]

_NUM_PREFIX = re.compile(r"^\s*(\d+(\.\d+)*|[A-Z])[.)]\s+")


def _looks_like_heading(line: str) -> bool:
    """A heading is short and visually distinct — numbered, or mostly
    upper/title case — not a full sentence."""
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return False
    if stripped.endswith("."):        # sentences end with a period; headings rarely do
        # allow a numbered heading like "1. SCOPE" whose only period is the number
        if not _NUM_PREFIX.match(stripped):
            return False
    words = stripped.split()
    if len(words) > 10:
        return False
    letters = [c for c in stripped if c.isalpha()]
    if letters:
        upper_ratio = sum(c.isupper() for c in letters) / len(letters)
        if upper_ratio >= 0.6 or _NUM_PREFIX.match(stripped):
            return True
        # Title Case (most words capitalised) also reads as a heading
        cap_words = sum(1 for w in words if w[:1].isupper())
        if cap_words >= max(1, len(words) - 1):
            return True
    return False


def detect_section(line: str) -> str | None:
    """If `line` is a section heading, return its canonical section name,
    else None."""
    if not _looks_like_heading(line):
        return None
    for name, pattern in _SECTION_CUES:
        if pattern.search(line):
            return name
    return None


def label_sections(lines: list[str]) -> list[tuple[str, str | None]]:
    """Walk the lines, carrying the current section forward. Returns
    [(line, section_or_None)] — lines before the first heading are None
    (front matter / cover page)."""
    current: str | None = None
    out: list[tuple[str, str | None]] = []
    for line in lines:
        found = detect_section(line)
        if found:
            current = found
        out.append((line, current))
    return out


def known_sections() -> list[str]:
    return [name for name, _ in _SECTION_CUES]
