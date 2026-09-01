"""VOC emission rate and the lower-explosive-limit safety gate.

Source: the client's own workbook `Paint shop VOC calculation.xlsx`
(delivered 2026-09-01), transcribed in `docs/client-calculation-sheets.md` §3.
Every formula and every limit below is the client's; nothing is inferred.

    mVOC (kg/hr) = paint consumption (l/hr) x density (kg/l) x VOC% / 100
    C (g/m3)     = mVOC (g/hr) / exhaust airflow (m3/h)
    C (mg/m3)    = C (g/m3) x 1000

THIS MODULE PRODUCES A VERDICT, NOT A SPEC ROW. A solvent concentration is a
safety question — the design either keeps the extracted air below the limit or
it does not — so the result belongs with the release checks, beside the other
pass/fail assessments, rather than as another number in a technical table.

On the LEL: the workbook states a typical solvent LEL of 1.2 % BY VOLUME and a
design rule of "stay under 25 % of LEL". Converting a volume percentage into
mg/m3 needs the solvent's molecular weight, which the workbook does not give and
which is not assumed here. So `percent_lel` is returned ONLY when the caller
supplies that solvent's LEL in mg/m3; the verdict itself rests on the workbook's
own practical limit of 1000 mg/m3, which needs no such conversion.
"""
from typing import NamedTuple, Optional

from . import standards_service as std

# --- the client's stated limits -------------------------------------------
# "Practical: < 1000 mg/m3" — the rule the verdict is decided on.
PRACTICAL_LIMIT_MG_M3 = 1000.0

# "LEL of typical solvent ~ 1.2 % by volume", "maintain < 25 % of LEL".
# Held as data because they are the client's stated basis; they are used for a
# reported margin only when a solvent-specific LEL in mg/m3 is supplied.
TYPICAL_SOLVENT_LEL_VOL_PCT = 1.2
MAX_FRACTION_OF_LEL = 0.25

PASS = "pass"
FAIL = "fail"


class VOCResult(NamedTuple):
    """The VOC calculation and its safety verdict.

    Any field may be None when the input it needs was not supplied — an honest
    gap the caller reports as unknown, never a filled-in guess.
    """
    voc_kg_hr: Optional[float]
    voc_g_hr: Optional[float]
    concentration_g_m3: Optional[float]
    concentration_mg_m3: Optional[float]
    limit_mg_m3: float
    verdict: Optional[str]              # PASS / FAIL, None when not computable
    reason: str
    percent_lel: Optional[float] = None  # only when the solvent LEL is supplied
    required_airflow_cmh: Optional[float] = None
    trail: tuple = ()                    # (name, value, formula, standard)


def voc_mass_rate_kg_hr(paint_consumption_l_hr: float,
                        density_kg_l: float,
                        voc_percent: float) -> float:
    """Solvent mass entering the extracted air, kg/hr."""
    return float(paint_consumption_l_hr) * float(density_kg_l) * (float(voc_percent) / 100.0)


def concentration_mg_m3(voc_kg_hr: float, airflow_cmh: float) -> float:
    """Solvent concentration in the extracted air, mg/m3."""
    return (voc_kg_hr * 1000.0) / float(airflow_cmh) * 1000.0


def required_airflow_cmh(voc_kg_hr: float,
                         limit_mg_m3: float = PRACTICAL_LIMIT_MG_M3) -> float:
    """The airflow that would hold this solvent load at the limit, m3/h.

    Straight algebraic inversion of the client's own formula — no new
    engineering — so a failing design can say what would fix it instead of only
    that it fails."""
    return (voc_kg_hr * 1000.0 * 1000.0) / float(limit_mg_m3)


def assess_voc(paint_consumption_l_hr: Optional[float],
               voc_percent: Optional[float],
               density_kg_l: Optional[float],
               airflow_cmh: Optional[float],
               limit_mg_m3: float = PRACTICAL_LIMIT_MG_M3,
               solvent_lel_mg_m3: Optional[float] = None) -> VOCResult:
    """Run the client's VOC calculation and return its safety verdict.

    Returns a result with `verdict=None` and a reason naming what is missing
    when any input is absent — an unanswered safety question is reported as
    unanswered, never as a pass.
    """
    missing = [name for name, v in (("paint consumption (l/hr)", paint_consumption_l_hr),
                                    ("VOC content (%)", voc_percent),
                                    ("paint density (kg/l)", density_kg_l),
                                    ("exhaust airflow (m3/h)", airflow_cmh))
               if v is None]
    if missing:
        return VOCResult(None, None, None, None, limit_mg_m3, None,
                         "not assessed: " + ", ".join(missing) + " not supplied")
    if float(airflow_cmh) <= 0:
        return VOCResult(None, None, None, None, limit_mg_m3, None,
                         "not assessed: exhaust airflow must be greater than zero")

    kg_hr = voc_mass_rate_kg_hr(paint_consumption_l_hr, density_kg_l, voc_percent)
    g_hr = kg_hr * 1000.0
    c_g = g_hr / float(airflow_cmh)
    c_mg = c_g * 1000.0

    trail = (
        ("VOC mass rate", f"{kg_hr:g} kg/hr",
         f"{float(paint_consumption_l_hr):g} l/hr x {float(density_kg_l):g} kg/l "
         f"x {float(voc_percent):g}%", std.CLIENT_VOC_CALC),
        ("VOC concentration", f"{round(c_mg)} mg/m3",
         f"{g_hr:g} g/hr / {float(airflow_cmh):g} m3/h x 1000", std.CLIENT_VOC_CALC),
    )

    ok = c_mg < limit_mg_m3
    if ok:
        reason = (f"{round(c_mg)} mg/m3 is below the {limit_mg_m3:g} mg/m3 design limit")
        needed = None
    else:
        needed = required_airflow_cmh(kg_hr, limit_mg_m3)
        reason = (f"{round(c_mg)} mg/m3 exceeds the {limit_mg_m3:g} mg/m3 design limit; "
                  f"{round(needed)} m3/h would be required at this paint consumption")

    pct_lel = None
    if solvent_lel_mg_m3:
        pct_lel = c_mg / float(solvent_lel_mg_m3) * 100.0

    return VOCResult(kg_hr, g_hr, c_g, c_mg, limit_mg_m3,
                     PASS if ok else FAIL, reason, pct_lel, needed, trail)
