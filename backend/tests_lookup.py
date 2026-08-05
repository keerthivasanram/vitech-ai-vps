"""Regression tests for project lookup (client identity vs. structured attrs).

Guards the fix for the "0.9 x 0.92 x 2 water wall paint booth returned 4
unrelated offers" bug: entity_hits must key on client identity (not equipment
words in titles), and a dimension query must resolve to the one matching project
via structured_project_hits. Runs against the real offers collection.
    .venv/bin/python tests_lookup.py
"""
import sys

from app.retriever import entity_hits, project_hits, structured_project_hits

_fail = 0


def check(name, cond, got=None):
    global _fail
    print(f"{'OK ' if cond else 'FAIL'}  {name}" + ("" if cond else f"   got={got}"))
    if not cond:
        _fail += 1


def ids(hits):
    return [h["id"] for h in hits]


# 1) dimension query -> exactly the Yonex water-wall booth, nothing else
dim = project_hits("For which client we worked for 0.9 x 0.92 x 2 m water wall paint booth?")
check("dimension query resolves to a single project", len(dim) == 1, ids(dim))
check("dimension query resolves to the Yonex paint booth", ids(dim) == ["OFF-YONEX-PB-367"], ids(dim))

# 2) equipment words in the query must NOT pull unrelated offers by title
#    (Armstrong is a CONVEYOR, Eco Chimneys is BLASTING — both had 'paint' in title)
bad = {"OFF-ARMSTRONG-CONV-395", "OFF-ECOCHIMNEYS-BLAST-072409R4", "OFF-BAKERHUGHES-PB-275R3A"}
check("no unrelated equipment-word matches leak in", not (set(ids(dim)) & bad), ids(dim))

# 3) named client lookup still works, and keys on identity
arm = project_hits("Tell me about Armstrong")
check("named client 'Armstrong' returns Armstrong record(s)",
      bool(arm) and all("ARMSTRONG" in h["id"] for h in arm), ids(arm))

# 4) 'Who is Yonex?' returns Yonex's records (both offers)
yon = project_hits("Who is Yonex?")
check("named client 'Yonex' returns Yonex records", bool(yon) and all("YONEX" in h["id"] for h in yon), ids(yon))

# 5) entity_hits must not match on title equipment words alone
#    'paint booth' names no client -> entity_hits should be empty (structured handles it)
check("entity_hits ignores bare equipment words", entity_hits("water wall paint booth") == [],
      ids(entity_hits("water wall paint booth")))

# 6) structured lookup needs a numeric attribute; the equipment type SCOPES the
#    search but must not gate it (client report 2026-08-01: a dimensions-only
#    question answered "no match", then fell through to relevance and returned
#    unrelated projects).
check("structured lookup empty without equipment+attrs", structured_project_hits("hello there") == [])

_LABELLED = "is there any client we worked with Length: 0.9 meters Width: 0.92 meters Height: 2 meters"
check("labelled dimensions with NO equipment word find the exact project",
      ids(structured_project_hits(_LABELLED)) == ["OFF-YONEX-PB-367"],
      ids(structured_project_hits(_LABELLED)))
check("labelled dimensions in mm resolve identically",
      ids(structured_project_hits("Length: 900 mm Width: 920 mm Height: 2000 mm")) == ["OFF-YONEX-PB-367"],
      ids(structured_project_hits("Length: 900 mm Width: 920 mm Height: 2000 mm")))
# The VALUE-FIRST phrasing ("0.9 m long") is at least as common as the
# label-first one, and used to be read off by one: the label-first pattern
# found "long", scanned forward and took the NEXT dimension's number, so
# "0.9 m long 0.92 m wide 2 m high" silently became length 0.92 / width 2 /
# no height. A wrong envelope draws a wrong GA, so it is pinned here.
from app.understand import _labelled_dims
check("value-first dimensions parse in order, not shifted by one",
      _labelled_dims("dust collector 3.9 m long 4 m wide 8.3 m high")
      == {"length_m": 3.9, "width_m": 4.0, "height_m": 8.3},
      _labelled_dims("dust collector 3.9 m long 4 m wide 8.3 m high"))
check("label-first dimensions are unaffected by the value-first support",
      _labelled_dims("length 900mm width 920mm height 2000mm")
      == {"length_m": 0.9, "width_m": 0.92, "height_m": 2.0},
      _labelled_dims("length 900mm width 920mm height 2000mm"))
_VF = "any client with 0.9 m long 0.92 m wide 2 m high booth"
check("a value-first dimensioned question finds the same exact project",
      ids(structured_project_hits(_VF)) == ["OFF-YONEX-PB-367"],
      ids(structured_project_hits(_VF)))

_WEAK = "which client did we do a 0.9 x 0.92 x 2 booth for"
check("a weakly-classified equipment word still yields the exact match only",
      ids(structured_project_hits(_WEAK)) == ["OFF-YONEX-PB-367"], ids(structured_project_hits(_WEAK)))
# Assert on the EXACT-match path itself: structured_project_hits deliberately
# falls back to a relevance search when nothing matches exactly, so a stray
# number must fail to produce an exact hit rather than fail to return anything.
from app.retriever import _exact_dimension_hit
check("a single stray number cannot pick an exact project",
      _exact_dimension_hit("the height is 3") == [],
      ids(_exact_dimension_hit("the height is 3")))
check("a lone capacity figure cannot pick an exact project without a category",
      _exact_dimension_hit("800") == [], ids(_exact_dimension_hit("800")))

# 7) equipment named but no parseable dimensions -> LIST the category's clients,
#    never claim we have none (the "hot air oven U-type 6.5L -> no clients" bug)
oven = project_hits("hot air oven conveyorised U-type 6.5L for this specification are we worked for any clients")
check("hot air oven query returns the category's real clients", len(oven) >= 2, ids(oven))
check("hot air oven query includes both known oven offers",
      {"OFF-ZFWABCO-OVEN-424R4", "OFF-SURFACE-OVEN-356R3"}.issubset(set(ids(oven))), ids(oven))
listq = project_hits("list clients we worked on hot air oven")
check("'list clients ... hot air oven' lists oven clients", len(listq) >= 2, ids(listq))

# 8) CONTENT relevance: "paint booth conveyor improvement" must find Armstrong
#    (category=conveyor) by what the project IS, and NOT dump paint booths — even
#    though the words "paint booth" classify the query as paint_booth.
conv = project_hits("is that we have any client worke for paint booth conveyor improvement")
check("content relevance surfaces Armstrong first", conv and conv[0]["id"] == "OFF-ARMSTRONG-CONV-395", ids(conv))
check("content relevance does not dump unrelated paint booths", len(conv) <= 3, ids(conv))

# 9) CORRECTIONS. A follow-up ("change the length to 8m") reaches the engine as
#    ONE restated requirement, and every extractor here uses .search(), which
#    takes the FIRST match — so the correction was parsed away and the drawing
#    came back unchanged. The value stated AFTER a correction phrase must win,
#    and a parameter the correction does not mention must survive untouched.
from app.understand import understand           # noqa: E402


def _dims(q):
    p = dict(understand(q).parameters)
    return {k: p.get(k) for k in ("length_m", "width_m", "height_m")}


BASE = "paint booth 5m x 3m x 4m liquid"
check("an ordinary requirement is parsed exactly as before",
      _dims(BASE) == {"length_m": 5.0, "width_m": 3.0, "height_m": 4.0}, _dims(BASE))
check("'changed to A x B x C' supersedes the original triple",
      _dims(f"{BASE} changed to 6m x 3m x 4m")["length_m"] == 6.0,
      _dims(f"{BASE} changed to 6m x 3m x 4m"))
check("'make it 8m long' corrects the ONE dimension it names",
      _dims(f"{BASE}, make it 8m long") == {"length_m": 8.0, "width_m": 3.0, "height_m": 4.0},
      _dims(f"{BASE}, make it 8m long"))
check("'change the height to 6m' corrects the field it names",
      _dims(f"{BASE} change the height to 6m")["height_m"] == 6.0,
      _dims(f"{BASE} change the height to 6m"))
check("a partial correction keeps the dimensions it does not mention",
      _dims(f"{BASE} now 7m long 4m wide") == {"length_m": 7.0, "width_m": 4.0, "height_m": 4.0},
      _dims(f"{BASE} now 7m long 4m wide"))
check("a correction word with NO value changes nothing",
      _dims(f"{BASE} handled now by the day shift")["length_m"] == 5.0,
      _dims(f"{BASE} handled now by the day shift"))

_scrub = dict(understand("wet scrubber 800 cfm 750mm tower change to 1200 cfm").parameters)
check("a corrected airflow supersedes the original",
      _scrub.get("air_volume_cfm") == 1200.0, _scrub.get("air_volume_cfm"))
check("correcting one unit recomputes its partner instead of leaving them disagreeing",
      _scrub.get("air_volume_cmh") == round(1200 * 1.699), _scrub.get("air_volume_cmh"))
check("a correction leaves unrelated parameters alone",
      _scrub.get("tower_diameter_mm") == 750.0, _scrub.get("tower_diameter_mm"))

# 10) A value the CLIENT STATED must never be printed as an engineering gap.
#     Asked for 9000 m3/h, the spec printed "Air volume (m3/h): To be determined"
#     while showing a DERIVED cfm figure as client-given.
from app.catalog import get_profile                       # noqa: E402
from app.spec_template import apply_template              # noqa: E402

_rows = apply_template(get_profile("dust_collector"), [], offers=[],
                       params={"air_volume_cmh": 9000})
_air = next((r for r in _rows if r["label"] == "Air volume (m3/h)"), None)
check("a client-stated value fills its template field instead of becoming TBD",
      _air is not None and _air["value"] == "9000", _air and _air["value"])
check("and it is attributed to the client, not to history",
      _air is not None and _air["origin"] == "given", _air and _air["origin"])

print()
if _fail:
    print(f"{_fail} LOOKUP TEST(S) FAILED")
    sys.exit(1)
print("ALL LOOKUP TESTS PASS")
