import { memo } from "react";
import { ChevronRight } from "lucide-react";
import { MotionCard, PanelHead } from "../common/Card";
import { NavIcon } from "./NavIcon";
import { CAPABILITIES } from "../lib/constants";

/** Card 2: what the agent can do. Each row asks the agent a real question. */
export const CapabilityCard = memo(function CapabilityCard({ onPick, onViewAll, index = 0 }) {
  return (
    <MotionCard index={index}>
      <PanelHead title="Top Capabilities" action="View all" onAction={onViewAll} />
      <ul className="rowlist" role="list">
        {CAPABILITIES.map((c) => (
          <li key={c.title}>
            <button type="button" className="rowitem" onClick={() => onPick(c.prompt)}>
              <span className="rowitem-ic">
                <NavIcon name={c.icon} size={18} />
              </span>
              <span className="rowitem-t">
                <span className="rowitem-title">{c.title}</span>
                <span className="rowitem-sub">{c.sub}</span>
              </span>
              <ChevronRight size={16} strokeWidth={1.8} className="rowitem-chev" aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
    </MotionCard>
  );
});
