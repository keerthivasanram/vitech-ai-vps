import { memo, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Bot, Check, CheckCheck, Copy, FileDown, FileText, MoreHorizontal, Sparkles,
  ThumbsDown, ThumbsUp,
} from "lucide-react";
import { Answer } from "../lib/markdown";
import { QuotationCard } from "./QuotationCard";
import { THINK_LABELS } from "../lib/constants";

/* POST a specification payload to the backend and download the returned PDF.
   Mirrors QuotationCard's downloadQuotePdf — the backend renders it, nothing is
   computed in the UI. Falls back to the raw answer text if there's no payload. */
async function downloadSpecPdf(spec, fallbackText) {
  const body = spec || { text: fallbackText };
  try {
    const resp = await fetch("/api/specification/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) return;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const name = (spec?.category_label || "specification").replace(/\s+/g, "_");
    a.href = url;
    a.download = `${name}_specification.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch {
    /* offline / backend down — no-op */
  }
}

/* Staged "thinking" label — advances while the first token is pending. */
const Thinking = memo(function Thinking() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((v) => Math.min(v + 1, THINK_LABELS.length - 1)), 2000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="thinking" role="status" aria-live="polite">
      <span className="thinking-label">{THINK_LABELS[i]}</span>
    </div>
  );
});

/* Reaction row under an assistant reply: copy / up / down / more. */
const Reactions = memo(function Reactions({ text }) {
  const [copied, setCopied] = useState(false);
  const [vote, setVote] = useState(null);

  const copy = () => {
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    });
  };

  return (
    <div className="msg-actions">
      <button
        type="button"
        className="msg-action"
        onClick={copy}
        aria-label={copied ? "Copied" : "Copy reply"}
      >
        {copied
          ? <Check size={15} strokeWidth={1.8} aria-hidden="true" />
          : <Copy size={15} strokeWidth={1.8} aria-hidden="true" />}
      </button>
      <button
        type="button"
        className={`msg-action${vote === "up" ? " is-on" : ""}`}
        onClick={() => setVote((v) => (v === "up" ? null : "up"))}
        aria-label="Good response"
        aria-pressed={vote === "up"}
      >
        <ThumbsUp size={15} strokeWidth={1.8} aria-hidden="true" />
      </button>
      <button
        type="button"
        className={`msg-action${vote === "down" ? " is-on" : ""}`}
        onClick={() => setVote((v) => (v === "down" ? null : "down"))}
        aria-label="Bad response"
        aria-pressed={vote === "down"}
      >
        <ThumbsDown size={15} strokeWidth={1.8} aria-hidden="true" />
      </button>
      <button type="button" className="msg-action" aria-label="More options">
        <MoreHorizontal size={15} strokeWidth={1.8} aria-hidden="true" />
      </button>
    </div>
  );
});

/* Download-as-PDF control shown below a generated specification. */
const SpecActions = memo(function SpecActions({ spec, text }) {
  return (
    <div className="spec-actions">
      <button
        type="button"
        className="spec-pdf-btn"
        onClick={() => downloadSpecPdf(spec, text)}
        aria-label="Download specification as PDF"
        title="Download specification as PDF"
      >
        <FileDown size={15} strokeWidth={1.8} aria-hidden="true" />
        Download PDF
      </button>
    </div>
  );
});

/* Citeable source files. Each opens its extracted content in the record
   inspector — clicking hands the source up to the chat window's onOpenSource. */
const Sources = memo(function Sources({ sources, onOpenSource }) {
  return (
    <div className="sources">
      <span className="sources-title">Source files</span>
      {sources.map((s, i) => (
        <button
          key={s.label || i}
          type="button"
          className="source is-open"
          onClick={() => onOpenSource?.(s)}
          title={`Open ${s.label}`}
        >
          <FileText size={12} strokeWidth={1.9} aria-hidden="true" />
          <span className="source-name">{s.label}</span>
        </button>
      ))}
    </div>
  );
});

/* Badges derived from which tools ran, then the answer itself. */
const AssistantBody = memo(function AssistantBody({ data, onOpenSource }) {
  if (data.small_talk) return <Answer text={data.answer} />;
  return (
    <>
      <div className="badge-row">
        {data.spec_mode === "knowledge" && <span className="badge gen">Consulting Engineer</span>}
        {data.spec_mode === "data" && <span className="badge cat">ATS Quotation Engineer</span>}
        {!data.spec_mode && data.grounded === false && <span className="badge gen">General knowledge</span>}
        {!data.spec_mode && data.grounded && data.category_label && (
          <span className="badge cat">{data.category_label}</span>
        )}
        {data.spec_mode && data.category_label && <span className="badge info">{data.category_label}</span>}
        {data.intent && <span className="badge info">{data.intent}</span>}
        {data.deterministic && <span className="badge ok">Deterministic</span>}
        {data.llm && <span className="badge soft">via {data.llm}</span>}
      </div>

      <Answer text={data.answer} />
      {data.quotation && <QuotationCard q={data.quotation} />}
      {data.spec && <SpecActions spec={data.spec} text={data.answer} />}

      {data.sources?.length > 0 && (
        <Sources sources={data.sources} onOpenSource={onOpenSource} />
      )}
    </>
  );
});

/** One transcript row — user bubble on the right, assistant card on the left. */
export const ChatBubble = memo(function ChatBubble({ msg, agentName, onOpenSource }) {
  const isUser = msg.role === "user";

  const row = (children) => (
    <motion.div
      className={`msg-row${isUser ? " is-user" : ""}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  );

  if (isUser) {
    return row(
      <div className="msg-user-col">
        {msg.time && <span className="msg-time">{msg.time}</span>}
        <div className="bubble-user">
          <Answer text={msg.text} />
          <div className="bubble-ticks">
            <CheckCheck size={14} strokeWidth={2} aria-label="Sent" />
          </div>
        </div>
      </div>
    );
  }

  const pending = msg.streaming && !msg.text;

  return row(
    <>
      <div className={`msg-ast-av${pending ? " is-pending" : ""}`}>
        <Bot size={20} strokeWidth={1.8} aria-hidden="true" />
      </div>

      <div className="bubble-ast">
        <div className="bubble-ast-head">
          <span className="bubble-ast-name">{agentName}</span>
          <span className="ai-tag">
            <Sparkles size={9} strokeWidth={2.4} aria-hidden="true" />
            AI
          </span>
          {msg.time && <span className="bubble-ast-time">{msg.time}</span>}
        </div>

        {msg.data
          ? <AssistantBody data={msg.data} onOpenSource={onOpenSource} />
          : pending
            ? <Thinking />
            : <Answer text={msg.text} streaming={msg.streaming} />}

        {!msg.streaming && msg.text && <Reactions text={msg.text} />}
      </div>
    </>
  );
});
