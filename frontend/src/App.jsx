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
import { RoadmapPage } from "./pages/RoadmapPage";
import { useAgentChat } from "./hooks/useAgentChat";
import { useHealth } from "./hooks/useHealth";
import { useTheme } from "./hooks/useTheme";
import { useIsCompact, useIsMobile } from "./hooks/useMediaQuery";
import { AGENT_UI, COLLECTION_KEYS, VIEW_TITLES, isChatView } from "./lib/constants";

/* Signed-in user. Wire to real auth when the multi-user phase lands. */
const USER = { name: "Loganathan R", role: "Admin" };

export default function App() {
  const [view, setView] = useState("engineering");
  const [navOpen, setNavOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);

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

  /* Asking a question from a non-chat page (a capability row, a quick action)
     lands you in the agent with the answer already streaming. */
  const ask = useCallback((prompt) => {
    if (!chatView) setView("engineering");
    setPanelOpen(false);
    send(prompt);
  }, [chatView, send]);

  const startNewChat = useCallback(() => {
    if (!chatView) setView("engineering");
    setNavOpen(false);
    newChat();
  }, [chatView, newChat]);

  const openConvo = useCallback((id) => {
    const convoView = openConversation(id);
    if (convoView) setView(convoView);
    setPanelOpen(false);
  }, [openConversation]);

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

  /* Leaving the breakpoint that made a rail a drawer resets its open state. */
  useEffect(() => { if (!isMobile) setNavOpen(false); }, [isMobile]);
  useEffect(() => { if (!isCompact) setPanelOpen(false); }, [isCompact]);

  const page = () => {
    if (chatView) {
      return (
        <ChatWindow
          ui={ui}
          userName={USER.name.split(" ")[0]}
          messages={chat.messages}
          input={chat.input}
          setInput={chat.setInput}
          send={send}
          loading={chat.loading}
        />
      );
    }
    if (view === "dashboard") return <Dashboard setView={go} />;
    if (view === "knowledge") return <KnowledgeBase setView={go} />;
    if (view === "upload") return <UploadPage />;
    if (COLLECTION_KEYS.includes(view)) return <CollectionPage collection={view} setView={go} />;
    return <RoadmapPage id={view} />;
  };

  const drawerOpen = (isMobile && navOpen) || (isCompact && panelOpen);

  return (
    <Shell>
      <Sidebar
        view={view}
        onSelect={go}
        onNewChat={startNewChat}
        user={USER}
        open={navOpen}
      />

      <ShellMain>
        <TopHeader
          title={VIEW_TITLES[view] || "Vitech AI"}
          online={health ? health.status === "ok" : false}
          notifications={3}
          isDark={isDark}
          onToggleTheme={toggleTheme}
          onToggleSidebar={() => setNavOpen((v) => !v)}
          onTogglePanel={() => setPanelOpen((v) => !v)}
          showPanelToggle={chatView}
        />

        <Workspace>
          <WorkspaceMain scroll={!chatView}>{page()}</WorkspaceMain>

          {chatView && (
            <RightSidebar
              ui={ui}
              conversations={chat.conversations}
              activeId={chat.sessionId}
              onPick={ask}
              onOpenConversation={openConvo}
              onDeleteConversation={chat.deleteConversation}
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
