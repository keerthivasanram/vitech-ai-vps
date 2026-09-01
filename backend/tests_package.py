"""Guards for the engineering PACKAGE layer (`app/package/`).

The package composes documents rather than engineering anything, so these tests
pin the composition contract: every value lands in exactly one assumption
bucket, assumptions never leak into the specification, a reused value can be
traced to a real project and document, a missing artifact is reported rather
than faked, and the whole package is deterministic.

    .venv/bin/python tests_package.py
"""
import io
import sys
import zipfile

from app.package import assumptions, builder, dashboard, identifiers, review, traceability
from app.package import export as pkg_export

FAILS: list[str] = []


def check(cond, label):
    print(("OK   " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


# A resolved analysis covering every origin the buckets must separate.
ANALYSIS = {
    "category": "paint_booth", "category_label": "Paint Booth",
    "confidence_pct": 93, "confidence_label": "High", "completeness": 80,
    "given_data": [{"label": "Dimensions", "value": "5 x 3 x 4 m"}],
    "completeness_missing": ["Paint process"],
    "technical_details": [
        {"label": "Dimensions", "value": "5 x 3 x 4 m", "origin": "given",
         "source": None, "reason": "Client requirement (authoritative)."},
        {"label": "Exhaust airflow", "value": "15120 m3/h", "origin": "rule",
         "source": "Vitech booth-type standard", "reason": "Calculated: area x velocity."},
        {"label": "Exhaust blower", "value": "CLP-4-10-9000", "origin": "rule",
         "source": "Continental Thermal blower specification chart", "reason": "Catalogue selection."},
        {"label": "Construction", "value": "panels MS 1.6mm", "origin": "reused",
         "source": "OFF-CRI-PB-082406R4", "reason": "Reused from historical offer."},
        {"label": "Dry scrubber", "value": "To be determined", "origin": "tbd",
         "source": None, "reason": "Needs an engineering calculation."},
        {"label": "Material handling", "value": "To be confirmed with the customer",
         "origin": "customer_decision", "source": None, "reason": "Customer to confirm."},
    ],
    "validation": [],
    "release": {"status": "Customer Review Draft", "blockers": [],
                "gaps": ["Dry scrubber"], "questions": ["Material handling"],
                "summary": "Customer Review Draft: 1 field(s) still need input."},
}
HITS = [
    {"id": "OFF-CRI-PB-082406R4", "title": "CRI booth", "score": 0.643,
     "record": {"id": "OFF-CRI-PB-082406R4", "source_file": "CRI PUMP PB 10.10.24-R4.pdf"}},
]
GEOMETRY = {"envelope_mm": {"length": 5000, "width": 3000, "height": 4000},
            "envelope_source": "given", "ready": True}
DRAWING = {"svg": "<svg>x</svg>", "ready": True, "views": [{"key": "plan"}],
           "legend": [{"tag": "5", "description": "Exhaust blower CLP-4-10-9000 (1 no)"}]}
BOM = {"lines": [{"section": "Rotating plant", "item": "Exhaust blower",
                  "spec": "CLP-4-10-9000", "qty": 1, "unit": "no", "amount": 65000}],
       "totals": {"amount": 65000, "weight_kg": 1240}, "uncosted": [], "notes": []}
QUOTE = {"ref": "VT/Q/1", "scope": [{"item": "Exhaust blower", "spec": "CLP-4-10-9000"}],
         "price_display": "Rs 6,50,000"}

PKG = builder.build(ANALYSIS, question="paint booth 5m x 3m x 4m", hits=HITS,
                    drawing=DRAWING, bom=BOM, quotation=QUOTE, geometry=GEOMETRY,
                    spec_markdown="**ENGINEERING SPECIFICATION**\n\n| a | b |",
                    project="CRI Paint Shop", client="CRI Pumps")

# --- the package carries all seven documents -------------------------------
names = [m["document"] for m in PKG["manifest"]]
check(names == builder.DOCUMENTS, f"all seven documents are declared ({len(names)})")
check(all(m["revision"] == "0" for m in PKG["manifest"]),
      "every document carries its own revision")
check(PKG["manifest"][1]["confidence_pct"] == 93,
      "the specification carries its own confidence")

# --- assumptions: a partition, not a sample --------------------------------
counts = PKG["assumptions"]["counts"]
check(sum(counts.values()) == len(ANALYSIS["technical_details"]),
      f"every resolved row lands in exactly one bucket ({sum(counts.values())})")
check(counts["customer_supplied"] == 1 and counts["engineering_calculated"] == 2
      and counts["historical_reused"] == 1, f"origins are separated correctly ({counts})")
check(counts["customer_confirmation"] == 1,
      "a customer decision is a question, not an engineering gap")
check(counts["engineering_review"] == 1, "a TBD is an engineering gap")

# The whole reason this is a separate document.
spec_md = PKG["specification"]["markdown"]
check("Reused from" not in spec_md and "assumption" not in spec_md.lower(),
      "assumptions do NOT leak into the specification")
check("Historical reused values" in PKG["markdown"]["assumptions"],
      "the assumption register states reuse explicitly")

# An unknown origin must be looked at, never assumed sound.
odd = assumptions.build([{"label": "X", "value": "1", "origin": "mystery"}])
check(odd["counts"]["engineering_review"] == 1,
      "an unrecognised origin is sent for engineering review, not trusted")

# --- traceability ----------------------------------------------------------
records = PKG["traceability"]
by_label = {r["label"]: r for r in records}
check(len(records) == 4, f"only POPULATED values are traceable ({len(records)}), TBDs excluded")
reused = by_label["Construction"]
check(reused["source_project"] == "OFF-CRI-PB-082406R4",
      "a reused value records its source project")
check(reused["source_drawing"] == "CRI PUMP PB 10.10.24-R4.pdf",
      "a reused value records the source DOCUMENT, not just the offer id")
check(reused["similarity_score"] == 0.643, "a reused value records how close the match was")
check(by_label["Exhaust airflow"]["calculation_reference"] == "Vitech booth-type standard",
      "a calculated value records its rule/standard")
check(by_label["Dimensions"]["source_project"] == "Customer requirement",
      "a customer-stated value is attributed to the customer")
check(traceability.unattributed(records) == [], "nothing is left unattributed here")

stray = traceability.build([{"label": "Ghost", "value": "42", "origin": "", "source": None}])
check(len(traceability.unattributed(stray)) == 1,
      "a value with no origin is REPORTED as unattributed")

# --- review ----------------------------------------------------------------
rev = PKG["review"]
levels = {f["check"]: f["level"] for f in rev["findings"]}
check(levels.get("Dimensions validated") == review.PASS, "a resolved envelope PASSes")
check(levels.get("Historical comparison") == review.PASS, "historical comparison PASSes")
check(levels.get("Engineering gap") == review.WARNING, "an engineering gap is a WARNING")
check(levels.get("Customer decision") == review.QUESTION, "a customer decision is a QUESTION")
check(rev["counts"][review.PASS] >= 3, "PASS findings are printed, not omitted")
check(rev["findings"][0]["level"] in (review.FAIL, review.WARNING),
      "findings are ordered worst-first")
check("ENGINEERING REVIEW REQUIRED" in rev["verdict"], f"verdict states what happens next")
check("Read this first" in PKG["markdown"]["review"],
      "the review sheet says it is the first document to read")

# A value with no provenance must FAIL the sheet, not merely warn.
bad = builder.build({**ANALYSIS, "technical_details": [
    {"label": "Ghost", "value": "42", "origin": "", "source": None}]},
    hits=HITS, geometry=GEOMETRY)
check(bad["review"]["counts"][review.FAIL] >= 1,
      "an untraceable value FAILs the review")
check("NOT FOR ISSUE" in bad["review"]["verdict"],
      "a failing package is marked NOT FOR ISSUE")

# No dimensions -> the drawing cannot be dimensioned, and the sheet says so.
nodims = builder.build(ANALYSIS, hits=HITS,
                       geometry={"envelope_mm": {}, "ready": False})
check(any(f["check"] == "Dimensions validated" and f["level"] == review.WARNING
          for f in nodims["review"]["findings"]),
      "an unresolved envelope is a WARNING, never a silent pass")

# --- cross-reference -------------------------------------------------------
xref = PKG["cross_reference"]
blower = next(e for e in xref["items"] if e["label"] == "Exhaust blower")
check(blower["drawing_balloons"] == ["5"],
      "a spec item resolves to its drawing balloon")
check(blower["bom_items"] == ["Exhaust blower"], "and to its BOM line")
check(blower["quotation_items"] == ["Exhaust blower"], "and to its quotation item")
check(len(blower["appears_in"]) == 4, "the blower appears in all four documents")
airflow = next(e for e in xref["items"] if e["label"] == "Exhaust airflow")
check(airflow["bom_items"] == [] and airflow["drawing_balloons"] == [],
      "a computed duty is NOT falsely linked to a part")
check(xref["coverage"]["drawing"] == 1 and xref["coverage"]["bom"] == 1,
      f"per-document coverage is reported ({xref['coverage']})")
check(identifiers.slug("Exhaust blower (nos)") == identifiers.slug("Exhaust blower"),
      "a count suffix does not create a second identity")
check(identifiers.slug("Construction") != identifiers.slug("Construction material"),
      "a near-name is a DIFFERENT item, not a loose spelling")

# --- a missing artifact is reported, never faked ---------------------------
bare = builder.build(ANALYSIS, hits=HITS, geometry=GEOMETRY)
by_doc = {m["document"]: m for m in bare["manifest"]}
check(by_doc["quotation"]["present"] is False and by_doc["quotation"]["absent_reason"],
      "an absent quotation is declared WITH its reason")
check(by_doc["drawing"]["present"] is False and by_doc["drawing"]["absent_reason"],
      "an absent drawing is declared WITH its reason")
check(bare["ok"] is True, "a package with missing artifacts still builds")

# --- dashboard -------------------------------------------------------------
meta = PKG["dashboard"]
check(meta["equipment"] == "Paint Booth" and meta["revision"] == "0",
      "the dashboard states equipment and revision")
check(meta["historical_projects_used"][0]["project"] == "OFF-CRI-PB-082406R4",
      "the dashboard lists the historical projects actually used")
check(len(meta["engineering_rules_applied"]) == 2,
      f"the dashboard lists the rules applied ({len(meta['engineering_rules_applied'])})")
check(meta["customer_questions"] == ["Material handling"],
      "the dashboard lists the customer's open questions")
check(meta["completion"]["percent"] == 67,
      f"completion counts resolved fields ({meta['completion']['percent']}%)")
check("not manufacturing lead time" in meta["completion"]["basis"],
      "completion is explicitly NOT a delivery date")

# --- export ----------------------------------------------------------------
files, manifest = pkg_export.build_files(PKG)
check("Review.md" in files, "the folder carries the review sheet")
check({"Assumptions.md", "Project_Summary.md", "Customer_Requirement.md",
       "Traceability.md", "Cross_Reference.md", "package.json"} <= set(files),
      f"the folder carries every report ({len(files)} files)")
check("Drawing_GA.svg" in files, "the GA drawing is exported as SVG")
check("BOM.xlsx" in files and files["BOM.xlsx"][:2] == b"PK",
      "the BOM is a real xlsx workbook")
check(files["package.json"] and b"Review.md" in files["package.json"],
      "the manifest names the document to read first")
missing = [m for m in manifest if not m["written"]]
check(all(m["note"] for m in missing),
      "every file that could not be written states why")
check(pkg_export.folder_name(PKG) == "CRI_Paint_Shop_Rev0",
      f"the folder is named from the project ({pkg_export.folder_name(PKG)})")

data, zipname = pkg_export.zip_package(PKG)
with zipfile.ZipFile(io.BytesIO(data)) as zf:
    entries = zf.namelist()
check(zipname == "CRI_Paint_Shop_Rev0.zip", f"the download is named for the project")
check(all(e.startswith("CRI_Paint_Shop_Rev0/") for e in entries),
      "the zip contains ONE project folder, not loose files")
check("CRI_Paint_Shop_Rev0/Review.md" in entries, "the zip carries the review sheet")

# --- determinism -----------------------------------------------------------
again = builder.build(ANALYSIS, question="paint booth 5m x 3m x 4m", hits=HITS,
                      drawing=DRAWING, bom=BOM, quotation=QUOTE, geometry=GEOMETRY,
                      spec_markdown="**ENGINEERING SPECIFICATION**\n\n| a | b |",
                      project="CRI Paint Shop", client="CRI Pumps")
check(again["markdown"] == PKG["markdown"],
      "the same analysis produces a byte-identical package")

print()
if FAILS:
    print(f"{len(FAILS)} PACKAGE TEST FAIL")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("ALL PACKAGE TESTS PASS")
