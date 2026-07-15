"""Decision ledger — a traceable audit trail for a generated specification.

Every value is recorded with WHERE it came from (client requirement / engineering
rule / historical offer / consensus) and its BASIS (formula + standard, or offer
id). This makes the system auditable: any number can answer "why is this value
what it is?". The ledger is machine-readable (export / PDF / review) and drives a
short provenance summary shown with the spec.
"""
from collections import Counter

# Internal origin -> human "kind" for the audit trail.
ORIGIN_KIND = {
    "given": "Client requirement",
    "rule": "Engineering rule",
    "interpolated": "Inferred (multi-project)",
    "scaled": "Scaled from nearest design",
    "consistent": "Historical consensus",
    "reused": "Reused from historical offer",
    "kept": "Reused from historical offer",
}


def build_ledger(items: list[dict]) -> list[dict]:
    """Turn the generated technical decisions into an ordered, ID'd audit trail."""
    ledger = []
    for n, it in enumerate(items or [], 1):
        ledger.append({
            "n": n,
            "field": it.get("label"),
            "value": it.get("value"),
            "origin": it.get("origin"),
            "kind": ORIGIN_KIND.get(it.get("origin"), it.get("origin_label", "Decision")),
            "source": it.get("source"),
            "basis": it.get("reason"),
        })
    return ledger


def provenance_summary(items: list[dict]) -> str:
    """One-line, human summary of where the decisions came from."""
    if not items:
        return ""
    counts = Counter(ORIGIN_KIND.get(it.get("origin"), "Other") for it in items)
    parts = ", ".join(f"{v} {k.lower()}" for k, v in counts.items())
    return (f"{len(items)} decisions — {parts}. Every value is traceable to its "
            f"source (see decision ledger).")
