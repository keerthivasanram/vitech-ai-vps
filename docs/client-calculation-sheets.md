# Client calculation sheets — extracted engineering (2026-09-01)

Source: six Excel workbooks supplied by Vitech, delivered 2026-09-01. Every formula
below is transcribed from the workbook cells, not inferred. Cell references are given
so any value can be traced back.

> **Status (2026-09-01, third pass): PARTIALLY IMPLEMENTED, and now VERIFIED AGAINST
> THE ACTUAL WORKBOOK CELLS** — the files reached the pod, so every formula below was
> re-read from the cell rather than from the transcription. **Phase 1 has landed.** Sections 1 (scrubber/duct diameter), 2 (heat load), 3 (VOC/LEL) and the
> stock-weight table in 6 are now executable in `app/engineering/scrubber_service.py`,
> `heat_load_service.py`, `voc_service.py` and `material_service.py`, guarded by
> anchor tests in `tests_engineering.py`. **No existing output path calls them yet**,
> which is why every golden and every contract fingerprint is unchanged. Sections 4
> and 5 (face velocity, panel weight, structure, cost and margin) are Phase 2: they
> MOVE customer-facing numbers and are blocked on DQ-2, DQ-4 and DQ-7.
> The implementation plan is `docs/agent-completion-plan.md`.

---

## 1. Vertical scrubber — diameter (`Vertical Scrubber - Diameter calculation.xlsx`)

```
Q(m3/s)      = air_volume_cmh / 3600
A(m2)        = Q / v
r(m)         = sqrt(A / 3.14)          # the sheet uses 3.14, not pi
D(mm)        = r * 1000 * 2
```

| Duty | Velocity | Cell |
|---|---|---|
| Across scrubber tower | **1.0 m/s** | D6 |
| Inlet duct | **15 m/s** | D19 |
| Exhaust duct | **15 m/s** | D33 |

**OPEN QUESTION — the rounding row is stale.** At 6750 cmh the sheet computes
D = 1545 mm (D12) but row D13 reads `~ 950`. 950 mm corresponds to ~2550 cmh, so
`~950` is a hand-typed leftover from an earlier run, not a rounding of 1545. Same for
the ducts: computed 399 mm, typed `~300` (inlet) and `~350` (exhaust). **We do not
know Vitech's standard-diameter ladder or their rounding direction.** Ask before
implementing the final selection step.

## 2. Heat load (`Heat Load.xlsx`) — three sheets

Shared: `kW = ROUNDUP(Kcal / 860, 0)`.
Steel specific heat **0.11**, air **0.24**, water **1.04** kcal/kg°C.
Steel density **7850** kg/m3, water **1.0** kg/l.

### Tank

```
volume_m3 = ROUNDUP((L/1000) * (W/1000) * ((H-200)/1000), 0)   # 200 mm freeboard
mass_kg   = volume_m3 * 1000 * 1.0
Kcal      = (mass * 1.04 * dT) + (tank_steel_mass * 0.11 * dT)
```

Worked: 2250x1500x1500, 25->75 C, steel 750 kg -> 264,125 Kcal -> **308 kW**.

### Dry-off oven

```
steel_mass = ROUNDUP(((L*H)*2 + (W*H)*2 + (L*W)*3) * 7850/1000 * thk_mm, 0)   # metres
total_mass = job_with_basket_mass * per_hour_qty + steel_mass
Kcal_steel = ROUNDUP((total_mass * 0.11 * dT) * 1.10, 0)        # +10%
air_mass   = volume_m3 * 101.325                                 # see note
Kcal_air   = ROUNDUP((air_mass * 0.24 * dT) * 1.10, 0)           # +10%
```

Worked: 4300x2750x3000, 30->120 C, 6/hr x 1500 kg, 1.2 mm -> 188,786 Kcal -> **220 kW**.

> **THE DRY-OFF WORKED TOTAL DOES NOT REPRODUCE — see DQ-8.** Applying the formulas
> above to those inputs, *including* the sheet's own `101.325` air factor, gives
> 105,993 (steel + load) + 85,406 (air) = **191,399 Kcal -> 223 kW**, not 188,786 /
> 220 kW. A ~1.4% gap means one recorded input differs from what the cell actually
> used. Found by implementing the formulas in `heat_load_service`, which reproduces
> the tank (264,125 Kcal / 308 kW) and both scrubber diameters exactly.

> **NOTE — air density 101.325 (N13) is wrong dimensionally**; that is standard
> atmospheric *pressure* in kPa, not density. The curing-oven sheet uses **1.204
> kg/m3** for the same quantity. The dry-off air figure is ~84x too high if read as
> density. Flag to Vitech: almost certainly a typo in their sheet, but we must not
> silently "fix" a client formula. See open item DQ-1.

### Curing oven

```
steel_mass  = ROUNDUP(((L*H)*2 + (W*H)*2 + (L*W)*3) * 7850/1000 * thk_mm, 0)
Kcal_steel  = ROUNDUP((steel_mass + conveyor_mass + job_with_jig_mass) * 0.11 * dT, 0)
air_mass    = volume_m3 * 1.204
Kcal_air    = ROUNDUP(air_mass * 0.24 * dT, 0)
insul_area  = ROUNDUP((L*H) + (W*H) + (L*W), 0)                  # m2
insul_kW    = ROUNDUP((insul_area * dT_kelvin * U) / 1000, 0)
Total Kcal  = (Kcal_steel + Kcal_air) * 1.15                     # 15% margin
```

Insulation U-values (W/m2K): **50 mm = 0.4, 100 mm = 0.35, 150 mm = 0.3**.
Worked: 25000x2100x3000, 30->220 C -> **209 kW**.

## 3. Paint shop VOC / LEL (`Paint shop VOC calculation.xlsx`)

```
mVOC_kg_hr = paint_consumption_l_hr * density_kg_l * (voc_percent / 100)
mVOC_g_hr  = mVOC_kg_hr * 1000
C_g_m3     = mVOC_g_hr / airflow_cmh
C_mg_m3    = C_g_m3 * 1000
```

Worked: 10 L/hr, 60% VOC, 1.2 kg/L, 10000 CMH -> 7.2 kg/hr -> **720 mg/m3**.

**Safety limits (this is a pass/fail gate, not a number):**

- LEL of typical solvent ~ **1.2 % by volume**
- Design rule: maintain **< 25 % of LEL**
- Practical: **< 1000 mg/m3**

## 4. Standard booth table (`Standard Booth.xlsx`)

```
CMH = L(m) * H(m) * 0.5 * 3600        # face velocity 0.5 m/s
cfm = CMH / 1.7
```

| Type | L (mm) | H (mm) | CMH | Blower |
|---|---|---|---|---|
| Wet | 1500 | 2400 | 6480 | 5"/3600/5.0HP |
| Wet | 2250 | 2400 | 9720 | 5"/6000/7.5HP |
| Wet | 3000 | 2400 | 12960 | 5"/7200/10.0HP |
| Dry | 1500 | 2400 | 6480 | 3"/3200/3.0HP |
| Dry | 2250 | 2400 | 9720 | 3"/6000/5.0HP |
| Dry | 3000 | 2400 | 12960 | 3"/10200/7.5HP |
| Dry (alt) | 1500 | 2400 | 6480 | 4"/3700/5.0HP |
| Dry (alt) | 2250 | 2400 | 9720 | 4"/6500/7.5HP |
| Dry (alt) | 3000 | 2400 | 12960 | 4"/9000/10.0HP |

Standard widths offered: 1250 / 1500 / 2250 / 3000 mm.

> **FACE VELOCITY IS 0.5 m/s, NOT 0.45.** `paint_shop_service.DEFAULT_FACE_VELOCITY`
> is 0.45 (NFPA 33), chosen only because the earlier client document did not state a
> value. It now does, in two independent workbooks. See open item DQ-2 — this moves
> every booth airflow by ~11% and WILL move the goldens.

## 5. Paint booth cost model (`Non pressurised ... 3.0m L x 2.4m W x 2.4m H.xlsx`)

### 5a. Panel count -> sheet weight (replaces the surface-area rule)

Outer envelope from working size:

```
L_out = L + 100
W_out = W + 750
H_out = H + 100 + 50
```

Panel counts (900 x 2500 x 1.2 MS sheet, **23 kg each**):

```
back  = ROUNDUP((L_out/750) * (H/2500), 0)
front = back
right = ROUNDUP((W_out/750) * (H/2500), 0)
left  = right
top   = ROUNDUP((L_out/750) * (W_out/2500), 0)
filter_frame_top_bottom = 4
service_door            = 2
panels = back+front+right+left+top+filter_frame+service_door
sheet_weight_kg = panels * 23
```

Worked (3000 x 2250 x 2400): 4+4+4+4+5+4+2 = **27 panels -> 621 kg**.

Plus: blower mounting plate 1 no x 150 kg; filter frame 2 nos x 50 kg (14 swg).

> **This is the fix for the 1,240 kg vs 3,645 kg vs 696 kg disagreement recorded in
> CLAUDE.md.** The engine's 5-side surface-area rule and the pricing model's
> 180 kg/m2 seed are both wrong. The client builds from a **panel module**, not a
> continuous skin.

### 5b. Structure lengths -> weight

```
sq_tube_m = ROUNDUP(L_out*3 + W_out*2 + 1.0*4 + 1.5*4 + 2.45*4, 0)
channel_m = ROUNDUP(L_out*3 + W_out*2 + H_out*8 + 1.0*4, 0)
flat_m    = 6
nos       = ROUNDUP(metres / 6, 0)
```

Weight per 6 m length: **sq tube 21 kg, channel 44 kg, flat 12 kg**.
Worked: 36 m -> 6 nos -> 126 kg; 40 m -> 7 nos -> 308 kg; 6 m -> 1 no -> 12 kg.

### 5c. Painting area

```
panel_paint_sqft     = ROUNDUP((plate_nos + panel_nos + filter_frame_nos) * 3.25 * 10.76, 0)
structure_paint_sqft = (sq_tube_nos + flat_nos + channel_nos) * 6 * 0.25 * 4
total_sqft           = panel_paint_sqft + structure_paint_sqft
```

Worked: 1050 + 84 = **1134 sq.ft**.

### 5d. Airflow (side draft, dry booth)

```
face_area_m2 = (L_working/1000) * (H_working/1000)
CMH          = face_area * 0.5 * 3600
cfm          = CMH / 1.7
```

Worked: 3.0 x 2.4 = 7.2 m2 -> 12,960 CMH -> 7,624 cfm -> blower **CLP-4-10-9000**.
(Matches `blower_service.select_booth_blower` — the anchor test still holds.)

> **THE FACE AXIS DOES NOT MATCH OURS — see DQ-9.** This sheet's face is **L x H**;
> `compute_spec` uses **W x H**. On this very booth (3.0L x 2.25W x 2.4H) we return
> 9,720 CMH against the sheet's 12,960 — a 33% gap, larger than the DQ-2 velocity
> change. It is NOT fixed unilaterally: which axis a customer's "length" refers to is
> a convention question only Vitech can settle, and guessing it wrong mis-sizes the
> blower on every booth.

### 5e. Rates confirmed (all match `rate_card.py`)

MS sheet **Rs 85/kg** RM + **Rs 45/kg** labour. MS sections **Rs 75/kg** + **Rs 50/kg**.
Painting **Rs 35/sq.ft**. Motor 10 HP = Rs 35,000 (**Rs 3,500/HP**).

### 5f. THE CROPPED ROW IS RECOVERED

CLAUDE.md records Rs 80,730 as unaccounted (visible Rs 5,68,534 against a stated
Rs 6,49,264). Row 8 of the costing sheet is that row:

> MS 18 SWG Sheet, 2500 x 900 x 1.2 thk, 621 kg -> RM 52,785 + labour 27,945 = **80,730**

5,68,534 + 80,730 = **6,49,264**. The total reconciles exactly. **The booth cost model
is now validatable end to end.**

### 5g. Quotation margin model (`Combine` sheet) — NEW, no equivalent in code

| Line | Works cost | Multiplier | Selling |
|---|---|---|---|
| Booth + blower + panel | 649,264 | **x 1.40** | 908,970 |
| Exhaust duct | 105,000 | **x 1.26** | 132,300 |
| Design & contingency | — | fixed | 25,000 |
| Packing & forwarding | — | fixed | 11,000 |
| E & C | — | fixed | 65,000 |
| Transport | — | customer scope | — |

```
subtotal   = sum of selling lines                  = 1,142,270
discount   = booth_selling * 0.10                  =    90,897
final      = subtotal - discount                   = 1,051,373
profit     = final - works_cost_total              =   297,109   (27%)
```

> This **replaces the flat 15% bought-out allowance** that CLAUDE.md identifies as the
> cause of the -57% cost-plus divergence. Bought-outs are no longer an allowance: they
> are line items at real unit prices, and margin is applied per line.

## 6. Cyclone recovery + cartridge filter (`Cyclone recovery & Cartridge filter unit.xlsx`)

Complete costed BOMs for a 9-filter (3x3) cartridge dust collector, a cyclone recovery
unit and dia-450 inlet/outlet ducting.

**Stock weight constants (kg per standard length/sheet) — these are the missing
structural weight rules:**

| Item | Size | kg |
|---|---|---|
| MS 16 swg CR sheet | 1250 x 2500 x 1.6 | 40 |
| MS 14 swg CR sheet | 1250 x 2500 x 2.0 | 50 |
| MS plate | 1250 x 2500 x 6 | 150 |
| MS angle ISA 65 | 65 x 65 x 6 x 6000 | 36 |
| MS angle | 40 x 40 x 6 x 6000 | 24 |
| MS channel | 75 x 40 x 6000 | 44 |
| MS flat | 40 x 6 x 6000 | 16 |
| MS square tube | 40 x 40 x 2 x 6000 | 18 |

Cartridge unit total **Rs 3,00,070**; cyclone **Rs 1,18,220**; duct **Rs 40,500**;
plus Rs 70,000 (unlabelled, B5) -> works cost **Rs 5,28,790**.
Margin options on the sheet: **x1.17, x1.25, x1.35**.

---

## 7. The two AI knowledge-base PDFs (delivered 2026-09-01)

`VITECH_AI_Paint_Booth_Database_V02_Source_Based.pdf` and
`VITECH_AI_Engineering_Knowledge_Base_...pdf` are written FOR this platform, and
they are careful about their own provenance — they mark derived relationships as
"observed", and say plainly where a VITECH value is still owed. Take them at their
word rather than treating everything in them as confirmed data.

**The product range, as source data.** `VT/<width>/DTPB/<OP|CL>` — front-open booths
are 1500 deep, enclosed are 2250, both 2425 high, widths 1500 / 2250 / 3000 / 3750 /
4500. Wet and dry, 2-row and 3-row filter variants, each with CMH, CFM and motor HP.
This is a real standard-product catalogue and belongs in the engine as one.

**The airflow formula it states — and why it contradicts `Standard Booth.xlsx`:**

```
CMH = W(m) x 1.5(m) x 0.5(m/s) x 3600      # 1.5 m EFFECTIVE FILTER OPENING
CFM = CMH x 0.588578                        # = / 1.69901, our own constant
```

`Standard Booth.xlsx` computes the same booth from the **full 2.4 m height**. On a
3.0 m booth: **8,100 CMH here against 12,960 there**. Both are Vitech documents,
delivered together. That is open item DQ-10, and it decides the blower.

The database also flags its own two unconfirmed factors: the 3-row table's airflow is
**1.4x** the 2-row at the same width (implying ~0.70 m/s, though the table prints 0.5),
and the wet table is **0.90x** the simple calculation. It says explicitly that the
basis "must be confirmed" — so neither is implemented.

**Conversions confirmed against ours:** 1 CFM = 1.69901 CMH (we use 1.699; the
costing sheets use a rounded 1.7). **A selection rule worth heeding:** "Final blower
selection must be from the approved manufacturer fan curve at the calculated duty
point. Never select a blower from CFM alone." Our `blower_service` pins the CLP-4
pressure class rather than working a duty point — defensible, and worth revisiting
when static pressure is available per design.

## Open items — MUST be resolved with Vitech before implementing

| id | Question | Blocks |
|---|---|---|
| **DQ-1** | Dry-off oven air density is **101.325** (kPa, a pressure) where the curing oven uses **1.204 kg/m3**. Typo? With their value the air term is 86,670 of their 188,786 Kcal — nearly half the oven. | Heat load service |
| ~~DQ-2~~ | **CLOSED 2026-09-01: 0.5 m/s adopted and made overridable.** | closed |
| **DQ-3** | Scrubber/duct rounding. **Confirmed by reading the cells: D13 / D26 / D40 are hand-typed TEXT** (`~ 950`, `~ 300`, `~ 350`), not formulas, and do not correspond to the computed 1545 / 399 / 399. What is the standard-diameter ladder and the rounding rule? | Scrubber diameter rule |
| ~~DQ-4~~ | **HALF CLOSED by the workbooks: the square-tube "conflict" was two different thicknesses** — booth 40x40x**3** = 21 kg, cyclone 40x40x**2** = 18 kg. Both are now on the table. **Still open:** MS flat 40x6x6000 is **12 kg** (booth) vs **16 kg** (cyclone) for the same nominal section, and 12 is what the steel actually weighs. | Structure weight (flat only) |
| **DQ-5** | Painting rate. Refined: it is not workbook-vs-workbook but **line-vs-line inside one workbook** — the cartridge filter unit is costed at **Rs 35/sq.ft** and the cyclone + duct at **Rs 50/sq.ft**. Different paint spec, or a rate change? | Rate card |
| **DQ-6** | `Combine` B5 = Rs 70,000. **Confirmed a hardcoded number with no label and no formula.** What is it? | Cyclone cost model |
| **DQ-7** | Margin. The booth `Combine` applies **x1.40** (booth) and **x1.26** (duct) then a 10% discount for 27% profit; the cyclone `Combine` is a scratch pad of **x1.35 / x1.25 / x1.17** beside a typed Rs 760,000 and a Rs 150,000 deduction. What selects the multiplier? | Quotation model |
| ~~DQ-8~~ | **CLOSED by reading the cell. It is a BRACKET, and it is in BOTH oven sheets.** `Dry off Oven` D18 and `Curing Oven` D17 apply `* density * thickness` to only the THIRD area term, so two wall areas in **m2** are added straight to a mass in **kg**: 377 kg where the prose formula gives 733, and 1,647 against 3,016. Their totals reproduce exactly once that is accounted for. Is the bracket the intent, or the typo it appears to be? | Both oven heat loads |
| **DQ-9** | **Which dimension is the open face?** The costing sheet computes the face from **L x H** (3.0 x 2.4), and `Standard Booth.xlsx` proves it: **W is a menu of options (1250/1500/2250/3000) that never enters the formula**. The model database calls that same dimension **W** and the depth **D**. Our engine uses `width_m x height`. Under Vitech's costing-sheet naming we are computing the face from the DEPTH. | Every booth's airflow, blower, filters and duct |
| **DQ-10** | **NEW, and larger than DQ-9: which HEIGHT?** `Standard Booth.xlsx` uses the full booth height (2.4 m); the model database computes `CMH = W x **1.5** x 0.5 x 3600` on an **effective filter-opening height of 1.5 m**, and states its own 3-row and wet factors (1.4x, 0.90x) are **unconfirmed**. For one 3.0 m booth that is **12,960 CMH against 8,100 — 60%**, and it selects a different blower. | Every booth's airflow and blower |
