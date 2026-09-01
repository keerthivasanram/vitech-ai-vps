import { memo } from "react";

/**
 * Three-column shell: sidebar rail, main column, right rail.
 * Below 1024px the right rail becomes a drawer; below 768px the sidebar does
 * too — both handled in App.css, so this stays pure structure.
 */
export const Shell = memo(function Shell({ children }) {
  return <div className="shell">{children}</div>;
});

/** Everything right of the sidebar: header on top, workspace below. */
export const ShellMain = memo(function ShellMain({ children }) {
  return <div className="shell-main">{children}</div>;
});

/** The padded row holding the main column and the right rail. `chat` tightens
    the bottom padding so the composer sits close to the bottom (ChatGPT-style). */
export const Workspace = memo(function Workspace({ chat = false, children }) {
  return <div className={`workspace${chat ? " is-chat" : ""}`}>{children}</div>;
});

/** Main column. `scroll` lets non-chat pages own their scrolling. */
export const WorkspaceMain = memo(function WorkspaceMain({ scroll = false, children }) {
  return (
    <main className={`workspace-main${scroll ? " workspace-scroll" : ""}`}>
      {children}
    </main>
  );
});

/** Click-catcher behind an open mobile drawer. */
export const Scrim = memo(function Scrim({ onClose, label = "Close" }) {
  return <button type="button" className="scrim" aria-label={label} onClick={onClose} />;
});
