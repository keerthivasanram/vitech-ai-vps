# Requirement Consultant — Architecture Design

> Status: **design proposal, not yet implemented.** Written before any code so the
> data model can be argued about while it is still cheap to change.
> Scope: Requirement Schema, RequirementSession, Question Policy, Assumption Engine.

## 0. The premise

The weakness is not the language model. It is that the engineering knowledge model
has nowhere to put engineering information. `wet_scrubber.required_inputs` is three
slots (`air_volume_cfm`, `tower_diameter_mm`, `qty`); contaminant, chemical
compatibility, tower material, available height, removal efficiency, utilities,
installation location and future expansion do not exist anywhere in the system.

So the work is: **make the requirement a first-class, versioned engineering object**,
give each slot enough metadata for a deterministic policy to reason about it, and
leave the LLM with exactly two narrow jobs — read language, write language.

Three invariants govern everything below.

1. **One source of truth for readiness.** `agent_router` already owns completeness,
   essential-input and threshold routing. The consultant extends it; it never
   becomes a second authority. (Note: `release_gate.assess()` also emits questions
   today — that must be folded in, see §7.)
2. **The LLM proposes, Python commits.** No value enters the requirement without
   passing schema validation and unit normalisation in Python.
3. **Golden rule #2 is unchanged.** Nothing here computes an engineering number.

---

## 1. Requirement Schema

### 1.1 Separate the schema from the instance

The metadata list in the brief mixes two different lifetimes:

| Property | Lifetime | Lives on |
|---|---|---|
| engineering impact, commercial impact, tier, default strategy, validation, dependencies | static, per category | `SlotSpec` (schema) |
| provenance, confidence, value, asked_count, confirmed | per conversation | `SlotValue` (session) |

Keeping provenance on the schema would mean a slot has one provenance for all
customers forever. `SlotSpec` describes *what the slot is*; `SlotValue` records
*what this customer said about it*. Everything in §2 is instance state.

### 1.2 `SlotSpec`

```python
@dataclass(frozen=True)
class SlotSpec:
    key: str                      # "inlet_temp_c" — canonical, snake_case
    label: str                    # "Inlet gas temperature"
    kind: Literal["quantity", "enum", "bool", "text", "dimension"]
    unit: str | None              # CANONICAL unit; input is normalised to this
    accepts_units: tuple[str, ...] = ()   # "F", "K" -> converted in Python
    choices: tuple[str, ...] = ()         # for kind="enum"

    # --- when is this slot mandatory -------------------------------------
    tier: Tier                    # lowest deliverable tier that REQUIRES it

    # --- what breaks if it is wrong --------------------------------------
    drives: tuple[str, ...] = ()  # output fields whose value depends on this
    cost_sensitivity: float = 0.0 # 0..1, share of price this slot can move
    compliance: bool = False      # gates release / safety / statutory

    # --- how to avoid asking ---------------------------------------------
    default: DefaultStrategy | None = None

    # --- correctness -------------------------------------------------------
    validators: tuple[str, ...] = ()      # named rules in validate.py
    depends_on: tuple[str, ...] = ()      # must be known BEFORE this is asked
    applicable_if: str | None = None      # predicate; slot doesn't exist unless true

    # --- elicitation (intent only — the LLM writes the sentence) ----------
    ask: AskSpec | None = None
```

### 1.3 `tier` replaces required/optional — and answers §3 for free

Rather than a binary flag plus a separate table of per-deliverable thresholds,
each slot declares **the lowest deliverable at which it becomes mandatory**:

```python
class Tier(IntEnum):
    CONCEPTUAL = 1   # conceptual budget indication
    BUDGETARY  = 2   # budgetary quotation
    DRAFT      = 3   # engineering draft
    REVIEW     = 4   # customer review draft
    RELEASED   = 5   # released design
```

Completeness stops being a single number and becomes a function of the target:

```python
def completeness(session, target: Tier) -> float:
    req = [s for s in applicable_slots(session) if s.tier <= target]
    return len([s for s in req if session.filled(s.key)]) / len(req)
```

One field now expresses both "is it required" and "required *for what*". The
existing `HYBRID_THRESHOLD = 0.6` becomes the BUDGETARY gate, so today's routing
behaviour is preserved rather than replaced.

### 1.4 Derive impact from `drives`, don't hand-assign it

A hand-tuned `engineering_impact: 0.8` rots the moment a formula changes and
nobody can defend the number in a review. `drives` is checkable: it is the list of
output fields whose computation consumes this slot, and it can be **verified
against the engine** — if `formula_service` reads `air_volume_cfm` while computing
`pump_capacity_hp`, then `pump_capacity_hp` belongs in that slot's `drives`.

Priority is then computed, not declared:

```python
def impact(spec, session) -> float:
    reach   = len(spec.drives) / max_drives_in_category
    money   = spec.cost_sensitivity
    gate    = 1.0 if spec.compliance else 0.0
    return 0.5 * reach + 0.35 * money + 0.15 * gate
```

A drift test (`tests_requirement.py`) should assert that every `drives` entry
names a real output field, so the schema cannot silently disagree with the engine.

### 1.5 `applicable_if` — not asking stupid questions

Half of sounding experienced is *not* asking about solvent type on a powder line.
`applicable_if` is a predicate over already-filled slots, evaluated in Python:

```python
SlotSpec(key="solvent_type", applicable_if="paint_type == 'liquid'", ...)
SlotSpec(key="ptfe_lining",  applicable_if="contaminant in ('chromic_acid','hf')", ...)
```

An inapplicable slot is excluded from completeness entirely — it is not missing,
it does not exist for this requirement.

### 1.6 `DefaultStrategy` — the machinery behind assumptions

```python
@dataclass(frozen=True)
class DefaultStrategy:
    basis: Literal["constant", "category_norm", "derived", "context"]
    value: Any | None = None        # basis="constant"
    formula: str | None = None      # basis="derived", evaluated in Python
    context_map: dict | None = None # basis="context", e.g. {"paint shop": "solvent_laden"}
    rationale: str = ""             # human sentence for the assumptions register
    disclose: bool = True           # surface to the customer, or footnote it
```

`category_norm` is the strongest basis and the one worth investing in: it reads the
33 historical offers and reports *n* and share ("22 of 31 paint-shop scrubbers on
file use FRP"). That is a defensible engineering assumption rather than a model's
opinion, and it is exactly what `analysis.py::_assumptions_and_missing` already
does in unstructured form.

### 1.7 Worked example — `wet_scrubber`

| key | tier | drives | cost_sens | default basis | depends_on |
|---|---|---|---|---|---|
| `air_volume_cfm` | CONCEPTUAL | tower_dia, pump_hp, tank_cap, blower_kw, price | 0.45 | — (must ask) | — |
| `contaminant` | CONCEPTUAL | tank_material, nozzle_material, demister, chemistry | 0.30 | context | — |
| `qty` | CONCEPTUAL | price, all counts | 0.25 | constant `1` | — |
| `inlet_temp_c` | BUDGETARY | material, demister, fan_class | 0.10 | constant `40` (ambient) | — |
| `tower_material` | BUDGETARY | tank_material, price | 0.35 | category_norm | `contaminant` |
| `removal_efficiency_pct` | DRAFT | stages, tower_height, nozzle_nos | 0.20 | constant `95` | `contaminant` |
| `available_height_m` | DRAFT | tower_height, layout | 0.05 | — (must ask) | — |
| `utilities` | REVIEW | pump_spec, control_panel | 0.05 | constant `415V/3ph/50Hz` | — |
| `install_location` | REVIEW | finish, weatherproofing | 0.08 | constant `indoor` | — |
| `future_expansion_pct` | REVIEW | tower_dia margin, fan margin | 0.10 | constant `0` | — |

Note `tower_material` depends on `contaminant`: material follows chemistry, so the
policy must never ask them in the same batch or in the wrong order.

---

## 2. RequirementSession

### 2.1 Event-sourced, because you already have the pattern

State is a **fold over an append-only event log**. This buys revision history,
audit trail, diffing and "who confirmed what" without additional machinery — and it
matches `ledger.py`, which already renders provenance for spec values.

```python
@dataclass
class RequirementSession:
    id: str                         # REQ-2026-0042
    chat_id: str                    # Flowise chatId — the interface, not the record
    category: str | None
    target_tier: Tier = Tier.BUDGETARY
    status: Status = Status.DRAFTING
    revision: int = 0
    events: list[Event] = field(default_factory=list)   # the source of truth

    # derived by folding `events` — never written to directly
    slots: dict[str, SlotValue] = field(default_factory=dict)
    assumptions: dict[str, Assumption] = field(default_factory=dict)
    conflicts: list[Conflict] = field(default_factory=list)
```

### 2.2 `SlotValue`

```python
@dataclass
class SlotValue:
    key: str
    value: Any                  # CANONICAL units, Python-normalised
    unit: str | None
    raw_text: str | None        # what the customer actually typed
    source: Source              # see 2.3 — reuses spec_schema's vocabulary
    confidence: float           # 0..1
    confirmed: bool = False     # customer explicitly agreed
    asked_count: int = 0        # nagging guard (see §3.5)
    set_at: datetime
    set_by_event: int           # index into events — full traceability
    superseded: list[SlotValue] = field(default_factory=list)
```

### 2.3 Reuse the existing provenance vocabulary

`spec_schema.py` already defines `REQUIREMENT`, `RULE`, `CONSENSUS`, `SCALED`,
`INTERPOLATED`, `ESTIMATE`, `TBD`. **Do not invent a second vocabulary** — the
ledger, the PDF and the release gate all read the existing one.

| Requirement source | Existing constant | Meaning |
|---|---|---|
| customer stated it | `REQUIREMENT` | authoritative |
| inferred from context | `ESTIMATE` | model read it from application |
| assumed from history | `CONSENSUS` | category norm over the corpus |
| derived from other slots | `RULE` | Python formula |
| unfilled | `TBD` | genuinely unknown |

Confidence ordering is then automatic: `REQUIREMENT > RULE > CONSENSUS > ESTIMATE`.

### 2.4 `Assumption`

```python
@dataclass
class Assumption:
    slot: str
    value: Any
    basis: str                  # constant | category_norm | derived | context
    rationale: str              # "22 of 31 paint-shop scrubbers on file use FRP"
    evidence: dict              # {n: 22, of: 31, offer_ids: [...]}
    risk: str                   # what breaks if this is wrong
    status: AssumptionStatus    # PROPOSED | ACCEPTED | REJECTED | OVERRIDDEN | STALE
    disclosed: bool
    proposed_at: datetime
    resolved_at: datetime | None = None
    invalidated_by: str | None = None   # slot whose change made this STALE
```

### 2.5 Events

```
SlotProposed        (slot, value, source, span)      # LLM extraction, uncommitted
SlotCommitted       (slot, value, source)            # passed validation
SlotSuperseded      (slot, old, new, reason)
SlotConfirmed       (slot)
AssumptionProposed  (slot, value, basis, rationale)
AssumptionAccepted  (slot)  /  AssumptionRejected (slot)
AssumptionStale     (slot, invalidated_by)
QuestionAsked       (slots[], batch_id)
ConflictDetected    (slots[], rule)  /  ConflictResolved (slots[], resolution)
TierReached         (tier)
RequirementFrozen   (revision, sha256)
```

### 2.6 Freeze + hash — the traceability link

This is the piece that makes the requirement an engineering record rather than
chat memory, and it is what Siemens/Dassault-class tooling actually sells:

```python
def freeze(session) -> RequirementRevision:
    """Immutable snapshot. Every downstream artifact references its sha."""
```

Every specification, drawing, BOM, quotation and package then carries
`requirement_rev: "sha256:ab34…"`, so **"which requirement drove this dimension,
and who approved it"** is answerable months later. `package/builder.py` is the
natural place to embed it.

### 2.7 Lifecycle

```
DRAFTING ──(completeness ≥ threshold(tier))──> SUFFICIENT(tier)
    │                                              │
    │<────── new information supersedes a slot ─────┤
    │                                              ▼
    │                                     FROZEN(rev, sha)
    │                                              │
    └──────────── amended ─────────────────> SUPERSEDED(by rev+1)
```

A frozen requirement is never mutated. New information opens revision *n+1* and
the diff between revisions is itself a reviewable artifact — that is what makes
change orders defensible.

### 2.8 Storage

Redis is already running and already keyed by `chatId` (`session.py`). The event
log is small (tens of events). Postgres is the right home once requirements must
outlive a chat and be queried across customers — but Redis first, with the event
log serialised as JSON, keeps this shippable and the migration is mechanical.

---

## 3. Question Policy

Deterministic. Signature:

```python
def next_batch(session, target: Tier) -> QuestionBatch:
    """QuestionBatch(questions[], assumptions_to_disclose[], sufficient: bool,
                     best_available_tier: Tier)"""
```

### 3.1 Algorithm

1. **Gap** — slots where `tier <= target`, `applicable_if` true, not filled.
2. **Split** — those with a `default` strategy vs those without.
3. **Auto-fill defaultables as PROPOSED assumptions.** Never silently committed
   (§4.2) — they are disclosed in one sentence, not asked as questions.
4. **Rank the must-asks** by `impact(spec, session)` from §1.4.
5. **Respect dependencies** — a slot whose `depends_on` is unfilled is not
   eligible this turn. Ask upstream first.
6. **Batch 2–3**, and only slots that are mutually dependency-independent.
7. **Stop** when `completeness(target) >= threshold(target)` and essential present.

### 3.2 Thresholds

| Tier | Completeness | Assumptions allowed | Extra gate |
|---|---|---|---|
| CONCEPTUAL | essential only | freely, footnoted | — |
| BUDGETARY | **0.60** (= today's `HYBRID_THRESHOLD`) | yes, disclosed | — |
| DRAFT | 0.80 | yes, all disclosed | validation clean |
| REVIEW | 0.95 | **must be ACCEPTED** | no open conflicts |
| RELEASED | 1.00 | zero unconfirmed | `release_gate.assess()` passes |

Setting BUDGETARY to the existing 0.60 means the first implementation is
behaviour-preserving and the goldens should not move.

### 3.3 The policy never blocks

`next_batch` always returns `best_available_tier`. A customer who says *"just give
me a ballpark"* gets one — at CONCEPTUAL, clearly labelled, with assumptions
listed. Completeness decides **what kind of document you get**, never *whether*
you get one. This is already the behaviour of `HYBRID_THRESHOLD` and it should
survive; a hard interview gate would make the product worse.

### 3.4 Two or three questions, with proposals — not eleven

The senior-engineer move is to ask the few things that change the design and
*propose* the rest:

> "For a paint-shop scrubber I'll assume ambient inlet (~40 °C), FRP tower and
>  95% removal — standard for this duty. I need the **airflow**, and whether
>  you're on **solvent or water-based** paint."

Two questions, five assumptions disclosed, ~70% complete after one turn. An
eleven-question interrogation gets abandoned.

### 3.5 Nagging guard

`asked_count >= 2` on a slot ⇒ stop asking. Fall back to its default if it has
one, else mark `TBD` and let the tier degrade. A loop that keeps re-asking the
same question is worse than an assumption on the record.

---

## 4. Assumption Engine

### 4.1 Assumptions are the commercial product

An assumption register is *more* valuable than a filled form: it is what protects
Vitech when a customer later says "we never told you it was ambient". Every
assumption carries `rationale`, `evidence` and `risk` for exactly that reason.
`spec_writeup` and `quotation_pdf` already render assumptions — they get a
structured object instead of free text.

### 4.2 Propose → disclose → confirm

Assumptions are **never silently committed**. They enter as `PROPOSED`, are
disclosed in the reply, and are promoted to `ACCEPTED` by explicit customer
agreement (or by tier REVIEW demanding confirmation). Silence is not consent at
REVIEW and above; below it, silence leaves them `PROPOSED` and clearly flagged.

### 4.3 Disclosure policy

Disclose when `impact(spec) >= 0.15` or `compliance` is set; footnote the rest.
**Never hide a cost-material assumption** — an undisclosed FRP-vs-PP choice that
moves price 30% is the kind of thing that destroys trust in the tool.

### 4.4 Staleness — the easy thing to get wrong

When a slot changes, every assumption whose `DefaultStrategy` consumed it must be
re-opened:

```python
def invalidate_dependents(session, changed: str):
    for a in session.assumptions.values():
        if changed in dependencies_of(a) and a.status in (PROPOSED, ACCEPTED):
            emit(AssumptionStale(a.slot, invalidated_by=changed))
```

Concretely: contaminant moves from *water-based* to *chromic acid* ⇒ the FRP
material assumption is `STALE` and must be re-proposed. Without this the register
silently lies, which is worse than having no register.

---

## 5. The LLM boundary

Exactly two calls, both narrow, both schema-validated. Everything else is Python.

```python
def extract(utterance, applicable_slots) -> list[RequirementDelta]
    # -> [{slot, raw_value, unit_as_written, span, confidence}]
    # Unknown slot -> REJECTED, not stored.
    # NO unit conversion here: "80F" is returned as raw_value=80, unit="F",
    # and engineering/unit_converter.py does the arithmetic.

def phrase(questions: list[AskSpec], assumptions: list[Assumption]) -> str
    # Pure prose. Receives no numbers it must compute and no decisions to make.
```

Unit conversion is deliberately outside the model. CLAUDE.md already records that
llama3.1 invented "1 CFM = 1725 CMH" against the true 1.699 — a 1.5% sizing error
that no validator would catch because the number looks plausible. `validate.py`
holds `_CFM_TO_CMH = 1.699`; that stays the only conversion path.

Because the model's job is now this small, **model choice becomes a quality dial
rather than an architecture decision** — which is what makes the model-agnostic
option (Llama / Qwen / GPT / Claude / any OpenAI-compatible endpoint) nearly free,
and on-prem deployment a configuration rather than a compromise.

---

## 6. Testing

`tests_golden.py` protects the numbers; nothing protects the conversation. Add:

- **`tests_requirement.py` — golden dialogues.** Fixed utterance sequences →
  expected slot state, expected next question, expected assumptions. This is what
  makes "did swapping the model help?" answerable instead of a vibe.
- **Schema drift test.** Every `drives` entry names a real output field; every
  `validators` entry names a real rule; every `applicable_if` parses.
- **Tier monotonicity.** Completeness at tier *n* ≥ completeness at tier *n+1*.
- **Staleness test.** Changing a dependency marks the dependent assumption STALE.

---

## 7. Integration and the divergence risks

| Module | Change |
|---|---|
| `catalog.py` | `required_inputs`/`optional_inputs` → `SlotSpec[]` (keep old keys as an alias during migration) |
| `understand.py` | returns `RequirementDelta[]` instead of a flat `parameters` dict |
| `agent_router.py` | reads session completeness — **stays the single routing authority** |
| `validate.py` | `cross_validate` extended to run over the requirement, not just the spec |
| `analysis.py` | `_assumptions_and_missing` replaced by the Assumption Engine |
| `ledger.py` | requirement events join the provenance ledger |
| `release_gate.py` | gains an "unconfirmed assumptions" blocker |
| `package/builder.py` | embeds `requirement_rev` sha |

**Two divergence risks to close deliberately:**

1. `release_gate.assess()` already returns `questions`. Once the Question Policy
   exists there are two things asking the customer for information. Fold the gate's
   questions into the policy so there is one asker.
2. `analysis.py::_assumptions_and_missing` already produces assumptions. It must be
   *replaced*, not paralleled, or two assumption lists will disagree in the PDF.

---

## 8. Migration

Sequenced so each step is independently verifiable and reversible.

- **Phase 0 — schema only.** Full `SlotSpec` for `wet_scrubber` alone. Derive
  today's `required_inputs` from `tier <= BUDGETARY`. **Goldens must not move.**
- **Phase 1 — session in shadow mode.** Build `RequirementSession` and the event
  log; compute new completeness *alongside* the old and log divergence. Change no
  behaviour. Do not proceed until they agree.
- **Phase 2 — Assumption Engine.** Replace `_assumptions_and_missing`; assumptions
  become structured and disclosed. Still no interview.
- **Phase 3 — Question Policy.** The sub-threshold branch asks instead of emitting
  an "Information Required" section. This is the first customer-visible change.
- **Phase 4 — tiers.** Deliverable-specific thresholds replace the single
  `HYBRID_THRESHOLD`; freeze/sha traceability into `package/builder.py`.
- **Phase 5 — remaining categories.** Paint booth, dust collector, oven, conveyor.

Phases 0–2 are local, golden-gated work. Phase 3 is the one needing pod-side agent
changes and a fresh `chatId` for every prompt test.

---

## 9. Open questions for review

1. **Tier granularity** — are five tiers right, or do CONCEPTUAL and BUDGETARY
   collapse in practice? Five is easy to define and hard to explain to a customer.
2. **Who owns `target_tier`?** Inferred from the ask ("ballpark" → CONCEPTUAL), or
   chosen explicitly by the engineer in the UI? Inference is smoother; explicit is
   auditable. Probably: infer, show, allow override.
3. **Does the customer see the requirement record**, or only the engineer? It is a
   strong trust artifact but it exposes the assumption machinery.
4. **Cross-category requirements** — a paint shop is booth + oven + scrubber +
   conveyor. Does one session hold several equipment requirements, or does a
   *project* own several sessions? (Recommend: project → sessions, and defer.)
5. **`cost_sensitivity` calibration** — hand-set initially, but it could be
   regressed from the 33 offers once enough slots exist.
