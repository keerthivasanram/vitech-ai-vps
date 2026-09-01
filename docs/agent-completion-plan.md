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

- [x] **Move the client files out of `frontend/public/`.** That directory is Vite's
      static web root: every file in it is served unauthenticated at
      `http://<host>:5173/<filename>`, and it held Vitech's **cost sheets, rate
      build-ups and a 27% profit margin**. Nothing in `frontend/src/` references any
      of them, so moving is safe.
      *Nothing to move on this checkout (2026-09-01): `frontend/public/` holds only
      `favicon.svg`. The workbooks are untracked, so they still exist only on the
      machine they were delivered to — whoever holds them must move them there before
      committing.*
      - Calculation workbooks + datasheets -> `backend/data/knowledge_docs/`
      - Confirm `.gitignore` does not exclude that path (it does not).
- [x] Delete the stray `S6Kc8k....jpg` — not present on this checkout either.
- [x] Commit the extraction doc + this plan — done in `00c241b`.

## Phase 1 — additive engineering services (LOCAL, goldens must stay byte-identical)

Each of these is **new code that no existing output path calls yet**, so the goldens
cannot move. Land them first, prove them against the workbooks' own worked examples,
then wire them in Phase 2.

- [x] **`app/engineering/voc_service.py`** — DONE — VOC mass rate, concentration, and the
      LEL gate. Anchor test: 10 L/hr, 60%, 1.2 kg/L, 10000 CMH -> 720 mg/m3, PASS
      against the < 1000 mg/m3 rule.
      *This is a safety verdict, not a number — it belongs in `release_gate.py`
      alongside the existing checks, not as another spec row.*
- [x] **`app/engineering/heat_load_service.py`** — DONE — tank, dry-off oven, curing oven.
      Anchor tests: 308 kW / 220 kW / 209 kW from the sheets' own inputs.
      **Blocked on DQ-1** for the dry-off air term — implement tank + curing oven
      first, leave dry-off air behind a flag until Vitech answers.
      *This closes the standing "oven exhaust is TBD until an ACH is supplied" gap.*
- [x] **Stock weight constants -> `app/engineering/material_service.py`** — DONE — the
      kg-per-standard-length table from the cyclone sheet. **Blocked on DQ-4** for
      square tube and flat; land the six unambiguous rows now.
      *This is the missing rule behind "MS structure is listed even though no rule
      computes its weight yet".*
- [x] **`app/engineering/scrubber_service.py`** — DONE — diameter from airflow at 1.0 m/s,
      duct diameter at 15 m/s. **Ship the computed diameter only.** The rounding to
      a standard size is **blocked on DQ-3** and must not be guessed.

### Phase 1 outcome (2026-09-01)

Landed as **163 added lines and zero deleted** — three new modules plus appends to
`material_service` and `standards_service`, and **nothing in `app/` imports any of
them yet** (checked by grep). That is what makes the claim below verifiable rather
than hopeful: **all ten offline suites pass and every golden is byte-identical**, and
the two HTTP suites cannot have moved because no route, response body or
`operation_id` was touched. 29 anchor checks were added to `tests_engineering.py`.

What the sheets' own worked examples proved, and what they did not:

| Anchor | Result |
|---|---|
| VOC 10 l/hr, 60%, 1.2 kg/l, 10000 CMH -> 720 mg/m3, PASS | reproduces exactly |
| Tank 2250x1500x1500, 25->75 C, 750 kg -> 264,125 Kcal / 308 kW | reproduces exactly |
| Scrubber tower 6750 m3/h -> 1545 mm; duct -> 399 mm | reproduces exactly |
| Structure 40 m of channel -> 7 lengths -> 308 kg | reproduces exactly |
| Dry-off oven -> 188,786 Kcal / 220 kW | **does NOT reproduce — new open item DQ-8** |
| Curing oven -> 209 kW | not assertable: the conveyor and job masses it needs are not recorded on the sheet |

Deliberate refusals, each of which a caller sees as a reported gap rather than a number:
the dry-off **air term is omitted** until DQ-1 is answered; the scrubber's
**standard-size rounding** is not applied (DQ-3); the two stock sections the client's
own workbooks disagree about return **None** rather than a picked side (DQ-4); and a
curing oven with no conveyor or job mass says so instead of totalling as if complete.

**The VOC gate is written but NOT yet wired into `release_gate.assess()`** — that is
a Phase 2 wiring step, because it changes what an assessment returns.

## Phase 2 — changes that MOVE the goldens (LOCAL, each one gated + signed off)

These are corrections, not additions. Every one changes numbers that already appear
in customer-facing documents, so each lands on its own commit with a recorded
before/after golden diff.

- [x] **Face velocity 0.45 -> 0.5 m/s — DONE 2026-09-01**, on the product owner's
      explicit decision, and made **overridable per design** rather than a fixed law
      (`compute_spec(face_velocity=...)`, fed from `params["face_velocity_ms"]`).
      Applied to the three face-based dry booth types plus the two module-level
      defaults; **full down draft, pressurized and powder were left alone** because
      the client's table is a face-based L x H calculation that does not describe
      them. Measured: booth airflow +11.1% (19,440 -> 21,600 m3/h on the 5x3x4 case),
      filters 16 -> 17, duct velocity 14.0 -> 15.6 m/s, **blower model unchanged** in
      both dry cases. Goldens re-recorded: **3 paint-booth cases moved, all 4
      wet-scrubber and all 3 knowledge cases byte-identical**, and the powder case
      moved in WORDING only (its 0.55 m/s and 47,520 m3/h are untouched) — which is
      the proof the change is scoped to the types it was meant to reach.
      **`tests_api_contract.py` still needs re-recording** for the booth endpoints:
      it requires an admin credential this session does not hold.
- [ ] **DQ-9, NEW and larger than DQ-2: the face axis.** The client's booth sheet
      computes the face as **L x H**; `compute_spec` uses **W x H**. On the client's
      own 3.0L x 2.25W x 2.4H booth that is 12,960 CMH against our 9,720 — **33%**.
      Not fixed unilaterally: which axis a customer's "length" means is a convention
      only Vitech can settle, and guessing wrong mis-sizes every booth's blower.
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
      **Divergence is 79 commits ahead / 3 behind, not "a few doc commits"** — that
      earlier reading was backwards and is corrected in CLAUDE.md (2026-09-01). Until
      this happens the pod cannot see any of the above, nor the last month's work.
      *This is the single highest-priority pod action.*
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
