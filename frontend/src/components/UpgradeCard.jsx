import { memo } from "react";
import { motion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";

/** Rising bar chart with a trend arrow — the banner's neon illustration. */
const ChartArt = memo(function ChartArt() {
  return (
    <svg className="upgrade-art" width="104" height="66" viewBox="0 0 104 66" aria-hidden="true">
      <g fill="currentColor" opacity="0.9">
        <rect x="2"  y="44" width="12" height="20" rx="2.5" opacity="0.5" />
        <rect x="20" y="34" width="12" height="30" rx="2.5" opacity="0.65" />
        <rect x="38" y="24" width="12" height="40" rx="2.5" opacity="0.8" />
        <rect x="56" y="12" width="12" height="52" rx="2.5" />
      </g>
      <path
        d="M6 40 L26 30 L44 18 L62 8 L88 8"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M78 3 L90 8 L78 13 Z" fill="currentColor" />
    </svg>
  );
});

/** Card 4: the premium upgrade banner. */
export const UpgradeCard = memo(function UpgradeCard({ onExplore, index = 0 }) {
  return (
    <motion.section
      className="upgrade"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1], delay: index * 0.05 }}
    >
      <div className="upgrade-t">
        <h3 className="upgrade-title">Upgrade your workflow</h3>
        <p className="upgrade-sub">Unlock advanced AI capabilities</p>
        <button type="button" className="upgrade-btn" onClick={onExplore}>
          Explore Features
          <ArrowUpRight size={15} strokeWidth={2.2} aria-hidden="true" />
        </button>
      </div>
      <ChartArt />
    </motion.section>
  );
});
