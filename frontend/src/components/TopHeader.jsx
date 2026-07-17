import { memo, useCallback, useState } from "react";
import { Bell, Maximize2, Menu, Minimize2, Moon, PanelRight, Search, Sun } from "lucide-react";
import { StatusBadge } from "../common/Badge";

/** Fullscreen toggle, tracking real document state rather than a local guess. */
function useFullscreen() {
  const [isFull, setIsFull] = useState(() => !!document.fullscreenElement);

  const toggle = useCallback(async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
      setIsFull(!!document.fullscreenElement);
    } catch {
      /* browser refused (permissions/iframe) — leave state as-is */
    }
  }, []);

  return { isFull, toggle };
}

/**
 * Header: page title + live badge on the left; search, notifications,
 * dark mode and fullscreen on the right.
 */
export const TopHeader = memo(function TopHeader({
  title, online, notifications = 0,
  isDark, onToggleTheme, onToggleSidebar, onTogglePanel, showPanelToggle,
}) {
  const { isFull, toggle: toggleFull } = useFullscreen();

  return (
    <header className="topheader">
      <div className="topheader-l">
        <button
          type="button"
          className="topheader-burger"
          onClick={onToggleSidebar}
          aria-label="Open navigation"
        >
          <Menu size={20} strokeWidth={1.8} aria-hidden="true" />
        </button>

        <h1 className="topheader-title">{title}</h1>
        <StatusBadge online={online} />
      </div>

      <div className="topheader-r">
        {/* Search and fullscreen drop out on narrow screens so the page title
            keeps its room — see .icon-btn.is-optional in App.css. */}
        <button type="button" className="icon-btn is-optional" aria-label="Search">
          <Search size={20} strokeWidth={1.8} aria-hidden="true" />
        </button>

        <button type="button" className="icon-btn" aria-label={`Notifications: ${notifications} unread`}>
          <Bell size={20} strokeWidth={1.8} aria-hidden="true" />
          {notifications > 0 && <span className="icon-btn-badge">{notifications}</span>}
        </button>

        <button
          type="button"
          className={`icon-btn${isDark ? " is-on" : ""}`}
          onClick={onToggleTheme}
          aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
          aria-pressed={isDark}
        >
          {isDark
            ? <Sun size={20} strokeWidth={1.8} aria-hidden="true" />
            : <Moon size={20} strokeWidth={1.8} aria-hidden="true" />}
        </button>

        <button
          type="button"
          className="icon-btn is-optional"
          onClick={toggleFull}
          aria-label={isFull ? "Exit fullscreen" : "Enter fullscreen"}
        >
          {isFull
            ? <Minimize2 size={20} strokeWidth={1.8} aria-hidden="true" />
            : <Maximize2 size={20} strokeWidth={1.8} aria-hidden="true" />}
        </button>

        {/* Only rendered on views that have a right rail, and only visible
            below 1024px where that rail becomes a drawer. */}
        {showPanelToggle && (
          <button
            type="button"
            className="icon-btn topheader-panel-btn"
            onClick={onTogglePanel}
            aria-label="Open agent panel"
          >
            <PanelRight size={20} strokeWidth={1.8} aria-hidden="true" />
          </button>
        )}
      </div>
    </header>
  );
});
