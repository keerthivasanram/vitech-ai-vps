"""Golden snapshot / regression oracle for the spec resolver.

Captures the DETERMINISTIC output of the engine so the resolver refactor can be
proven byte-identical. Covers BOTH policies:
  * ATS (data mode)        -> full spec_writeup + structured surface
  * Consulting (knowledge) -> the requirement-echo surface the LLM narrates
Run with `--capture` to write the golden file, and with no args to compare.
"""
import hashlib
import json
import sys

from app.analysis import analyze
from app.prompt import spec_writeup
from app.resolver import ATS, CONSULTING, resolve
from app.retriever import retrieve
from app.schema import QueryUnderstanding

GOLDEN = "tests_golden.json"

# Representative ATS requirements across the rule-backed categories.
CASES = [
    ("wet_scrubber", {"air_volume_cfm": 735, "air_volume_cmh": 1250, "tower_diameter_mm": 700, "qty": 1},
     "wet scrubber for 735 cfm 700mm tower 1 no"),
    ("wet_scrubber", {"air_volume_cfm": 800, "air_volume_cmh": 1359, "tower_diameter_mm": 750, "qty": 4},
     "wet scrubber for 800 cfm 750mm tower 4 nos"),
    ("wet_scrubber", {"air_volume_cfm": 3000, "air_volume_cmh": 5097, "tower_diameter_mm": 1000, "qty": 2},
     "wet scrubber for 3000 cfm 1000mm tower 2 nos"),
    ("wet_scrubber", {"air_volume_cfm": 2300, "air_volume_cmh": 4000, "tower_diameter_mm": 1000, "operating_temp": "80C", "qty": 1},
     "wet scrubber for 2300 cfm 1000mm tower 80C 1 no"),
    ("paint_booth", {"length_m": 10, "width_m": 6, "height_m": 4, "paint_type": "powder"},
     "paint booth 10 x 6 powder"),
    ("paint_booth", {"length_m": 3, "width_m": 3, "height_m": 2.35, "paint_type": "liquid"},
     "paint booth 3 x 3 liquid"),
    ("paint_booth", {"length_m": 5, "width_m": 3, "height_m": 4, "paint_type": "liquid"},
     "paint booth 5 x 3 x 4 liquid"),
]

# Consulting (knowledge) requirements — incl. a no-rule category (hot_air_oven)
# to lock the category-agnostic requirement echo.
KNOWLEDGE_CASES = [
    ("wet_scrubber", {"air_volume_cfm": 800, "tower_diameter_mm": 750, "qty": 4},
     "wet scrubber for 800 cfm 750mm tower 4 nos"),
    ("paint_booth", {"length_m": 10, "width_m": 6, "height_m": 4, "paint_type": "powder"},
     "paint booth 10 x 6 powder"),
    ("hot_air_oven", {"operating_temp": "200C", "batch_kg": 500},
     "hot air oven 200C 500kg batch"),
]


def _run(cat, params, question):
    u = QueryUnderstanding(intent="specification", category=cat, parameters=dict(params), source="regex")
    hits = retrieve(question, top_k=10, where={"category": cat})
    a = resolve(question, hits, u, ATS)
    a["spec_mode"] = "data"
    writeup = spec_writeup(a)
    # keep the structured surface that the writeup + UI depend on
    surface = {
        "spec_writeup": writeup,
        "spec_writeup_sha": hashlib.sha256(writeup.encode("utf-8")).hexdigest(),
        "nearest_match": a.get("nearest_match"),
        "confidence_pct": a.get("confidence_pct"),
        "confidence_label": a.get("confidence_label"),
        "decision_origin": a.get("decision_origin"),
        "n_ledger": len(a.get("ledger") or []),
        "n_validation": len(a.get("validation") or []),
        "technical": [(t["label"], t["value"], t["origin"]) for t in a.get("technical_details", [])],
    }
    return surface


def _run_knowledge(cat, params, question):
    """Deterministic surface of the Consulting/knowledge path (LLM prose aside)."""
    u = QueryUnderstanding(intent="specification", category=cat, parameters=dict(params), source="regex")
    k = resolve(question, [], u, CONSULTING)
    surface = {
        "spec_mode": k.get("spec_mode"),
        "category": k.get("category"),
        "category_label": k.get("category_label"),
        "n_technical": len(k.get("technical_details") or []),
        "n_similar": len(k.get("similar_offers") or []),
        "nearest_match": k.get("nearest_match"),
        "exact_match": k.get("exact_match"),
        "confidence_pct": k.get("confidence_pct"),
        "given_data": [(g["label"], g["value"]) for g in k.get("given_data", [])],
    }
    surface["sha"] = hashlib.sha256(
        json.dumps(surface, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return surface


def capture():
    out = {question: _run(cat, params, question) for cat, params, question in CASES}
    for cat, params, question in KNOWLEDGE_CASES:
        out["K:" + question] = _run_knowledge(cat, params, question)
    with open(GOLDEN, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"captured {len(CASES)} ATS + {len(KNOWLEDGE_CASES)} knowledge cases -> {GOLDEN}")


def compare():
    with open(GOLDEN, encoding="utf-8") as f:
        gold = json.load(f)
    fails = 0
    for cat, params, question in CASES:
        cur = _run(cat, params, question)
        exp = gold.get(question, {})
        if cur["spec_writeup_sha"] != exp.get("spec_writeup_sha"):
            fails += 1
            print(f"XX  [ATS] {question}\n    writeup sha differs")
            g = exp.get("spec_writeup", "").splitlines()
            c = cur["spec_writeup"].splitlines()
            for i in range(max(len(g), len(c))):
                gv = g[i] if i < len(g) else "<none>"
                cv = c[i] if i < len(c) else "<none>"
                if gv != cv:
                    print(f"    L{i}: - {gv}\n         + {cv}")
        else:
            print(f"OK  [ATS] {question}  (conf {cur['confidence_pct']}%, {cur['n_ledger']} ledger)")
    for cat, params, question in KNOWLEDGE_CASES:
        cur = _run_knowledge(cat, params, question)
        exp = gold.get("K:" + question, {})
        if cur["sha"] != exp.get("sha"):
            fails += 1
            print(f"XX  [KNOW] {question}\n    - {exp}\n    + {cur}")
        else:
            print(f"OK  [KNOW] {question}  (mode {cur['spec_mode']}, {cur['n_technical']} rows, "
                  f"{len(cur['given_data'])} given)")
    print("ALL GOLDEN PASS" if fails == 0 else f"{fails} GOLDEN FAIL")
    return fails


if __name__ == "__main__":
    if "--capture" in sys.argv:
        capture()
    else:
        sys.exit(1 if compare() else 0)
