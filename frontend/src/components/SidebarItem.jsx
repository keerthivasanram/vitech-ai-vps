import { memo } from "react";
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
