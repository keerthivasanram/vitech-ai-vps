"""Export the hand-extracted offers into a NORMALIZED, Supabase/Postgres-ready
table structure — the clean, client-showable version of the knowledge base.

Produces (in data/export/):
  schema.sql               CREATE TABLE statements (documents + 3 detail tables)
  data.sql                 INSERT statements (schema.sql + data.sql = full load)
  documents.csv            one row per file (the client-facing overview)
  given_data.csv           tidy: document_id, field, value  (the requirement)
  technical_details.csv    tidy: document_id, field, value  (the engineered spec)
  price_items.csv          tidy: document_id, item, amount, currency

Load into Supabase either way:
  * Dashboard -> Table editor -> Import CSV (one per table), or
  * SQL editor -> run schema.sql then data.sql, or
  * psql "$SUPABASE_DB_URL" -f schema.sql -f data.sql
Run:  .venv/Scripts/python export_supabase.py
"""
import csv
import glob
import json
import os

OFFERS = "data/offers/*.json"
OUT = "data/export"
_TOTAL_KEYS = ("final_price", "grand_total", "total")


def _records():
    recs = []
    for f in sorted(glob.glob(OFFERS)):
        d = json.load(open(f, encoding="utf-8"))
        recs += d if isinstance(d, list) else [d]
    return recs


def _flatten(obj, prefix=""):
    """Flatten one nested level into dotted keys: {'booth':{'moc':'MS'}} ->
    [('booth.moc','MS')]. Scalars/lists become a single (key, text) pair."""
    out = []
    for k, v in (obj or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out += _flatten(v, f"{key}.")
        elif isinstance(v, list):
            out.append((key, ", ".join(str(x) for x in v)))
        else:
            out.append((key, v))
    return out


def _total(ps):
    if not ps:
        return None, None
    cur = ps.get("currency", "INR")
    for k in _TOTAL_KEYS:
        if isinstance(ps.get(k), (int, float)):
            return float(ps[k]), cur
    nums = [v for k, v in ps.items() if isinstance(v, (int, float))]
    return (float(sum(nums)) if nums else None), cur


def _headline(r):
    gd = r.get("given_data", {}) or {}
    for k, unit in (("air_volume_cfm", "CFM"), ("air_volume_cmh", "CMH")):
        if gd.get(k):
            return f"{gd[k]} {unit}"
    if gd.get("length_m") and gd.get("width_m"):
        return f"{gd['length_m']} x {gd['width_m']} m"
    return None


# ---- SQL helpers ----------------------------------------------------------
def _sql(v):
    if v is None or v == "":
        return "NULL"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


SCHEMA = """-- Vitech AI knowledge base — normalized offer tables (Supabase / Postgres)
drop table if exists price_items cascade;
drop table if exists technical_details cascade;
drop table if exists given_data cascade;
drop table if exists documents cascade;

create table documents (
    id           text primary key,
    category     text,
    title        text,
    client       text,
    vendor       text,
    ref          text,
    doc_date     date,
    source_file  text,
    headline     text,
    price_total  numeric,
    currency     text
);

create table given_data (
    id           bigserial primary key,
    document_id  text references documents(id) on delete cascade,
    field        text,
    value        text
);

create table technical_details (
    id           bigserial primary key,
    document_id  text references documents(id) on delete cascade,
    field        text,
    value        text
);

create table price_items (
    id           bigserial primary key,
    document_id  text references documents(id) on delete cascade,
    item         text,
    amount       numeric,
    currency     text
);
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    recs = _records()

    documents, given, tech, prices = [], [], [], []
    for r in recs:
        did = r.get("id")
        total, cur = _total(r.get("price_schedule"))
        documents.append({
            "id": did, "category": r.get("category"), "title": r.get("title"),
            "client": r.get("client"), "vendor": r.get("vendor"), "ref": r.get("ref"),
            "doc_date": r.get("date"), "source_file": r.get("source_file"),
            "headline": _headline(r), "price_total": total, "currency": cur,
        })
        for field, value in _flatten(r.get("given_data")):
            given.append({"document_id": did, "field": field, "value": value})
        for field, value in _flatten(r.get("technical_details")):
            tech.append({"document_id": did, "field": field, "value": value})
        for k, v in (r.get("price_schedule") or {}).items():
            if k == "currency":
                continue
            prices.append({"document_id": did, "item": k,
                           "amount": v if isinstance(v, (int, float)) else None,
                           "currency": cur})

    def write_csv(name, rows, cols):
        with open(f"{OUT}/{name}", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)

    write_csv("documents.csv", documents,
              ["id", "category", "title", "client", "vendor", "ref", "doc_date",
               "source_file", "headline", "price_total", "currency"])
    write_csv("given_data.csv", given, ["document_id", "field", "value"])
    write_csv("technical_details.csv", tech, ["document_id", "field", "value"])
    write_csv("price_items.csv", prices, ["document_id", "item", "amount", "currency"])

    # SQL: schema + data
    with open(f"{OUT}/schema.sql", "w", encoding="utf-8") as f:
        f.write(SCHEMA)

    lines = ["-- data (run after schema.sql)"]
    for d in documents:
        lines.append(
            "insert into documents (id,category,title,client,vendor,ref,doc_date,"
            "source_file,headline,price_total,currency) values ("
            + ",".join(_sql(d[k]) for k in ("id", "category", "title", "client",
              "vendor", "ref", "doc_date", "source_file", "headline",
              "price_total", "currency")) + ");")
    for row in given:
        lines.append("insert into given_data (document_id,field,value) values ("
                     + ",".join(_sql(row[k]) for k in ("document_id", "field", "value")) + ");")
    for row in tech:
        lines.append("insert into technical_details (document_id,field,value) values ("
                     + ",".join(_sql(row[k]) for k in ("document_id", "field", "value")) + ");")
    for row in prices:
        lines.append("insert into price_items (document_id,item,amount,currency) values ("
                     + ",".join(_sql(row[k]) for k in ("document_id", "item", "amount", "currency")) + ");")
    with open(f"{OUT}/data.sql", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"exported -> {OUT}/")
    print(f"  documents        : {len(documents)} rows")
    print(f"  given_data       : {len(given)} rows")
    print(f"  technical_details: {len(tech)} rows")
    print(f"  price_items      : {len(prices)} rows")
    print(f"  files: documents.csv, given_data.csv, technical_details.csv, "
          f"price_items.csv, schema.sql, data.sql")


if __name__ == "__main__":
    main()
