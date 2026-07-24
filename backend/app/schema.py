"""Typed domain model — the contract shared by query understanding, the rule
engine, the reasoning layer, and (Phase 2) the quotation generator.
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Intent = Literal["specification", "comparison", "concept", "search", "quotation", "general", "unknown"]

# Where a generated value came from:
#   given       — echoed straight from the client's requirement
#   kept        — copied unchanged from the nearest historical offer
#   adapted     — scaled from the nearest offer to suit the new requirement
#   rule        — computed by an engineering rule (formula + standard)
#   existing    — taken from a document (non-spec extras)
#   recommended — generic inferred value
#   tbd         — a spec-template field with no client value, rule, or historical
#                 match yet: an explicit gap for engineering input (NEVER guessed)
Origin = Literal["given", "kept", "adapted", "rule", "existing", "recommended", "tbd"]


class QueryUnderstanding(BaseModel):
    """Structured form of a natural-language request (produced by understand.py).
    Category-agnostic: `parameters` holds whatever given-data the user supplied."""
    intent: Intent = "specification"
    category: Optional[str] = None                 # e.g. "wet_scrubber", "paint_booth"
    parameters: dict[str, Any] = Field(default_factory=dict)
    topic: Optional[str] = None                    # for concept/comparison questions
    source: str = "llm"                            # "llm" or "regex"


class RuleResult(BaseModel):
    """One computed engineering value with its formula and governing standard."""
    name: str
    value: str
    formula: str
    standard: str


class SpecValue(BaseModel):
    label: str
    value: str
    origin: Origin


class ComputedSpec(BaseModel):
    """Output of a category rule engine for a given requirement."""
    length_m: Optional[float] = None
    width_m: Optional[float] = None
    height_m: Optional[float] = None
    values: list[SpecValue] = Field(default_factory=list)
    rules: list[RuleResult] = Field(default_factory=list)
