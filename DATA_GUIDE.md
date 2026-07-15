# Data Guide — feeding the ATS Engineering Assistant

This document is the **data contract** for the ATS reasoning engine: the exact
shape every *offer record* must have, how it must be stored in Chroma so the
reasoning engine can read it, and how to register a **new equipment type** so
it reasons correctly.

> **Two ingestion paths, one collection.**
> - **Offer records** (this guide) — hand-curated `given_data`/`technical_details`
>   JSON that the deterministic ATS spec/quote engine reasons over. Ingest with
>   `python -m app.ingest`.
> - **Reference documents** (PDF/DOCX/XLSX/TXT — standards, catalogs, datasheets,
>   past offers as source files) now have a real loader/extraction pipeline in
>   [`backend/rag/`](backend/rag/README.md): it preserves pages, tables and
>   engineering sections and writes rich filterable metadata (customer, project,
>   equipment type, revision, offer number, date, section). Ingest with
>   `python -m rag.ingest <path>`. These are stored as `type="document"` and
>   ground conversational/Consulting answers; they never alter a calculated
>   number (the engine only reasons over `type="offer"`).

---

## 1. The offer record (one historical quotation = one record)

Every record is a JSON object with this shape:

```json
{
  "id": "OFF-WS-014",                         // unique id
  "type": "offer",                             // "offer" (a quotation) or "spec" (a standard doc)
  "category": "wet_scrubber",                  // MUST match a category profile (see §4)
  "title": "Wet Scrubber Offer - 735 CFM",
  "source_file": "WetScrubber_735CFM_4nos.pdf", // original file name -> shown as provenance

  "given_data": {                              // the REQUIREMENT the client gave
    "air_volume_cfm": 735,
    "air_volume_cmh": 1250,
    "operating_temp": "ambient",
    "tower_diameter_mm": 700,
    "qty": 4
  },

  "technical_details": {                       // the ENGINEERED answer that was quoted
    "tower_diameter_mm": 700,
    "tower_height_m": 3.5,
    "chamber": "SS-304 2mm",
    "spray_nozzle_nos": 17,
    "pump_capacity_hp": 1.0,
    "pump_make": "ANALA",
    "tank_capacity_litre": 250,
    "finish": "SS 2b / MS epoxy primer + epoxy top coat"
  }
}
```

**Rules**
- `given_data` = inputs (what the customer specifies). `technical_details` = outputs (what engineering decided). This split is what lets the system learn *requirement → spec*.
- Use **numbers for numeric values** (`735`, not `"735 CFM"`). Keep units in the key name (`air_volume_cfm`, `tank_capacity_litre`).
- Use **consistent key names** across all records of a category (the engine compares fields by key — `pump_capacity_hp` everywhere, never `pumpHP` in one and `pump_hp` in another).
- `category` and `source_file` are required.

---

## 2. How records must sit in Chroma (read this before manual upload)

The retriever does **not** read raw Chroma documents — it reads a `_raw`
metadata field and rebuilds the record. So each Chroma entry must be:

| Chroma field | Must contain |
|---|---|
| `id` | the record `id` |
| `document` (embedded text) | a flattened text of category + given_data + technical_details |
| `metadata._raw` | the **full record JSON as a string** (`json.dumps(record)`) |
| `metadata.category` | the category string (used for filtering) |
| `metadata.source_file` | the file name |

If you upload a record **without `_raw`**, retrieval returns it but the reasoning
engine sees an empty record. So `_raw` is mandatory.

**Easiest correct path (no new code):** drop your JSON files into
`backend/data/offers/<category>.json` (a JSON array per file) and run
`python -m app.ingest`. That existing command builds the embed text + `_raw` +
metadata exactly right. It is the supported "manual upload" — you only produce
the JSON. (When you build the real upload/extraction service later, have it
produce the same Chroma entries described in the table above.)

---

## 3. How much / what data per category (so the reasoning works)

The engine's intelligence depends on the data spread:

- **≥ 3–4 offers per category, spanning the size range.** Interpolation needs two
  offers that *bracket* the request (one below, one above) on the size driver.
  With only one offer, everything degrades to "reused".
- **Repeat the standard component choices** (material, make, finish) across
  offers — that's what produces "Historical consensus (4/4)".
- **Fill `given_data` consistently** — missing inputs become "assumptions" only
  if a consensus exists across offers; otherwise "missing".

Rule of thumb: a category with ~5–10 well-spread historical offers reasons well.

---

## 4. Registering a NEW equipment type (the important part)

You have many equipment types. Each one needs a **category profile** in
`backend/app/catalog.py` → `CATEGORY_PROFILES`. Without a profile, a category
still loads but reasons in a degraded generic mode (no size driver → no
interpolation, no scaling, weak match). The profile is what unlocks full
reasoning.

Profile template (copy per equipment type):

```python
"centrifugal_blower": {                      # category key (matches record.category)
    "label": "Centrifugal Blower",
    "scale_driver": "air_volume_cfm",        # the ONE number the design scales with
    "driver_label": "Airflow",
    "diff_unit": "airflow",                  # word used in the "+13% airflow" column
    "dimension_keys": ["impeller_dia_mm"],   # given_data keys that are "dimensions"
    "process_keys": ["operating_temp"],      # given_data keys that are "conditions"
    "expected_inputs": [                      # inputs you expect a client to give
        ("air_volume_cfm", "Air volume"),
        ("static_pressure_mmwc", "Static pressure"),
        ("operating_temp", "Operating temperature"),
        ("qty", "Quantity"),
    ],
    "scalable": [                             # technical_details that scale with the driver
        "motor_hp", "rpm", "casing_size",
    ],
    "from_given": {"impeller_dia_mm": "impeller_dia_mm"},  # technical fields set straight from the requirement
    "rules": None,                            # None = case-based; or a function for formula-based (see §5)
    "rule_covers": [],
    "field_labels": {                         # pretty labels for technical_details keys
        "motor_hp": "Motor (HP)", "rpm": "RPM", "casing_size": "Casing size",
    },
},
```

**What each field controls**
- `scale_driver` → the basis for interpolation/scaling and the match %.
- `scalable` → fields that get interpolated between bracketing offers (synthesis).
- `dimension_keys` / `process_keys` → the engineering-match sub-scores.
- `expected_inputs` → drives "requirement coverage", assumptions, and missing-inputs.
- `from_given` → fields taken directly from the requirement (tagged "From Requirement").
- everything not scalable / not from_given → "Historical consensus" or "Reused".

---

## 5. Optional: make a category formula-based (true rule engine)

If a category has real engineering formulas (like paint booths use NFPA 33),
add a `rules` function (see `paint_booth` + `app/rules.py`). Then those values
become **"Calculated (Engineering Rule)"** and cite the standard, instead of
being interpolated from history. Without formulas, case-based synthesis is used —
which is still valid reasoning, just labeled honestly.

---

## 6. Checklist before testing a category

- [ ] Category profile added to `CATEGORY_PROFILES` (with the right `scale_driver`).
- [ ] ≥ 3–4 offers, spanning the size range, in `data/offers/<category>.json`.
- [ ] Consistent key names; numbers are numbers; units in key names.
- [ ] `category` + `source_file` set on every record.
- [ ] `python -m app.ingest` run (or your upload produced `_raw` + metadata).
- [ ] Test a request that falls *between* two offers → expect interpolation;
      a request matching one → expect exact/consensus.
```
