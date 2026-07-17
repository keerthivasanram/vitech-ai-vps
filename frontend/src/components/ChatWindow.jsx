import { memo, useEffect, useRef } from "react";
import { HeroCard } from "./HeroCard";
import { QuickActions } from "./QuickActions";
import { ChatBubble } from "./ChatBubble";
import { ChatInput } from "./ChatInput";

/**
 * The centre column: hero + quick actions scroll above a growing transcript,
 * with the composer pinned to the bottom of the surface.
 */
export const ChatWindow = memo(function ChatWindow({
  ui, userName, messages, input, setInput, send, loading,
}) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  return (
    <div className="chat-surface">
      <div className="chat-scroll">
        <HeroCard userName={userName} title={ui.hero} subtitle={ui.sub} />
        <QuickActions onPick={send} disabled={loading} />

        {messages.length > 0 && (
          <div className="transcript" role="log" aria-live="polite" aria-label="Conversation">
            {messages.map((m) => (
              <ChatBubble key={m.id} msg={m} agentName={ui.name} />
            ))}
          </div>
        )}

        <div ref={endRef} />
      </div>

      <ChatInput value={input} onChange={setInput} onSend={() => send()} disabled={loading} />
    </div>
  );
});
