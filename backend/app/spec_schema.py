"""Specification schema contract + policy presets for the single resolver.

One resolver authors the spec; a POLICY decides which evidence sources may
AUTHOR a value. Both presets emit the same schema — only the origin distribution
differs. `spec_mode` is preserved as the external UI/back-compat label.
"""
from dataclasses import dataclass

# --- provenance origins (authoring sources) --------------------------------
# The first six reuse the EXACT strings the current engine already emits, so
# nothing downstream (ORIGIN_LABELS, DECISION_TYPES, spec_writeup, UI) changes.
REQUIREMENT = "given"          # client requirement (authoritative)
RULE = "rule"                  # engineering formula + standard
INTERPOLATED = "interpolated"  # synthesised between two historical offers
SCALED = "scaled"              # scaled from the nearest historical offer
CONSENSUS = "consistent"       # historical consensus across offers
REUSE = "reused"               # reused from the nearest historical offer
REUSE_KEPT = "kept"            # (Track-A alias for reuse)
# --- reserved for the Consulting policy (not populated in this phase) -------
STANDARD = "standard"
CALCULATION = "calculation"
ESTIMATE = "estimate"
TBD = "tbd"

_HISTORICAL = frozenset({INTERPOLATED, SCALED, CONSENSUS, REUSE, REUSE_KEPT})


@dataclass(frozen=True)
class Policy:
    name: str
    spec_mode: str          # UI/back-compat contract: "knowledge" | "data"
    render: str             # presentation: "narrative" | "writeup"
    authoring: frozenset    # origins allowed to AUTHOR a value
    history_authoring: bool  # may historical offers set values?
    history_crosscheck: bool  # may historical offers observe/flag (never author)?
    allow_estimate: bool

    def can_author(self, origin: str) -> bool:
        return origin in self.authoring


# Historical quotations may AUTHOR values; evidence-backed and traceable.
ATS = Policy(
    name="ATS Engineering Expert",
    spec_mode="data",
    render="writeup",
    authoring=frozenset({REQUIREMENT, RULE, INTERPOLATED, SCALED,
                         CONSENSUS, REUSE, REUSE_KEPT}),
    history_authoring=True,
    history_crosscheck=True,
    allow_estimate=False,
)

# Engineering knowledge only; historical data must NOT author (cross-check only).
CONSULTING = Policy(
    name="Consulting Engineer",
    spec_mode="knowledge",
    render="narrative",
    authoring=frozenset({REQUIREMENT, RULE, STANDARD, CALCULATION, ESTIMATE, TBD}),
    history_authoring=False,
    history_crosscheck=True,
    allow_estimate=True,
)


def select_policy(refer_db: bool) -> Policy:
    """Same trigger as today: 'refer db' -> ATS, otherwise Consulting."""
    return ATS if refer_db else CONSULTING
