import { useEffect, useState } from "react";

/** Subscribe to a media query. Used to decide when the rails become drawers. */
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(
    () => window.matchMedia?.(query).matches ?? false
  );

  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = (e) => setMatches(e.matches);
    setMatches(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [query]);

  return matches;
}

/** Below 768px the sidebar collapses to a drawer. */
export const useIsMobile = () => useMediaQuery("(max-width: 768px)");

/** Below 1024px the right panel becomes a drawer. */
export const useIsCompact = () => useMediaQuery("(max-width: 1024px)");
