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

# Wet scrubber
ATS_SPRAY_COVERAGE = "ATS wet-scrubber spray-coverage standard"
HYDRAULIC_PUMP_POWER = "Hydraulic pump-power formula"
ATS_RECIRC_TANK = "ATS recirculation-tank standard"
ATS_SPRAY_TOWER_HEIGHT = "ATS spray-tower height standard"
