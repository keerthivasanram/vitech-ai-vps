/* Presentation metadata for knowledge-base collections.
   The backend supplies each collection's `state`; these map it to a badge. */

/* The collection icon is chosen HERE, not taken from the API's own `icon`
   field, which is an emoji. A row of emoji is the wrong register for a page of
   engineering records, and picking the glyph on the client keeps
   /api/knowledge/overview's response — and its contract fingerprint —
   untouched. Names resolve through <NavIcon>. */
export const COLL_ICON = {
  historical_projects: "FolderKanban",
  specifications:      "FileText",
  quotations:          "ReceiptText",
  standards:           "BookOpen",
  vendor_catalogues:   "Package",
  drawings:            "PenTool",
  rules:               "Settings",
};

export const COLL_BADGE = {
  live: "ok",
  on_demand: "info",
  ingest: "soft",
  roadmap: "soft",
  engine: "gen",
};

export const COLL_STATE = {
  live: "Live",
  on_demand: "On demand",
  ingest: "Ingestion-ready",
  roadmap: "Roadmap",
  engine: "Engine",
};
