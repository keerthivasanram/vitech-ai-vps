/* Lightweight markdown renderer for agent replies.
   Deliberately not a full parser: it handles exactly what the agents emit —
   headings, lists, blockquotes, tables, and inline bold/code/em. */

const isTableRow = (s) => /^\s*\|.*\|\s*$/.test(s);
const isTableSep = (s) => /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(s) && s.includes("-");
const cells = (s) => s.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

export function inline(text) {
  return String(text)
    .split(/(\*\*[^*]+\*\*|`[^`]+`|_[^_]+_)/g)
    .map((p, i) => {
      if (p.startsWith("**") && p.endsWith("**")) return <strong key={i}>{p.slice(2, -2)}</strong>;
      if (p.startsWith("`") && p.endsWith("`")) return <code key={i}>{p.slice(1, -1)}</code>;
      if (p.startsWith("_") && p.endsWith("_")) return <em key={i}>{p.slice(1, -1)}</em>;
      return <span key={i}>{p}</span>;
    });
}

export function Answer({ text, streaming }) {
  if (!text) return null;
  const lines = text.split("\n");
  const out = [];
  let key = 0;

  for (let i = 0; i < lines.length; i++) {
    const t = lines[i].replace(/\s+$/, "").trim();

    // markdown table: header row + separator row + body rows
    if (isTableRow(lines[i]) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const head = cells(lines[i]);
      const rows = [];
      i += 2;
      while (i < lines.length && isTableRow(lines[i])) { rows.push(cells(lines[i])); i++; }
      i--;
      out.push(
        <div key={key++} className="tbl-wrap">
          <table className="mdtable">
            <thead>
              <tr>{head.map((c, j) => <th key={j}>{inline(c)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>{head.map((_, ci) => <td key={ci}>{inline(r[ci] ?? "")}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    if (!t) { out.push(<div key={key++} className="gap" />); continue; }

    const h = t.match(/^(#{1,3})\s+(.*)$/);
    if (h) {
      out.push(<div key={key++} className={`h h${h[1].length}`}>{inline(h[2])}</div>);
      continue;
    }
    if (t.startsWith(">")) {
      out.push(<blockquote key={key++}>{inline(t.slice(1).trim())}</blockquote>);
      continue;
    }
    const ol = t.match(/^(\d+)[.)]\s+(.*)$/);
    if (ol) {
      out.push(
        <div key={key++} className="li ol">
          <span className="marker">{ol[1]}.</span>
          <span className="li-body">{inline(ol[2])}</span>
        </div>
      );
      continue;
    }
    const ul = t.match(/^[•\-*]\s+(.*)$/);
    if (ul) {
      out.push(
        <div key={key++} className="li ul">
          <span className="marker">•</span>
          <span className="li-body">{inline(ul[1])}</span>
        </div>
      );
      continue;
    }
    out.push(<p key={key++} className="para">{inline(t)}</p>);
  }

  return (
    <div className="answer">
      {out}
      {streaming && <span className="caret" />}
    </div>
  );
}
