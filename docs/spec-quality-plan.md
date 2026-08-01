# Specification Quality — Review Findings and Completion Plan

> Source: client engineering review of a generated paint-booth specification
> (2026-08-01). Verdict **8.3/10** — "a good engineering draft, not ready for
> customer release". Airflow and blower selection rated excellent; component
> selection, engineering consistency and standards compliance rated incomplete.
>
> This document records **why** each defect occurred (traced to code and data,
> not guessed) and the plan to close them.

## 0. The specification under review

`paint booth 10 x 10 x 10 water based` → confidence 87%. Verified correct by the
reviewer: exhaust airflow 162,000 m³/h, inlet air 145,800 m³/h, 2 × 61,000 CFM
blowers, enclosure sheet weight 7,850 kg. Everything below is what went wrong.

---

## 1. WHY THIS HAPPENED — one root cause, six symptoms

The engine has exactly **three** ways to produce a field:

```
   engineering rule   →  origin "rule"      (airflow, blower, weight …)
   nearest offer      →  origin "reused"    (verbatim copy, unscaled)
   neither fired      →  origin "tbd"       (spec_template gap-fill)
```

There is **no layer between them**. Specifically, the pipeline has no
*component-selection* stage, no *cross-validation* stage, no *standards
inference* stage, and it never re-queries history for a field the template
flagged as missing. That single architectural gap produces every defect the
reviewer found.

### 1a. The compound-string problem (defects #1 and #2)

Both contradictions come from **one reused field**. Offer
`OFF-SYNERGY-PB-209R3` (NewSynergy L.L.C, Oman) stores:

```
booth_type = "dry type side down draft, non-pressurized, 0.6 m/s cross velocity"
```

That one opaque string packs **four distinct engineering facts** — filtration
type, draft configuration, pressurisation, and design cross velocity. The engine
copies it verbatim as a single blob, so:

* **"side down draft"** is not a standard booth type — but it is what the
  client's own archive says. We reproduced the source faithfully; the defect is
  in the historical record as much as in our engine. Nothing validates a reused
  categorical value against a controlled vocabulary.
* **0.6 m/s vs 0.45 m/s.** The reused string asserts 0.6 m/s cross velocity
  while `formula_service.FACE_VELOCITY = 0.45` computed the airflow. Nothing
  reconciles them, because the velocity is buried inside prose no code parses.
  The spec therefore states a velocity it did not use.

This is precisely the **B0b** item already logged in CLAUDE.md ("reconcile a
client-given attribute that conflicts with a REUSED design") — now with a
concrete, reproducible instance.

### 1b. Reuse is verbatim and unscaled (defect #5)

The 10 × 10 × 10 m booth (**100 m² face**) reused fields from a
**7.5 × 4.0 × 3.5 m** booth (**14 m² face**) — a **7× size difference** — and
also from a `liquid` booth when the requirement said `water-based`.
`illumination = "20w x 10 LED weatherproof"` was sized for the small booth and
restated as fact for the large one. Reused values are copied whole, with no
check that the field is size-dependent and no scaling when it is.

### 1c. Seeded constants standing in for engineering (defects #4, #2)

`FILTERS_PER_M2 = 0.6` gave 60 filters for 100 m². It is a placeholder, not a
selection: real filter count follows from filter size, airflow and the velocity
through the media. Same class of problem as `FACE_VELOCITY` being a single
constant rather than a per-configuration design value.

### 1d. Deterministic material rule that should be advisory (defect #3)

`material_service.PROCESS_RULES["water-based"] = {"material": "GI", ...}` is a
hard mapping. Material selection actually depends on humidity, corrosion
exposure, chemical exposure and customer preference. The rule should recommend
with a reason, not assert.

### 1e. TBD is a dead end, not a question (defects #6–#10)

`dry_scrubber`, `exhaust_duct` and `control_panel` are **`None` in the source
offer**, so the template correctly marked them TBD — and stopped. Nothing then:

* re-queried history for that field against a similar airflow (#6),
* computed the field from data already in hand — duct sizing from
  162,000 m³/h is a solved calculation (#7),
* derived the field from an established scope rule — a 2 × 60 HP load implies
  MCC, star-delta/VFD, overload, isolator, e-stop (#8),
* inferred it from a standard — fire protection follows from paint type,
  NFPA 33 for solvent (#9),
* or asked the customer, rather than silently blanking (#10).

**The TBD guardrail was built to stop hallucination, and it does. But it became
the answer to every hard field rather than the last resort.**

---

## 2. THE PLAN

Target pipeline — the reviewer's own, which matches the intended architecture:

```
Customer input → Engineering rules → Historical retrieval → Engineering
calculations → Component selection → Validation → Specification
```

Every field must carry one of six provenances: **customer input, engineering
calculation, design rule, historical retrieval, standard, or equipment
catalogue**. `To be determined` survives only where essential *customer*
information is genuinely missing.

### Phase A — Stop the specification contradicting itself
*No new client data needed. Highest value: these are correctness defects.*

| # | Work | Closes |
|---|---|---|
| A1 | **Decompose compound historical fields.** Parse `booth_type` into `filtration` / `draft_config` / `pressurisation` / `cross_velocity_ms` at ingest, keeping the raw string for traceability. | #1, #2 |
| A2 | **Controlled vocabulary for booth type** — Cross Draft / Side Draft / Semi Down Draft / Full Down Draft × Dry Filter / Water Wash. A reused value outside it is flagged, not printed as fact. | #1 |
| A3 | **Cross-validation layer** (`analysis.py::cross_validate`, the seam already identified in B0b). When a reused value contradicts a computed one, the rule wins and the spec carries an explicit reconciliation note. A spec must never state two different values for one quantity. | #2 |
| A4 | **Scale-or-refuse reused values.** Mark each catalog field size-dependent or not. A size-dependent value from an offer more than ~1.5× different in the driving dimension is scaled if a rule exists, else demoted to TBD instead of being asserted. | #5 |

### Phase B — Component selection engine
*New `app/engineering/selection/` package, mirroring `blower_service` — which is
the pattern the reviewer rated excellent, so extend it rather than invent.*

| # | Work | Closes |
|---|---|---|
| B1 | **Filter selection** — from airflow, filter size and face velocity through media. Count follows from `airflow / (filter area × media velocity)`, with pressure drop reported. Replaces `FILTERS_PER_M2`. | #4 |
| B2 | **Illumination** — lux-based: `fixtures = target lux × area / fixture lumens`, per booth-lighting practice. Replaces the copied fixture count. | #5 |
| B3 | **Duct sizing** — from the airflow we already compute: transport velocity (18–20 m/s) → duct area → diameter → static pressure. | #7 |
| B4 | **Electrical scope** — from connected load: MCC, star-delta or VFD, overload, isolator, emergency stop. | #8 |
| B5 | **Fire protection** — inferred from paint process: solvent → NFPA 33 scope; water-based → ABC extinguishers, detection, interlocks. | #9 |
| B6 | **Material selection becomes advisory** — recommend with a reason ("GI enclosure recommended: higher moisture exposure in water-based painting") instead of asserting. | #3 |

### Phase C — Retrieve before declaring TBD

| # | Work | Closes |
|---|---|---|
| C1 | **Field-level retrieval fallback.** Before a template field becomes TBD, query history for that specific field scoped to a comparable design (e.g. nearest airflow). Populate when the match is strong, attributing the source offer; otherwise TBD. | #6 |

### Phase D — Ask instead of blanking

| # | Work | Closes |
|---|---|---|
| D1 | **Customer-decision fields** (material handling: conveyor / monorail / trolley / manual) move from silent TBD into `missing_inputs`, so the agent *asks*. | #10 |

### Phase E — Validation gate

| # | Work |
|---|---|
| E1 | Extend `validate.py` into a release gate: no contradictory values, no size-dependent value reused across a large size gap, no TBD outside the customer-input set. Surface a **"customer-ready / engineering draft"** status so the 8.3/10 judgement becomes something the system reports about itself. |

---

## 3. WHAT WE NEED FROM THE CLIENT

Phases A3, C1 and E1 need no new data. These do:

1. **Booth-type vocabulary** — confirm the standard set and how each maps to a
   design cross velocity (this also settles the 0.45 vs 0.6 question).
2. **Filter data** — makes, sizes, rated airflow, clean/dirty pressure drop.
3. **Lighting standard** — target lux inside the booth, and the fixture
   catalogue (wattage, lumens, flame-proof rating).
4. **Duct standard** — transport velocity, material and gauge by diameter.
5. **Electrical panel scope** — standard inclusions by connected load, and when
   VFD is preferred over star-delta.
6. **Fire-protection standard** per paint type (and which authority applies —
   NFPA 33, IS, or local).
7. **Material selection matrix** — when GI / MS / SS is actually chosen, so B6
   recommends the way Vitech's engineers do.

## 4. Sequencing

**Phase A first** — a specification that contradicts itself is worse than one
with honest gaps, and A needs nothing from the client. **Then C1 and D1**, which
convert dead-end TBDs into either a retrieved value or a question. **Then B**, as
each standard arrives from the client — every item in B is independent, so they
can land one at a time. **E1 last**, once there is enough substance for the gate
to be meaningful.
