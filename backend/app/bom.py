"""Bill of materials from the resolved engineering specification.

The spec already knows the machine: how much sheet it takes, which blower was
selected, how many filters at what size, how many luminaires, what duct bore.
A BOM is that same engineering read a second way — by what has to be BOUGHT and
MADE — so it is derived from the spec's own rows rather than estimated
separately. One engineering model, two documents.

WHAT IS COSTED AND WHAT IS NOT. Quantities and weights are engineering, so they
are computed wherever the spec supports them. MONEY is different: a line is
priced only where the client's own rate card covers it (`engineering/rate_card`,
read off their costed sheet). Everything else is returned as an UNCOSTED line
naming what is missing, and the total is explicitly partial.

That restraint is deliberate. The client's supplied cost sheet has its first row
cut off — its visible lines sum to Rs 5,68,534 against a stated Rs 6,49,264 — so
no total built here can be validated against theirs yet. A confident-looking
grand total would be the most dangerous number this platform could print. The
uncosted list IS the answer to "what else do we need from you".
"""
import re
from typing import Any, Optional

from .engineering import rate_card

# Sections in the order the client's own cost sheet works through a machine.
SECTIONS = ["Structure & panels", "Rotating plant", "Filtration", "Ducting",
            "Electrical", "Finishing", "Bought-outs"]

_SQM_PER_SQFT = 0.092903


def _row(rows: list, *needles: str) -> Optional[dict]:
    for r in rows or []:
        label = str(r.get("label", "")).lower()
        if all(n in label for n in needles):
            return r
    return None


def _value(rows: list, *needles: str) -> str:
    r = _row(rows, *needles)
    v = str((r or {}).get("value", "")).strip()
    return "" if v.lower() in ("", "to be determined", "to be confirmed with the customer") else v


def _num(text) -> Optional[float]:
    m = re.search(r"-?\d+(?:\.\d+)?", str(text or "").replace(",", ""))
    return float(m.group()) if m else None


def _nos(text) -> Optional[int]:
    """A stated count, never a bare number — the same rule the drawing uses."""
    m = re.search(r"(\d+)\s*(?:nos?\b|no's|sets?\b)", str(text or ""), re.I)
    return int(m.group(1)) if m else None


def _line(section: str, item: str, spec: str = "", qty=None, unit: str = "",
          weight_kg=None, amount=None, basis: str = "", source: str = "") -> dict:
    return {"section": section, "item": item, "spec": spec, "qty": qty, "unit": unit,
            "weight_kg": weight_kg, "amount": amount, "basis": basis, "source": source}


def _five_side_area_m2(env: dict) -> Optional[float]:
    """Enclosure surface area by the client's own convention: five sides, floor
    excluded. Same formula `paint_shop_service` uses, so the two agree."""
    L, W, H = (env or {}).get("length"), (env or {}).get("width"), (env or {}).get("height")
    if not (L and W and H):
        return None
    l, w, h = L / 1000.0, W / 1000.0, H / 1000.0
    return round(l * w + 2 * (l * h) + 2 * (w * h), 2)


def build_bom(spec: dict[str, Any]) -> dict[str, Any]:
    """Resolved specification -> bill of materials.

    Every line states WHERE its quantity came from. A line the engineering
    supports but the rate card does not price is still listed, with its cost
    left open — dropping it would hide scope, and pricing it would invent money.
    """
    rows = spec.get("technical_details") or []
    env = (spec.get("geometry") or {}).get("envelope_mm") or {}
    lines: list[dict] = []

    # --- Structure & panels ------------------------------------------------
    sheet_kg = _num(_value(rows, "sheet weight")) or _num(_value(rows, "enclosure", "weight"))
    if sheet_kg:
        mat, lab = rate_card.steel_cost(sheet_kg, "sheet")
        lines.append(_line("Structure & panels", "MS sheet panels",
                           _value(rows, "construction") or "MS sheet",
                           round(sheet_kg), "kg", weight_kg=round(sheet_kg),
                           amount=round(mat + lab),
                           basis=f"{round(sheet_kg)} kg x (Rs {rate_card.SHEET_MATERIAL_RATE:g}/kg "
                                 f"material + Rs {rate_card.SHEET_LABOUR_RATE:g}/kg fabrication)",
                           source="Enclosure sheet weight (engineering rule)"))
    # The client's own sheet prices structure separately, but no rule computes
    # its weight yet, so it is scheduled rather than estimated.
    lines.append(_line("Structure & panels", "MS structure / supports",
                       _value(rows, "construction") or "MS sections", None, "kg",
                       basis="Section weight needs a structural take-off - not yet an "
                             "engineering rule"))

    # --- Rotating plant ----------------------------------------------------
    blower = _value(rows, "exhaust blower")
    if blower and not blower.isdigit():
        qty = _nos(_value(rows, "blower", "nos")) or _num(_value(rows, "blower", "nos")) or 1
        lines.append(_line("Rotating plant", "Exhaust blower", blower, int(qty), "no",
                           amount=(lambda c: round(c * qty) if c else None)(
                               rate_card.blower_cost(blower)),
                           basis="Catalogue selection (Continental Thermal chart)"
                                 if rate_card.blower_cost(blower)
                                 else f"Model {blower} is not on the client's priced list",
                           source="Exhaust blower (engineering rule)"))
    hp = _num(_value(rows, "blower motor", "hp")) or _num(_value(rows, "motor", "hp"))
    if hp:
        lines.append(_line("Rotating plant", "Blower motor", f"{hp:g} HP", hp, "HP",
                           amount=round(rate_card.motor_cost(hp)),
                           basis=f"{hp:g} HP x Rs {rate_card.MOTOR_RATE_PER_HP:g}/HP",
                           source="Exhaust blower motor (engineering rule)"))

    # --- Filtration --------------------------------------------------------
    filt = _value(rows, "arresting filter") or _value(rows, "paper filter")
    n_filt = _nos(filt)
    if n_filt:
        dims = re.findall(r"(\d{3,4})\s*x\s*(\d{3,4})", filt)
        area = round(n_filt * (int(dims[0][0]) / 1000) * (int(dims[0][1]) / 1000), 2) if dims else None
        lines.append(_line("Filtration", "Paint arresting filter", filt, n_filt, "no",
                           amount=(round(rate_card.bought_out_cost("paint_arrest_filter", area))
                                   if area else None),
                           basis=(f"{n_filt} nos = {area} sq.m x Rs "
                                  f"{rate_card.BOUGHT_OUT_RATES['paint_arrest_filter'].price:g}/sq.m"
                                  if area else "Filter area not derivable from the stated size"),
                           source="Paint arresting filter (engineering rule)"))
    inlet = _value(rows, "intake filter") or _value(rows, "inlet filter")
    if inlet:
        n_in = _nos(inlet)
        lines.append(_line("Filtration", "Air inlet filter", inlet, n_in, "no",
                           amount=(round(rate_card.bought_out_cost("air_inlet_filter", n_in))
                                   if n_in else None),
                           basis="Client rate card" if n_in
                                 else "Quantity not stated - inlet filter count needs sizing",
                           source="Air intake filter"))

    # --- Ducting -----------------------------------------------------------
    duct = _value(rows, "duct")
    if duct:
        lines.append(_line("Ducting", "Exhaust duct", duct, None, "sq.m",
                           basis="Duct bore is engineered; the RUN LENGTH is a site "
                                 "measurement, so the area cannot be taken off yet",
                           source="Exhaust ducts (engineering rule)"))

    # --- Electrical --------------------------------------------------------
    lux = _value(rows, "illumination")
    n_lux = _nos(lux)
    if n_lux:
        lines.append(_line("Electrical", "Light fitting", lux, n_lux, "no",
                           amount=round(rate_card.bought_out_cost("led_light", n_lux)),
                           basis=f"{n_lux} nos x Rs "
                                 f"{rate_card.BOUGHT_OUT_RATES['led_light'].price:g}/no",
                           source="Illumination (engineering rule)"))
    panel = _value(rows, "control panel")
    if panel:
        kw = _num(panel)
        lines.append(_line("Electrical", "Control panel", panel, 1, "lot",
                           basis=(f"Rate card prices a 10 HP booth panel; this is a "
                                  f"{kw:g} kW scope, so it is not extrapolated"
                                  if kw else "Panel scope priced per project"),
                           source="Control panel (engineering rule)"))
        lines.append(_line("Electrical", "Field wiring", "As per panel scope", 1, "lot",
                           basis="Priced with the panel; scope depends on the layout"))

    # --- Finishing ---------------------------------------------------------
    area_m2 = _num(_value(rows, "surface area")) or _five_side_area_m2(env)
    if area_m2:
        sqft = round(area_m2 / _SQM_PER_SQFT)
        lines.append(_line("Finishing", "Painting", "Primer + finish coat", sqft, "sq.ft",
                           amount=round(sqft * rate_card.PAINTING_RATE_PER_SQFT),
                           basis=f"{area_m2} sq.m ({sqft} sq.ft) x Rs "
                                 f"{rate_card.PAINTING_RATE_PER_SQFT:g}/sq.ft; five-side area, "
                                 f"floor excluded",
                           source="Enclosure surface area (client formula)"))

    # --- Bought-outs the spec explicitly names ------------------------------
    for label, key in (("view glass", "view_glass"), ("sliding door", "sliding_door_kit")):
        val = _value(rows, label.split()[0])
        if val:
            n = _nos(val) or 1
            lines.append(_line("Bought-outs", label.title(), val, n,
                               rate_card.BOUGHT_OUT_RATES[key].unit,
                               amount=round(rate_card.bought_out_cost(key, n)),
                               basis="Client rate card"))

    costed = [l for l in lines if l["amount"] is not None]
    uncosted = [l for l in lines if l["amount"] is None]
    totals = {
        "weight_kg": round(sum(l["weight_kg"] or 0 for l in lines), 1),
        "costed_amount": round(sum(l["amount"] or 0 for l in costed)),
        "costed_lines": len(costed),
        "uncosted_lines": len(uncosted),
        "partial": bool(uncosted),
    }
    return {
        "ok": True,
        "category": spec.get("category"),
        "category_label": spec.get("category_label"),
        "sections": [s for s in SECTIONS if any(l["section"] == s for l in lines)],
        "lines": lines,
        "totals": totals,
        "uncosted": [{"item": l["item"], "reason": l["basis"]} for l in uncosted],
        "notes": _notes(totals),
        "bom_markdown": _markdown(spec, lines, totals),
    }


def _notes(totals: dict) -> list[str]:
    notes = ["Quantities and weights are taken from the engineering specification.",
             "Rates are Vitech's own, from the costed sheet dated 24.07.2026."]
    if totals["partial"]:
        notes.append(
            f"PARTIAL COST: {totals['uncosted_lines']} line(s) carry no price because the "
            f"client's rate card does not cover them. The figure below is not a quotation.")
    return notes


def _markdown(spec: dict, lines: list, totals: dict) -> str:
    """A printable BOM the agent can output verbatim."""
    L = [f"**BILL OF MATERIALS — {spec.get('category_label') or 'Equipment'} (DRAFT)**", ""]
    if totals["partial"]:
        L += [f"> **Partial costing.** {totals['costed_lines']} of "
              f"{totals['costed_lines'] + totals['uncosted_lines']} lines are priced from "
              f"Vitech's rate card; the rest are listed with the cost left open.", ""]
    current = None
    L += ["| Item | Specification | Qty | Unit | Amount (Rs) |", "| --- | --- | ---: | --- | ---: |"]
    for l in lines:
        if l["section"] != current:
            current = l["section"]
            L.append(f"| **{current}** | | | | |")
        qty = "" if l["qty"] is None else f"{l['qty']:g}" if isinstance(l["qty"], float) else str(l["qty"])
        amt = f"{l['amount']:,}" if l["amount"] is not None else "—"
        L.append(f"| {l['item']} | {str(l['spec'])[:46]} | {qty} | {l['unit']} | {amt} |")
    L.append("")
    if totals["weight_kg"]:
        L.append(f"**Fabricated weight:** {totals['weight_kg']:g} kg")
    L.append(f"**Priced lines total:** Rs {totals['costed_amount']:,} "
             f"({totals['costed_lines']} of "
             f"{totals['costed_lines'] + totals['uncosted_lines']} lines)")
    if totals["partial"]:
        L += ["", "_Not a quotation. Lines shown as — need either a client rate or a "
              "site/structural take-off._"]
    return "\n".join(L)
