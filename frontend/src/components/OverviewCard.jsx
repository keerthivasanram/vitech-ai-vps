import { memo } from "react";
import { Bot, MoreHorizontal, Zap } from "lucide-react";
import { MotionCard, PanelHead } from "../common/Card";

/** Hexagon plate behind the bot mark — echoes the brand's angular geometry. */
const HexPlate = memo(function HexPlate() {
  return (
    <svg className="ov-hex" viewBox="0 0 66 66" aria-hidden="true">
      <path
        d="M33 2 L60 17.5 V48.5 L33 64 L6 48.5 V17.5 Z"
        fill="currentColor"
        stroke="rgba(34,197,94,0.28)"
        strokeWidth="1.5"
      />
    </svg>
  );
});

/** Card 1: who the agent is. */
export const OverviewCard = memo(function OverviewCard({ name, description, index = 0 }) {
  return (
    <MotionCard index={index}>
      <PanelHead
        title="AI Agent Overview"
        action={<MoreHorizontal size={18} strokeWidth={1.8} aria-label="Overview options" />}
      />
      <div className="ov">
        <span className="ov-mark">
          <HexPlate />
          <Bot size={30} strokeWidth={1.8} className="ov-hex-bot" aria-hidden="true" />
        </span>
        <div className="ov-t">
          <h3 className="ov-name">{name}</h3>
          <p className="ov-desc">{description}</p>
          <span className="ov-chip">
            <Zap size={12} strokeWidth={2.2} aria-hidden="true" />
            Powered by Vitech AI
          </span>
        </div>
      </div>
    </MotionCard>
  );
});
