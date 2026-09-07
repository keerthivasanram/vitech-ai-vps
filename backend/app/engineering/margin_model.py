"""Vitech's OWN quotation margin model - the `Combine` sheet, as data.

WHAT THIS REPLACES AND WHY IT MATTERS. The cost-plus signal has always closed
with a flat bought-out ALLOWANCE (15% of works cost) and a seeded 20% margin,
and on a paint booth that diverged from the historical price by -57%. The
reason was never the rates: bought-outs are 76.5% of a booth (blower, control
panel, field wiring, LED, view glass), so representing them as a percentage of
the steel is representing the tail as a fraction of the dog. `booth_cost` now
prices them line by line at Vitech's own unit prices, and this module carries
the commercial layer that sits on top of it.

EVERY NUMBER HERE IS THE CLIENT'S. The multipliers, the three fixed adders and
the discount are transcribed from their `Combine` sheet, and the worked example
below is theirs and reproduces to the rupee. Nothing is averaged, rounded to
something tidier, or extended to a line they did not price that way.

    Booth + blower + panel   649,264  x 1.40  =   908,970
    Exhaust duct             105,000  x 1.26  =   132,300
    Design & contingency                          25,000
    Packing & forwarding                          11,000
    E & C                                         65,000
                                              -----------
    subtotal                                   1,142,270
    less 10% on the booth line                   -90,897
                                              -----------
    final                                      1,051,373

THEIR STATED PROFIT DOES NOT RECONCILE WITH THEIR OWN ARITHMETIC, and it is
recorded rather than quietly matched. The sheet writes the profit as
`final - works_total` = 297,109 and annotates it **27%**, but 297,109 on a
final of 1,051,373 is 28.3%, on the 1,142,270 subtotal 26.0%, and on the
754,264 works cost 39.4%. No base gives 27%. `profit_pct` here is stated
explicitly ON THE FINAL SELLING PRICE so the reader knows which of those they
are looking at; the 1-point gap is the same class of thing as DQ-8 and is
listed with the other queries.

STILL OPEN - DQ-7. What SELECTS the multiplier is not answered anywhere in the
workbooks: the booth sheet applies 1.40/1.26 and the cyclone sheet is a scratch
pad of 1.35/1.25/1.17 beside a typed total. So the multiplier is an INPUT here
with the client's booth figure as the default, and every result says which was
used. That is the difference between using a client model and guessing one.
"""
from typing import NamedTuple, Optional

# --- the Combine sheet's own constants -------------------------------------
BOOTH_MULTIPLIER = 1.40          # booth + blower + control panel
DUCT_MULTIPLIER = 1.26           # exhaust ducting
DESIGN_CONTINGENCY = 25_000.0    # fixed
PACKING_FORWARDING = 11_000.0    # fixed
ERECTION_COMMISSIONING = 65_000.0
BOOTH_DISCOUNT_PCT = 0.10        # applied to the BOOTH selling line only

# Transport is the customer's scope on their sheet, so it is not a line here.
FIXED_ADDERS = (("Design & contingency", DESIGN_CONTINGENCY),
                ("Packing & forwarding", PACKING_FORWARDING),
                ("Erection & commissioning", ERECTION_COMMISSIONING))


class Selling(NamedTuple):
    """A selling price and the whole build-up that produced it."""
    final: float
    subtotal: float
    discount: float
    profit: float
    profit_pct: Optional[float]
    lines: tuple            # (label, works, multiplier, selling)
    basis: str


def booth_selling_price(booth_works_cost: float,
                        duct_works_cost: float = 0.0, *,
                        booth_multiplier: float = BOOTH_MULTIPLIER,
                        duct_multiplier: float = DUCT_MULTIPLIER,
                        discount_pct: float = BOOTH_DISCOUNT_PCT) -> Selling:
    """Works cost -> selling price, by the client's own `Combine` arithmetic.

    `duct_works_cost` is separate because the sheet marks it up differently; a
    quotation with no ducting in scope simply passes 0 and the line disappears
    rather than being folded into the booth at the booth's multiplier.
    """
    booth_selling = float(booth_works_cost) * booth_multiplier
    lines = [("Booth, blower and control panel", float(booth_works_cost),
              booth_multiplier, booth_selling)]
    duct_selling = 0.0
    if duct_works_cost:
        duct_selling = float(duct_works_cost) * duct_multiplier
        lines.append(("Exhaust ducting", float(duct_works_cost),
                      duct_multiplier, duct_selling))
    for label, amount in FIXED_ADDERS:
        lines.append((label, 0.0, None, amount))

    subtotal = sum(line[3] for line in lines)
    # The sheet discounts the BOOTH line, not the subtotal - discounting the
    # fixed adders as well would give away the design and erection charges.
    discount = booth_selling * float(discount_pct)
    final = subtotal - discount

    works_total = float(booth_works_cost) + float(duct_works_cost)
    profit = final - works_total
    profit_pct = (profit / final * 100.0) if final else None

    basis = (f"Vitech Combine sheet: booth x{booth_multiplier:g}"
             + (f", duct x{duct_multiplier:g}" if duct_works_cost else "")
             + f", fixed adders {int(sum(a for _, a in FIXED_ADDERS)):,}"
             + f", less {round(discount_pct * 100)}% on the booth line"
             + " (multiplier selection is DQ-7, unconfirmed)")
    return Selling(final, subtotal, discount, profit, profit_pct,
                   tuple(lines), basis)
