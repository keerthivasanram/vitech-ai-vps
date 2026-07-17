import { memo } from "react";
import { ChevronDown } from "lucide-react";
import { NavIcon } from "./NavIcon";

/**
 * One sidebar nav row: 52px tall, 14px radius, icon + label.
 * Selected state carries the light-green fill, green icon and the green
 * left indicator bar (drawn by .side-item.is-active::before).
 */
export const SidebarItem = memo(function SidebarItem({ item, active, onSelect }) {
  return (
    <li>
      <button
        type="button"
        className={`side-item${active ? " is-active" : ""}`}
        aria-current={active ? "page" : undefined}
        onClick={() => onSelect(item.id)}
      >
        <span className="side-item-ic">
          <NavIcon name={item.icon} size={20} />
        </span>
        <span className="side-item-label">{item.label}</span>
        {item.status === "soon" && (
          <span className="side-item-dot" title="Coming soon" aria-label="Coming soon" />
        )}
      </button>
    </li>
  );
});

/**
 * Expandable nav group (the AI Agent dropdown). The parent is a disclosure
 * toggle, not a destination — its children are the destinations. It reads as
 * active whenever one of its children is the current view.
 */
export const SidebarGroup = memo(function SidebarGroup({
  item, view, open, onToggle, onSelect,
}) {
  const childActive = item.children.some((c) => c.id === view);

  return (
    <li>
      <button
        type="button"
        className={`side-item${childActive && !open ? " is-active" : ""}`}
        aria-expanded={open}
        onClick={onToggle}
      >
        <span className="side-item-ic">
          <NavIcon name={item.icon} size={20} />
        </span>
        <span className="side-item-label">{item.label}</span>
        <ChevronDown
          size={16}
          strokeWidth={2}
          className={`side-caret${open ? " is-open" : ""}`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <ul className="side-sub" role="list">
          {item.children.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={`side-item side-subitem${view === c.id ? " is-active" : ""}`}
                aria-current={view === c.id ? "page" : undefined}
                onClick={() => onSelect(c.id)}
              >
                <span className="side-item-ic">
                  <NavIcon name={c.icon} size={17} />
                </span>
                <span className="side-item-label">{c.label}</span>
                {c.status === "soon" && (
                  <span className="side-item-dot" title="Coming soon" aria-label="Coming soon" />
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
});
