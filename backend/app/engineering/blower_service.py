"""Blower selection from the vendor's published specification chart.

Source: "BLOWER SPECIFICATION CHART" — CONTINENTAL THERMAL ENGINEERS PVT LTD,
DIRECT DRIVE BLOWERS (client-supplied 2026-08-01). This is the actual catalogue
Vitech selects from: the costed paint-booth BOM of 24.07.2026 lists
"CLP-4" WC-10 HP-9000Cfm-Direct Drive", which is exactly `CLP-4-10-9000` below.

This module is a LOOKUP, not a formula — selection returns a real catalogue
model or nothing. It never interpolates a blower that the vendor does not sell,
and it never invents a motor HP (golden rule #2). When no model covers the duty,
`select_blower` returns None and the caller surfaces an explicit TBD.

Model naming: <SERIES>-<CASING>-<MOTOR HP>-<CFM>, e.g. CLP-4-10-9000 = CLP
series, 4" WC casing, 10 HP, 9000 CFM. The series prefix encodes the pressure
class, so TOTAL PRESSURE is constant within a series:

    CLP-2   50 mmwc     CHB-8   200 mmwc    CCB-20  500 mmwc    CHP-40  1000 mmwc
    CLP-3   75 mmwc     CHB-10  250 mmwc    CCB-24  600 mmwc    CHPT-44 1100 mmwc
    CLP-4  100 mmwc     CHB-12  300 mmwc    CSP-28  700 mmwc    CHPT-48 1200 mmwc
    CLP-5  125 mmwc     CCB-16  400 mmwc    CSP-32  800 mmwc
    CLP-6  150 mmwc     CCB-18  450 mmwc    CSP-36  900 mmwc

CLIENT-EXTENSION POINT: adding a vendor/series = appending rows to `_CHART`.
Nothing else changes.
"""
from typing import NamedTuple, Optional

# Pressure CLASS Vitech builds paint booths around. Evidence-based, NOT assumed:
# the client's costed booth BOM (24.07.2026, 9000 CFM) names the machine
# 'CLP-4" WC-10 HP-9000Cfm-Direct Drive' — the CLP-4 (4" water column = 100 mmwc
# total) series. A booth is selected WITHIN this family, not against a fixed
# static-pressure floor, because static pressure inside a series is the FAN CURVE
# (it falls as CFM rises: 95 mmwc at 1600 CFM down to 54 mmwc at 61000 CFM).
# Holding a flat static floor would push a larger booth out of the family Vitech
# actually builds and into a costlier high-pressure series.
PAINT_BOOTH_SERIES = "CLP-4"

# Static pressure floor for the GENERIC duty-based path, where the caller states
# the system resistance instead of a product family. Same evidence: the client's
# 9000 CFM booth blower is rated 89 mmwc static.
BOOTH_STATIC_PRESSURE_MMWC = 89.0


class Blower(NamedTuple):
    """One catalogue row, verbatim from the vendor chart."""
    model: str
    total_pressure_mmwc: int
    static_pressure_mmwc: int
    cfm: int
    cmh: Optional[int]      # vendor's own m3/h figure; None where the chart is blank
    motor_hp: float
    poles: int
    motor_rpm: int
    fan_rpm: int

    @property
    def drive(self) -> str:
        return "direct drive"

    def describe(self) -> str:
        """One-line human summary, e.g. for a spec row or a BOM line."""
        return (f'{self.model} — {self.cfm} CFM @ {self.static_pressure_mmwc} mmwc static '
                f'({self.total_pressure_mmwc} mmwc total), {self.motor_hp:g} HP, '
                f'{self.poles}-pole {self.motor_rpm} rpm, direct drive')


# (model, total_mmwc, static_mmwc, cfm, cmh, hp, poles, motor_rpm, fan_rpm)
# Transcribed verbatim from the vendor chart — vendor figures are authoritative
# and are NOT recomputed here (the chart's own CFM->m3/h ratio is ~1.715, which
# differs slightly from unit_converter.CFM_TO_CMH 1.699; vendor data wins, and
# the discrepancy is left visible rather than silently "corrected").
_CHART: list[Blower] = [
    # --- CLP-2 : 50 mmwc total -------------------------------------------
    Blower("CLP-2-2-2500", 50, 36, 2500, 4290, 2, 4, 1450, 1450),
    Blower("CLP-2-3-4000", 50, 30, 4000, 6860, 3, 4, 1450, 1450),
    Blower("CLP-2-5-8500", 50, 34, 8500, 14575, 5, 4, 1450, 1450),
    Blower("CLP-2-7.5-14000", 50, 23, 14000, 24000, 7.5, 4, 1450, 1450),
    Blower("CLP-2-10-18000", 50, 32, 18000, 30860, 10, 6, 960, 960),
    Blower("CLP-2-15-25000", 50, 27, 25000, 42860, 15, 6, 965, 965),
    Blower("CLP-2-20-37000", 50, 30, 37000, 63430, 20, 8, 720, 720),
    Blower("CLP-2-25-47000", 50, 35, 47000, 80575, 25, 8, 725, 725),
    Blower("CLP-2-30-55000", 50, 33, 55000, 94290, 30, 8, 725, 725),
    Blower("CLP-2-40-75000", 50, 27, 75000, 128575, 40, 8, 730, 730),
    # --- CLP-3 : 75 mmwc total -------------------------------------------
    Blower("CLP-3-2-2300", 75, 62, 2300, 3945, 2, 4, 1450, 1450),
    Blower("CLP-3-3-3200", 75, 59, 3200, 5490, 3, 4, 1450, 1450),
    Blower("CLP-3-5-6000", 75, 63, 6000, 10290, 5, 4, 1450, 1450),
    Blower("CLP-3-7.5-10000", 75, 62, 10000, 17145, 7.5, 4, 1450, 1450),
    Blower("CLP-3-10-12000", 75, 60, 12000, 20575, 10, 4, 1450, 1450),
    Blower("CLP-3-15-18000", 75, 55, 18000, 30860, 15, 4, 1450, 1450),
    Blower("CLP-3-20-25000", 75, 50, 25000, 42860, 20, 4, 1450, 1450),
    Blower("CLP-3-25-33000", 75, 45, 33000, 56575, 25, 4, 1450, 1450),
    Blower("CLP-3-30-40000", 75, 40, 40000, 68575, 30, 4, 1450, 1450),
    Blower("CLP-3-40-53000", 75, 51, 53000, 90860, 40, 6, 960, 960),
    Blower("CLP-3-50-68000", 75, 47, 68000, 116575, 50, 6, 960, 960),
    # --- CLP-4 : 100 mmwc total ------------------------------------------
    Blower("CLP-4-2-1600", 100, 95, 1600, 2745, 2, 4, 1450, 1450),
    Blower("CLP-4-3-2200", 100, 95, 2200, 3775, 3, 4, 1450, 1450),
    Blower("CLP-4-5-3700", 100, 93, 3700, 6345, 5, 4, 1450, 1450),
    Blower("CLP-4-7.5-6500", 100, 91, 6500, 11145, 7.5, 4, 1450, 1450),
    Blower("CLP-4-10-9000", 100, 89, 9000, 15430, 10, 4, 1450, 1450),
    Blower("CLP-4-15-14500", 100, 84, 14500, 24860, 15, 4, 1450, 1450),
    Blower("CLP-4-20-19500", 100, 80, 19500, 33430, 20, 4, 1450, 1450),
    Blower("CLP-4-25-25000", 100, 76, 25000, 42860, 25, 4, 1450, 1450),
    Blower("CLP-4-30-30500", 100, 72, 30500, 52290, 30, 4, 1450, 1450),
    Blower("CLP-4-40-41000", 100, 65, 41000, 70290, 40, 4, 1450, 1450),
    Blower("CLP-4-50-51000", 100, 60, 51000, 87430, 50, 4, 1450, 1450),
    Blower("CLP-4-60-61000", 100, 54, 61000, 104575, 60, 4, 1450, 1450),
    # --- CLP-5 : 125 mmwc total ------------------------------------------
    Blower("CLP-5-2-1200", 125, 124, 1200, 2060, 2, 4, 1450, 1450),
    Blower("CLP-5-3-1900", 125, 120, 1900, 3260, 3, 4, 1450, 1450),
    Blower("CLP-5-5-3600", 125, 116, 3600, 6175, 5, 4, 1450, 1450),
    Blower("CLP-5-7.5-6000", 125, 117, 6000, 10290, 7.5, 4, 1450, 1450),
    Blower("CLP-5-10-7200", 125, 116, 7200, 12345, 10, 4, 1450, 1450),
    Blower("CLP-5-15-12000", 125, 112, 12000, 20575, 15, 4, 1450, 1450),
    Blower("CLP-5-20-16000", 125, 108, 16000, 27430, 20, 4, 1450, 1450),
    Blower("CLP-5-25-20000", 125, 105, 20000, 34290, 25, 4, 1450, 1450),
    Blower("CLP-5-30-24500", 125, 101, 24500, 42000, 30, 4, 1450, 1450),
    Blower("CLP-5-40-32500", 125, 96, 32500, 55715, 40, 4, 1450, 1450),
    Blower("CLP-5-50-41000", 125, 90, 41000, 70290, 50, 4, 1450, 1450),
    Blower("CLP-5-60-49500", 125, 86, 49500, 84860, 60, 4, 1450, 1450),
    # --- CLP-6 : 150 mmwc total ------------------------------------------
    Blower("CLP-6-2-1000", 150, 148, 1000, 1715, 2, 4, 1450, 1450),
    Blower("CLP-6-3-1600", 150, 146, 1600, 2745, 3, 4, 1450, 1450),
    Blower("CLP-6-5-2900", 150, 143, 2900, 4975, 5, 4, 1450, 1450),
    Blower("CLP-6-7.5-4500", 150, 140, 4500, 7715, 7.5, 4, 1450, 1450),
    Blower("CLP-6-10-6000", 150, 137, 6000, 10290, 10, 4, 1450, 1450),
    Blower("CLP-6-15-10000", 150, 132, 10000, 17145, 15, 4, 1450, 1450),
    Blower("CLP-6-20-13000", 150, 135, 13000, 22290, 20, 4, 1450, 1450),
    Blower("CLP-6-25-16000", 150, 133, 16000, 27430, 25, 4, 1450, 1450),
    Blower("CLP-6-30-20000", 150, 130, 20000, 34290, 30, 4, 1450, 1450),
    Blower("CLP-6-40-27000", 150, 125, 27000, 46290, 40, 4, 1450, 1450),
    Blower("CLP-6-50-34000", 150, 120, 34000, 58290, 50, 4, 1450, 1450),
    Blower("CLP-6-60-41000", 150, 116, 41000, 70290, 60, 4, 1450, 1450),
    # --- CHB-8 : 200 mmwc total ------------------------------------------
    Blower("CHB-8-2-700", 200, 194, 700, 1200, 2, 2, 2900, 2900),
    Blower("CHB-8-3-1100", 200, 190, 1100, 1890, 3, 2, 2900, 2900),
    Blower("CHB-8-5-2200", 200, 183, 2200, 3775, 5, 2, 2900, 2900),
    Blower("CHB-8-7.5-3300", 200, 176, 3300, 5660, 7.5, 2, 2900, 2900),
    Blower("CHB-8-10-4400", 200, 182, 4400, 7545, 10, 2, 2900, 2900),
    Blower("CHB-8-15-6600", 200, 178, 6600, 11315, 15, 2, 2900, 2900),
    Blower("CHB-8-20-9000", 200, 190, 9000, 15430, 20, 4, 1450, 1450),
    Blower("CHB-8-25-11500", 200, 188, 11500, 19715, 25, 4, 1450, 1450),
    Blower("CHB-8-30-14700", 200, 185, 14700, 25200, 30, 4, 1450, 1450),
    Blower("CHB-8-40-20000", 200, 180, 20000, 34290, 40, 4, 1450, 1450),
    Blower("CHB-8-50-25000", 200, 178, 25000, 42860, 50, 4, 1450, 1450),
    Blower("CHB-8-60-30500", 200, 173, 30500, 52290, 60, 4, 1450, 1450),
    # --- CHB-10 : 250 mmwc total -----------------------------------------
    Blower("CHB-10-2-600", 250, 249, 600, 1030, 2, 2, 2900, 2900),
    Blower("CHB-10-3-1000", 250, 246, 1000, 1715, 3, 2, 2900, 2900),
    Blower("CHB-10-5-1500", 250, 244, 1500, 2575, 5, 2, 2900, 2900),
    Blower("CHB-10-7.5-2500", 250, 240, 2500, 4285, 7.5, 2, 2900, 2900),
    Blower("CHB-10-10-3500", 250, 247, 3500, 6000, 10, 2, 2900, 2900),
    Blower("CHB-10-15-5000", 250, 245, 5000, 8575, 15, 4, 1450, 1450),
    Blower("CHB-10-20-6700", 250, 243, 6700, 11490, 20, 4, 1450, 1450),
    Blower("CHB-10-25-9500", 250, 240, 9500, 16290, 25, 4, 1450, 1450),
    Blower("CHB-10-30-12000", 250, 238, 12000, 20575, 30, 4, 1450, 1450),
    Blower("CHB-10-40-15500", 250, 235, 15500, 26575, 40, 4, 1450, 1450),
    Blower("CHB-10-50-20500", 250, 231, 20500, 35145, 50, 4, 1450, 1450),
    Blower("CHB-10-60-24000", 250, 228, 24000, 41145, 60, 4, 1450, 1450),
    # --- CHB-12 : 300 mmwc total -----------------------------------------
    Blower("CHB-12-2-500", 300, 300, 500, 860, 2, 2, 2900, 2900),
    Blower("CHB-12-3-800", 300, 298, 800, 1375, 3, 2, 2900, 2900),
    Blower("CHB-12-5-1300", 300, 296, 1300, 2230, 5, 2, 2900, 2900),
    Blower("CHB-12-7.5-2200", 300, 292, 2200, 3775, 7.5, 2, 2900, 2900),
    Blower("CHB-12-10-2900", 300, 289, 2900, 4975, 10, 2, 2900, 2900),
    Blower("CHB-12-15-4200", 300, 297, 4200, 7200, 15, 4, 1450, 1450),
    Blower("CHB-12-20-6000", 300, 295, 6000, 10290, 20, 4, 1450, 1450),
    Blower("CHB-12-25-8000", 300, 293, 8000, 13715, 25, 4, 1450, 1450),
    Blower("CHB-12-30-9500", 300, 291, 9500, 16290, 30, 4, 1450, 1450),
    Blower("CHB-12-40-13000", 300, 288, 13000, 22290, 40, 4, 1450, 1450),
    Blower("CHB-12-50-17000", 300, 285, 17000, 29145, 50, 4, 1450, 1450),
    Blower("CHB-12-60-20000", 300, 282, 20000, 34290, 60, 4, 1450, 1450),
    # --- CCB-16 : 400 mmwc total -----------------------------------------
    Blower("CCB-16-2-400", 400, 400, 400, 690, 2, 2, 2900, 2900),
    Blower("CCB-16-3-600", 400, 398, 600, 1030, 3, 2, 2900, 2900),
    Blower("CCB-16-5-1000", 400, 394, 1000, 1715, 5, 2, 2900, 2900),
    Blower("CCB-16-7.5-1600", 400, 390, 1600, 2745, 7.5, 2, 2900, 2900),
    Blower("CCB-16-10-2100", 400, 387, 2100, 3600, 10, 2, 2900, 2900),
    Blower("CCB-16-15-3200", 400, 390, 3200, 5490, 15, 2, 2900, 2900),
    Blower("CCB-16-20-4200", 400, 383, 4200, 7200, 20, 2, 2900, 2900),
    Blower("CCB-16-25-6000", 400, 385, 6000, 10290, 25, 2, 2900, 2900),
    Blower("CCB-16-30-7500", 400, 386, 7500, 12860, 30, 2, 2900, 2900),
    Blower("CCB-16-40-10000", 400, 386, 10000, 17145, 40, 2, 2900, 2900),
    Blower("CCB-16-50-12500", 400, 383, 12500, 21430, 50, 2, 2900, 2900),
    Blower("CCB-16-60-15000", 400, 386, 15000, 25715, 60, 2, 2900, 2900),
    # --- CCB-18 : 450 mmwc total -----------------------------------------
    Blower("CCB-18-2-350", 450, 450, 350, 600, 2, 2, 2900, 2900),
    Blower("CCB-18-3-550", 450, 449, 550, 945, 3, 2, 2900, 2900),
    Blower("CCB-18-5-900", 450, 446, 900, 1545, 5, 2, 2900, 2900),
    Blower("CCB-18-7.5-1450", 450, 442, 1450, 2490, 7.5, 2, 2900, 2900),
    Blower("CCB-18-10-1900", 450, 439, 1900, 3260, 10, 2, 2900, 2900),
    Blower("CCB-18-15-3000", 450, 435, 3000, 5145, 15, 2, 2900, 2900),
    Blower("CCB-18-20-4000", 450, 434, 4000, 6860, 20, 2, 2900, 2900),
    Blower("CCB-18-25-5000", 450, 435, 5000, 8575, 25, 2, 2900, 2900),
    Blower("CCB-18-30-6500", 450, 435, 6500, 11145, 30, 2, 2900, 2900),
    Blower("CCB-18-40-9000", 450, 434, 9000, 15430, 40, 2, 2900, 2900),
    Blower("CCB-18-50-11000", 450, 436, 11000, 18860, 50, 2, 2900, 2900),
    Blower("CCB-18-60-13500", 450, 438, 13500, 23145, 60, 2, 2900, 2900),
    # --- CCB-20 : 500 mmwc total -----------------------------------------
    Blower("CCB-20-2-300", 500, 500, 300, 515, 2, 2, 2900, 2900),
    Blower("CCB-20-3-500", 500, 499, 500, 860, 3, 2, 2900, 2900),
    Blower("CCB-20-5-800", 500, 498, 800, 1375, 5, 2, 2900, 2900),
    Blower("CCB-20-7.5-1300", 500, 497, 1300, 2230, 7.5, 2, 2900, 2900),
    Blower("CCB-20-10-1800", 500, 495, 1800, 3090, 10, 2, 2900, 2900),
    Blower("CCB-20-15-2700", 500, 490, 2700, 4630, 15, 2, 2900, 2900),
    Blower("CCB-20-20-3800", 500, 486, 3800, 6515, 20, 2, 2900, 2900),
    Blower("CCB-20-25-4700", 500, 486, 4700, 8060, 25, 2, 2900, 2900),
    Blower("CCB-20-30-5800", 500, 487, 5800, 9945, 30, 2, 2900, 2900),
    Blower("CCB-20-40-7800", 500, 487, 7800, 13375, 40, 2, 2900, 2900),
    Blower("CCB-20-50-10000", 500, 488, 10000, 17145, 50, 2, 2900, 2900),
    Blower("CCB-20-60-12000", 500, 485, 12000, 20575, 60, 2, 2900, 2900),
    # --- CCB-24 : 600 mmwc total (no 2 HP model in the chart) ------------
    Blower("CCB-24-3-400", 600, 600, 400, 690, 3, 2, 2900, 2900),
    Blower("CCB-24-5-700", 600, 599, 700, 1200, 5, 2, 2900, 2900),
    Blower("CCB-24-7.5-1000", 600, 598, 1000, 1715, 7.5, 2, 2900, 2900),
    Blower("CCB-24-10-1500", 600, 594, 1500, 2575, 10, 2, 2900, 2900),
    Blower("CCB-24-15-2400", 600, 591, 2400, 4115, 15, 2, 2900, 2900),
    Blower("CCB-24-20-3200", 600, 590, 3200, 5490, 20, 2, 2900, 2900),
    Blower("CCB-24-25-4000", 600, 590, 4000, 6860, 25, 2, 2900, 2900),
    Blower("CCB-24-30-4200", 600, 589, 4200, 7200, 30, 2, 2900, 2900),
    Blower("CCB-24-40-6700", 600, 587, 6700, 11485, 40, 2, 2900, 2900),
    Blower("CCB-24-50-8500", 600, 587, 8500, 14575, 50, 2, 2900, 2900),
    Blower("CCB-24-60-10200", 600, 584, 10200, 17490, 60, 2, 2900, 2900),
    # --- CSP-28 : 700 mmwc total (no 2 HP model in the chart) ------------
    Blower("CSP-28-3-350", 700, 680, 350, 600, 3, 2, 2900, 2900),
    Blower("CSP-28-5-600", 700, 680, 600, 1030, 5, 2, 2900, 2900),
    Blower("CSP-28-7.5-900", 700, 680, 900, 1545, 7.5, 2, 2900, 2900),
    Blower("CSP-28-10-1250", 700, 680, 1250, 2145, 10, 2, 2900, 2900),
    Blower("CSP-28-15-1850", 700, 680, 1850, 3175, 15, 2, 2900, 2900),
    Blower("CSP-28-20-2500", 700, 665, 2500, 4290, 20, 2, 2900, 2900),
    Blower("CSP-28-25-3100", 700, 665, 3100, 5315, 25, 2, 2900, 2900),
    Blower("CSP-28-30-3700", 700, 665, 3700, 6345, 30, 2, 2900, 2900),
    Blower("CSP-28-40-5000", 700, 665, 5000, 8575, 40, 2, 2900, 2900),
    Blower("CSP-28-50-6200", 700, 655, 6200, 10630, 50, 2, 2900, 2900),
    Blower("CSP-28-60-7500", 700, 655, 7500, 12860, 60, 2, 2900, 2900),
    # --- CSP-32 : 800 mmwc total (no 2 HP model in the chart) ------------
    Blower("CSP-32-3-275", 800, 785, 275, 475, 3, 2, 2900, 2900),
    Blower("CSP-32-5-500", 800, 785, 500, 860, 5, 2, 2900, 2900),
    Blower("CSP-32-7.5-750", 800, 785, 750, 1290, 7.5, 2, 2900, 2900),
    Blower("CSP-32-10-1050", 800, 785, 1050, 1800, 10, 2, 2900, 2900),
    Blower("CSP-32-15-1550", 800, 780, 1550, 2660, 15, 2, 2900, 2900),
    Blower("CSP-32-20-2100", 800, 780, 2100, 3600, 20, 2, 2900, 2900),
    Blower("CSP-32-25-2600", 800, 775, 2600, 4460, 25, 2, 2900, 2900),
    Blower("CSP-32-30-3100", 800, 775, 3100, 5315, 30, 2, 2900, 2900),
    Blower("CSP-32-40-4200", 800, 760, 4200, 7200, 40, 2, 2900, 2900),
    Blower("CSP-32-50-5200", 800, 760, 5200, 8915, 50, 2, 2900, 2900),
    Blower("CSP-32-60-6200", 800, 760, 6200, 10630, 60, 2, 2900, 2900),
    # --- CSP-36 : 900 mmwc total (no 2 HP model in the chart) ------------
    Blower("CSP-36-3-250", 900, 885, 250, 430, 3, 2, 2900, 2900),
    Blower("CSP-36-5-450", 900, 885, 450, 775, 5, 2, 2900, 2900),
    Blower("CSP-36-7.5-700", 900, 885, 700, 1200, 7.5, 2, 2900, 2900),
    Blower("CSP-36-10-900", 900, 885, 900, 1545, 10, 2, 2900, 2900),
    Blower("CSP-36-15-1400", 900, 885, 1400, 2400, 15, 2, 2900, 2900),
    Blower("CSP-36-20-1850", 900, 885, 1850, 3175, 20, 2, 2900, 2900),
    Blower("CSP-36-25-2300", 900, 875, 2300, 3950, 25, 2, 2900, 2900),
    Blower("CSP-36-30-2750", 900, 875, 2750, 4715, 30, 2, 2900, 2900),
    Blower("CSP-36-40-3700", 900, 860, 3700, 6345, 40, 2, 2900, 2900),
    Blower("CSP-36-50-4600", 900, 860, 4600, 7890, 50, 2, 2900, 2900),
    Blower("CSP-36-60-5500", 900, 860, 5500, 9430, 60, 2, 2900, 2900),
    # --- CHP-40 : 1000 mmwc total (starts at 5 HP) -----------------------
    Blower("CHP-40-5-350", 1000, 995, 350, 600, 5, 2, 2900, 2900),
    Blower("CHP-40-7.5-600", 1000, 990, 600, 1030, 7.5, 2, 2900, 2900),
    Blower("CHP-40-10-800", 1000, 985, 800, 1375, 10, 2, 2900, 2900),
    Blower("CHP-40-15-1300", 1000, 982, 1300, 2230, 15, 2, 2900, 2900),
    Blower("CHP-40-20-1900", 1000, 980, 1900, 3260, 20, 2, 2900, 2900),
    Blower("CHP-40-25-2400", 1000, 978, 2400, 4115, 25, 2, 2900, 2900),
    Blower("CHP-40-30-2900", 1000, 975, 2900, 4975, 30, 2, 2900, 2900),
    Blower("CHP-40-40-4000", 1000, 973, 4000, 6860, 40, 2, 2900, 2900),
    Blower("CHP-40-50-5000", 1000, 970, 5000, 8575, 50, 2, 2900, 2900),
    Blower("CHP-40-60-6000", 1000, 965, 6000, 10290, 60, 2, 2900, 2900),
    # --- CHPT-44 : 1100 mmwc total (starts at 5 HP) ----------------------
    # NB the chart's m3/h column for this series is internally inconsistent
    # (e.g. 250 CFM shown as 690 m3/h). CFM is authoritative — it is also in the
    # model name — so selection uses CFM and the vendor m3/h is carried as-is.
    Blower("CHPT-44-5-250", 1100, 1095, 250, 690, 5, 2, 2900, 2900),
    Blower("CHPT-44-7.5-500", 1100, 1090, 500, 1030, 7.5, 2, 2900, 2900),
    Blower("CHPT-44-10-700", 1100, 1085, 700, 1715, 10, 2, 2900, 2900),
    Blower("CHPT-44-15-1200", 1100, 1080, 1200, 2400, 15, 2, 2900, 2900),
    Blower("CHPT-44-20-1600", 1100, 1075, 1600, 3090, 20, 2, 2900, 2900),
    Blower("CHPT-44-25-2100", 1100, 1070, 2100, 3945, 25, 2, 2900, 2900),
    Blower("CHPT-44-30-2600", 1100, 1060, 2600, 5490, 30, 2, 2900, 2900),
    Blower("CHPT-44-40-3600", 1100, 1045, 3600, 7030, 40, 2, 2900, 2900),
    Blower("CHPT-44-50-4600", 1100, 1035, 4600, 8400, 50, 2, 2900, 2900),
    Blower("CHPT-44-60-5500", 1100, 1030, 5500, None, 60, 2, 2900, 2900),
    # --- CHPT-48 : 1200 mmwc total (starts at 5 HP) ----------------------
    Blower("CHPT-48-5-250", 1200, 1180, 250, 430, 5, 2, 2900, 2900),
    Blower("CHPT-48-7.5-400", 1200, 1178, 400, 690, 7.5, 2, 2900, 2900),
    Blower("CHPT-48-10-600", 1200, 1170, 600, 1030, 10, 2, 2900, 2900),
    Blower("CHPT-48-15-1000", 1200, 1165, 1000, 1715, 15, 2, 2900, 2900),
    Blower("CHPT-48-20-1400", 1200, 1160, 1400, 2400, 20, 2, 2900, 2900),
    Blower("CHPT-48-25-1800", 1200, 1155, 1800, 3090, 25, 2, 2900, 2900),
    Blower("CHPT-48-30-2300", 1200, 1150, 2300, 3945, 30, 2, 2900, 2900),
    Blower("CHPT-48-40-3200", 1200, 1145, 3200, 5490, 40, 2, 2900, 2900),
    Blower("CHPT-48-50-4100", 1200, 1140, 4100, 7030, 50, 2, 2900, 2900),
    Blower("CHPT-48-60-4900", 1200, 1135, 4900, 8400, 60, 2, 2900, 2900),
]

# model -> row, for an exact catalogue lookup (e.g. resolving a historical
# offer's blower model back to its full specification).
_BY_MODEL: dict[str, Blower] = {b.model: b for b in _CHART}


def chart() -> list[Blower]:
    """The full catalogue (a copy, so callers cannot mutate the source data)."""
    return list(_CHART)


def by_model(model: str) -> Optional[Blower]:
    """Exact catalogue row for a model code, or None if not in the chart."""
    return _BY_MODEL.get((model or "").strip().upper())


def select_blower(required_cfm: float,
                  static_pressure_mmwc: float = BOOTH_STATIC_PRESSURE_MMWC
                  ) -> Optional[Blower]:
    """Smallest catalogue blower that delivers `required_cfm` at or above
    `static_pressure_mmwc`.

    Selection rule (deterministic, no interpolation): keep every model whose
    rated CFM covers the duty AND whose STATIC pressure meets the resistance,
    then take the lowest motor HP; ties break on the lowest CFM (least
    oversizing) and finally on model code so the result is stable.

    Static — not total — pressure is the comparison, because static is what is
    available to overcome filter and duct resistance.

    Returns None when no catalogue model covers the duty; the caller must then
    emit a TBD rather than inventing a blower.
    """
    if not isinstance(required_cfm, (int, float)) or required_cfm <= 0:
        return None
    sp = static_pressure_mmwc if isinstance(static_pressure_mmwc, (int, float)) else 0.0

    fits = [b for b in _CHART if b.cfm >= required_cfm and b.static_pressure_mmwc >= sp]
    if not fits:
        return None
    return min(fits, key=lambda b: (b.motor_hp, b.cfm, b.model))


def series_of(model: str) -> str:
    """Series (pressure class) prefix of a model code: 'CLP-4-10-9000' -> 'CLP-4'.
    The code is <SERIES>-<HP>-<CFM> where SERIES itself contains one hyphen."""
    parts = (model or "").split("-")
    return "-".join(parts[:2]) if len(parts) >= 2 else (model or "")


def select_in_series(required_cfm: float, series: str) -> Optional[Blower]:
    """Smallest model WITHIN one pressure class that covers `required_cfm`.
    Returns None when the duty exceeds the series' largest machine."""
    fits = [b for b in _CHART
            if series_of(b.model) == series and b.cfm >= required_cfm]
    if not fits:
        return None
    return min(fits, key=lambda b: (b.cfm, b.motor_hp, b.model))


def select_booth_blower(required_cfm: float) -> Optional[Blower]:
    """Exhaust blower for a paint booth / paint-shop enclosure.

    Selects within `PAINT_BOOTH_SERIES` — the family the client's own costed BOM
    uses — so booths scale coherently through one product range instead of
    hopping pressure classes as the fan curve droops. Falls back to the generic
    duty-based search only when the requirement exceeds that series' largest
    machine, and returns None if nothing in the catalogue covers it (-> TBD).
    """
    return (select_in_series(required_cfm, PAINT_BOOTH_SERIES)
            or select_blower(required_cfm, BOOTH_STATIC_PRESSURE_MMWC))


def select_booth_blower_set(required_cfm: float) -> tuple[Optional[Blower], int]:
    """Booth exhaust blower AND how many units are needed: `(blower, qty)`.

    One machine whenever the catalogue has one big enough. When the duty exceeds
    even the largest machine in the booth series, the load is split across
    several of that largest model — real practice for a big booth, and still
    entirely catalogue-backed. Returns `(None, 0)` if nothing applies, so the
    caller emits a TBD instead of a number.
    """
    single = select_booth_blower(required_cfm)
    if single is not None:
        return single, 1

    in_series = [b for b in _CHART if series_of(b.model) == PAINT_BOOTH_SERIES]
    if not in_series or not isinstance(required_cfm, (int, float)) or required_cfm <= 0:
        return None, 0
    largest = max(in_series, key=lambda b: b.cfm)
    qty = -(-int(required_cfm) // largest.cfm)      # ceil division
    return largest, qty
