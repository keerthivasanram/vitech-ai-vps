import { memo } from "react";
import { MessageSquare, PanelRightClose, Plus, Trash2 } from "lucide-react";
import { relativeTime } from "../lib/format";

/**
 * The right rail's main panel: the full conversation history.
 * Opening an entry reuses its chatId, so the agent's Flowise memory is restored
 * alongside the visible transcript.
 */
export const ChatHistoryCard = memo(function ChatHistoryCard({
  conversations, activeId, onOpen, onDelete, onNewChat, onMinimize,
}) {
  return (
    <section className="card history">
      <header className="panel-head">
        <h2 className="panel-title">Chat History</h2>
        <div className="panel-head-actions">
          <button
            type="button"
            className="panel-icon"
            onClick={onNewChat}
            aria-label="Start a new chat"
            title="New chat"
          >
            <Plus size={16} strokeWidth={2} aria-hidden="true" />
          </button>
          <button
            type="button"
            className="panel-icon"
            onClick={onMinimize}
            aria-label="Minimize panel"
            title="Minimize panel"
          >
            <PanelRightClose size={16} strokeWidth={1.8} aria-hidden="true" />
          </button>
        </div>
      </header>

      {conversations.length === 0 ? (
        <p className="rowlist-empty">
          No conversations yet — ask the agent something and it will appear here.
        </p>
      ) : (
        <ul className="rowlist history-list" role="list">
          {conversations.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={`rowitem${c.id === activeId ? " is-active" : ""}`}
                onClick={() => onOpen(c.id)}
              >
                <span className="conv-ic">
                  <MessageSquare size={15} strokeWidth={1.8} aria-hidden="true" />
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
                  <Trash2 size={13} strokeWidth={1.8} aria-hidden="true" />
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
});
