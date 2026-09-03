import { memo, useCallback, useEffect, useState } from "react";
import {
  Maximize2, Minimize2, Moon, PanelLeft, PanelLeftClose,
  PanelRight, PanelRightClose, Sun,
} from "lucide-react";

/** Fullscreen toggle, tracking real document state rather than a local guess. */
function useFullscreen() {
  const [isFull, setIsFull] = useState(() => !!document.fullscreenElement);

  // The user can leave fullscreen with Esc without touching our button, so the
  // icon has to follow the document rather than our own last click.
  useEffect(() => {
    const sync = () => setIsFull(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);

  const toggle = useCallback(async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch {
      /* browser refused (permissions/iframe) — leave state as-is */
    }
  }, []);

  return { isFull, toggle };
}

/**
 * The controls that used to sit in the top header, kept in the same place with
 * the header itself removed — no bar, no background, no border, no page title.
 *
 * The title is deliberately gone rather than moved: every page already renders
 * its own <h1> in .page-head, so the header was printing it a second time. What
 * is left here is only what has nowhere else to live: the two layout toggles,
 * the theme switch and fullscreen.
 */
export const ViewControls = memo(function ViewControls({
  isDark, onToggleTheme,
  onToggleNav, navHidden,
  onTogglePanel, showPanelToggle, panelOpen,
}) {
  const { isFull, toggle: toggleFull } = useFullscreen();

  return (
    <div className="viewbar">
      <div className="viewbar-l">
        <button
          type="button"
          className="ctl-btn"
          onClick={onToggleNav}
          aria-label={navHidden ? "Show navigation" : "Hide navigation"}
          aria-pressed={!navHidden}
          title={navHidden ? "Show navigation  [" : "Hide navigation  ["}
        >
          {navHidden
            ? <PanelLeft size={18} strokeWidth={1.7} aria-hidden="true" />
            : <PanelLeftClose size={18} strokeWidth={1.7} aria-hidden="true" />}
        </button>
      </div>

      <div className="viewbar-r">
        <button
          type="button"
          className="ctl-btn"
          onClick={onToggleTheme}
          aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
          aria-pressed={isDark}
          title={isDark ? "Light mode" : "Dark mode"}
        >
          {isDark
            ? <Sun size={18} strokeWidth={1.7} aria-hidden="true" />
            : <Moon size={18} strokeWidth={1.7} aria-hidden="true" />}
        </button>

        <button
          type="button"
          className="ctl-btn is-optional"
          onClick={toggleFull}
          aria-label={isFull ? "Exit fullscreen" : "Enter fullscreen"}
          title={isFull ? "Exit fullscreen" : "Fullscreen"}
        >
          {isFull
            ? <Minimize2 size={18} strokeWidth={1.7} aria-hidden="true" />
            : <Maximize2 size={18} strokeWidth={1.7} aria-hidden="true" />}
        </button>

        {/* Chat-history rail. Rendered only on views that have one. */}
        {showPanelToggle && (
          <button
            type="button"
            className={`ctl-btn${panelOpen ? " is-on" : ""}`}
            onClick={onTogglePanel}
            aria-label={panelOpen ? "Hide chat history" : "Show chat history"}
            aria-pressed={panelOpen}
            title={panelOpen ? "Hide chat history  ]" : "Show chat history  ]"}
          >
            {panelOpen
              ? <PanelRightClose size={18} strokeWidth={1.7} aria-hidden="true" />
              : <PanelRight size={18} strokeWidth={1.7} aria-hidden="true" />}
          </button>
        )}
      </div>
    </div>
  );
});
