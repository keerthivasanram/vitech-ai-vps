/**
 * Deterministic 2D GA-drawing preview (client-side).
 *
 * A stand-in for the future backend `generate_drawing` engine so the Drawing
 * Studio renders real, dimensioned drawings NOW. Every line/number here is
 * derived from the given envelope — nothing is invented; an unknown dimension
 * becomes a TBD callout (golden rule #2). When the backend lands, swap the SVG
 * source for the tool response; the studio UI stays the same.
 *
 * Draws two third-angle views (PLAN + FRONT ELEVATION) with dimension lines and
 * a Vitech title block, grouped by layer (data-layer) so the studio can toggle
 * envelope / dimensions / grid / title-block.
 */

const MM = (v) => (v == null ? null : Math.round(v));

/* Parse "5 x 3 x 4", "5000x3000", "L 6 W 3 H 4 m", "800 dia" etc. into mm. */
export function parseEnvelope(text) {
  const t = (text || "").toLowerCase();
  // explicit L x W x H (metres if <100, else mm)
  const nums = (t.match(/\d+(?:\.\d+)?/g) || []).map(Number);
  const toMm = (n) => (n == null ? null : n < 100 ? Math.round(n * 1000) : Math.round(n));
  const label =
    /scrubber/.test(t) ? "Wet Scrubber" :
    /booth/.test(t) ? "Paint Booth" :
    /oven/.test(t) ? "Hot Air Oven" :
    /dust|collector/.test(t) ? "Dust Collector" :
    /conveyor/.test(t) ? "Conveyor" : "Equipment";
  return {
    label,
    length: toMm(nums[0]),
    width: toMm(nums[1]),
    height: toMm(nums[2]),
  };
}

const esc = (s) => String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

/* A dimension line with witness lines + arrows + centered text (horizontal). */
function dimH(x1, x2, y, val, cls = "") {
  const mid = (x1 + x2) / 2;
  const txt = val == null ? "TBD" : `${val}`;
  const t = val == null ? "tbd" : "";
  return `<g data-layer="dimensions" class="dim ${cls} ${t}">
    <line x1="${x1}" y1="${y - 6}" x2="${x1}" y2="${y + 6}"/>
    <line x1="${x2}" y1="${y - 6}" x2="${x2}" y2="${y + 6}"/>
    <line class="dim-line" x1="${x1}" y1="${y}" x2="${x2}" y2="${y}"/>
    <polygon class="arr" points="${x1},${y} ${x1 + 7},${y - 3.2} ${x1 + 7},${y + 3.2}"/>
    <polygon class="arr" points="${x2},${y} ${x2 - 7},${y - 3.2} ${x2 - 7},${y + 3.2}"/>
    <rect class="dim-bg" x="${mid - 26}" y="${y - 9}" width="52" height="14" rx="2"/>
    <text x="${mid}" y="${y + 1}">${txt}</text>
  </g>`;
}
function dimV(x, y1, y2, val, cls = "") {
  const mid = (y1 + y2) / 2;
  const txt = val == null ? "TBD" : `${val}`;
  const t = val == null ? "tbd" : "";
  return `<g data-layer="dimensions" class="dim ${cls} ${t}">
    <line x1="${x - 6}" y1="${y1}" x2="${x + 6}" y2="${y1}"/>
    <line x1="${x - 6}" y1="${y2}" x2="${x + 6}" y2="${y2}"/>
    <line class="dim-line" x1="${x}" y1="${y1}" x2="${x}" y2="${y2}"/>
    <polygon class="arr" points="${x},${y1} ${x - 3.2},${y1 + 7} ${x + 3.2},${y1 + 7}"/>
    <polygon class="arr" points="${x},${y2} ${x - 3.2},${y2 - 7} ${x + 3.2},${y2 - 7}"/>
    <rect class="dim-bg" x="${x - 26}" y="${mid - 7}" width="52" height="14" rx="2"/>
    <text x="${x}" y="${mid + 1}" transform="rotate(-90 ${x} ${mid})">${txt}</text>
  </g>`;
}

/**
 * Build an SVG string for the given envelope.
 * @param {{label,length,width,height}} env  dimensions in mm (null = TBD)
 * @param {{ref,date,scaleText}} meta
 */
export function buildDrawingSvg(env, meta = {}) {
  const W = 1120, H = 760;                       // sheet units
  const label = env.label || "Equipment";
  const L = env.length, Wd = env.width, Ht = env.height;

  // Fit each view into a box; fall back to a nominal box when a dim is TBD.
  const NOM = 3000;
  const l = L || NOM, w = Wd || NOM, h = Ht || NOM;

  // scale so the larger view fits ~360px wide / ~300px tall
  const planMax = Math.max(l, w), elevMax = Math.max(l, h);
  const s = 300 / Math.max(planMax, elevMax);

  // PLAN (top-left): length(x) by width(y)
  const px = 120, py = 150, pw = l * s, ph = w * s;
  const plan = `<g data-layer="envelope">
    <rect class="body" x="${px}" y="${py}" width="${pw}" height="${ph}"/>
    <line class="hatch" x1="${px}" y1="${py}" x2="${px + pw}" y2="${py + ph}"/>
    <line class="hatch" x1="${px + pw}" y1="${py}" x2="${px}" y2="${py + ph}"/>
  </g>
  <text class="view-t" x="${px}" y="${py - 16}">PLAN</text>
  ${dimH(px, px + pw, py + ph + 34, L)}
  ${dimV(px - 34, py, py + ph, Wd)}`;

  // FRONT ELEVATION (right): length(x) by height(y), sitting on a ground line
  const ex = 640, eyBase = py + 300;               // baseline
  const ew = l * s, eh = h * s, ey = eyBase - eh;
  const elev = `<g data-layer="envelope">
    <rect class="body" x="${ex}" y="${ey}" width="${ew}" height="${eh}"/>
    <line class="ground" x1="${ex - 30}" y1="${eyBase}" x2="${ex + ew + 30}" y2="${eyBase}"/>
  </g>
  <text class="view-t" x="${ex}" y="${ey - 16}">FRONT ELEVATION</text>
  ${dimH(ex, ex + ew, eyBase + 34, L)}
  ${dimV(ex + ew + 34, ey, eyBase, Ht)}`;

  // grid (behind)
  let grid = "";
  for (let gx = 40; gx < W; gx += 40) grid += `<line x1="${gx}" y1="0" x2="${gx}" y2="${H - 120}"/>`;
  for (let gy = 40; gy < H - 120; gy += 40) grid += `<line x1="0" y1="${gy}" x2="${W}" y2="${gy}"/>`;

  // title block (bottom strip) — Vitech stationery
  const ref = meta.ref || "VT/DRG/PREVIEW";
  const date = meta.date || new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  const scaleText = meta.scaleText || "NTS (preview)";
  const tb = `<g data-layer="titleblock">
    <rect class="tb" x="0" y="${H - 118}" width="${W}" height="118"/>
    <text class="tb-co" x="24" y="${H - 82}">VITECH ENVIRO SYSTEMS PVT. LTD</text>
    <text class="tb-sub" x="24" y="${H - 62}">AP-123, AF-BLOCK, 6th STREET, 11th MAIN ROAD, ANNA NAGAR, CHENNAI-600 040</text>
    <text class="tb-sub" x="24" y="${H - 42}">General Arrangement — ${esc(label)}</text>
    <line class="tb-div" x1="${W - 360}" y1="${H - 118}" x2="${W - 360}" y2="${H}"/>
    <text class="tb-k" x="${W - 344}" y="${H - 92}">Ref</text><text class="tb-v" x="${W - 250}" y="${H - 92}">${esc(ref)}</text>
    <text class="tb-k" x="${W - 344}" y="${H - 70}">Date</text><text class="tb-v" x="${W - 250}" y="${H - 70}">${esc(date)}</text>
    <text class="tb-k" x="${W - 344}" y="${H - 48}">Scale</text><text class="tb-v" x="${W - 250}" y="${H - 48}">${esc(scaleText)}</text>
    <text class="tb-k" x="${W - 344}" y="${H - 26}">Status</text><text class="tb-v draft" x="${W - 250}" y="${H - 26}">DRAFT — preview</text>
    <text class="tb-units" x="24" y="${H - 18}">All dimensions in mm unless noted · Third-angle projection</text>
  </g>`;

  return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" class="ga-svg" preserveAspectRatio="xMidYMid meet">
    <g data-layer="grid" class="grid">${grid}</g>
    <rect class="sheet-border" x="6" y="6" width="${W - 12}" height="${H - 12}"/>
    ${plan}
    ${elev}
    ${tb}
  </svg>`;
}

/* Which envelope dimensions are still TBD — for the studio's TBD schedule. */
export function tbdList(env) {
  const out = [];
  if (env.length == null) out.push("Length — needs engineering input");
  if (env.width == null) out.push("Width — needs engineering input");
  if (env.height == null) out.push("Height — needs engineering input");
  return out;
}
