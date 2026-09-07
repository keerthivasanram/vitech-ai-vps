#!/usr/bin/env python3
"""Give the Quotation Agent LESS to summarise, so it stops inventing a cost sheet.

THE DEFECT THIS FIXES, observed live. Asked "why is that the price? show me the
pricing basis and how the margin was fixed", the Quotation Agent replied with a
cost break-up of its own invention:

    Material costs: Rs 8,00,000   Labor costs: Rs 4,00,000
    Overheads: Rs 2,00,000        Profit margin: 6%

None of those four figures appears anywhere in the tool response. The tool had
returned a complete, correct `pricing_basis_markdown` - 1,886 characters of
Vitech's own rate card and Combine sheet - and the model wrote past it. This is
fabricated MONEY reaching a user on a quotation, which is the most damaging
thing this platform can emit.

WHY THIS IS NOT A PROMPT FIX. RULE 2 already says every price comes from a tool
and RULE 5 already says to print `pricing_basis_markdown` verbatim and "never
invent a margin, cost, rate or percentage". The rules are correct and were
ignored. The project has been here twice before - the `lookup_markdown` leak and
the Drawing Agent's 16 kB SVG - and both times the fix that held was structural:
STRIP THE STRUCTURED FIELDS SO THERE IS NOTHING LEFT TO SUMMARISE. A model
handed a nested `pricing_intelligence` tree full of amounts will summarise it;
handed only the finished markdown, it prints the markdown.

WHAT IS REMOVED, and what must NOT be. Removed: `pricing_intelligence` (the
direct cause - it carries every cost element as raw numbers), the nested `price`
dict, `scope`, `given_data`, `terms`, `basis_offers` and `headline`. KEPT,
because the two agents' prompts name them by field: `quotation_markdown`
(RULE 4), `pricing_basis_markdown` and `pricing_rationale` (RULE 5),
`price_display` / `price_range_display` (RULE 2 and the compare flow), and
`unit_price_display`, which is lifted out of the `price` dict before it goes so
that the field survives its container.

The tool row is SHARED with the Engineering Agent. Nothing removed here is
named in either prompt, and the Engineering Agent's own "print the _display
strings verbatim" bullet is served by the fields that remain.

Idempotent: re-running against an already-trimmed row changes nothing.
"""
import re
import subprocess
import sys

REPO = "/workspace/vitech-ai-vps"
TOOL = "generate_quotation"
BASIS_TOOL = "explain_pricing"

# Lifted out before its container is dropped - a prompt names this field.
TRIM = '''
const data = await res.json();
// A MODEL SUMMARISES WHATEVER IT IS GIVEN. See the module docstring: handed the
// whole pricing_intelligence tree, llama3.1 wrote its own cost sheet. It now
// gets the finished markdown the prompt tells it to print, and nothing that
// invites a second opinion about the money.
if (data && data.price && data.price.unit_price_display) {
    data.unit_price_display = data.price.unit_price_display;
}
['pricing_intelligence', 'price', 'scope', 'given_data', 'terms',
 'basis_offers', 'headline'].forEach(function (k) { delete data[k]; });
return JSON.stringify(data);'''


def dsn() -> str:
    env = {}
    with open(f"{REPO}/.env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return (f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
            f"@localhost:5432/{env['POSTGRES_DB']}")


DSN = dsn()


def psql(sql: str) -> str:
    r = subprocess.run(["psql", DSN, "-tAc", sql], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr)
    return r.stdout


# `explain_pricing` hits the SAME endpoint and returns exactly ONE document.
# That is the whole point of it: trimming `pricing_intelligence` off
# `generate_quotation` stopped the model inventing a cost sheet out of the
# numbers, and it then invented one anyway out of nothing, because it still had
# two markdown documents in front of it and a question that matched neither
# cleanly. A tool that can return only the basis cannot be answered with a
# summary of something else.
BASIS_TRIM = """
const data = await res.json();
// ONE TOOL, ONE DOCUMENT. Everything except the finished pricing-basis block is
// removed, so there is nothing here to summarise, compare or re-total. See the
// module docstring for the fabricated cost sheet that made this necessary.
return JSON.stringify({
    ok: data.ok,
    pricing_basis_markdown: data.pricing_basis_markdown,
    pricing_rationale: data.pricing_rationale,
    need_inputs: data.need_inputs,
    note: data.note
});"""


def _patch(tool: str, trim: str, marker: str) -> int:
    func = psql(f"SELECT func FROM tool WHERE name='{tool}';")
    if not func.strip():
        print(f"no tool row named {tool}", file=sys.stderr)
        return 1
    if marker in func:
        print(f"{tool} already trimmed - nothing to do")
        return 0
    if "return JSON.stringify(await res.json());" not in func:
        print(f"the {tool} body is not the shape this script knows how to "
              "rewrite; inspect it by hand rather than letting this guess:\n" + func,
              file=sys.stderr)
        return 1
    new = func.replace("return JSON.stringify(await res.json());", trim.strip())
    subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1", "-c",
                    "UPDATE tool SET func = $trim$" + new + "$trim$ "
                    f"WHERE name='{tool}';"], check=True)
    print(f"  {tool} trimmed")
    return 0


def main() -> int:
    rc = _patch(TOOL, TRIM, "delete data[k]")
    rc |= _patch(BASIS_TOOL, BASIS_TRIM, "pricing_basis_markdown: data.pricing_basis_markdown")
    if rc == 0:
        print("RESTART FLOWISE for the change to take effect, then re-verify "
              "RULE 4 (quotation verbatim) and RULE 5 (pricing basis verbatim).")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
