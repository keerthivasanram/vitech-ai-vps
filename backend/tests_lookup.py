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

# 6) structured lookup needs a confident equipment type + a numeric attribute
check("structured lookup empty without equipment+attrs", structured_project_hits("hello there") == [])

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

print()
if _fail:
    print(f"{_fail} LOOKUP TEST(S) FAILED")
    sys.exit(1)
print("ALL LOOKUP TESTS PASS")
