# GA Drawing Quality — Gap Analysis

**Date:** 2026-08-05 · **Scope:** `backend/app/drawing/` (2,939 lines) measured against a
production industrial general-arrangement sheet.

**Premise, agreed with the product owner:** the deterministic vector pipeline is CORRECT and
stays. Nothing here proposes an image-generation model. Every recommendation below is a
deterministic geometry/text addition that preserves byte-identical rendering for a given spec.

**Method:** the renderer was read, then four categories were RENDERED and the emitted SVG
inspected — the standing lesson of this project is that drawing defects are invisible in source
and only appear in output. Every finding below is verified, not inferred.

---

## 0. THE BLOCKER — the flagship category draws nothing

**`wet_scrubber` renders an empty "NO DIMENSIONED VIEWS" sheet on the documented anchor case.**

Verified: `wet scrubber 800 cfm 750mm tower 4 nos` →
`envelope_mm = {length: null, width: null, height: null}`, `scale: NTS`, `views: []`,
`legend: 0 rows`. The richest glyph in the codebase (209 lines — spray headers, demister,
baffle stage, sump, working level, pump, OF/MU/DR connections, access door) **never executes.**

**Root cause — a label mismatch, exactly the class of bug `CLAUDE.md` already warns about
("template labels must match what the engine emits").** `envelope._wet_scrubber` was written for
a VERTICAL SPRAY TOWER and looks for rows named `tower diameter` and `tower height`. The engine
emits neither. What it actually resolves is:

| label | value | origin |
|---|---|---|
| `Scrubber type` | horizontal baffle plate | reused |
| `Scrubber dimension` | `700mm W x 1700mm L` | **reused** |

Three independent reasons the envelope cannot form:
1. The label is `Scrubber dimension`, not `tower diameter`.
2. The value carries only **two axes** (W and L) — there is no height anywhere in the spec.
3. Its origin is `reused`, which `_TRUSTED_ORIGINS` correctly refuses — a historical offer's
   casing is a different machine's casing.

**Vitech builds HORIZONTAL baffle scrubbers, but the envelope deriver models a vertical tower.**
This is not a rendering bug; it is a missing engineering rule. Point 3 is the platform working
as designed and must not be loosened.

**Fix (P0, needs one client input):** ask Vitech for the **scrubber height rule** for a
horizontal baffle unit (it will follow from airflow and gas velocity, the same way the booth's
does). Then `_wet_scrubber` reads `Scrubber dimension` for L/W and the new rule output for H,
and the 209-line glyph starts earning its keep. Until that rule lands the honest blank sheet is
the correct output — but it should be **stated in the TBD schedule as "scrubber height — no
engineering rule supplied"**, which today it is not.

---

## 1. View quality

| | status |
|---|---|
| Plan / Front / Side | ✅ third-angle, correctly placed, centred, captioned |
| Isometric | ❌ **absent** — `VIEW_SETS` offers only `ga` / `plan` / `elevation` |
| Section views | ❌ no section line, no cutting plane, no hatching primitive |
| Detail bubbles | ❌ none |
| Break lines (long runs) | ❌ none — verified consequence below |

**Verified defect — long equipment renders as a hairline.** A 60 m conveyor forces scale 1:500,
at which its 3 m width draws **6 mm** on the sheet. A drawing office would draw this with a
**break line** at 1:50 and note the true length. Same applies to ducting runs.

**Also verified — an axis is silently lost.** `overhead conveyor 60 m track 3m x 1m x 4m` →
`{length: 60000, width: 3000, height: 1000}`. The stated **4 m height was dropped** and 1 m
became the height. That is an `understand.py` extraction defect, not a drawing one, but it
reaches the customer through the drawing. Worth its own regression test.

**Priority:** break lines (P1, deterministic, high value for conveyor/ducting) → section views
with hatching (P2) → isometric (P2; a true axonometric of a box envelope is cheap and
deterministic, and it is what a client recognises as "a proper drawing").

## 2. Component library

Objective depth per category (balloons = drawn+ballooned items):

| category | lines | balloons | lettered notes | flow arrows | plan | side |
|---|---:|---:|---:|---:|:--:|:--:|
| wet_scrubber | 209 | 10 | 4 | 3 | Y | Y |
| dust_collector | 194 | 10 | 4 | 2 | Y | Y |
| paint_booth | 160 | 11 | 3 | 3 | Y | Y |
| powder_coating_plant | 160 | 3 | 2 | 0 | Y | Y |
| hot_air_oven | 75 | 6 | 0 | 0 | Y | Y |
| conveyor | 50 | 3 | 0 | 0 | Y | Y |
| pretreatment_plant | 45 | 2 | 1 | 0 | Y | – |
| paint_drying_oven | 44 | 3 | 0 | 0 | Y | Y |
| fume_extraction | 35 | 2 | 0 | 0 | Y | – |
| ducting | 34 | 2 | 0 | 0 | Y | Y |
| flash_off_zone | 32 | 3 | 0 | 0 | Y | – |
| blast_booth | 31 | 1 | 0 | 0 | Y | – |
| cleaning_room | 25 | **0** | 0 | 0 | Y | – |
| buffing_booth | 23 | 1 | 0 | 0 | Y | Y |

**Three tiers, and the bottom tier is the problem.** Three categories are production-credible
(scrubber, collector, booth). One is mid (oven, plant). **Ten are near-empty boxes** — and
`cleaning_room` draws **zero ballooned components**, i.e. a captioned rectangle. Seven have **no
side elevation at all**, so a third of their sheet is blank.

**Scale consistency** ✅ — all glyphs are proportional to the view, so nothing breaks at any
scale. **Recognisability** is the gap, not correctness.

## 3. Dimensioning — the largest single gap

`views.draw_view` emits **exactly two dimensions per view**: overall width and overall height.
That is all. Verified across every render.

| dimension class | status |
|---|---|
| Overall L/W/H | ✅ with extension lines, solid arrowheads, TBD-honest text |
| Centre lines | ✅ both axes per view, correct CENTER dash pattern |
| Extension lines / arrowheads | ✅ correct drafting form |
| **Critical dimensions** | ❌ **none** — no tower dia, duct bore, door opening, filter pitch, hopper height, platform height, discharge height |
| **Diameter / radius symbols** | ❌ no `Ø` or `R` — a round duct is dimensioned as a plain number |
| Chain / running / baseline dims | ❌ none |
| Anchor-bolt / hole setting-out | ❌ none (correctly blocked on client foundation standard) |
| Elevation / datum marks | ❌ none |
| Angular dimensions | ❌ none (hopper cone angle is drawn but never dimensioned) |

**The honest constraint:** most component POSITIONS have no engineered setting-out rule, and
dimensioning them would be fabrication — golden rule #2 forbids it, correctly.

**But a large subset is already resolved and dimensionable today with zero new client input**,
because these are values the spec engine ALREADY computes:
- duct **Ø** (`select_duct` computes it — currently printed only as legend text),
- filter element size (`600 x 600` is in the spec),
- tower/collector casing size where stated,
- blower and motor frame envelope where the catalogue model is known.

**This is the highest-value deterministic win in the whole analysis:** a `Dim` with a `Ø` prefix
on values the engine already owns. **P0 after the blocker.**

## 4. Legends

| | status |
|---|---|
| Numbered callouts | ✅ self-allocating (`item()`), no gaps in sequence |
| Lettered schedule rows | ✅ `note_item()` — a genuinely good idea: resolved-but-unpositioned items are scheduled, not dropped |
| Automatic item list | ⚠️ **capped at 8 rows and silently truncated** |
| Symbol consistency | ⚠️ no symbol key; a circle means fan, pump, nozzle, airlock and balloon depending on context |

**Verified truncation:** a paint booth resolves **12 BOM rows**; the sheet prints 8 and
"... and 4 more". A parts list that omits a third of the parts is not a parts list. The TBD
schedule is likewise capped at 12 and the legend is **unbounded** (see §8).

**Recommend:** overflow to a second column, or a continuation sheet, rather than a cap. P1.

## 5. Engineering annotations

| | status |
|---|---|
| Flow arrows | ✅ good — scrubber/booth/collector, direction-only, never dimensioned (correct) |
| Inlet / outlet labels | ✅ `GAS IN` / `GAS OUT` / `DIRTY AIR IN` / `INLET SIDE` |
| **Equipment tags** | ❌ **no tag numbers** — no `SC-01`, `F-01`, `P-01`, `M-01` |
| **North arrow** | ❌ absent entirely |
| Connection schedule | ⚠️ scrubber marks `OF`/`MU`/`DR` on the drawing ✅ but sizes are a lettered note, not a table |
| Weld / finish symbols | ❌ none |
| Datum / grid references | ❌ none |
| Sheet zoning (A/B/C, 1/2/3) | ❌ none — a revision cannot cite a zone |

**Equipment tags are the notable miss.** Every other document the platform emits (BOM,
quotation, cross-reference schedule via `identifiers.py`) already carries `VT-nn` ids — but the
drawing balloons number **1, 2, 3 independently**, so the GA and the BOM use different
identifiers for the same part. `identifiers.py` deliberately chose not to renumber, and that
reasoning holds for the BOM — but the drawing should at minimum **print the `VT-nn` id
alongside the balloon number in the item list**, which is a text change, fully deterministic.
**P1, and it closes a real cross-document traceability gap.**

North arrow: trivial, deterministic, but only meaningful on a plot-plan; **P2** and only where
the client supplies orientation.

## 6. Technical tables

| | status |
|---|---|
| Item / parts list | ✅ present (capped — §4) |
| **Design-data table** | ❌ **absent** |
| Material table | ❌ absent (MOC appears only as scattered legend text) |
| Notes | ✅ 3 standing notes, correct and well-judged |
| Weight / finish schedule | ❌ absent |

**A production GA carries a design-data block** — airflow, static pressure, motor kW, material,
finish, operating temperature, power supply. The platform **already resolves every one of these
values**; they are simply never tabulated on the sheet. Today they leak out as truncated legend
strings (`f"Exhaust duct {duct}"[:52]`).

**This is the second-highest-value win: a `_data_table()` in `sheet.py` fed from
`technical_details`, filtered to the non-hardware rows.** Pure composition of resolved values —
no new engineering, no new client input, fully deterministic. **P0/P1.**

## 7. Title block

Present ✅: company + address (shared with the letterhead), title, duty, client, drawing no.,
scale, size, units, date, drawn, checked, rev, status.

| missing | priority |
|---|---|
| **APPROVED field** (only DRAWN / CHECKED exist) | P1 — release needs a third signature |
| **Third-angle projection symbol** | **P1 — ISO-mandatory, trivial, deterministic** (two concentric-circle frustum views) |
| Weight | P2 (booth sheet weight IS computed — 1,240 kg — and could print) |
| General tolerance note | P1 (one line of text) |
| Finish / paint spec | P2 |
| Sheet n of m | P1 |
| Drawing-number scheme | P2 — today `VT/GA/{yymmdd}/DRAFT` is date-based, not a project register |

**Revision block** ✅ exists and is correctly hidden when empty — but shows only the **last 3**
revisions, and has **no "by" column** and no zone reference.

## 8. Layout

| | status |
|---|---|
| Margins / frame | ✅ consistent 10 mm + inner frame |
| View centring | ✅ fixed previously, verified good |
| Typography | ⚠️ **8 hard-coded sizes** (1.9–4.2 mm) with no type scale; ISO 3098 prefers 2.5/3.5/5/7 |
| Text wrapping | ✅ `_wrap()` breaks at spaces, 2-line cap |
| **Column overflow** | ❌ **verified defect** |

**Verified defect — the notes overprint the title block on A4.** `side_column` advances `y`
with no bound check against the title block's top edge:

| sheet | title-block top | notes-layer text landing inside it |
|---|---:|---:|
| **A4** dust collector | 158 mm | **6 text elements** |
| **A4** paint booth | 158 mm | **2 text elements** |
| A3 (default) | 245 mm | 0 ✅ |

A3 is the default so this is not currently customer-visible — but A4 is offered in the studio
and produces an unreadable sheet. **P1, cheap fix:** measure the column before drawing and
overflow/elide against `sh - MARGIN - TB_H`.

**Colour:** the renderer is deliberately monochrome (`currentColor`) so the studio can theme it.
The DXF exporter already assigns **per-layer ACI colours**. Semantic colour (grey body, blue
motors, green filter media, red valves) would need component sub-layers — worthwhile, but it is
a **presentation preference, not an engineering gap**, and monochrome prints correctly. **P2.**

## 9. Category-specific gaps

Against what a professional engineering department would show:

**Wet Scrubber** — has: spray header ✅, mist eliminator ✅, inspection door ✅, overflow ✅,
drain ✅, make-up ✅, sump + working level ✅, pump ✅, baffle stage ✅.
**Missing: access ladder, platform, level indicator (instrument — only a dashed level line
today), interconnecting piping, pH/dosing point, sample point.** *(All moot until §0 is fixed.)*

**Dust Collector** — has: cartridge/bag array ✅, pulse-jet header ✅, solenoids ✅, hopper ✅,
rotary airlock ✅, DP gauge ✅, tube sheet ✅.
**Missing: dust bin / collection drum drawn (lettered note only), support structure and legs,
access platform + ladder, explosion vent drawn (lettered note only), compressed-air receiver.**

**Paint Booth** — has: filter bank ✅, airflow arrows ✅, lighting ✅, doors ✅, view panels ✅,
control panel ✅, carbon chamber ✅, intake filter ✅.
**Missing: exhaust plenum and stack (only a wall stub), floor grating / ramp, separate man
door, manometer / DP gauge, fire-suppression nozzles (fire system is a lettered note only).**

**Conveyor** — **the weakest of the four the client named.** 50 lines, 3 balloons, **0 BOM rows**,
plan view is a bare centreline. Has: track ✅, carriers ✅, drive unit ✅.
**Missing: tail pulley / take-up, rollers, motor + gearbox as distinct items, support columns
and hangers, chain/trolley detail, track section profile, turn radii, transfer points.**

**Ten remaining categories** need the §2 treatment before they are presentable at all.

---

## Recommended order

**Every item below is deterministic and preserves byte-identical rendering for a given spec.**

| # | work | area | why first |
|---|---|---|---|
| **0** | **Wet scrubber envelope — get the height rule from Vitech, fix `_wet_scrubber`** | §0 | The flagship category currently draws nothing. Blocks the best glyph in the codebase. |
| **1** | **Design-data table on the sheet** | §6 | Values are already resolved; pure composition. Biggest credibility gain per line of code. |
| **2** | **Ø / critical dimensions for engine-owned values** (duct bore, filter size, casing) | §3 | Already computed; no client input needed. Closes the largest drafting gap. |
| **3** | Projection symbol, APPROVED field, tolerance note, sheet n of m | §7 | Hours of work; ISO compliance. |
| **4** | A4 column-overflow fix + item-list overflow instead of truncation | §8, §4 | Real defects, both verified. |
| **5** | `VT-nn` ids in the drawing item list | §5 | Closes GA↔BOM traceability. Text-only change. |
| **6** | Break lines for long runs | §1 | Makes conveyor and ducting sheets usable. |
| **7** | Lift the ten thin glyphs to scrubber/collector depth | §2 | Largest effort; one function each, fully additive. |
| **8** | Section views + hatching, then isometric | §1 | Highest polish, lowest urgency. |

**Blocked on client input (do not invent):** component setting-out and anchor bolts (foundation
layout), maintenance clearances (access standard), scrubber height rule (§0), plot orientation
for a north arrow, drawing-number register.

**Guardrails for all of the above:** run `tests_drawing.py` (122 checks) and `tests_golden.py`
before and after; both must stay ALL PASS. Any new sheet element must be absent when its value
is unresolved — an empty table header is worse than no table. Screenshot every change; this
file exists because rendering, not reading, is what finds drawing defects.
