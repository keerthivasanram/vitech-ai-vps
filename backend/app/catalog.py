"""Category profiles — the per-equipment knowledge that drives case-based
adaptation. Adding a new equipment type = adding one entry here; the reasoning
engine, prompt, and UI stay unchanged.

Each profile declares:
  scale_driver  — the given-data key whose ratio scales the design
  scalable      — technical_details fields that scale with the driver  -> origin "adapted"
  from_given    — technical fields set directly from the requirement   -> origin "given"
  rules         — optional callable(params) -> ComputedSpec (physics)  -> origin "rule"
  rule_covers   — technical fields superseded by the rule engine
  field_labels  — pretty labels for technical_details keys
"""
from typing import Any, Callable, Optional

from .rules import compute_spec, compute_wet_scrubber
from .schema import ComputedSpec, RuleResult, SpecValue


def _booth_rules(params: dict[str, Any]) -> ComputedSpec:
    # `face_velocity_ms` is the per-design override (DQ-2): absent, the booth
    # type's own design velocity governs. It is deliberately NOT in
    # `required_inputs` / `optional_inputs` yet — adding it there changes the
    # studio form and the drawing catalog response, which is a UI decision, not
    # an engineering one.
    return compute_spec(params.get("length_m"), params.get("width_m"),
                        params.get("height_m"), params.get("paint_type"),
                        params.get("booth_type"), params.get("face_velocity_ms"))


def _paint_shop_rules(unit: str) -> Callable[[dict[str, Any]], ComputedSpec]:
    """Rule engine for one paint-shop line unit, from the client's calculation
    document (see `engineering/paint_shop_service`).

    The service returns a trail of (name, value, formula, standard) rows — every
    one of them a computed engineering value — which maps straight onto the
    ComputedSpec the resolver expects. Only rows the client's formulas actually
    produced appear; a value needing an input nobody supplied (e.g. the oven's
    ACH) simply is not in the trail, and the spec template turns it into a TBD.
    """
    def run(params: dict[str, Any]) -> ComputedSpec:
        from .engineering.paint_shop_service import (compute_paint_shop_unit,
                                                     normalise_draft)
        L = params.get("length_m")
        W = params.get("width_m")
        H = params.get("height_m")
        calc = compute_paint_shop_unit(
            unit, L, W, H,
            draft=normalise_draft(params.get("draft_type") or params.get("booth_type")),
            ach=params.get("ach"),
        )
        spec = ComputedSpec(length_m=L, width_m=W, height_m=H)
        if L is not None and W is not None and H is not None:
            spec.values.append(SpecValue(
                label="Dimensions", value=f"{L:g} x {W:g} x {H:g} m", origin="rule"))
        for name, value, formula, standard in calc.trail:
            spec.rules.append(RuleResult(name=name, value=value,
                                         formula=formula, standard=standard))
            spec.values.append(SpecValue(label=name, value=value, origin="rule"))
        return spec
    return run


# The output fields a paint-shop enclosure spec must cover. Shared by the four
# line units — they differ in their inlet-air rule, not in what they report.
_PAINT_SHOP_TEMPLATE = [
    {"label": "Dimensions", "kind": "geometry"},
    {"label": "Exhaust air volume", "kind": "computed"},
    {"label": "Inlet air volume", "kind": "computed"},
    {"label": "Enclosure surface area", "kind": "computed"},
    {"label": "Enclosure sheet weight", "kind": "computed"},
    {"label": "Construction", "kind": "standard"},
    {"label": "Illumination", "kind": "standard"},
    {"label": "Control panel", "kind": "standard"},
    {"label": "Finish", "kind": "standard"},
]

_PAINT_SHOP_LABELS = {
    "exhaust_air_m3h": "Exhaust air volume",
    "inlet_air_m3h": "Inlet air volume",
    "surface_area_m2": "Enclosure surface area",
    "sheet_weight_kg": "Enclosure sheet weight",
    "construction": "Construction",
    "illumination": "Illumination",
    "control_panel": "Control panel",
    "finish": "Finish",
}


def _paint_shop_profile(key: str, label: str, extra_template=()) -> dict[str, Any]:
    """One paint-shop line unit's catalog profile. They share their inputs and
    their output shape; `_paint_shop_rules` carries the per-unit differences."""
    return {
        "label": label,
        "scale_driver": None,
        "driver_label": "Dimensions",
        "diff_unit": "floor area",
        "dimension_keys": ["length_m", "width_m", "height_m"],
        "process_keys": [],
        "required_inputs": [("length_m", "Length"), ("width_m", "Width"),
                            ("height_m", "Height")],
        "optional_inputs": [("draft_type", "Draft type"), ("qty", "Quantity")]
                           + ([("ach", "Air changes per hour")]
                              if key == "paint_drying_oven" else []),
        "expected_inputs": [("length_m", "Length"), ("width_m", "Width"),
                            ("height_m", "Height")],
        "scalable": [],
        "from_given": {},
        "rules": _paint_shop_rules(key),
        "rule_covers": ["exhaust_air_m3h", "inlet_air_m3h", "surface_area_m2",
                        "sheet_weight_kg"],
        "rule_value_map": {},
        "field_labels": dict(_PAINT_SHOP_LABELS),
        "spec_template": _PAINT_SHOP_TEMPLATE + list(extra_template),
    }


# Engineering-oriented labels for value provenance (shown to users).
ORIGIN_LABELS = {
    "given": "From Requirement",
    "rule": "Calculated (Engineering Rule)",
    "interpolated": "Inferred from multiple projects",
    "scaled": "Scaled from nearest design",
    "consistent": "Historical consensus",
    "reused": "Reused from nearest design",
    "tbd": "To be determined (needs engineering input)",
    # Provenance tags from the client's standards package.
    "standard": "Engineering Standard",
    "advisory": "Advisory Recommendation",
    "customer_decision": "Customer Decision Required",
    # legacy
    "kept": "Reused from nearest design",
    "adapted": "Scaled from nearest design",
    "existing": "Reused from nearest design",
    "recommended": "Recommended",
}

# Map internal origin -> the decision-type shown in the reasoning summary.
DECISION_TYPES = {
    "rule": "Engineering Rule",
    "interpolated": "Inferred",
    "scaled": "Recommended",
    "consistent": "Historical Consensus",
    "reused": "Reused",
    "kept": "Reused",
    "adapted": "Recommended",
    "given": "From Requirement",
    "standard": "Engineering Standard",
    "advisory": "Advisory Recommendation",
}

# Canonical order for the Decision Origin table (rows shown even when count is 0,
# so users see the system mature as rules are added).
DECISION_ORIGIN_ORDER = ["Engineering Rule", "Inferred", "Historical Consensus", "Reused"]


def origin_label(origin: str) -> str:
    return ORIGIN_LABELS.get(origin, origin.capitalize())


CATEGORY_PROFILES: dict[str, dict[str, Any]] = {
    "wet_scrubber": {
        "label": "Wet Scrubber",
        "scale_driver": "air_volume_cfm",
        "driver_label": "Airflow",
        "diff_unit": "airflow",
        "dimension_keys": ["tower_diameter_mm"],
        "process_keys": ["operating_temp", "blower_mounting"],
        # required = needed to size; optional = refines the design (assumed if absent)
        "required_inputs": [
            ("air_volume_cfm", "Air volume"),
            ("tower_diameter_mm", "Tower / blower diameter"),
            ("qty", "Quantity"),
        ],
        "optional_inputs": [
            ("operating_temp", "Operating temperature"),
            ("operating_pressure", "Operating pressure"),
        ],
        "expected_inputs": [
            ("air_volume_cfm", "Air volume"),
            ("tower_diameter_mm", "Tower / blower diameter"),
            ("operating_temp", "Operating temperature"),
            ("operating_pressure", "Operating pressure"),
            ("qty", "Quantity"),
        ],
        "scalable": ["spray_nozzle_nos", "tank_capacity_litre",
                     "pump_capacity_hp", "tower_height_m"],
        "standard_sizes": {
            "pump_capacity_hp": [0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 7.5, 10.0],
            "tank_capacity_litre": [100, 150, 200, 250, 300, 400, 500, 750, 1000],
        },
        "round_to": {"tower_height_m": 0.5},
        "from_given": {"tower_diameter_mm": "tower_diameter_mm"},
        "rules": None,
        # field-level engineering rules (formulas) applied within case-based mode:
        # these fields are computed from physics, the rest are reused from the offer.
        "field_rules": compute_wet_scrubber,
        "rule_covers": ["spray_nozzle_nos", "pump_capacity_hp",
                        "tank_capacity_litre", "tower_height_m"],
        "field_labels": {
            "tower_diameter_mm": "Tower diameter (mm)",
            "tower_height_m": "Tower height (m)",
            "chamber": "Scrubber chamber",
            "tank_material": "Scrubber tank",
            "no_of_tower": "No. of towers",
            "spray_nozzle_nos": "Spray nozzles (nos)",
            "spray_nozzle_material": "Spray nozzle material",
            "pump_capacity_hp": "Pump capacity (HP)",
            "pump_make": "Pump make",
            "demister": "Eliminator / demister",
            "tank_capacity_litre": "Tank capacity (litre)",
            "finish": "Finish",
        },
    },
    "paint_booth": {
        "label": "Paint Booth",
        "scale_driver": None,
        "driver_label": "Dimensions",
        "diff_unit": "floor area",
        "dimension_keys": ["length_m", "width_m", "height_m"],
        "process_keys": ["paint_type"],
        "required_inputs": [
            ("length_m", "Length"),
            ("width_m", "Width"),
            ("paint_type", "Paint process"),
        ],
        "optional_inputs": [
            ("height_m", "Height"),
            ("qty", "Quantity"),
        ],
        "expected_inputs": [
            ("length_m", "Length"),
            ("width_m", "Width"),
            ("height_m", "Height"),
            ("paint_type", "Paint type"),
        ],
        "scalable": [],
        "from_given": {},
        "rules": _booth_rules,
        # The exhaust blower now comes from the vendor catalogue, so the rule
        # engine supersedes the historical blower fields as well as the airflow
        # ones — a reused blower spec must not contradict the selected model.
        "rule_covers": ["airflow_m3h", "filters", "filter_type", "material",
                        "blower_cfm", "blower_qty", "blower_motor_hp", "blower_drive",
                        # now selected from the client's standards package, so the
                        # historical value must NOT also be emitted (it produced a
                        # duplicate row, once computed and once copied)
                        "booth_type", "illumination", "paper_filter", "exhaust_duct",
                        "control_panel", "sprinkler_fire_protection"],
        "rule_value_map": {"Exhaust airflow": "airflow_m3h",
                           "Filters": "filters", "Construction material": "material",
                           "Blower airflow (CFM)": "blower_cfm",
                           "Exhaust blower (nos)": "blower_qty",
                           "Exhaust blower motor (HP)": "blower_motor_hp",
                           "Blower drive": "blower_drive"},
        "field_labels": {
            "airflow_m3h": "Exhaust airflow (m3/h)",
            "inlet_air_m3h": "Inlet air volume",
            "enclosure_sheet_kg": "Enclosure sheet weight",
            "filters": "Filters",
            "filter_type": "Filter type",
            "material": "Construction material",
            "access": "Access",
            "standard": "Standard",
            "job_size": "Job / workpiece envelope",
            # labels for the fields reused from historical booths, worded as on
            # the client's "DATA SHEET FOR PAINTING PLANT"
            "booth_type": "Type of paint booth",
            "construction": "Construction",
            "illumination": "Illumination",
            "blower_motor_hp": "Exhaust blower motor (HP)",
            "blower_type": "Blower type",
            "blower_drive": "Blower drive",
            "blower_qty": "Exhaust blower (nos)",
            "blower_cfm": "Blower airflow (CFM)",
            "blower_moc": "Blower MOC",
            "paper_filter": "Paint arresting filter",
            "air_inlet_filter": "Air intake filter",
            "dry_scrubber": "Dry scrubber",
            "activated_carbon_chamber": "Activated carbon chamber",
            "exhaust_duct": "Exhaust ducts",
            "control_panel": "Control panel",
            "conveyor": "Material handling for painting",
            "sprinkler_fire_protection": "Fire extinguishing system",
            "finish": "Finish",
        },
        # SPEC TEMPLATE — output fields a complete paint-booth spec must cover,
        # ordered as section 3.0 PAINTING BOOTH of the client's data sheet.
        # Uncovered fields surface as explicit TBD rows (never a guess).
        # NB labels must match what the engine actually emits (the rule labels
        # and `field_labels` above), or a resolved row and its template entry
        # both appear - once with the value, once as a phantom TBD.
        "spec_template": [
            {"label": "Type of paint booth", "kind": "standard"},
            {"label": "Dimensions", "kind": "geometry"},
            {"label": "Construction", "kind": "standard"},
            {"label": "Construction material", "kind": "standard"},
            {"label": "Exhaust airflow", "kind": "computed"},
            {"label": "Inlet air volume", "kind": "computed"},
            {"label": "Exhaust blower", "kind": "computed"},
            {"label": "Blower airflow (CFM)", "kind": "computed"},
            {"label": "Exhaust blower (nos)", "kind": "computed"},
            {"label": "Exhaust blower motor (HP)", "kind": "computed"},
            {"label": "Blower drive", "kind": "computed"},
            {"label": "Enclosure sheet weight", "kind": "computed"},
            {"label": "Blower MOC", "kind": "standard"},
            {"label": "Paint arresting filter", "kind": "standard"},
            {"label": "Air intake filter", "kind": "standard"},
            {"label": "Dry scrubber", "kind": "standard"},
            {"label": "Exhaust ducts", "kind": "standard"},
            {"label": "Illumination", "kind": "standard"},
            {"label": "Electrical fittings & motors", "kind": "standard"},
            {"label": "Fire extinguishing system", "kind": "standard"},
            {"label": "Material handling for painting", "kind": "customer_decision"},
            {"label": "Control panel", "kind": "standard"},
            {"label": "Finish", "kind": "standard"},
        ],
    },
    # Consulting-ready categories (engineering rules come in a later sprint).
    "hot_air_oven": {
        "label": "Hot Air Oven",
        "scale_driver": None,
        "driver_label": "Chamber size",
        "diff_unit": "chamber volume",
        "dimension_keys": ["length_m", "width_m", "height_m"],
        "process_keys": ["operating_temp"],
        "required_inputs": [
            ("length_m", "Chamber length"),
            ("width_m", "Chamber width"),
            ("height_m", "Chamber height"),
            ("operating_temp", "Operating temperature"),
        ],
        "optional_inputs": [("qty", "Quantity")],
        "expected_inputs": [
            ("length_m", "Chamber length"), ("width_m", "Chamber width"),
            ("height_m", "Chamber height"), ("operating_temp", "Operating temperature"),
            ("qty", "Quantity"),
        ],
        "scalable": [], "from_given": {}, "rules": None, "field_rules": None,
        "rule_covers": [],
        # CASE-BASED: ovens have no closed-form sizing rules, but Vitech has real
        # oven offers to reuse. Rather than consulting from scratch (which left the
        # LLM to invent dimensions), build the spec by REUSING the nearest matching
        # historical oven design — deterministic, with honest "reused from offer X"
        # provenance. The nearest offer is chosen by semantic + given-attribute rank.
        "case_based": True,
        "field_labels": {"chamber": "Chamber", "insulation": "Insulation",
                         "heating": "Heating source", "operating_temp": "Operating temperature",
                         "oven_type": "Oven type", "baking_time_min": "Baking time (min)",
                         "circulation_blower_hp": "Circulation blower (HP)",
                         "circulation_blower_qty": "Circulation blower (nos)",
                         "circulation_blower_drive": "Circulation blower drive",
                         "circulation_fan_hp": "Circulation fan (HP)",
                         "no_of_zones": "No. of heating zones", "conveyor": "Conveyor",
                         "door": "Door", "motorized_trolley": "Motorized trolley",
                         "heating_mode": "Heating mode", "finish": "Finish"},
        # SPEC TEMPLATE — the sections a complete oven spec must cover (the ones
        # the client asks for). Each field resolves to given/calc/reuse or an
        # explicit TBD. Labels for reused fields match field_labels so history
        # fills them; the rest (dimensions, control panel, utilities, safety)
        # stay TBD until an engineering calc / the client's data supplies them.
        "spec_template": [
            {"label": "Oven type", "kind": "standard"},
            {"label": "Overall dimensions (mm)", "kind": "geometry"},
            {"label": "Chamber", "kind": "standard"},
            {"label": "Airflow (m3/h)", "kind": "computed"},
            {"label": "Circulation blower (HP)", "kind": "computed"},
            {"label": "Baking time (min)", "kind": "computed"},
            {"label": "Insulation", "kind": "computed"},
            {"label": "Heating source", "kind": "computed"},
            {"label": "Heating capacity (kcal/hr)", "kind": "computed"},
            {"label": "Conveyor", "kind": "standard"},
            {"label": "Control panel", "kind": "standard"},
            {"label": "Utilities", "kind": "standard"},
            {"label": "Safety features", "kind": "standard"},
            {"label": "Finish", "kind": "standard"},
        ],
    },
    "dust_collector": {
        "label": "Dust Collector",
        "scale_driver": "air_volume_cmh",
        "driver_label": "Airflow",
        "diff_unit": "airflow",
        "dimension_keys": [],
        "process_keys": ["dust_type"],
        "required_inputs": [
            ("air_volume_cmh", "Airflow"),
            ("dust_type", "Dust type"),
        ],
        "optional_inputs": [("operating_temp", "Operating temperature"), ("qty", "Quantity")],
        "expected_inputs": [
            ("air_volume_cmh", "Airflow"), ("dust_type", "Dust type"),
            ("operating_temp", "Operating temperature"), ("qty", "Quantity"),
        ],
        "scalable": [], "from_given": {}, "rules": None, "field_rules": None,
        "rule_covers": [],
        # CASE-BASED, for the same reason ovens are (see hot_air_oven above).
        # A dust collector has no closed-form sizing rule here yet (the client's
        # pollution-control calculation document is still outstanding), but Vitech
        # has 5 real collector offers. Without this the router consulted from
        # scratch and returned a spec with ZERO technical details — which in turn
        # gave the GA drawing an empty row list, so the sheet drew a bare casing
        # with no filter elements, no airlock and a legend reading "ID fan HP"
        # with no value. Reuse is deterministic and attributed ("reused from
        # offer X"), and `validate.demote_unscalable` still refuses a
        # size-dependent value copied across a >20% size gap.
        "case_based": True,
        "field_labels": {"filter_area": "Filter area", "fan": "Fan",
                         "cleaning": "Cleaning system",
                         # reused-field labels, worded as on the client's
                         # "DATA SHEET FOR DUST COLLECTION EQUIPMENT"
                         "air_volume_cmh": "Air volume (m3/h)",
                         "collector_size_m": "Collector size (m)",
                         "collector_size_mm": "Collector size (mm)",
                         "casing_hopper_moc": "Casing & hopper MOC",
                         "casing_moc": "Casing MOC",
                         "filter_bags": "Filter bags",
                         "solenoid_valve": "Solenoid valve",
                         "blower_type": "Blower type",
                         "blower_motor_hp": "Blower motor (HP)",
                         "blower_drive": "Blower drive",
                         "blower_motor": "Blower motor",
                         "rotary_airlock": "Rotary airlock",
                         "suction_duct": "Suction ducts",
                         "exhaust_duct": "Exhaust duct",
                         "explosion_vent": "Explosion vent",
                         "control_panel": "Control panel",
                         "finish": "Finish"},
        # SPEC TEMPLATE — output fields a complete dust-collector spec must
        # cover. Input concerns from the client's data sheet (dust nature,
        # collector location, suction points) drive the fields below.
        "spec_template": [
            {"label": "Collector type", "kind": "standard"},
            {"label": "Air volume (m3/h)", "kind": "computed"},
            {"label": "Collector size (m)", "kind": "geometry"},
            {"label": "Casing & hopper MOC", "kind": "standard"},
            {"label": "Filter bags", "kind": "standard"},
            {"label": "Filter area", "kind": "computed"},
            {"label": "Cleaning system", "kind": "standard"},
            {"label": "Solenoid valve", "kind": "standard"},
            {"label": "Blower type", "kind": "standard"},
            {"label": "Blower motor (HP)", "kind": "computed"},
            {"label": "Blower drive", "kind": "standard"},
            {"label": "Rotary airlock", "kind": "standard"},
            {"label": "Suction ducts", "kind": "standard"},
            {"label": "Exhaust duct", "kind": "standard"},
            {"label": "Dust collector location", "kind": "text"},
            {"label": "Control panel", "kind": "standard"},
            {"label": "Finish", "kind": "standard"},
        ],
    },
    # --- Consulting-ready categories (no engineering rules yet, so they REASON
    #     from knowledge and defer sizing to engineering; historical offers are
    #     reference evidence, never a template to copy). ---
    "powder_coating_plant": {
        "label": "Powder Coating Plant",
        "scale_driver": None, "driver_label": "Component envelope",
        "diff_unit": "component size",
        "dimension_keys": ["length_m", "width_m", "height_m"],
        "process_keys": ["booth_type", "painting_method"],
        "required_inputs": [
            ("length_m", "Largest component length"),
            ("width_m", "Largest component width"),
            ("height_m", "Largest component height"),
            ("booth_type", "Booth type (e.g. dry side-draft / down-draft)"),
            ("painting_method", "Application method (manual / automatic)"),
            ("throughput", "Production rate / throughput"),
        ],
        "optional_inputs": [("paint_type", "Coating type"), ("qty", "Quantity")],
        "expected_inputs": [
            ("length_m", "Component length"), ("width_m", "Component width"),
            ("height_m", "Component height"), ("booth_type", "Booth type"),
            ("painting_method", "Application method"), ("throughput", "Throughput"),
        ],
        "scalable": [], "from_given": {}, "rules": None, "field_rules": None,
        "rule_covers": [],
        # CASE-BASED (see hot_air_oven / dust_collector above). HONEST LIMIT:
        # there is exactly ONE powder-coating-plant offer on file, so reuse here
        # is a copy of that single plant, not a choice between designs. That is
        # still strictly better than the previous behaviour (an empty spec, and a
        # GA sheet showing three empty boxes), because every reused value is
        # attributed to its source offer and a size-dependent one is demoted to
        # TBD beyond the tolerance. It improves the moment more plants are filed.
        "case_based": True,
        "field_labels": {"booth": "Spray booth", "pulse_jet": "Powder recovery / pulse-jet",
                         "oven": "Curing oven", "conveyor": "Conveyor",
                         # keys as they actually appear on the historical plant
                         # offers, labelled per "DATA SHEET FOR POWDER COATING PLANT"
                         "powder_spray_booth": "Powder coating booth",
                         "pulse_jet_system": "Powder recovery",
                         "hot_air_oven": "Curing oven",
                         "overhead_conveyor": "Material handling"},
        # SPEC TEMPLATE — the plant sections of the client's powder-coating data
        # sheet (2.0 process / 3.0 pretreatment / 4.0 booth / 5.0 curing oven).
        "spec_template": [
            {"label": "Pretreatment", "kind": "standard"},
            {"label": "Component envelope (mm)", "kind": "geometry"},
            {"label": "Powder coating booth", "kind": "standard"},
            {"label": "Type of coating", "kind": "text"},
            {"label": "No. of operators", "kind": "text"},
            {"label": "Powder recovery", "kind": "standard"},
            {"label": "Curing oven", "kind": "standard"},
            {"label": "Curing temperature (deg C)", "kind": "computed"},
            {"label": "Oven heating media", "kind": "standard"},
            {"label": "Material handling", "kind": "standard"},
            {"label": "Control panel", "kind": "standard"},
            {"label": "Utilities", "kind": "standard"},
            {"label": "Finish", "kind": "standard"},
        ],
    },
    "fume_extraction": {
        "label": "Fume Extraction System",
        "scale_driver": None, "driver_label": "Airflow", "diff_unit": "airflow",
        "dimension_keys": [], "process_keys": ["source_process"],
        "required_inputs": [
            ("air_volume_cmh", "Extraction airflow"),
            ("source_process", "Fume source / process"),
            ("capture_points", "Number of capture points / hoods"),
        ],
        "optional_inputs": [("operating_temp", "Gas temperature"), ("qty", "Quantity")],
        "expected_inputs": [
            ("air_volume_cmh", "Airflow"), ("source_process", "Source process"),
            ("capture_points", "Capture points"),
        ],
        "scalable": [], "from_given": {}, "rules": None, "field_rules": None,
        "rule_covers": [], "field_labels": {},
    },
    "pretreatment_plant": {
        "label": "Pretreatment Plant",
        "scale_driver": None, "driver_label": "Component envelope",
        "diff_unit": "component size",
        "dimension_keys": ["length_m", "width_m", "height_m"],
        "process_keys": ["process_stages"],
        "required_inputs": [
            ("length_m", "Largest component length"),
            ("width_m", "Largest component width"),
            ("height_m", "Largest component height"),
            ("process_stages", "Process stages (e.g. degrease / rinse / phosphate)"),
            ("throughput", "Production rate / throughput"),
        ],
        "optional_inputs": [("qty", "Quantity")],
        "expected_inputs": [
            ("length_m", "Component length"), ("width_m", "Component width"),
            ("height_m", "Component height"), ("process_stages", "Process stages"),
            ("throughput", "Throughput"),
        ],
        "scalable": [], "from_given": {}, "rules": None, "field_rules": None,
        "rule_covers": [], "field_labels": {},
    },
    "blast_booth": {
        "label": "Blast Booth / Room",
        "scale_driver": None, "driver_label": "Component envelope",
        "diff_unit": "component size",
        "dimension_keys": ["length_m", "width_m", "height_m"],
        "process_keys": ["blast_media"],
        "required_inputs": [
            ("length_m", "Largest component length"),
            ("width_m", "Largest component width"),
            ("height_m", "Largest component height"),
            ("blast_media", "Blast media (e.g. steel grit / garnet)"),
            ("recovery_type", "Abrasive recovery (manual / mechanical / pneumatic)"),
        ],
        "optional_inputs": [("qty", "Quantity")],
        "expected_inputs": [
            ("length_m", "Component length"), ("width_m", "Component width"),
            ("height_m", "Component height"), ("blast_media", "Blast media"),
            ("recovery_type", "Recovery type"),
        ],
        "scalable": [], "from_given": {}, "rules": None, "field_rules": None,
        "rule_covers": [], "field_labels": {},
    },
    "conveyor": {
        "label": "Conveyor System",
        "scale_driver": None, "driver_label": "Track length", "diff_unit": "length",
        "dimension_keys": [], "process_keys": ["conveyor_type"],
        "required_inputs": [
            ("conveyor_type", "Conveyor type (overhead / floor / power-and-free)"),
            ("track_length_m", "Track length"),
            ("load_capacity", "Load per carrier / trolley"),
        ],
        "optional_inputs": [("qty", "Quantity")],
        "expected_inputs": [
            ("conveyor_type", "Conveyor type"), ("track_length_m", "Track length"),
            ("load_capacity", "Load capacity"),
        ],
        "scalable": [], "from_given": {}, "rules": None, "field_rules": None,
        "rule_covers": [], "field_labels": {},
    },
    # --- paint-shop line units (client calculation doc, 2026-08-01) --------
    # Their formulas live in engineering/paint_shop_service; the profiles differ
    # only in the inlet-air rule that service applies per unit.
    "cleaning_room": _paint_shop_profile("cleaning_room", "Cleaning Room"),
    "buffing_booth": _paint_shop_profile("buffing_booth", "Buffing Booth"),
    "flash_off_zone": _paint_shop_profile("flash_off_zone", "Flash Off Zone"),
    "paint_drying_oven": _paint_shop_profile(
        "paint_drying_oven", "Paint Drying Oven",
        extra_template=[{"label": "Heat load", "kind": "computed"},
                        {"label": "Heat load (kCal)", "kind": "computed"},
                        {"label": "Heating mode", "kind": "standard"},
                        {"label": "Insulation", "kind": "standard"}]),
    "ducting": {
        "label": "Ducting",
        "scale_driver": None, "driver_label": "Airflow", "diff_unit": "airflow",
        "dimension_keys": [], "process_keys": ["material"],
        "required_inputs": [
            ("air_volume_cmh", "Design airflow"),
            ("layout_length_m", "Total duct run / layout length"),
            ("material", "Duct material (GI / SS / MS)"),
        ],
        "optional_inputs": [("qty", "Quantity")],
        "expected_inputs": [
            ("air_volume_cmh", "Airflow"), ("layout_length_m", "Layout length"),
            ("material", "Material"),
        ],
        "scalable": [], "from_given": {}, "rules": None, "field_rules": None,
        "rule_covers": [], "field_labels": {},
    },
}


def get_profile(category: Optional[str]) -> Optional[dict[str, Any]]:
    return CATEGORY_PROFILES.get(category or "")


def label_for(category: Optional[str], key: str) -> str:
    prof = get_profile(category)
    if prof and key in prof["field_labels"]:
        return prof["field_labels"][key]
    return key.replace("_", " ").capitalize()


def known_categories() -> list[str]:
    return list(CATEGORY_PROFILES.keys())
