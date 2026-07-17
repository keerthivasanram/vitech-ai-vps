import { memo, useMemo } from "react";
import { ChevronDown, Plus } from "lucide-react";
import { SidebarItem } from "./SidebarItem";
import { Logo, CircuitDeco } from "./Logo";
import { Avatar } from "../common/Avatar";
import { NAV } from "../lib/constants";

/**
 * Left rail: logo, New Chat, grouped nav, user card.
 * `open` only matters below 768px, where the rail is a drawer.
 */
export const Sidebar = memo(function Sidebar({ view, onSelect, onNewChat, user, open }) {
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
        <Logo height={44} />
      </div>

      <button type="button" className="side-newchat" onClick={onNewChat}>
        <Plus size={18} strokeWidth={2.2} aria-hidden="true" />
        New Chat
      </button>

      <nav className="side-nav">
        {groups.map((g) => (
          <div key={g.name}>
            <h2 className="side-group-label">{g.name}</h2>
            <ul className="rowlist" role="list">
              {g.items.map((item) => (
                <SidebarItem
                  key={item.id}
                  item={item}
                  active={view === item.id}
                  onSelect={onSelect}
                />
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <button type="button" className="side-user" aria-label={`Signed in as ${user.name}`}>
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
