"""Governing standards registry.

Every engineering value cites the standard it follows. Centralising the strings
means the client can hand over their standards list once and have every rule
reference the exact wording — and an auditor sees, in one file, which standards
the platform claims to follow. The client will supply the authoritative set;
these are the current ATS/NFPA defaults the formulas were calibrated to.
"""

# Paint booth / surface finishing
NFPA_33_FACE_VELOCITY = "NFPA 33 (face velocity 0.4-0.5 m/s)"
ATS_FAN_SIZING = "ATS fan-sizing standard"
ATS_OVERSPRAY_CAPTURE = "ATS overspray-capture standard"
ATS_MATERIAL_SELECTION = "ATS material-selection standard"

# Paint shop plant — the client's OWN engineering-calculation document
# (received 2026-08-01). These rules are transcribed from it, not inferred, so
# they cite the client as the authority rather than an external standard.
CLIENT_PAINT_SHOP_CALC = "Vitech paint-shop design calculation"
CLIENT_OVEN_HEAT_LOAD = "Vitech oven heat-load rule (100 ft3 = 12 kW; 1 kW = 860 kCal)"
MS_SHEET_BASIS = "MS sheet basis (2 mm / 14 SWG, 7850 kg/m3)"
BLOWER_CHART_SELECTION = "Continental Thermal blower specification chart (direct drive)"

# Client engineering-standards package (2026-08-01) — the design rules that
# replaced the seeded placeholders flagged in the client's specification review.
CLIENT_BOOTH_STANDARD = "Vitech booth-type standard (canonical type -> design face velocity)"
CLIENT_FILTER_STANDARD = "Vitech filter standard (media velocity 0.8-1.2 m/s)"
CLIENT_LIGHTING_STANDARD = "Vitech lighting standard (lux-based selection)"
CLIENT_DUCT_STANDARD = "Vitech duct standard (transport velocity)"
CLIENT_ELECTRICAL_STANDARD = "Vitech electrical panel standard (load-banded starter)"
CLIENT_FIRE_STANDARD = "Fire protection by paint process (NFPA 33 for solvent)"
CLIENT_MATERIAL_MATRIX = "Vitech material selection matrix (advisory)"

# Wet scrubber
ATS_SPRAY_COVERAGE = "ATS wet-scrubber spray-coverage standard"
HYDRAULIC_PUMP_POWER = "Hydraulic pump-power formula"
ATS_RECIRC_TANK = "ATS recirculation-tank standard"
ATS_SPRAY_TOWER_HEIGHT = "ATS spray-tower height standard"
