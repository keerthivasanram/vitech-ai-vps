import { memo } from "react";
import { OverviewCard } from "./OverviewCard";
import { CapabilityCard } from "./CapabilityCard";
import { ConversationCard } from "./ConversationCard";
import { UpgradeCard } from "./UpgradeCard";

/**
 * Right rail: agent overview, capabilities, recent conversations, upgrade.
 * `open` only matters below 1024px, where the rail is a drawer.
 */
export const RightSidebar = memo(function RightSidebar({
  ui, conversations, activeId, onPick, onOpenConversation, onDeleteConversation,
  onViewAll, open,
}) {
  return (
    <aside className={`rightbar${open ? " is-open" : ""}`} aria-label="Agent panel">
      <OverviewCard name={ui.name} description={ui.overview} index={0} />
      <CapabilityCard onPick={onPick} onViewAll={onViewAll} index={1} />
      <ConversationCard
        conversations={conversations}
        activeId={activeId}
        onOpen={onOpenConversation}
        onDelete={onDeleteConversation}
        onViewAll={onViewAll}
        index={2}
      />
      <UpgradeCard onExplore={onViewAll} index={3} />
    </aside>
  );
});
