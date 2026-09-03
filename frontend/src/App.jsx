import { useCallback, useEffect, useState } from "react";
import { Shell, ShellMain, Workspace, WorkspaceMain, Scrim } from "./common/Layout";
import { Sidebar } from "./components/Sidebar";
import { ViewControls } from "./components/ViewControls";
import { ChatWindow } from "./components/ChatWindow";
import { RightSidebar } from "./components/RightSidebar";
import { Dashboard } from "./pages/Dashboard";
import { KnowledgeBase } from "./pages/KnowledgeBase";
import { CollectionPage } from "./pages/CollectionPage";
import { UploadPage } from "./pages/UploadPage";
import { ProfilePage } from "./pages/ProfilePage";
import { SettingsPage } from "./pages/SettingsPage";
import { DrawingStudio } from "./pages/DrawingStudio";
import { SitePlacement } from "./pages/SitePlacement";
import { LoginPage } from "./pages/LoginPage";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { PackageCenter } from "./pages/PackageCenter";
import { DevOpsConsole } from "./pages/DevOpsConsole";
import { LiveHelpPage } from "./pages/LiveHelpPage";
import { RoadmapPage } from "./pages/RoadmapPage";
import { useAgentChat } from "./hooks/useAgentChat";
import { useHealth } from "./hooks/useHealth";
import { useTheme } from "./hooks/useTheme";
import { useIsCompact, useIsMobile } from "./hooks/useMediaQuery";
import { useAuth } from "./auth/AuthProvider";
import { SESSION_EXPIRED } from "./lib/api";
import { AGENT_UI, COLLECTION_KEYS, VIEW_TITLES, isChatView } from "./lib/constants";

const PANEL_KEY = "vitech_panel";
const NAV_KEY = "vitech_nav";

/* The rail is maximized by default on a roomy screen and minimized on a narrow
   one, but an explicit choice always wins and is remembered. */
const initialPanel = () => {
  const saved = localStorage.getItem(PANEL_KEY);
  if (saved === "1") return true;
  if (saved === "0") return false;
  return window.innerWidth > 1024;
};

/* The navigation rail collapses to an icon strip. Same contract as the panel:
   a remembered explicit choice wins, otherwise it follows the screen. */
const initialNav = () => {
  const saved = localStorage.getItem(NAV_KEY);
  if (saved === "1") return true;
  if (saved === "0") return false;
  return window.innerWidth < 1280;
};

export default function App() {
  const [view, setView] = useState("engineering");
  const [navOpen, setNavOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(initialPanel);
  const [navCollapsed, setNavCollapsed] = useState(initialNav);

  const { user, ready, login, logout, changePassword } = useAuth();
  // Set when a session ends mid-use, so the login screen can explain itself
  // instead of appearing without reason.
  const [sessionNotice, setSessionNotice] = useState("");

  /* The fetch interceptor fires this when a request comes back 401 — the
     session expired, was revoked, or the server was rebuilt. Explaining that is
     the whole improvement: without it the user is dropped on a login screen
     with no reason and assumes the application broke. */
  useEffect(() => {
    const onExpired = () =>
      setSessionNotice("Your session ended. Please sign in again.");
    window.addEventListener(SESSION_EXPIRED, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED, onExpired);
  }, []);
  const health = useHealth();
  const { isDark, toggle: toggleTheme } = useTheme();
  const isMobile = useIsMobile();
  const isCompact = useIsCompact();

  const chat = useAgentChat(view, health);
  const { send, newChat, openConversation } = chat;

  const ui = AGENT_UI[view] || AGENT_UI.engineering;
  const chatView = isChatView(view);

  /* Navigating closes the mobile drawers — otherwise the rail covers the page
     you just asked for. */
  const go = useCallback((next) => {
    setView(next);
    setNavOpen(false);
    setPanelOpen(false);
  }, []);

  const startNewChat = useCallback(() => {
    if (!chatView) setView("engineering");
    setNavOpen(false);
    newChat();
  }, [chatView, newChat]);

  const openConvo = useCallback((id) => {
    const convoView = openConversation(id);
    if (convoView) setView(convoView);
    // Only a drawer needs dismissing; on desktop the rail stays put.
    if (isCompact) setPanelOpen(false);
  }, [openConversation, isCompact]);

  /* Persist only a deliberate maximize/minimize. Writing this from an effect
     instead would record the responsive default on first paint, so opening the
     app once in a narrow window would stick as "minimized" forever. */
  const togglePanel = useCallback(() => {
    setPanelOpen((v) => {
      localStorage.setItem(PANEL_KEY, v ? "0" : "1");
      return !v;
    });
  }, []);

  const minimizePanel = useCallback(() => {
    localStorage.setItem(PANEL_KEY, "0");
    setPanelOpen(false);
  }, []);

  /* One control, two meanings by breakpoint: on a phone the rail is a drawer,
     so this opens it; on a desktop it collapses the rail to an icon strip. */
  const toggleNav = useCallback(() => {
    if (isMobile) { setNavOpen((v) => !v); return; }
    setNavCollapsed((v) => {
      localStorage.setItem(NAV_KEY, v ? "0" : "1");
      return !v;
    });
  }, [isMobile]);

  /* Esc closes whichever drawer is open. */
  useEffect(() => {
    if (!navOpen && !panelOpen) return;
    const onKey = (e) => {
      if (e.key !== "Escape") return;
      setNavOpen(false);
      setPanelOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navOpen, panelOpen]);

  /* [ and ] hide/show the two rails. Ignored while typing, so they never eat a
     bracket the user meant for the composer or a studio field. */
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== "[" && e.key !== "]") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const el = e.target;
      const tag = el?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el?.isContentEditable) return;
      e.preventDefault();
      if (e.key === "[") toggleNav();
      else togglePanel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleNav, togglePanel]);

  /* The header used to name the view on screen; the browser tab does it now. */
  useEffect(() => {
    const name = VIEW_TITLES[view];
    document.title = name ? `${name} \u2014 Vitech AI` : "Vitech AI";
  }, [view]);

  /* Leaving mobile closes the nav drawer; entering the drawer breakpoint closes
     the rail so it never covers the chat unasked. */
  useEffect(() => { if (!isMobile) setNavOpen(false); }, [isMobile]);
  useEffect(() => { if (isCompact) setPanelOpen(false); }, [isCompact]);

  /* `key={view}` forces a fresh mount per view (rather than React reconciling
     same-tag roots across branches, e.g. two <div className="page-inner">),
     so the page-fade-in animation on each page's root actually replays on
     every navigation instead of only on first load. */
  const page = () => {
    if (chatView) {
      return (
        <ChatWindow
          key={view}
          ui={ui}
          userName={(user?.name || "there").split(" ")[0]}
          messages={chat.messages}
          input={chat.input}
          setInput={chat.setInput}
          send={send}
          loading={chat.loading}
        />
      );
    }
    if (view === "drawing") return <DrawingStudio key={view} isDark={isDark} />;
    if (view === "siting") return <SitePlacement key={view} />;
    if (view === "dashboard") return <Dashboard key={view} setView={go} />;
    if (view === "packages") return <PackageCenter key={view} />;
    // Service-provider console. The nav hides it from engineers and the
    // server refuses them anyway, so this is a straight route.
    if (view === "devops") return <DevOpsConsole key={view} />;
    if (view === "knowledge") return <KnowledgeBase key={view} setView={go} />;
    if (view === "upload") return <UploadPage key={view} />;
    if (view === "profile") {
      return (
        <ProfilePage
          key={view}
          user={user}
          health={health}
          sessionId={chat.sessionId}
          conversationCount={chat.conversations.length}
          isDark={isDark}
          onToggleTheme={toggleTheme}
          onLogout={logout}
        />
      );
    }
    if (view === "settings") {
      return (
        <SettingsPage
          key={view}
          user={user}
          health={health}
          sessionId={chat.sessionId}
          isDark={isDark}
          onToggleTheme={toggleTheme}
          onLogout={logout}
        />
      );
    }
    if (view === "live_help") {
      return <LiveHelpPage key={view} health={health} onOpenAgent={() => go("engineering")} />;
    }
    if (COLLECTION_KEYS.includes(view)) return <CollectionPage key={view} collection={view} setView={go} />;
    return <RoadmapPage key={view} id={view} />;
  };

  const drawerOpen = (isMobile && navOpen) || (isCompact && panelOpen);

  /* Auth gate. All hooks above run unconditionally (Rules of Hooks); only the
     render branches. `ready` prevents a login flash before the stored session
     is read on first paint. */
  if (!ready) return null;
  if (!user) {
    return (
      <LoginPage
        onLogin={async (creds) => {
          const res = await login(creds);
          if (res.ok) setSessionNotice("");
          return res;
        }}
        notice={sessionNotice}
        isDark={isDark}
        onToggleTheme={toggleTheme}
      />
    );
  }

  /* MANDATORY password change. Rendered INSTEAD of the application, not beside
     it: an account still on its issued password is a credential someone else
     may have seen, so it must not reach the engineering data. A dismissible
     banner would make the protection optional. The server sets the flag; this
     only honours it, and the routes stay protected either way. */
  if (user.mustChangePassword) {
    return (
      <ChangePasswordPage
        username={user.username}
        onSubmit={changePassword}
        onLogout={logout}
        isDark={isDark}
        onToggleTheme={toggleTheme}
      />
    );
  }

  return (
    <Shell>
      <Sidebar
        view={view}
        onSelect={go}
        onNewChat={startNewChat}
        user={user}
        open={navOpen}
        collapsed={!isMobile && navCollapsed}
        online={health ? health.status === "ok" : false}
        isDark={isDark}
      />

      <ShellMain>
        <ViewControls
          isDark={isDark}
          onToggleTheme={toggleTheme}
          onToggleNav={toggleNav}
          navHidden={isMobile ? !navOpen : navCollapsed}
          onTogglePanel={togglePanel}
          showPanelToggle={chatView}
          panelOpen={panelOpen}
        />

        <Workspace chat={chatView}>
          <WorkspaceMain scroll={!chatView}>{page()}</WorkspaceMain>

          {chatView && (
            <RightSidebar
              conversations={chat.conversations.filter((c) => c.view === view)}
              activeId={chat.sessionId}
              onOpenConversation={openConvo}
              onDeleteConversation={chat.deleteConversation}
              onNewChat={startNewChat}
              onMinimize={minimizePanel}
              open={panelOpen}
            />
          )}
        </Workspace>
      </ShellMain>

      {drawerOpen && (
        <Scrim onClose={() => { setNavOpen(false); setPanelOpen(false); }} />
      )}
    </Shell>
  );
}
