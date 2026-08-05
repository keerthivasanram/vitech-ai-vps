import { useEffect, useState } from "react";

/**
 * Corpus size, from the authenticated knowledge overview.
 *
 * Exists because `/api/health` is public and was reduced to a status probe —
 * it no longer reports how much is indexed, and it should not. Anything the
 * UI wants to SHOW about the corpus has to come from an endpoint that
 * authenticates the caller first.
 *
 * Returns null while in flight or if the call fails, so callers render a
 * placeholder rather than a misleading zero.
 */
export function useKnowledgeStats() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/knowledge/overview")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("bad status"))))
      .then((d) => alive && setStats(d))
      .catch(() => alive && setStats(null));
    return () => { alive = false; };
  }, []);

  return stats;
}
