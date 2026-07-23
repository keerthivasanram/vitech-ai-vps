import { memo, useCallback, useEffect, useRef, useState } from "react";
import { HeroCard } from "./HeroCard";
import { QuickActions } from "./QuickActions";
import { ChatBubble } from "./ChatBubble";
import { ChatInput } from "./ChatInput";
import { OfferDrawer } from "./OfferDrawer";

/**
 * The centre column: hero + quick actions scroll above a growing transcript,
 * with the composer pinned to the bottom of the surface.
 */
export const ChatWindow = memo(function ChatWindow({
  ui, userName, messages, input, setInput, send, loading,
}) {
  const endRef = useRef(null);
  // The record inspector opened from a reply's source-file chip.
  const [openRec, setOpenRec] = useState(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  /* Open a cited source file's extracted content in the inspector. lookup_project
     already carries the full record; a bare filename is resolved to its record
     via the backend (graceful no-op if it's not found / backend is down). */
  const handleOpenSource = useCallback(async (source) => {
    if (source?.record) { setOpenRec(source.record); return; }
    if (!source?.sourceFile) return;
    try {
      const resp = await fetch(`/api/offers/by-source/${encodeURIComponent(source.sourceFile)}`);
      if (!resp.ok) return;
      const rec = await resp.json();
      if (rec && rec.id) setOpenRec(rec);
    } catch {
      /* backend down — no-op */
    }
  }, []);

  return (
    <div className="chat-surface">
      <div className="chat-scroll">
        <HeroCard userName={userName} title={ui.hero} subtitle={ui.sub} />
        <QuickActions onPick={send} disabled={loading} />

        {messages.length > 0 && (
          <div className="transcript" role="log" aria-live="polite" aria-label="Conversation">
            {messages.map((m) => (
              <ChatBubble key={m.id} msg={m} agentName={ui.name} onOpenSource={handleOpenSource} />
            ))}
          </div>
        )}

        <div ref={endRef} />
      </div>

      <ChatInput value={input} onChange={setInput} onSend={() => send()} disabled={loading} />

      {openRec && <OfferDrawer rec={openRec} onClose={() => setOpenRec(null)} />}
    </div>
  );
});
