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

# Client calculation workbooks (delivered 2026-09-01), transcribed in
# docs/client-calculation-sheets.md. Like the paint-shop rules above, these cite
# Vitech's own sheets as the authority because that is exactly what they are.
CLIENT_VOC_CALC = "Vitech paint-shop VOC calculation (design limit 1000 mg/m3)"
CLIENT_HEAT_LOAD_CALC = "Vitech heat-load calculation (1 kW = 860 Kcal)"
CLIENT_SCRUBBER_DIAMETER_CALC = "Vitech scrubber diameter calculation (tower 1.0 m/s, duct 15 m/s)"
CLIENT_STOCK_WEIGHTS = "Vitech stock-section weight table (kg per standard length)"

# Vitech's own standard product range (AI database PDF, 2026-09-01). A value
# carrying this standard was QUOTED from their catalogue, not calculated.
CLIENT_BOOTH_CATALOGUE = "Vitech standard paint-booth range (published model data)"
