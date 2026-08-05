import { useEffect, useState } from "react";

/**
 * Backend liveness. Returns null while in flight, then `{status}` — or
 * `{status:"down"}` if the API is unreachable, which is the normal case when
 * the frontend runs locally without the stack behind it.
 *
 * `/api/health` is PUBLIC and deliberately returns status only. It used to
 * carry the model name, the Ollama host and the index size, which was a free
 * reconnaissance report for anyone who could reach the port. Those live behind
 * the administrator role now (`/api/admin/health/detail`), so any UI that used
 * to read them must get its numbers from an authenticated endpoint instead.
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
