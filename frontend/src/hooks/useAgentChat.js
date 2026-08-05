import { useCallback, useEffect, useState } from "react";
import { sanitizeAgentReply } from "../lib/agentReply";
import { agentUrl, isChatView, DETERMINISTIC_TOOLS } from "../lib/constants";
import { fmtTime, newId, titleFrom } from "../lib/format";

const SESSION_MAP_KEY = "vitech_sessions"; // JSON: { [view]: sessionId } - one chatId per agent
const CONVO_KEY = "vitech_convos";
const CONVO_LIMIT = 20; // per agent, not shared across agents

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

const readSessionIds = () => {
  try { return JSON.parse(localStorage.getItem(SESSION_MAP_KEY)) || {}; }
  catch { return {}; }
};

/**
 * Owns the agent conversation: transcript, streaming, per-agent session
 * slots and the locally-persisted conversation list that feeds the Recent
 * Conversations panel.
 *
 * Conversation memory itself lives in Flowise, keyed by chatId (= sessionId).
 * We persist the transcript locally so reopening a conversation restores both
 * the visible history AND the agent's memory (same chatId).
 *
 * Each chat-capable view (Engineering, Quotation, ...) keeps its OWN live
 * session slot in `sessionsByView`, like separate tabs: navigating away and
 * back restores exactly what was there instead of wiping it, and two agents
 * never share a chatId (which would blend their Flowise memory together).
 */
export function useAgentChat(view, health) {
  const [sessionsByView, setSessionsByView] = useState(() => {
    const ids = readSessionIds();
    return { [view]: { sessionId: ids[view] || newId(), messages: [] } };
  });
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversations, setConversations] = useState(readConvos);

  // First visit to a chat view this session: give it its own slot (restoring
  // its last known chatId if one was persisted) instead of reusing whatever
  // view was previously active.
  useEffect(() => {
    if (!isChatView(view)) return;
    setSessionsByView((prev) => {
      if (prev[view]) return prev;
      const ids = readSessionIds();
      return { ...prev, [view]: { sessionId: ids[view] || newId(), messages: [] } };
    });
  }, [view]);

  // Persist only the {view: chatId} map — small and cheap to write on every
  // change, so a browser refresh still resumes the right agent's chatId
  // instead of reusing whichever agent was used last.
  useEffect(() => {
    const ids = {};
    for (const [v, s] of Object.entries(sessionsByView)) ids[v] = s.sessionId;
    try { localStorage.setItem(SESSION_MAP_KEY, JSON.stringify(ids)); } catch { /* quota — skip */ }
  }, [sessionsByView]);

  const active = sessionsByView[view] || { sessionId: null, messages: [] };
  const { sessionId, messages } = active;

  /* Update the transcript for a given view (defaults to the current one).
     Accepts a value or an updater fn, mirroring setState's own contract. */
  const setMessagesFor = useCallback((forView, updater) => {
    setSessionsByView((prev) => {
      const cur = prev[forView] || { sessionId: newId(), messages: [] };
      const nextMessages = typeof updater === "function" ? updater(cur.messages) : updater;
      return { ...prev, [forView]: { ...cur, messages: nextMessages } };
    });
  }, []);

  /* Persist the transcript against its sessionId, capped PER AGENT so a busy
     Quotation session can never evict Engineering's history (or vice versa). */
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
      const rest = prev.filter((c) => c.id !== id);
      const sameAgent = [entry, ...rest.filter((c) => c.view === forView)].slice(0, CONVO_LIMIT);
      const otherAgents = rest.filter((c) => c.view !== forView);
      const next = [...sameAgent, ...otherAgents];
      try { localStorage.setItem(CONVO_KEY, JSON.stringify(next)); } catch { /* quota — skip */ }
      return next;
    });
  }, []);

  const send = useCallback(
    async (q) => {
      const text = (q ?? input).trim();
      if (!text || loading) return;

      const forView = view;
      const forSession = sessionId;

      setInput("");
      setLoading(true);

      const userMsg = { id: newId(), role: "user", text, time: fmtTime() };
      const astId = newId();
      // Track the running transcript outside state so we can persist it at the
      // end without waiting for a re-render.
      let running = [];
      setMessagesFor(forView, (m) => {
        running = [...m, userMsg, { id: astId, role: "assistant", text: "", streaming: true }];
        return running;
      });

      const patch = (p) =>
        setMessagesFor(forView, (m) => {
          running = m.map((x) => (x.id === astId ? { ...x, ...p } : x));
          return running;
        });

      // Flowise keys conversation memory by chatId — reuse this view's session
      // so the agent remembers context across turns.
      const body = JSON.stringify({ question: text, streaming: true, chatId: forSession });

      try {
        const resp = await fetch(agentUrl(forView), {
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
          const resp = await fetch(agentUrl(forView), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: text, chatId: forSession }),
          });
          if (!resp.ok) throw new Error("bad status");
          const data = await resp.json();
          // Guard against the agent showing its own plumbing on a greeting —
          // a documented, pre-existing leak. See lib/agentReply.js for why this
          // is a boundary guard rather than a prompt change.
          const answer = sanitizeAgentReply(
            data.text ?? data.answer ?? "(no response)",
            (raw) => console.warn("[agent] tool-call mechanics suppressed:", raw));
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
        persist(forSession, running, forView);
      }
    },
    [input, loading, sessionId, view, health, persist, setMessagesFor]
  );

  /** A fresh sessionId gives the Flowise agent a clean memory context, scoped
      to the currently active agent only. */
  const newChat = useCallback(() => {
    setSessionsByView((prev) => ({ ...prev, [view]: { sessionId: newId(), messages: [] } }));
    setInput("");
  }, [view]);

  /** Reopen a stored conversation — restores the transcript and the agent's
      memory together (both keyed by the same chatId), into that conversation's
      OWN agent slot so it doesn't disturb whatever the other agent has live. */
  const openConversation = useCallback((id) => {
    const c = readConvos().find((x) => x.id === id);
    if (!c) return null;
    setSessionsByView((prev) => ({ ...prev, [c.view]: { sessionId: c.id, messages: c.messages || [] } }));
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
