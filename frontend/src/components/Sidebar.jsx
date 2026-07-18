import { memo, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Plus } from "lucide-react";
import { SidebarGroup, SidebarItem } from "./SidebarItem";
import { Logo, CircuitDeco } from "./Logo";
import { Avatar } from "../common/Avatar";
import { AGENT_VIEWS, NAV } from "../lib/constants";
import { useRipple } from "../hooks/useRipple";

/**
 * Left rail: logo, New Chat, grouped nav, user card.
 * `open` only matters below 768px, where the rail is a drawer.
 */
export const Sidebar = memo(function Sidebar({
  view, onSelect, onNewChat, user, open, isDark,
}) {
  // The agent dropdown starts open when one of its agents is the current view.
  const [agentsOpen, setAgentsOpen] = useState(() => AGENT_VIEWS.includes(view));

  // New Chat: a brief success bloom confirms the click landed, on top of the
  // shared ripple. Timeout id is tracked so a rapid double-click restarts the
  // flash cleanly instead of letting an earlier timer cut it short.
  const [justClicked, setJustClicked] = useState(false);
  const successTimer = useRef(null);
  const { ripples, onPointerDown } = useRipple();

  const handleNewChat = () => {
    clearTimeout(successTimer.current);
    setJustClicked(true);
    successTimer.current = setTimeout(() => setJustClicked(false), 500);
    onNewChat();
  };
  useEffect(() => () => clearTimeout(successTimer.current), []);

  // Navigating to an agent from elsewhere (a dashboard button, say) reveals it
  // in the nav rather than leaving the active item hidden inside a closed group.
  useEffect(() => {
    if (AGENT_VIEWS.includes(view)) setAgentsOpen(true);
  }, [view]);
  const groups = useMemo(() => {
    const order = [];
    const byGroup = new Map();
    for (const item of NAV) {
      if (!byGroup.has(item.group)) { byGroup.set(item.group, []); order.push(item.group); }
      byGroup.get(item.group).push(item);
    }
    return order.map((name) => ({ name, items: byGroup.get(name) }));
  }, []);

  return (
    <aside className={`sidebar${open ? " is-open" : ""}`} aria-label="Main navigation">
      <CircuitDeco />

      <div className="side-brand">
        <Logo height={44} isDark={isDark} />
      </div>

      <button
        type="button"
        className={`side-newchat${justClicked ? " is-success" : ""}`}
        onClick={handleNewChat}
        onPointerDown={onPointerDown}
      >
        <span className="side-newchat-ic">
          <Plus size={18} strokeWidth={2.2} aria-hidden="true" />
        </span>
        New Chat
        <span className="side-newchat-hover-shimmer" aria-hidden="true" />
        {ripples.map((r) => (
          <span key={r.id} className="ripple" style={{ left: r.x, top: r.y }} aria-hidden="true" />
        ))}
      </button>

      <nav className="side-nav">
        {groups.map((g) => (
          <div key={g.name}>
            <h2 className="side-group-label">{g.name}</h2>
            <ul className="rowlist" role="list">
              {g.items.map((item) =>
                item.children ? (
                  <SidebarGroup
                    key={item.id}
                    item={item}
                    view={view}
                    open={agentsOpen}
                    onToggle={() => setAgentsOpen((v) => !v)}
                    onSelect={onSelect}
                  />
                ) : (
                  <SidebarItem
                    key={item.id}
                    item={item}
                    active={view === item.id}
                    onSelect={onSelect}
                  />
                )
              )}
            </ul>
          </div>
        ))}
      </nav>

      <button
        type="button"
        className={`side-user${view === "profile" ? " is-active" : ""}`}
        onClick={() => onSelect("profile")}
        aria-label={`Signed in as ${user.name} — open profile`}
      >
        <Avatar name={user.name} size={38} />
        <span className="side-user-t">
          <span className="side-user-name">{user.name}</span>
          <span className="side-user-role">{user.role}</span>
        </span>
        <ChevronDown size={16} strokeWidth={1.8} className="side-user-chev" aria-hidden="true" />
      </button>
    </aside>
  );
});
