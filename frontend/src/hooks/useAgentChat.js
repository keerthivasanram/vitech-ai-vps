import { useCallback, useEffect, useRef, useState } from "react";
import { agentUrl, isChatView, DETERMINISTIC_TOOLS } from "../lib/constants";
import { fmtTime, newId, titleFrom } from "../lib/format";

const SESSION_KEY = "ats_session";
const CONVO_KEY = "vitech_convos";
const CONVO_LIMIT = 20;

/* Flowise reports each tool call as {tool, toolInput, toolOutput}; toolOutput is
   a JSON string of our backend's response. Parse it defensively. */
function parseOutput(raw) {
  if (raw == null) return null;
  if (typeof raw === "object") return raw;
  try { return JSON.parse(raw); } catch { return null; }
}

/* Pull the citeable source files out of the tool outputs, as things the UI can
   open. lookup_project carries the full record (opens directly in the inspector);
   generate_specification / retrieve_knowledge carry only a filename, opened by
   resolving it to its record on click. Deduped, most useful first. */
function collectSources(calls) {
  const out = [];
  const seen = new Set();
  const push = (key, item) => {
    if (!key || seen.has(key)) return;
    seen.add(key);
    out.push(item);
  };
  for (const c of calls) {
    const o = parseOutput(c.toolOutput);
    if (!o) continue;
    if (c.tool === "lookup_project" && Array.isArray(o.records)) {
      for (const r of o.records) {
        push(r.id || r.source_file, {
          label: r.source_file || r.id,
          record: r,               // full record — open in the drawer with no fetch
        });
      }
    } else if (c.tool === "generate_specification" && Array.isArray(o.sources)) {
      for (const sf of o.sources) push(sf, { label: sf, sourceFile: sf });
    } else if (c.tool === "retrieve_knowledge" && Array.isArray(o.results)) {
      for (const h of o.results) {
        if (h.source_file) push(h.source_file, { label: h.source_file, sourceFile: h.source_file });
      }
    }
  }
  return out;
}

/* True once generate_quotation actually produced a quotation (not a guard
   "need_requirement" bounce), plus the payload the QuotationCard + PDF route
   consume. This is what surfaces the "Download PDF" button under a quote. */
function findQuote(calls) {
  for (const c of calls) {
    if (c.tool !== "generate_quotation") continue;
    const o = parseOutput(c.toolOutput);
    if (o && o.ok !== false && o.price && (o.ref || o.headline)) return o;
  }
  return null;
}

/* True once generate_specification actually produced a structured spec (not a
   guard "need_requirement" bounce), plus the payload we hand to the PDF route. */
function findSpec(calls) {
  for (const c of calls) {
    if (c.tool !== "generate_specification") continue;
    const o = parseOutput(c.toolOutput);
    if (o && (o.spec_markdown || (o.technical_details && o.technical_details.length))) {
      return o;
    }
  }
  return null;
}

/* Shape the agent's reply the way <AssistantBody> expects: it renders
   data.answer, so `answer` is required — without it the reply renders blank.
   The badges then fall out of which tools ran: no tools = Mode A consulting,
   a spec/quote tool = Mode B deterministic project work.

   `calls` is the raw Flowise usedTools array ({tool, toolInput, toolOutput}). */
function agentData(answer, calls, llm) {
  const tools = calls.map((c) => c.tool).filter(Boolean);
  const deterministic = tools.some((t) => DETERMINISTIC_TOOLS.includes(t));
  const spec = findSpec(calls);
  const quotation = findQuote(calls);
  const sources = collectSources(calls);
  return {
    answer,
    llm,
    deterministic,
    grounded: tools.length > 0,
    spec_mode: deterministic ? "data" : tools.length === 0 ? "knowledge" : undefined,
    intent: tools.length ? tools.join(" · ") : undefined,
    spec,                                  // structured spec payload → PDF (null if none)
    quotation,                             // structured quote payload → QuotationCard + PDF
    sources: sources.length ? sources : undefined,
  };
}

const readConvos = () => {
  try { return JSON.parse(localStorage.getItem(CONVO_KEY)) || []; }
  catch { return []; }
};

/**
 * Owns the agent conversation: transcript, streaming, session rotation and the
 * locally-persisted conversation list that feeds the Recent Conversations panel.
 *
 * Conversation memory itself lives in Flowise, keyed by chatId (= sessionId).
 * We persist the transcript locally so reopening a conversation restores both
 * the visible history AND the agent's memory (same chatId).
 */
export function useAgentChat(view, health) {
  const [sessionId, setSessionId] = useState(
    () => localStorage.getItem(SESSION_KEY) || newId()
  );
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversations, setConversations] = useState(readConvos);

  const prevChatView = useRef(view);

  useEffect(() => { localStorage.setItem(SESSION_KEY, sessionId); }, [sessionId]);

  // Switching directly between the two chat agents starts a fresh transcript +
  // memory so Engineering and Quotation conversations never blend.
  useEffect(() => {
    if (!isChatView(view)) return;
    if (isChatView(prevChatView.current) && view !== prevChatView.current) {
      setSessionId(newId());
      setMessages([]);
    }
    prevChatView.current = view;
  }, [view]);

  /* Persist the transcript against its sessionId. Called once a turn settles,
     never per token. */
  const persist = useCallback((id, list, forView) => {
    const firstUser = list.find((m) => m.role === "user");
    if (!firstUser) return;
    setConversations((prev) => {
      const entry = {
        id,
        view: forView,
        title: titleFrom(firstUser.text),
        updatedAt: new Date().toISOString(),
        messages: list,
      };
      const next = [entry, ...prev.filter((c) => c.id !== id)].slice(0, CONVO_LIMIT);
      try { localStorage.setItem(CONVO_KEY, JSON.stringify(next)); } catch { /* quota — skip */ }
      return next;
    });
  }, []);

  const send = useCallback(
    async (q) => {
      const text = (q ?? input).trim();
      if (!text || loading) return;

      setInput("");
      setLoading(true);

      const userMsg = { id: newId(), role: "user", text, time: fmtTime() };
      const astId = newId();
      // Track the running transcript outside state so we can persist it at the
      // end without waiting for a re-render.
      let running = [];
      setMessages((m) => {
        running = [...m, userMsg, { id: astId, role: "assistant", text: "", streaming: true }];
        return running;
      });

      const patch = (p) =>
        setMessages((m) => {
          running = m.map((x) => (x.id === astId ? { ...x, ...p } : x));
          return running;
        });

      // Flowise keys conversation memory by chatId — reuse the session so the
      // agent remembers context across turns.
      const body = JSON.stringify({ question: text, streaming: true, chatId: sessionId });

      try {
        const resp = await fetch(agentUrl(view), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
        });
        if (!resp.ok || !resp.body) throw new Error("no stream");

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = "", acc = "", calls = [];
        // coalesce tokens: render at most once per animation frame, not per token
        let raf = 0;
        const flush = () => { raf = 0; patch({ text: acc }); };
        const schedule = () => { if (!raf) raf = requestAnimationFrame(flush); };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          let nl;
          // Flowise SSE record: "message:\ndata:{"event":..,"data":..}", split on blank line
          while ((nl = buf.indexOf("\n\n")) >= 0) {
            const raw = buf.slice(0, nl);
            buf = buf.slice(nl + 2);
            const dataLine = raw.split("\n").find((l) => l.startsWith("data:"));
            if (!dataLine) continue;
            const json = dataLine.replace(/^data:\s?/, "").trim();
            if (!json || json === "[DONE]") continue;
            let evt;
            try { evt = JSON.parse(json); } catch { continue; }

            if (evt.event === "token" && evt.data) {
              acc += evt.data;
              schedule();
            } else if (evt.event === "usedTools" && Array.isArray(evt.data)) {
              calls = evt.data.filter((t) => t && t.tool);
            } else if (evt.event === "end") {
              if (raf) { cancelAnimationFrame(raf); raf = 0; }
              patch({
                text: acc,
                data: agentData(acc, calls, health?.llm_model),
                streaming: false,
                time: fmtTime(),
              });
            }
          }
        }
        if (raf) cancelAnimationFrame(raf);
        if (!acc) throw new Error("empty stream");
        patch({
          text: acc,
          data: agentData(acc, calls, health?.llm_model),
          streaming: false,
          time: fmtTime(),
        });
      } catch {
        // fall back to a non-streaming prediction call
        try {
          const resp = await fetch(agentUrl(view), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: text, chatId: sessionId }),
          });
          if (!resp.ok) throw new Error("bad status");
          const data = await resp.json();
          const answer = data.text ?? data.answer ?? "(no response)";
          const used = (data.usedTools || []).filter((t) => t && t.tool);
          patch({
            text: answer,
            data: agentData(answer, used, health?.llm_model),
            streaming: false,
            time: fmtTime(),
          });
        } catch {
          patch({
            text: "Agent not reachable — is Flowise running on :3000?",
            streaming: false,
            error: true,
          });
        }
      } finally {
        setLoading(false);
        persist(sessionId, running, view);
      }
    },
    [input, loading, sessionId, view, health, persist]
  );

  /** A fresh sessionId gives the Flowise agent a clean memory context. */
  const newChat = useCallback(() => {
    setSessionId(newId());
    setMessages([]);
    setInput("");
  }, []);

  /** Reopen a stored conversation — restores the transcript and the agent's
      memory together, because both are keyed by the same chatId. */
  const openConversation = useCallback((id) => {
    const c = readConvos().find((x) => x.id === id);
    if (!c) return null;
    setSessionId(c.id);
    setMessages(c.messages || []);
    return c.view;
  }, []);

  const deleteConversation = useCallback((id) => {
    setConversations((prev) => {
      const next = prev.filter((c) => c.id !== id);
      try { localStorage.setItem(CONVO_KEY, JSON.stringify(next)); } catch { /* skip */ }
      return next;
    });
  }, []);

  return {
    sessionId, messages, input, setInput, loading,
    send, newChat,
    conversations, openConversation, deleteConversation,
  };
}
