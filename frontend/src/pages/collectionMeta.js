/* Presentation metadata for knowledge-base collections.
   The backend supplies each collection's `state`; these map it to a badge. */

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
