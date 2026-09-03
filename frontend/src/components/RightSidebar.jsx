import { memo } from "react";
import { ChatHistoryCard } from "./ChatHistoryCard";

/**
 * Right rail: the chat history, and nothing else.
 *
 * It used to carry an "Upgrade your workflow / Unlock advanced AI
 * capabilities" banner under the list. There is no upgrade — the button
 * opened the Knowledge Base — so it was template marketing copy taking a
 * third of the rail away from the history it sat under.
 *
 * `open` drives both the desktop minimize/maximize state and, below 1024px,
 * the drawer.
 */
export const RightSidebar = memo(function RightSidebar({
  conversations, activeId, onOpenConversation, onDeleteConversation,
  onNewChat, onMinimize, open,
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
    </aside>
  );
});
