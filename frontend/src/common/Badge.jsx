import { memo } from "react";

/**
 * Pill badge.
 * tone: ok | info | gen | cat | warn | soft
 */
export const Badge = memo(function Badge({ tone = "soft", icon: Icon, children, className = "" }) {
  return (
    <span className={`badge ${tone} ${className}`.trim()}>
      {Icon && <Icon size={12} strokeWidth={2} aria-hidden="true" />}
      {children}
    </span>
  );
});

/** Live/offline status pill used in the header next to the page title. */
export const StatusBadge = memo(function StatusBadge({ online, label }) {
  return (
    <span className={`status-badge${online ? "" : " is-off"}`}>
      <span className="status-dot" aria-hidden="true" />
      {label ?? (online ? "Online" : "Offline")}
    </span>
  );
});
