"""Per-equipment engineering formulas — the knowledge in 'knowledge-based'.

These are deterministic engineering rules, not LLM guesses: every value traces
to a formula (here), a unit basis (unit_converter), a governing standard
(standards_service), and a material rule (material_service). The same engine
feeds the spec generator and the quotation BOM.

The DESIGN CONSTANTS below are the ATS design standard and the primary surface
the client tunes/overrides ("the client will provide details") — they are
calibrated against real historical offers (e.g. wet scrubber against
OFF-C2C-WS-172: 735 CFM -> 17 nozzles, 1.0 HP pump) so the formulas reproduce
actual designs rather than guess. Change a constant in ONE place here.
"""
from typing import Optional

from ..schema import ComputedSpec, RuleResult, SpecValue
from . import standards_service as std
from . import design_standards as ds
from . import booth_catalogue as bc
from . import scrubber_service as sc
from .blower_service import select_booth_blower_set
from .calculation_engine import count_ceil, count_round, round_to_step
from .material_service import select_paint_process
from .paint_shop_service import (INLET_LESS_10, enclosure_surface_area,
                                 normalise_draft, sheet_weight_kg)
from .unit_converter import CFM_TO_CMH, air_cmh

# --- Paint booth design constants ------------------------------------------
# Face velocity and filter count are NO LONGER constants: the client's standards
# package gives a design velocity per canonical booth type and a filter count
# derived from media velocity (see `design_standards`). FACE_VELOCITY remains
# only as the fallback when no booth type can be resolved.
FACE_VELOCITY = 0.50          # m/s, fallback only (Dry Filter Cross Draft)
DEFAULT_HEIGHT = 4.0          # assumed booth height when not specified

# --- DQ-9 and DQ-10, settled by the product owner 2026-09-02 ---------------
# The open face is the OPEN FRONT x an EFFECTIVE FILTER OPENING of 1.5 m, and
# the booth's own height does not enter its airflow at all.
#
# DQ-10 (the height): `Standard Booth.xlsx` computes on the full 2.4 m booth
# height, the model database on a 1.5 m effective filter opening. The published
# range settles it — `VT/3.0/DTPB/OP` (1.5 m deep) and `VT/3.0/DTPB/CL` (2.25 m
# deep) both publish 8,100 m3/h, identical despite different depths and
# different from any full-height figure, so the second factor is neither the
# depth nor the height but this fixed opening:
#     3.0 x 1.5 x 0.5 x 3600 = 8,100 m3/h, exactly as published.
#
# DQ-9 (the axis): Vitech's open front is the dimension they write FIRST — their
# worked booth is 3.0L x 2.25W x 2.4H, where 2.25 is the depth. The engine used
# `width_m`, i.e. their DEPTH, which undersized every booth longer than it is
# wide. The catalogue lookup in `_add_standard_model` reads the same way.
EFFECTIVE_OPENING_M = 1.5

# ONLY the types the client's face x velocity table actually describes. Powder
# (0.55 m/s), full down draft (0.35) and pressurized are NOT in it, so applying
# this to them would be our extrapolation of their document rather than their
# engineering — the same scoping decision taken when DQ-2 moved the face
# velocity to 0.5. The published range's own 3-row (x1.4) and wet (x0.90)
# factors are deliberately NOT applied: the database flags them as unconfirmed.
FACE_BASED_BOOTH_TYPES = frozenset(
    {"cross_draft", "side_draft", "semi_down_draft", "water_wash"})

# --- Wet scrubber design constants (ATS, calibrated to OFF-C2C-WS-172) -----
WS_LG_RATIO = 5.0             # recirculation liquid-to-gas ratio, L per m3 of gas
WS_NOZZLE_LPM = 6.0           # spray-nozzle throughput at design pressure, L/min
WS_PUMP_HEAD_M = 25.0         # total pump head: nozzle pressure + static + losses
WS_PUMP_EFF = 0.60            # combined pump + motor efficiency
WS_TANK_RETENTION_MIN = 2.5   # recirculation tank retention time, minutes
WS_HEIGHT_PER_DIA = 5.0       # spray-tower height / diameter (gas-liquid contact)
WS_MIN_HEIGHT_M = 3.0
_G = 9.81                     # m/s^2


def compute_spec(length_m: Optional[float], width_m: Optional[float],
                 height_m: Optional[float] = None,
                 paint_type: Optional[str] = None,
                 booth_type: Optional[str] = None,
                 face_velocity: Optional[float] = None) -> ComputedSpec:
    """Apply engineering rules to a paint-booth requirement. Returns computed
    values, each tagged with provenance, plus the rule trail (formula + standard).
    booth_type is honoured so a liquid booth's filtration/material stays coherent
    with the actual booth design (dry-filter unless a water-wash booth).

    `face_velocity` overrides the booth type's design velocity for THIS design.
    A stated override is engineering the customer or our engineer has specified
    (a duty a local regulator requires, a booth built to a customer standard),
    so it must beat the table rather than be silently ignored — and the rule
    trail says which value was used and where it came from, so a reader can
    never be left wondering which velocity produced the airflow."""
    spec = ComputedSpec(length_m=length_m, width_m=width_m, height_m=height_m)
    if length_m is None or width_m is None:
        return spec  # not enough to compute a booth; caller handles concept Qs

    height = height_m or DEFAULT_HEIGHT
    spec.height_m = height
    paint = (paint_type or "powder").lower()
    proc = select_paint_process(paint_type, booth_type)

    floor_area = length_m * width_m

    # Booth type drives the design face velocity (client standards package), so
    # the velocity the spec states and the velocity that computed the airflow are
    # by construction the same number — the contradiction the review found.
    booth, booth_warning = ds.resolve_booth_type(booth_type, paint_type)
    velocity = float(face_velocity) if face_velocity else booth.velocity
    velocity_source = ("stated for this design" if face_velocity
                       else f"design face velocity for {booth.label}")

    # The open working face (DQ-9 / DQ-10 above). A type the client's table does
    # not describe keeps the previous width x height reading rather than being
    # given a basis their document never stated for it.
    if booth.key in FACE_BASED_BOOTH_TYPES:
        face_area = length_m * EFFECTIVE_OPENING_M
        face_basis = (f"open front {length_m:g} m x effective filter opening "
                      f"{EFFECTIVE_OPENING_M:g} m = {face_area:g} m2")
    else:
        face_area = width_m * height
        face_basis = f"face area {width_m}x{height} = {face_area:g} m2"
    airflow = face_area * velocity * 3600

    # Exhaust blower comes from the VENDOR CATALOGUE, not a capacity heuristic:
    # a real Continental Thermal model, its rated CFM and its motor HP. This is
    # what supersedes the old invented "13000 m3/h per fan" constant, and is the
    # same selection that reproduces the client's own costed booth BOM.
    airflow_cfm = airflow / CFM_TO_CMH
    blower, blower_qty = select_booth_blower_set(airflow_cfm)

    # Make-up air and enclosure sheet weight, per the client's calculation doc.
    # Booths run under negative pressure: inlet is 10% BELOW exhaust so paint
    # fume cannot escape the enclosure.
    inlet = airflow * INLET_LESS_10
    surface_area = enclosure_surface_area(length_m, width_m, height)
    sheet_kg = sheet_weight_kg(surface_area)

    # Component selection from the client's standards package. These fields were
    # previously either a seeded ratio (filters), copied verbatim from a
    # different-sized booth (illumination), or left "To be determined" (duct,
    # electrical, fire) even though the airflow and load needed to size them were
    # already in hand.
    filters_sel = ds.select_filters(airflow)
    light_sel = ds.select_lighting(
        floor_area, "powder" if "powder" in paint else "manual_painting")
    duct_sel = ds.select_duct(
        airflow, "powder" if "powder" in paint else "paint_fume")
    fire_sel = ds.select_fire_protection(paint_type)
    material_sel = ds.recommend_material(paint_type)

    spec.rules = [
        RuleResult(name="Type of paint booth", value=booth.label,
                   formula=f"canonical booth type; face velocity {velocity:g} m/s "
                           f"({velocity_source})",
                   standard=std.CLIENT_BOOTH_STANDARD),
        RuleResult(name="Exhaust airflow", value=f"{round_to_step(airflow, 10)} m3/h",
                   formula=(f"{face_basis} x velocity "
                            f"{velocity:g} m/s ({velocity_source}) x 3600"),
                   standard=std.CLIENT_BOOTH_STANDARD),
        RuleResult(name="Inlet air volume", value=f"{round_to_step(inlet, 10)} m3/h",
                   formula=f"exhaust {round_to_step(airflow, 10)} m3/h 10% less (booth held under suction)",
                   standard=std.CLIENT_PAINT_SHOP_CALC),
        RuleResult(name="Paint arresting filter", value=filters_sel.value,
                   formula=filters_sel.formula, standard=std.CLIENT_FILTER_STANDARD),
        RuleResult(name="Construction material", value=material_sel.value,
                   formula=material_sel.formula, standard=std.CLIENT_MATERIAL_MATRIX),
        RuleResult(name="Exhaust ducts", value=duct_sel.value,
                   formula=duct_sel.formula, standard=std.CLIENT_DUCT_STANDARD),
        RuleResult(name="Illumination", value=light_sel.value,
                   formula=light_sel.formula, standard=std.CLIENT_LIGHTING_STANDARD),
        RuleResult(name="Fire extinguishing system", value=fire_sel.value,
                   formula=fire_sel.formula, standard=std.CLIENT_FIRE_STANDARD),
        RuleResult(name="Enclosure sheet weight", value=f"{round(sheet_kg)} kg",
                   formula=(f"5-side surface area {surface_area:.1f} m2 (floor excluded) "
                            f"x 2 mm MS sheet"),
                   standard=std.MS_SHEET_BASIS),
    ]

    spec.values = [
        SpecValue(label="Dimensions", value=f"{length_m:g} x {width_m:g} x {height:g} m", origin="rule"),
        SpecValue(label="Type of paint booth", value=booth.label, origin="rule"),
        SpecValue(label="Exhaust airflow", value=f"{round_to_step(airflow, 10)} m3/h", origin="rule"),
        SpecValue(label="Inlet air volume", value=f"{round_to_step(inlet, 10)} m3/h", origin="rule"),
        SpecValue(label="Paint arresting filter", value=filters_sel.value, origin="rule"),
        SpecValue(label="Construction material", value=material_sel.value, origin="advisory"),
        SpecValue(label="Exhaust ducts", value=duct_sel.value, origin="rule"),
        SpecValue(label="Illumination", value=light_sel.value, origin="rule"),
        SpecValue(label="Fire extinguishing system", value=fire_sel.value, origin="standard"),
        SpecValue(label="Paint process", value=paint, origin="rule"),
        SpecValue(label="Enclosure sheet weight", value=f"{round(sheet_kg)} kg", origin="rule"),
    ]

    if blower is not None:
        # Panel scope follows from the connected load, which is only known once
        # the blower is selected.
        elec = ds.select_electrical(blower.motor_hp * blower_qty,
                                    light_sel.detail.get("watts_total", 0) / 1000.0)
        spec.rules.append(RuleResult(name="Electrical fittings & motors", value=elec.value,
                                     formula=elec.formula, standard=std.CLIENT_ELECTRICAL_STANDARD))
        spec.values.append(SpecValue(label="Electrical fittings & motors",
                                     value=f"{elec.value}; {', '.join(ds.PANEL_SCOPE[:4])}",
                                     origin="rule"))
        spec.values.append(SpecValue(label="Control panel",
                                     value=f"{elec.detail['starter']} MCC, {elec.detail['connected_kw']} kW",
                                     origin="rule"))
        spec.rules.append(RuleResult(name="Control panel",
                                     value=f"{elec.detail['starter']} MCC",
                                     formula=elec.formula, standard=std.CLIENT_ELECTRICAL_STANDARD))

        # Each catalogue-derived row carries its OWN formula + standard. Without
        # that the planner's rule-matching falls back to origin "given", which
        # would wrongly attribute vendor catalogue data to the customer.
        pick = (f"duty {round(airflow_cfm)} CFM -> smallest {blower.model} "
                f"covering it in the booth series")
        spec.rules += [
            RuleResult(name="Exhaust blower", value=blower.model, formula=pick,
                       standard=std.BLOWER_CHART_SELECTION),
            RuleResult(name="Blower airflow (CFM)", value=str(blower.cfm),
                       formula=f"{blower.model} rated air volume", standard=std.BLOWER_CHART_SELECTION),
            RuleResult(name="Exhaust blower (nos)", value=str(blower_qty),
                       formula=f"{blower_qty} x {blower.model} to cover {round(airflow_cfm)} CFM",
                       standard=std.BLOWER_CHART_SELECTION),
            RuleResult(name="Exhaust blower motor (HP)", value=f"{blower.motor_hp:g}",
                       formula=f"{blower.model} rated motor ({blower.poles}-pole, {blower.motor_rpm} rpm)",
                       standard=std.BLOWER_CHART_SELECTION),
            RuleResult(name="Blower drive", value=blower.drive,
                       formula=f"{blower.model} is a direct-drive machine", standard=std.BLOWER_CHART_SELECTION),
        ]
        spec.values += [
            SpecValue(label="Exhaust blower", value=blower.model, origin="rule"),
            SpecValue(label="Blower airflow (CFM)", value=str(blower.cfm), origin="rule"),
            SpecValue(label="Exhaust blower (nos)", value=str(blower_qty), origin="rule"),
            SpecValue(label="Exhaust blower motor (HP)", value=f"{blower.motor_hp:g}", origin="rule"),
            SpecValue(label="Blower drive", value=blower.drive, origin="rule"),
        ]

    _add_standard_model(spec, booth, length_m, width_m, height, airflow)
    return spec


def _add_standard_model(spec: ComputedSpec, booth, length_m: float,
                        width_m: float, height_m: float, airflow: float) -> None:
    """Name the published model when the customer has asked for one Vitech builds.

    Until now the platform engineered every booth from first principles, even
    where Vitech already publish the machine, its airflow and its motor. A
    standard model is the better answer: it is what they actually sell, and it
    needs no assumptions.

    It is REPORTED, never substituted. The catalogue's published airflow rests
    on a 1.5 m effective filter opening while `Standard Booth.xlsx` computes the
    same booth on the full 2.4 m height — 8,100 m3/h against 12,960 on one 3.0 m
    booth, which is a different blower. That contradiction is open question
    DQ-10 and only Vitech can settle it, so where the two disagree BOTH are put
    in front of the engineer with the gap named. Silently adopting either basis
    would be this platform choosing between two of the client's own documents.
    """
    family = bc.family_for(booth.filtration)
    if family is None:                 # powder booths are not in this range
        return
    # The catalogue's WIDTH is the open front, which under Vitech's own naming
    # (DQ-9) is the dimension written first — so `length_m` here, and `width_m`
    # is their depth. Reading these the other way round matched a 3.0 m machine
    # to a booth whose open front is 1.5 m.
    model = bc.match_requirement(width_mm=length_m * 1000, depth_mm=width_m * 1000,
                                 height_mm=height_m * 1000, family=family)
    if model is None:                  # not in the range: a special, engineered above
        return

    # ONE row, and it is an IDENTIFICATION, not a component. The published
    # airflow and motor ride in the basis trail rather than becoming rows of
    # their own: emitted as values they were picked up as bill-of-materials
    # lines, and a BOM that lists both a 10 HP engineered motor and a 5 HP
    # published one is a procurement document contradicting itself.
    published = f"{model.airflow_cmh} m3/h ({model.airflow_cfm} cfm)"
    motor = f"{model.motor_hp:g} HP" if model.motor_hp else "not rated in the catalogue"
    computed = round_to_step(airflow, 10)
    # 5% absorbs rounding between their published figure and ours; a real
    # disagreement between the two airflow bases is far larger than that.
    agrees = abs(model.airflow_cmh - computed) <= 0.05 * model.airflow_cmh
    # With DQ-10 settled, a face-based booth computes its published duty exactly,
    # so the two can now only diverge where the published figure carries one of
    # the range's OWN factors that the database marks unconfirmed — 3-row x1.4
    # and wet x0.90 — which the engine deliberately does not apply.
    caution = ("" if agrees else
               f" — against {computed} m3/h engineered here on the 1.5 m opening "
               f"basis, so CONFIRM WHICH FIGURE GOVERNS before ordering the blower: "
               f"the published duty carries the range's own filter-row / wet-booth "
               f"factor, which the database itself marks unconfirmed")

    spec.values.append(SpecValue(label="Standard model", value=model.model,
                                 origin="standard"))
    spec.rules.append(RuleResult(
        name="Standard model", value=model.model,
        formula=(f"stated {length_m:g} x {width_m:g} x {height_m:g} m matches the published "
                 f"{model.config} {model.family.replace('_', ' ')} machine "
                 f"({model.width_mm} W x {model.depth_mm} D x {model.height_mm} H mm), "
                 f"published duty {published}, motor {motor}{caution}"),
        standard=std.CLIENT_BOOTH_CATALOGUE))


def compute_wet_scrubber(params: dict) -> dict[str, dict]:
    """Return {technical_field: {value, formula, standard}} for the values that
    engineering formulas can determine. The caller keeps client-supplied values
    authoritative and snaps results to standard sizes."""
    out: dict[str, dict] = {}
    q_cmh = air_cmh(params)
    if not q_cmh:
        return out

    # Recirculation liquid flow that everything else derives from.
    l_lpm = WS_LG_RATIO * q_cmh / 60.0

    nozzles = count_round(l_lpm / WS_NOZZLE_LPM)
    out["spray_nozzle_nos"] = {
        "value": nozzles,
        "formula": (f"recirculation L/G {WS_LG_RATIO} L/m3 x {round(q_cmh)} m3/h "
                    f"= {round(l_lpm)} L/min, / {WS_NOZZLE_LPM:g} L/min per nozzle"),
        "standard": std.ATS_SPRAY_COVERAGE,
    }

    q_ls = l_lpm / 60000.0                         # L/min -> m3/s
    hp = (1000 * _G * q_ls * WS_PUMP_HEAD_M / WS_PUMP_EFF) / 745.7
    out["pump_capacity_hp"] = {
        "value": hp,
        "formula": (f"P = rho.g.Q.H / eff with Q {round(l_lpm)} L/min, "
                    f"H {WS_PUMP_HEAD_M:g} m, eff {WS_PUMP_EFF:g}"),
        "standard": std.HYDRAULIC_PUMP_POWER,
    }

    out["tank_capacity_litre"] = {
        "value": l_lpm * WS_TANK_RETENTION_MIN,
        "formula": f"{round(l_lpm)} L/min x {WS_TANK_RETENTION_MIN:g} min retention",
        "standard": std.ATS_RECIRC_TANK,
    }

    d_mm = params.get("tower_diameter_mm")
    if not isinstance(d_mm, (int, float)):
        # DERIVED from the duty on the client's own basis (1.0 m/s across the
        # tower). Until this ran, a scrubber that stated ONLY an airflow had no
        # diameter, so it had no footprint either: `geometry_service` fell
        # through to the baffle path and the GA came back with no envelope, no
        # scale and ZERO VIEWS — a blank sheet for a machine we could size.
        #
        # A CLIENT-STATED DIAMETER STILL WINS: this only runs when none was
        # given, and it is emitted as its own row so the reader can see it was
        # calculated rather than quoted. The standard-size rounding is NOT
        # applied — Vitech's diameter ladder is still outstanding (DQ-3) — so
        # the value is the true bore, not a snapped one.
        bore = sc.tower_diameter(q_cmh)
        if bore is not None:
            d_mm = bore.diameter_mm
            out["tower_diameter_mm"] = {
                "value": round(d_mm),
                "formula": bore.trail[0][2] if bore.trail else "tower bore at 1.0 m/s",
                "standard": std.CLIENT_SCRUBBER_DIAMETER_CALC,
            }
    if isinstance(d_mm, (int, float)):
        h = max(WS_MIN_HEIGHT_M, WS_HEIGHT_PER_DIA * d_mm / 1000.0)
        out["tower_height_m"] = {
            "value": h,
            "formula": f"{WS_HEIGHT_PER_DIA:g} x tower diameter {d_mm:g} mm (gas-liquid contact height)",
            "standard": std.ATS_SPRAY_TOWER_HEIGHT,
        }
    return out
