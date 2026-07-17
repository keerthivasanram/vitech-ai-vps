import { memo } from "react";
import { MessageSquare, Trash2 } from "lucide-react";
import { MotionCard, PanelHead } from "../common/Card";
import { relativeTime } from "../lib/format";

/**
 * Card 3: recent conversations, restored from local history.
 * Opening one reuses its chatId, so the agent's own memory comes back with it.
 */
export const ConversationCard = memo(function ConversationCard({
  conversations, activeId, onOpen, onDelete, onViewAll, index = 0,
}) {
  const list = conversations.slice(0, 4);

  return (
    <MotionCard index={index}>
      <PanelHead
        title="Recent Conversations"
        action={conversations.length > 4 ? "View all" : undefined}
        onAction={onViewAll}
      />

      {list.length === 0 ? (
        <p className="rowlist-empty">
          No conversations yet — ask the agent something and it will appear here.
        </p>
      ) : (
        <ul className="rowlist" role="list">
          {list.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={`rowitem${c.id === activeId ? " is-active" : ""}`}
                onClick={() => onOpen(c.id)}
              >
                <span className="conv-ic">
                  <MessageSquare size={16} strokeWidth={1.8} aria-hidden="true" />
                </span>
                <span className="rowitem-t">
                  <span className="rowitem-title">{c.title}</span>
                </span>
                <span className="conv-time">{relativeTime(c.updatedAt)}</span>
                <span
                  role="button"
                  tabIndex={0}
                  className="conv-kebab"
                  aria-label={`Delete conversation: ${c.title}`}
                  onClick={(e) => { e.stopPropagation(); onDelete(c.id); }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      e.stopPropagation();
                      onDelete(c.id);
                    }
                  }}
                >
                  <Trash2 size={14} strokeWidth={1.8} aria-hidden="true" />
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </MotionCard>
  );
});
