"""Single Engineering Specification Resolver.

One reasoning engine authors every specification; the POLICY (see spec_schema)
decides which evidence sources may AUTHOR a value. Both external products —
the *Consulting Engineer* and the *ATS Engineering Expert* — route through the
one `resolve()` entrypoint, differing only by the policy passed in. There is a
single code path; `spec_mode` ("knowledge" / "data") is preserved as the
external UI/back-compat label.

Migration note (Phase 2): the ATS/data path is now authored by the policy-aware
engine (`analysis.analyze`, gated by `policy.can_author`). The Consulting/
knowledge path still delegates to the legacy `requirement_only`; Phase 3 folds
its authoring into the same engine under the CONSULTING policy. The seam below
is the only place that knowledge of the two products lives.
"""
from typing import Any

from .analysis import analyze, requirement_only
from .schema import QueryUnderstanding
from .spec_schema import ATS, CONSULTING, Policy, select_policy  # re-exported

__all__ = ["resolve", "Policy", "ATS", "CONSULTING", "select_policy"]


def resolve(question: str, hits: list[dict[str, Any]], u: QueryUnderstanding,
            policy: Policy) -> dict[str, Any]:
    """Author a specification (or a conversational analysis) under `policy`.

    ATS policy  -> history may author values (data mode, evidence-backed).
    Consulting  -> engineering knowledge only (knowledge mode, no history author).
    """
    if policy.history_authoring:
        return analyze(question, hits, u, policy)
    return requirement_only(u)
