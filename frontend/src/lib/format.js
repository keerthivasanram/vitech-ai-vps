/* Formatting + id helpers shared across the app. */

export const fmtTime = () =>
  new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

export const newId = () => Math.random().toString(36).slice(2, 14);

/** "wet_scrubber" -> "Wet Scrubber" */
export const catLabel = (c) =>
  (c || "other").replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());

/** Indian-grouped rupees. Null-safe: renders an em dash when there is no number. */
export const inrMaybe = (n) => (n == null ? "—" : "₹ " + Number(n).toLocaleString("en-IN"));

export const inr = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN");

export const fileSize = (n) =>
  n < 1024 ? `${n} B`
  : n < 1048576 ? `${(n / 1024).toFixed(0)} KB`
  : `${(n / 1048576).toFixed(1)} MB`;

/** "Good morning" / "Good afternoon" / "Good evening" by local clock. */
export function greeting(d = new Date()) {
  const h = d.getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

/** Relative day label for the conversation list: Today -> time, else 1d/2d/date. */
export function relativeTime(iso) {
  if (!iso) return "";
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "";
  const now = new Date();
  const startOf = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((startOf(now) - startOf(then)) / 86400000);
  if (days <= 0) return then.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  return then.toLocaleDateString([], { day: "numeric", month: "short" });
}

/** First line of a message, trimmed to fit the conversation list. */
export const titleFrom = (text, max = 42) => {
  const one = String(text || "").replace(/\s+/g, " ").trim();
  return one.length > max ? one.slice(0, max - 1).trimEnd() + "…" : one || "New conversation";
};

/**
 * Buckets a list into Today / Yesterday / Last 7 Days / Earlier by `dateKey`,
 * newest-first within each bucket (the list is expected to arrive sorted).
 * Empty buckets are dropped so the panel never shows an empty section.
 */
export function groupByRecency(list, dateKey = "updatedAt") {
  const startOf = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const today = startOf(new Date());
  const buckets = new Map([["Today", []], ["Yesterday", []], ["Last 7 Days", []], ["Older", []]]);

  for (const item of list) {
    const d = new Date(item[dateKey]);
    const bucket = Number.isNaN(d.getTime())
      ? "Older"
      : (() => {
          const days = Math.round((today - startOf(d)) / 86400000);
          if (days <= 0) return "Today";
          if (days === 1) return "Yesterday";
          if (days < 7) return "Last 7 Days";
          return "Older";
        })();
    buckets.get(bucket).push(item);
  }

  return [...buckets.entries()]
    .filter(([, items]) => items.length > 0)
    .map(([label, items]) => ({ label, items }));
}
