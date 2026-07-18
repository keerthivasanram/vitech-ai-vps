import { memo } from "react";
import {
  CornerDownLeft, Globe, Paperclip, SendHorizontal, ShieldCheck,
  SlidersHorizontal, Sparkles,
} from "lucide-react";
import { useRipple } from "../hooks/useRipple";

/**
 * Composer: tool icons on the left, the input, then the Enter hint and the
 * green send button. Enter sends; the button mirrors it.
 */
export const ChatInput = memo(function ChatInput({ value, onChange, onSend, disabled }) {
  const canSend = !disabled && value.trim().length > 0;
  const { ripples, onPointerDown } = useRipple();

  const keyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (canSend) onSend();
    }
  };

  return (
    <div className="composer-wrap">
      <div className="composer">
        <input
          className="composer-input"
          value={value}
          placeholder="Ask anything or type your message..."
          aria-label="Message the agent"
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={keyDown}
        />

        <div className="composer-tools">
          <button type="button" className="composer-tool" aria-label="Attach a file">
            <Paperclip size={18} strokeWidth={1.8} aria-hidden="true" />
          </button>
          <button type="button" className="composer-tool" aria-label="Browse the web">
            <Globe size={18} strokeWidth={1.8} aria-hidden="true" />
          </button>
          <button type="button" className="composer-tool" aria-label="Tools and settings">
            <SlidersHorizontal size={18} strokeWidth={1.8} aria-hidden="true" />
          </button>
          <button type="button" className="composer-tool is-accent" aria-label="Improve the prompt">
            <Sparkles size={18} strokeWidth={1.8} aria-hidden="true" />
          </button>
        </div>

        <div className="composer-r">
          <span className="enter-hint" aria-hidden="true">
            Enter <CornerDownLeft size={11} strokeWidth={2} />
          </span>
          <button
            type="button"
            className="send-btn"
            onClick={onSend}
            onPointerDown={onPointerDown}
            disabled={!canSend}
            aria-label="Send message"
          >
            <SendHorizontal size={19} strokeWidth={1.9} aria-hidden="true" />
            {ripples.map((r) => (
              <span key={r.id} className="ripple" style={{ left: r.x, top: r.y }} aria-hidden="true" />
            ))}
          </button>
        </div>
      </div>

      <p className="composer-foot">
        <ShieldCheck size={13} strokeWidth={1.8} aria-hidden="true" />
        Enterprise-grade security
        <span className="sep foot-extra">·</span>
        <span className="foot-extra">Your data is protected</span>
        <span className="sep">·</span>
        Powered by Vitech AI
      </p>
    </div>
  );
});
