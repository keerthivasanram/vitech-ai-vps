"""Directional engineering knowledge base for AI (Consulting Engineer) mode.

STRICT PRINCIPLE — the system-level rule the whole product is built on:
    Never state a precise engineering value unless it is
      (a) given by the customer, or
      (b) calculated / derived from a documented engineering rule.
    Everything else is design DIRECTION, or "To be determined".

So this KB deliberately holds ONLY directional guidance (booth type, filtration
approach, construction, standards) and, for each value that must be *calculated*,
the list of INPUTS required to size it. It contains NO airflow, fan HP, filter
counts or dimensions — those are computed by the rule engine, never looked up.

Add a new equipment type = add one entry here; AI mode extends automatically.
"""
from typing import Any, Optional

DIRECTIONAL_KB: dict[str, dict[str, Any]] = {
    "paint_booth": {
        # (Item, directional recommendation) — approach only, no numbers
        "recommendation": [
            ("Booth type", "Dry powder-coating booth"),
            ("Construction", "GI or painted MS (subject to operating environment)"),
            ("Filtration", "Dry cartridge filters with a powder-recovery system"),
            ("Fresh air / exhaust", "Balanced supply + exhaust; sized after airflow calc"),
            ("Lighting", "Industrial LED, flame-proof where solvents are present"),
            ("Control panel", "Motor protection + safety interlocks"),
            ("Access", "Doors sized to the workpiece handling method"),
        ],
        "standards": ["NFPA 33 (spray application)", "IS 1642 (fire safety)"],
        # value that must be CALCULATED -> inputs required before it can be sized
        "computed_values": {
            "Booth dimensions": ["largest workpiece size", "handling method", "clearance"],
            "Exhaust airflow": ["booth open-face area", "design face velocity", "applicable standard"],
            "Fan selection": ["airflow", "system static pressure", "duct layout"],
            "Filter area / count": ["airflow", "filter face velocity"],
            "Motor ratings": ["fan/pump duty after sizing"],
        },
    },
    "wet_scrubber": {
        "recommendation": [
            ("Scrubber type", "Vertical spray or packed tower"),
            ("Construction", "SS-304 / SS-316 or FRP (subject to gas chemistry)"),
            ("Liquid system", "Recirculation pump + tank with make-up water"),
            ("Mist elimination", "PP mist eliminator / demister"),
            ("Control panel", "Pump + blower control with interlocks"),
        ],
        "standards": ["APC good engineering practice", "CPCB emission norms (as applicable)"],
        "computed_values": {
            "Tower diameter": ["airflow", "design gas velocity"],
            "Tower height": ["required transfer units / gas-liquid contact time"],
            "Spray nozzles": ["recirculation flow (L/G ratio)", "nozzle throughput"],
            "Pump rating": ["recirculation flow", "nozzle pressure + static head"],
            "Tank capacity": ["recirculation flow", "retention time"],
        },
    },
    # --- extensible stubs for upcoming categories --------------------------
    "hot_air_oven": {
        "recommendation": [
            ("Oven type", "Batch or conveyorised hot-air oven (per production flow)"),
            ("Heating", "Diesel/gas burner or electric (subject to fuel availability)"),
            ("Insulation", "Mineral wool panels (thickness per operating temperature)"),
            ("Air circulation", "Recirculation blowers for uniform temperature"),
            ("Control panel", "PID temperature control + safety interlocks"),
        ],
        "standards": ["IS / good practice for industrial ovens"],
        "computed_values": {
            "Chamber size": ["largest workpiece size", "batch size / conveyor pitch"],
            "Heat load / burner rating": ["mass throughput", "target temperature", "cycle time"],
            "Circulation airflow": ["chamber volume", "target uniformity"],
            "Insulation thickness": ["operating temperature", "skin-temperature limit"],
        },
    },
    "dust_collector": {
        "recommendation": [
            ("Collector type", "Pulse-jet bag filter or cartridge (per dust characteristics)"),
            ("Construction", "MS with suitable coating (subject to dust/environment)"),
            ("Cleaning", "Automatic pulse-jet with compressed air"),
            ("Disposal", "Rotary airlock + collection bin/screw"),
            ("Control panel", "Sequential pulse timer + fan control"),
        ],
        "standards": ["Good APC practice", "CPCB emission norms (as applicable)"],
        "computed_values": {
            "Filter area": ["airflow", "air-to-cloth ratio (per dust type)"],
            "Fan selection": ["airflow", "system static pressure"],
            "Hopper / airlock size": ["dust load", "collection interval"],
        },
    },
}


def directional(category: Optional[str]) -> Optional[dict[str, Any]]:
    return DIRECTIONAL_KB.get(category or "")


def known_ai_categories() -> list[str]:
    return list(DIRECTIONAL_KB.keys())
