# Agent completion plan — 2026-09-01

Written after extracting the six client calculation workbooks
(`docs/client-calculation-sheets.md`). This plan sequences the work to bring all
three Flowise agents to a finished state, and says plainly what is blocked and on
what.

## Honest scope note

**This is not a one-day job, and the reason is not effort — it is dependencies.**

1. **Seven of the extracted rules carry open questions** (DQ-1..DQ-7 in the
   extraction doc). Three are load-bearing: the face-velocity change moves every
   booth number, the dry-off air density looks like a client typo, and the scrubber
   rounding ladder is unknown. Implementing a formula we have misread would put
   wrong engineering into customer-facing documents — the exact failure golden rule
   #2 exists to prevent.
2. **The agents live in Flowise on the RunPod pod, and the pod is stopped.** No
   agent prompt, tool row or chatflow can be touched from this machine.
3. **The pod runs `main`; this work is on `fix/list-projects-category-filter`.**
   Until that is merged or the branch is deployed, nothing shipped here reaches an
   agent at all.

What *is* achievable today is the whole local engine track (Phase 1–2 below), fully
golden-gated. That is the majority of the new value, and it is what the agents will
then expose.

---

## Phase 0 — housekeeping (do first, ~15 min, LOCAL)

- [ ] **Move the client files out of `frontend/public/`.** That directory is Vite's
      static web root: every file in it is served unauthenticated at
      `http://<host>:5173/<filename>`. It currently holds Vitech's **cost sheets,
      rate build-ups and a 27% profit margin**, plus product datasheets. Nothing in
      `frontend/src/` references any of them, so moving is safe.
      - Calculation workbooks + datasheets -> `backend/data/knowledge_docs/`
      - Confirm `.gitignore` does not exclude that path (it does not).
- [ ] Delete the stray `S6Kc8k....jpg` (looks like an accidental paste).
- [ ] Commit the extraction doc + this plan.

## Phase 1 — additive engineering services (LOCAL, goldens must stay byte-identical)

Each of these is **new code that no existing output path calls yet**, so the goldens
cannot move. Land them first, prove them against the workbooks' own worked examples,
then wire them in Phase 2.

- [ ] **`app/engineering/voc_service.py`** — VOC mass rate, concentration, and the
      LEL gate. Anchor test: 10 L/hr, 60%, 1.2 kg/L, 10000 CMH -> 720 mg/m3, PASS
      against the < 1000 mg/m3 rule.
      *This is a safety verdict, not a number — it belongs in `release_gate.py`
      alongside the existing checks, not as another spec row.*
- [ ] **`app/engineering/heat_load_service.py`** — tank, dry-off oven, curing oven.
      Anchor tests: 308 kW / 220 kW / 209 kW from the sheets' own inputs.
      **Blocked on DQ-1** for the dry-off air term — implement tank + curing oven
      first, leave dry-off air behind a flag until Vitech answers.
      *This closes the standing "oven exhaust is TBD until an ACH is supplied" gap.*
- [ ] **Stock weight constants -> `app/engineering/material_service.py`** — the
      kg-per-standard-length table from the cyclone sheet. **Blocked on DQ-4** for
      square tube and flat; land the six unambiguous rows now.
      *This is the missing rule behind "MS structure is listed even though no rule
      computes its weight yet".*
- [ ] **`app/engineering/scrubber_service.py`** — diameter from airflow at 1.0 m/s,
      duct diameter at 15 m/s. **Ship the computed diameter only.** The rounding to
      a standard size is **blocked on DQ-3** and must not be guessed.

## Phase 2 — changes that MOVE the goldens (LOCAL, each one gated + signed off)

These are corrections, not additions. Every one changes numbers that already appear
in customer-facing documents, so each lands on its own commit with a recorded
before/after golden diff.

- [ ] **Face velocity 0.45 -> 0.5 m/s.** *Blocked on DQ-2.* One constant
      (`paint_shop_service.DEFAULT_FACE_VELOCITY`), but it moves every booth's
      airflow ~11%, and therefore blower selection, motor HP and price.
      **Do not land this without an explicit decision.**
- [ ] **Booth sheet weight: surface-area rule -> panel-count model.** The engine
      computes 1,240 kg and the pricing model seeds 3,645 kg where the client's own
      sheet builds 621 kg from 27 panels. Replace `sheet_weight_kg`'s booth path
      with the panel module. Anchor test: 3000x2250x2400 -> 27 panels -> 621 kg.
- [ ] **Structure weight + painting area** from the length formulas (5b, 5c).
      Anchor: 126 / 308 / 12 kg and 1134 sq.ft.
- [ ] **Booth BOM cost model** built on the above + `rate_card`, validated against
      the sheet's own **Rs 6,49,264**. This is now possible for the first time —
      the cropped row is recovered (5f), so the total reconciles exactly.
- [ ] **Quotation margin model** (5g) replaces the flat 15% bought-out allowance.
      **Blocked on DQ-7** for how the multiplier is selected. Structure the code so
      the multiplier is an input, then a single answer from Vitech configures it.

## Phase 3 — agent completion (POD REQUIRED)

Nothing here can start until the pod is up and the branch question is settled.

- [ ] **Merge `fix/list-projects-category-filter` -> `main`, or deploy the branch.**
      Divergence is small (doc commits). Until this happens the pod cannot see any
      of the above. *This is the single highest-priority pod action.*
- [ ] **Wire the two orphaned tools.** `generate_bom` and
      `generate_engineering_package` both have live endpoints and `operation_id`s
      but **no chatflow calls either**. Decide per agent:
      - Quotation Agent gains `generate_bom`
      - `generate_engineering_package` is heavy (spec + drawing + quote + retrieval);
        it likely belongs to a UI action rather than a chat tool.
- [ ] **New tool rows** for the Phase 1 services that should be reachable by chat:
      `calculate_heat_load`, `check_voc_safety`. Follow the Drawing Agent pattern,
      and keep the payload small — the `delete data.svg` lesson.
- [ ] **Fix the two standing agent defects** (both recorded in CLAUDE.md):
      - Engineering Agent leaks tool-call-shaped JSON on general conversation. The
        frontend guard added 2026-08-05 masks the symptom; the prompt fix is still
        open.
      - Engineering Agent paraphrases `quotation_markdown` instead of printing it
        verbatim — it needs a RULE-4 equivalent, scoped narrowly.
- [ ] **Ingest the knowledge documents.** `python -m rag.ingest data/knowledge_docs/`
      with a `--manifest` for explicit metadata. This is the standing fix for
      `retrieve_knowledge` returning `count:0`.
- [ ] **End-to-end verification** of all three agents, then re-record the 28 contract
      fingerprints only if a change was intended.

## Phase 4 — V1.0 close-out (unchanged from the readiness review)

PDF renderer tests, dependency pinning, CI, HTTPS deployment, and rewriting
`docs/developer_handbook.md` (substantially wrong today).

---

## Decisions needed before Phase 2 can complete

Send DQ-1 .. DQ-7 to Vitech as one list. **DQ-2 (face velocity) is the one that
blocks the most work** — until it is answered, every booth number is provisional.
