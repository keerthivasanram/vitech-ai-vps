import { memo } from "react";
import { ChatHistoryCard } from "./ChatHistoryCard";
import { UpgradeCard } from "./UpgradeCard";

/**
 * Right rail: chat history, with the upgrade banner pinned beneath it.
 * `open` drives both the desktop minimize/maximize state and, below 1024px,
 * the drawer.
 */
export const RightSidebar = memo(function RightSidebar({
  conversations, activeId, onOpenConversation, onDeleteConversation,
  onNewChat, onMinimize, onViewAll, open,
}) {
  return (
    <aside className={`rightbar${open ? " is-open" : ""}`} aria-label="Chat history">
      <ChatHistoryCard
        conversations={conversations}
        activeId={activeId}
        onOpen={onOpenConversation}
        onDelete={onDeleteConversation}
        onNewChat={onNewChat}
        onMinimize={onMinimize}
      />
      <UpgradeCard onExplore={onViewAll} index={1} />
    </aside>
  );
});
