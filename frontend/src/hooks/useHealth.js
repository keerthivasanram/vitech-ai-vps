import { useEffect, useState } from "react";

/**
 * Backend health probe. Returns null while in flight, then the payload
 * ({status, llm_model, documents_indexed, memory}) or {status:"down"} if the
 * API is unreachable — which is the normal case when the frontend runs
 * locally without the VPS stack behind it.
 */
export function useHealth() {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/health")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("bad status"))))
      .then((d) => alive && setHealth(d))
      .catch(() => alive && setHealth({ status: "down" }));
    return () => { alive = false; };
  }, []);

  return health;
}
