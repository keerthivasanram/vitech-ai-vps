"""Render the knowledge-based prototype architecture as a PNG for slides."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = Path(__file__).resolve().parent.parent / "docs" / "architecture.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

W, H = 16, 10
fig, ax = plt.subplots(figsize=(W, H), dpi=150)
ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
fig.patch.set_facecolor("white")

ING   = ("#dbeafe", "#2563eb")
DB    = ("#1e3a8a", "#1e3a8a")
VEC   = ("#dbeafe", "#1e3a8a")
RULE  = ("#ccfbf1", "#0d9488")   # knowledge / rule engine
UND   = ("#fde68a", "#d97706")   # understanding (NLP)
REASON= ("#fed7aa", "#ea580c")   # reasoning engine
QRY   = ("#e5e7eb", "#374151")
OUT_C = ("#bbf7d0", "#16a34a")
STD   = ("#f1f5f9", "#64748b")


def box(x, y, w, h, text, fill, edge, tcolor="#111827", fs=11, bold=False, lw=1.8):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                 linewidth=lw, edgecolor=edge, facecolor=fill, zorder=2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            color=tcolor, zorder=3, fontweight="bold" if bold else "normal")
    return (x, y, w, h)


def arrow(p1, p2, color="#6b7280"):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=16,
                 linewidth=1.7, color=color, zorder=1))


def right(b):  return (b[0] + b[2], b[1] + b[3] / 2)
def left(b):   return (b[0], b[1] + b[3] / 2)
def top(b):    return (b[0] + b[2] / 2, b[1] + b[3])
def bottom(b): return (b[0] + b[2] / 2, b[1])

ax.text(W / 2, 9.55, "ATS Engineering Assistant — Knowledge-Based Architecture",
        ha="center", fontsize=18, fontweight="bold", color="#0f172a")

# -------- Ingestion strip --------
ax.text(0.4, 8.95, "INGESTION  (faked CAD/PDF extraction)", fontsize=10.5,
        fontweight="bold", color=ING[1])
i1 = box(0.4, 8.0, 3.0, 0.82, "Extracted JSON\n(CAD / PDF)", *ING, fs=10)
i2 = box(3.7, 8.0, 2.8, 0.82, "Embed · MiniLM\n(local)", *ING, fs=10)
i3 = box(6.8, 8.0, 4.4, 0.82, "", DB[0], DB[1])
ax.text(6.8 + 2.2, 8.0 + 0.55, "Chroma Knowledge Base", ha="center", color="white",
        fontsize=11, fontweight="bold", zorder=3)
ax.text(6.8 + 2.2, 8.0 + 0.22, "vectors + structured fields", ha="center",
        color="#c7d2fe", fontsize=8.5, zorder=3)
arrow(right(i1), left(i2)); arrow(right(i2), left(i3))

# -------- Standards (knowledge for rule engine) --------
std = box(0.4, 6.45, 3.0, 0.78, "Engineering Standards\nNFPA 33 · ATS rules", *STD, fs=9.5)

# -------- Query lane --------
ax.text(0.4, 5.62, "QUERY  (live · per request)", fontsize=10.5,
        fontweight="bold", color=QRY[1])
q_user = box(0.4, 4.35, 2.4, 1.0, "User question\n(React UI)", *QRY, fs=10)
q_und  = box(3.05, 4.35, 2.8, 1.0, "Requirement\nUnderstanding\n(LLM = NLP)", *UND, fs=10.5, bold=True)

# knowledge sources (hybrid)
ax.text(7.65, 6.75, "KNOWLEDGE SOURCES", ha="center", fontsize=9,
        fontweight="bold", color="#475569")
ks_vec  = box(6.25, 5.55, 2.9, 1.0, "Vector Search\n(similar projects)", *VEC, fs=10)
ks_rule = box(6.25, 3.15, 2.9, 1.0, "Rule Engine\n(compute from standards)", *RULE, fs=10, bold=True)

reason = box(9.55, 4.35, 2.95, 1.0, "Reasoning Engine\n(reconcile +\nconfidence)", *REASON, fs=10, bold=True)
llm    = box(12.75, 4.55, 2.55, 0.95, "LLM\n(explanation only)", *QRY, fs=10)
out    = box(12.6, 2.55, 2.85, 1.15, "Spec / Quotation\n+ confidence\n+ source files",
             *OUT_C, fs=10, bold=True)

arrow(bottom(i3), top(ks_vec))                 # KB -> vector search
arrow(right(std), left(ks_rule))               # standards -> rule engine
arrow(right(q_user), left(q_und))
arrow(right(q_und), left(ks_vec))              # understanding -> both sources
arrow(right(q_und), left(ks_rule))
arrow(right(ks_vec), (reason[0], reason[1] + reason[3] * 0.75))
arrow(right(ks_rule), (reason[0], reason[1] + reason[3] * 0.25))
arrow(right(reason), left(llm))
arrow(bottom(llm), (out[0] + out[2] / 2, out[1] + out[3]))

# captions
ax.text(4.45, 4.05, "intent · dims · material · topic", ha="center", fontsize=8,
        color="#92400e")
ax.text(11.02, 3.75, "rules vs history\n→ confidence", ha="center", fontsize=8,
        color="#9a3412")

ax.text(W / 2, 0.5,
        "Understand → Retrieve + Compute → Reason → Explain   |   "
        "FastAPI · Chroma · MiniLM · Rule Engine (Pydantic) · Ollama Qwen2.5-3B · React",
        ha="center", fontsize=9, color="#475569")

plt.savefig(OUT, bbox_inches="tight", facecolor="white")
print(f"Saved {OUT}")
