import { useCallback, useRef, useState } from "react";

const RIPPLE_MS = 550;

/**
 * Click-feedback ripple: spawns a `.ripple` span at the pointer position,
 * self-removing once its expand+fade animation finishes.
 *
 * Usage: const { ripples, onPointerDown } = useRipple();
 *   <button onPointerDown={onPointerDown} style={{ position: "relative", overflow: "hidden" }}>
 *     {ripples.map((r) => <span key={r.id} className="ripple" style={{ left: r.x, top: r.y }} />)}
 *   </button>
 */
export function useRipple() {
  const [ripples, setRipples] = useState([]);
  const nextId = useRef(0);

  const onPointerDown = useCallback((e) => {
    const el = e.currentTarget;
    const rect = el.getBoundingClientRect();
    const id = nextId.current++;
    const ripple = { id, x: e.clientX - rect.left, y: e.clientY - rect.top };
    setRipples((prev) => [...prev, ripple]);
    setTimeout(() => {
      setRipples((prev) => prev.filter((r) => r.id !== id));
    }, RIPPLE_MS);
  }, []);

  return { ripples, onPointerDown };
}
