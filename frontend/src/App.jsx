import { useCallback, useEffect, useState } from "react";
import { Shell, ShellMain, Workspace, WorkspaceMain, Scrim } from "./common/Layout";
import { Sidebar } from "./components/Sidebar";
import { TopHeader } from "./components/TopHeader";
import { ChatWindow } from "./components/ChatWindow";
import { RightSidebar } from "./components/RightSidebar";
import { Dashboard } from "./pages/Dashboard";
import { KnowledgeBase } from "./pages/KnowledgeBase";
import { CollectionPage } from "./pages/CollectionPage";
import { UploadPage } from "./pages/UploadPage";
import { ProfilePage } from "./pages/ProfilePage";
import { SettingsPage } from "./pages/SettingsPage";
import { LoginPage } from "./pages/LoginPage";
import { LiveHelpPage } from "./pages/LiveHelpPage";
import { RoadmapPage } from "./pages/RoadmapPage";
import { useAgentChat } from "./hooks/useAgentChat";
import { useHealth } from "./hooks/useHealth";
import { useTheme } from "./hooks/useTheme";
import { useIsCompact, useIsMobile } from "./hooks/useMediaQuery";
import { useAuth } from "./auth/AuthProvider";
import { AGENT_UI, COLLECTION_KEYS, VIEW_TITLES, isChatView } from "./lib/constants";

const PANEL_KEY = "vitech_panel";

/* The rail is maximized by default on a roomy screen and minimized on a narrow
   one, but an explicit choice always wins and is remembered. */
const initialPanel = () => {
  const saved = localStorage.getItem(PANEL_KEY);
  if (saved === "1") return true;
  if (saved === "0") return false;
  return window.innerWidth > 1024;
};

export default function App() {
  const [view, setView] = useState("engineering");
  const [navOpen, setNavOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(initialPanel);

  const { user, ready, login, logout } = useAuth();
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
    if (view === "dashboard") return <Dashboard key={view} setView={go} />;
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
    return <LoginPage onLogin={login} isDark={isDark} onToggleTheme={toggleTheme} />;
  }

  return (
    <Shell>
      <Sidebar
        view={view}
        onSelect={go}
        onNewChat={startNewChat}
        user={user}
        open={navOpen}
        isDark={isDark}
      />

      <ShellMain>
        <TopHeader
          title={VIEW_TITLES[view] || "Vitech AI"}
          online={health ? health.status === "ok" : false}
          notifications={3}
          isDark={isDark}
          onToggleTheme={toggleTheme}
          onToggleSidebar={() => setNavOpen((v) => !v)}
          onTogglePanel={togglePanel}
          showPanelToggle={chatView}
          panelOpen={panelOpen}
          flat={chatView}
        />

        <Workspace chat={chatView}>
          <WorkspaceMain scroll={!chatView}>{page()}</WorkspaceMain>

          {chatView && (
            <RightSidebar
              conversations={chat.conversations}
              activeId={chat.sessionId}
              onOpenConversation={openConvo}
              onDeleteConversation={chat.deleteConversation}
              onNewChat={startNewChat}
              onMinimize={minimizePanel}
              onViewAll={() => go("knowledge")}
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
