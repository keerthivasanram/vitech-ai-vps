import { memo, useState } from "react";
import { ChevronDown, ChevronRight, MessageSquare, PanelRightClose, Plus, Trash2 } from "lucide-react";
import { groupByRecency, relativeTime } from "../lib/format";

/** One floating conversation card. Active carries a slow, subtle green pulse. */
const HistoryRow = memo(function HistoryRow({ c, active, onOpen, onDelete }) {
  return (
    <li>
      <button
        type="button"
        className={`hist-card${active ? " is-active" : ""}`}
        onClick={() => onOpen(c.id)}
      >
        <span className="hist-card-ic">
          <MessageSquare size={15} strokeWidth={1.8} aria-hidden="true" />
        </span>
        <span className="hist-card-t">
          <span className="hist-card-title">{c.title}</span>
          <span className="hist-card-time">{relativeTime(c.updatedAt)}</span>
        </span>
        <ChevronRight size={14} strokeWidth={2} className="hist-card-arrow" aria-hidden="true" />
        <span
          role="button"
          tabIndex={0}
          className="hist-card-del"
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
  );
});

/** A collapsible "Today" / "Yesterday" / … section of history cards. */
const HistoryGroup = memo(function HistoryGroup({ label, items, activeId, onOpen, onDelete }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="hist-group">
      <button
        type="button"
        className="hist-group-head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span>{label}</span>
        <span className="hist-group-count">{items.length}</span>
        <ChevronDown size={13} strokeWidth={2} className={`hist-group-caret${open ? " is-open" : ""}`} aria-hidden="true" />
      </button>
      {open && (
        <ul className="hist-cards" role="list">
          {items.map((c) => (
            <HistoryRow key={c.id} c={c} active={c.id === activeId} onOpen={onOpen} onDelete={onDelete} />
          ))}
        </ul>
      )}
    </div>
  );
});

/**
 * The right rail's main panel: the full conversation history, grouped by
 * recency (Today / Yesterday / Last 7 Days / Earlier), each collapsible.
 * Opening an entry reuses its chatId, so the agent's Flowise memory is restored
 * alongside the visible transcript.
 */
export const ChatHistoryCard = memo(function ChatHistoryCard({
  conversations, activeId, onOpen, onDelete, onNewChat, onMinimize,
}) {
  const groups = groupByRecency(conversations);

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
        <div className="history-list">
          {groups.map((g) => (
            <HistoryGroup key={g.label} label={g.label} items={g.items} activeId={activeId} onOpen={onOpen} onDelete={onDelete} />
          ))}
        </div>
      )}
    </section>
  );
});
