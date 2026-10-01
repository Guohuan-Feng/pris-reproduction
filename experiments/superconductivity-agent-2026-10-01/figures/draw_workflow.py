"""Advisor-facing static summary of the frozen first Tc-agent pilot."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = Path(__file__).resolve().parent
fig, ax = plt.subplots(figsize=(13.0, 10.1), dpi=180)
fig.patch.set_facecolor("#ffffff")
ax.set_xlim(0, 13)
ax.set_ylim(0, 10.1)
ax.axis("off")

navy = "#172e4f"
blue = "#245ca6"
gray = "#5d6976"
green = "#247358"
amber = "#916121"

def box(x, y, w, h, title, lines, face="#edf4fc", edge=blue):
    p = FancyBboxPatch((x-w/2, y-h/2), w, h,
        boxstyle="round,pad=0.045,rounding_size=0.12",
        linewidth=1.5, edgecolor=edge, facecolor=face, zorder=3)
    ax.add_patch(p)
    ax.text(x, y+h/2-0.21, title, ha="center", va="top", fontsize=12.4,
        color=navy, weight="bold", zorder=4)
    ax.text(x, y-0.10, lines, ha="center", va="center", fontsize=11.8,
        color=navy, linespacing=1.30, zorder=4)

def arrow(points, color=gray, dashed=False):
    for start, end in zip(points[:-2], points[1:-1]):
        ax.plot([start[0],end[0]], [start[1],end[1]], color=color, lw=1.7,
            ls="--" if dashed else "-", zorder=2)
    p = FancyArrowPatch(points[-2], points[-1], arrowstyle="-|>",
        mutation_scale=14, linewidth=1.7, color=color,
        linestyle="--" if dashed else "-", zorder=2)
    ax.add_patch(p)

ax.text(0.45, 9.77, "Current superconductivity workflow", fontsize=22,
    color=navy, weight="bold", va="top")
ax.text(0.45, 9.23, "Frozen first pilot  |  Composition + matched crystal structures → Tc prediction",
    fontsize=12.6, color=gray, va="top")

# Development and frozen retrospective phases are deliberately separate.
ax.add_patch(FancyBboxPatch((3.52,4.17), 8.95, 4.63,
    boxstyle="round,pad=0.02,rounding_size=0.16", facecolor="#f6f9fd",
    edgecolor="#c1d1e4", linewidth=1.2, zorder=0))
ax.text(3.73,8.58,"DEVELOPMENT — adaptive feedback", fontsize=11,
    color=blue, weight="bold")

box(1.75,7.95,2.65,1.36,"3DSC-MP cohort", "5,773 records\nStrict groups: chemical\nsystem + MP parent")
box(1.75,5.98,2.65,1.26,"Training data", "3,764 records\nFit + training inspection")
box(5.45,7.50,3.15,1.25,"GPT proposes + codes", "Structure descriptors\n≤12 new scalar features")
box(10.45,7.50,3.40,1.25,"Restricted numerical tools", "Compute descriptors\nExtraTrees fit: log1p(Tc)")
box(10.45,5.56,3.40,1.40,"Adaptive validation", "869 records\nWeighted MAE + error cases\n5 experiments total")
box(5.45,5.56,3.15,1.40,"Comparison models", "Composition baseline\nConventional structure\nNumeric feature search")
box(7.70,3.25,3.55,1.12,"Select + freeze", "Validation selects candidates\nCode, models + run trace frozen",
    face="#eaf5ef", edge=green)
box(1.75,2.24,2.65,1.45,"Historical test cohort", "1,140 records\nPreviously analyzed\nOutside this run's feedback",
    face="#fff7e8", edge=amber)
box(7.70,1.49,3.55,1.05,"Retrospective evaluation", "Frozen models only\nScores + subgroup errors",
    face="#fff7e8", edge=amber)
box(11.36,1.49,2.45,1.05,"Audit + report", "Numerical replay\nRepresentation checks",
    face="#edf2f6", edge=gray)

# Source splits and training flow.
arrow([(1.75,7.22),(1.75,6.66)])
arrow([(3.12,8.10),(3.34,8.10),(3.34,8.98),(12.72,8.98),(12.72,5.56),(12.20,5.56)],color=gray)
ax.text(8.0,9.02,"validation partition",ha="center",va="bottom",fontsize=9.8,color=gray)
arrow([(3.12,5.98),(3.35,5.98),(3.35,7.50),(3.83,7.50)],color=blue)
arrow([(7.07,7.50),(8.70,7.50)],color=blue)
arrow([(10.45,6.82),(10.45,6.30)],color=blue)
# Explicit feedback returns from metrics/counterexamples to feature proposals.
arrow([(8.70,5.78),(7.93,5.78),(7.93,6.50),(5.45,6.50),(5.45,6.82)],color=blue)
ax.text(6.63,6.55,"feedback + revision",ha="center",va="bottom",fontsize=10.4,color=blue)
arrow([(3.12,5.56),(3.83,5.56)],color=gray)
# Same validation partition scores controls as the agent, without hiding a feedback edge.
arrow([(8.70,5.32),(7.07,5.32)],color=gray,dashed=True)
ax.text(7.84,5.08,"same validation",ha="center",va="top",fontsize=9.8,color=gray)
arrow([(5.45,4.82),(5.45,3.25),(5.88,3.25)],color=green)
arrow([(10.45,4.82),(10.45,3.25),(9.52,3.25)],color=green)
arrow([(7.70,2.65),(7.70,2.05)],color=green)
# Historical branch stays to the left and never enters agent feedback.
arrow([(0.40,7.95),(0.18,7.95),(0.18,2.24),(0.38,2.24)],color=amber)
arrow([(3.12,2.24),(4.30,2.24),(4.30,1.49),(5.88,1.49)],color=amber)
arrow([(9.52,1.49),(10.08,1.49)],color=gray)

ax.text(0.47,0.47,
    "Run completed: 12 tool calls, 5 agent experiments. Historical evaluation is not a fresh independent test.",
    fontsize=11.5,color=gray,va="bottom")
fig.subplots_adjust(left=0,right=1,bottom=0,top=1)
fig.savefig(OUT/"workflow.png", dpi=180, facecolor="white")
fig.savefig(OUT/"workflow.svg", facecolor="white")
plt.close(fig)
print("Created workflow.png and workflow.svg")
