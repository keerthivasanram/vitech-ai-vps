import { memo, useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
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

  const started = messages.length > 0;

  return (
    <div className={`chat-surface${started ? " is-active" : ""}`}>
      <div className="chat-scroll">
        {/* The welcome state (hero + quick actions) only makes sense before the
            first message — once a conversation is under way it collapses away
            like Claude/ChatGPT, handing its space straight to the transcript. */}
        <AnimatePresence initial={false}>
          {!started && (
            <motion.div
              key="welcome"
              className="chat-welcome"
              initial={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0, marginBottom: 0 }}
              transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
            >
              <HeroCard userName={userName} title={ui.hero} subtitle={ui.sub} />
              <QuickActions onPick={send} disabled={loading} />
            </motion.div>
          )}
        </AnimatePresence>

        {started && (
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
