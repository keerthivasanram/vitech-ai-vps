import { memo, useCallback, useLayoutEffect, useRef } from "react";
import {
  CornerDownLeft, Globe, Paperclip, SendHorizontal, ShieldCheck,
  SlidersHorizontal, Sparkles,
} from "lucide-react";
import { useRipple } from "../hooks/useRipple";

// How tall the composer may grow before it scrolls instead, in px. Eight or so
// lines: enough that a pasted enquiry - the size, the open front, the face
// velocity, the filter, the construction - is readable in one glance, and not
// so much that it swallows the conversation above it.
const MAX_INPUT_H = 200;

/**
 * Composer: tool icons on the left, the input, then the Enter hint and the
 * green send button. Enter sends, Shift+Enter starts a new line; the button
 * mirrors Enter.
 *
 * IT IS A TEXTAREA, NOT AN INPUT, and that is the point. A single-line input
 * silently flattens a pasted multi-line requirement onto one unreadable line -
 * exactly the shape a real enquiry arrives in - so the one thing the user most
 * needs to check before sending is the one thing they cannot see. It grows with
 * its content up to MAX_INPUT_H and scrolls after that.
 */
export const ChatInput = memo(function ChatInput({ value, onChange, onSend, disabled }) {
  const canSend = !disabled && value.trim().length > 0;
  const { ripples, onPointerDown } = useRipple();

  const ref = useRef(null);

  // Height follows content: reset first, then measure, or the box can only ever
  // grow - deleting a line would leave the composer stretched around nothing.
  const fit = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_INPUT_H)}px`;
    el.style.overflowY = el.scrollHeight > MAX_INPUT_H ? "auto" : "hidden";
  }, []);

  // useLayoutEffect, not useEffect: this runs on every value change including
  // the reset to "" after a send, and measuring before paint keeps the box from
  // flashing at its old height.
  useLayoutEffect(fit, [value, fit]);

  const keyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (canSend) onSend();
    }
  };

  return (
    <div className="composer-wrap">
      <div className="composer">
        <textarea
          ref={ref}
          className="composer-input"
          rows={1}
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
