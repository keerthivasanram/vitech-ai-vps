/**
 * Guard against the agent showing the user its own plumbing.
 *
 * THE DEFECT (documented in CLAUDE.md since 2026-08-01, pre-existing): on a
 * plain greeting the Tool Agent scaffold occasionally wraps a normal reply in a
 * fake tool-call shape and the user sees `There is no function call needed for
 * your greeting.` or a literal `{"name": "answer", "parameters": {}}`. RULE 1
 * of the system prompt already forbids exactly this, and it still happens.
 *
 * WHY THIS IS A BOUNDARY GUARD AND NOT A PROMPT CHANGE. Prompt tuning has
 * already been tried and backfired: a standalone rule fixed the target case and
 * broke greetings 5/5, and the project's own conclusion was to fix this class
 * of problem structurally instead — the same reasoning that made
 * `lookup_markdown` a code-rendered field the agent prints verbatim.
 *
 * WHAT THIS IS NOT. It does not cure the model; it stops the leak reaching the
 * user. The real fix is a stronger tool-capable model (roadmap D2) — this is an
 * 8B limitation, and the leak becomes more likely the longer a Flowise process
 * has been serving rapid requests. Restarting Flowise clears it.
 *
 * IMPORTANT: only replies that are ENTIRELY mechanics are replaced. A real
 * answer that happens to mention a tool keeps its text — losing an engineering
 * answer to an over-eager filter would be far worse than the leak it prevents.
 */

// Whole-reply shapes that carry no content. Anchored, and matched against the
// TRIMMED reply, so a genuine answer containing one of these phrases survives.
const MECHANICS = [
  /^there (is|are) no (function|tool) calls? (needed|required)\b/i,
  /^no (function|tool) calls? (is |are )?(needed|required)\b/i,
  /^\{\s*"?name"?\s*:/i,                    // {"name": "answer", ...}
  /^```?\s*\{\s*"?name"?\s*:/i,             // fenced variant
  /^i (will|'ll) (now )?call the \w+ (tool|function)\.?$/i,
  /^\s*<?\|?(tool_call|function_call)\|?>?/i,
];

const FALLBACK =
  "I'm the Vitech Engineering Assistant. I turn a requirement into a technical " +
  "specification, a general-arrangement drawing and a budgetary quotation. " +
  "Tell me the equipment and its size to get started.";

/** True when the reply is nothing but tool-call mechanics. */
export function isLeakedMechanics(text) {
  const t = String(text ?? "").trim();
  if (!t) return false;
  // A long reply is a real answer even if it opens awkwardly; the leak is
  // always short.
  if (t.length > 240) return false;
  return MECHANICS.some((re) => re.test(t));
}

/**
 * The reply to show. Substitutes only when the whole message is mechanics.
 * `onLeak` lets the caller record that it happened, so the defect stays
 * visible in the logs rather than being silently papered over.
 */
export function sanitizeAgentReply(text, onLeak) {
  if (isLeakedMechanics(text)) {
    if (typeof onLeak === "function") onLeak(String(text ?? "").trim());
    return FALLBACK;
  }
  return text;
}
