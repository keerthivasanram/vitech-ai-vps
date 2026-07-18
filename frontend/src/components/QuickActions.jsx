import { memo } from "react";
import { motion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import { NavIcon } from "./NavIcon";
import { QUICK_ACTIONS } from "../lib/constants";
import { useRipple } from "../hooks/useRipple";

/** One quick-action card. Owns its own ripple state — each card gets its own click feedback. */
const QuickCard = memo(function QuickCard({ a, i, onPick, disabled }) {
  const { ripples, onPointerDown } = useRipple();
  return (
    <motion.button
      type="button"
      className="quick-card"
      disabled={disabled}
      onClick={() => onPick(a.prompt)}
      onPointerDown={onPointerDown}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1], delay: 0.04 * i }}
    >
      <span className="quick-glow" aria-hidden="true" />
      <span className="quick-ic">
        <NavIcon name={a.icon} size={20} />
      </span>
      <span className="quick-t">
        <span className="quick-title">{a.title}</span>
        <span className="quick-sub">{a.sub}</span>
      </span>
      <ChevronRight size={18} strokeWidth={1.8} className="quick-chev" aria-hidden="true" />
      {ripples.map((r) => (
        <span key={r.id} className="ripple" style={{ left: r.x, top: r.y }} aria-hidden="true" />
      ))}
    </motion.button>
  );
});

/**
 * Four quick-action cards under the hero. Each fires a real prompt at the
 * agent rather than being decorative.
 */
export const QuickActions = memo(function QuickActions({ onPick, disabled }) {
  return (
    <div className="quick">
      {QUICK_ACTIONS.map((a, i) => (
        <QuickCard key={a.title} a={a} i={i} onPick={onPick} disabled={disabled} />
      ))}
    </div>
  );
});
