"""Export a static advisor-facing workflow; contains no experimental results."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "figures"
OUT.mkdir(exist_ok=True)
FONT = Path("C:/Windows/Fonts/msyh.ttc")
if FONT.exists():
    font_manager.fontManager.addfont(str(FONT))
    family = font_manager.FontProperties(fname=str(FONT)).get_name()
else:
    family = "DejaVu Sans"
plt.rcParams.update({"font.family": family, "axes.unicode_minus": False,
                     "svg.fonttype": "path"})

fig, ax = plt.subplots(figsize=(13.8, 8.5), dpi=170)
fig.patch.set_facecolor("#f7f9fc")
ax.set_facecolor("#f7f9fc")
ax.set_xlim(0, 14)
ax.set_ylim(0, 8.6)
ax.axis("off")
ink, muted, line = "#142b46", "#50637a", "#547392"
ax.text(7, 8.15, "超导研究 Agent 的自循环", ha="center", va="center",
        fontsize=25, weight="bold", color=ink)
ax.text(7, 7.62, "每轮实验产生反馈，反馈决定下一轮假设与方案", ha="center",
        va="center", fontsize=13.2, color=muted)

def box(x, y, number, title, description, fill="#ffffff", edge="#b7c8d9"):
    width, height = 3.55, 1.55
    ax.add_patch(FancyBboxPatch((x, y), width, height,
                               boxstyle="round,pad=0.035,rounding_size=0.13",
                               linewidth=1.35, edgecolor=edge, facecolor=fill))
    ax.text(x + .22, y + 1.14, number, ha="left", va="center", fontsize=12,
            weight="bold", color="#547392")
    ax.text(x + .66, y + 1.14, title, ha="left", va="center", fontsize=17,
            weight="bold", color=ink)
    ax.text(x + width / 2, y + .52, description, ha="center", va="center",
            fontsize=11.9, linespacing=1.5, color=muted)

def arrow(start, end, color=line, style="-", lw=1.8):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>",
                                mutation_scale=17, linewidth=lw,
                                color=color, linestyle=style,
                                shrinkA=0, shrinkB=0))

left, middle, right = 1.02, 5.23, 9.44
top, bottom = 5.62, 3.03
box(left, top, "01", "读取研究记忆", "训练证据、历史实验\n最佳方案与剩余预算", fill="#eef5fc")
box(middle, top, "02", "提出下一轮假设", "模型选择实验配置\n说明修改依据与证伪条件")
box(right, top, "03", "执行数值实验", "固定三折分组交叉验证\n相同配置复用可信结果")
box(right, bottom, "04", "按规则检查结果", "整体 MAE 与正 Tc 子组约束\n决定是否更新最佳方案")
box(middle, bottom, "05", "反思与修订", "模型分析实测误差与反例\n确定下一步关注点")
box(left, bottom, "06", "写入持久记忆", "保存提案、结果与反思\n检查点与累计预算", fill="#eef5fc")

arrow((left+3.62, top+.77), (middle-.10, top+.77))
arrow((middle+3.62, top+.77), (right-.10, top+.77))
arrow((right+1.77, top-.08), (right+1.77, bottom+1.66))
ax.text(right+2.03, 5.12, "实测反馈", ha="left", va="center", fontsize=10.8, color=muted)
arrow((right-.10, bottom+.77), (middle+3.65, bottom+.77))
arrow((middle-.10, bottom+.77), (left+3.65, bottom+.77))

# The closed return edge makes continuation visible without an extra human step.
ax.plot([left-.08, .40, .40], [bottom+.77, bottom+.77, top+.77],
        color=line, linewidth=1.8)
arrow((.40, top+.77), (left-.10, top+.77))
ax.text(7.02, 5.07, "自动进入下一轮", ha="center", va="center",
        fontsize=14.3, weight="bold", color="#27577f")

stop_x, stop_y, stop_w, stop_h = 2.40, .83, 9.20, 1.12
ax.add_patch(FancyBboxPatch((stop_x, stop_y), stop_w, stop_h,
                           boxstyle="round,pad=0.035,rounding_size=0.12",
                           linewidth=1.2, edgecolor="#d7b579", facecolor="#fff5e4"))
ax.text(7, 1.57, "停止或暂停，并保存原因", ha="center", va="center",
        fontsize=15.2, weight="bold", color="#795221")
ax.text(7, 1.14, "预算用尽  ·  连续停滞  ·  模型主动停止  ·  用户停止  ·  异常",
        ha="center", va="center", fontsize=11.8, color="#795221")
arrow((7, bottom-.10), (7, stop_y+stop_h+.10), color="#ac813c", style="--", lw=1.5)
ax.text(7.20, 2.47, "全过程检查停止条件", ha="left", va="center",
        fontsize=11.2, color="#886027")

ax.text(7, .29, "固定训练数据与折外证据  |  SQLite 记忆与检查点  |  同一运行恢复后沿用原预算",
        ha="center", va="center", fontsize=10.9, color=muted)
fig.subplots_adjust(left=.015, right=.985, top=.99, bottom=.01)
fig.savefig(OUT / "workflow.png", dpi=170, facecolor=fig.get_facecolor())
fig.savefig(OUT / "workflow.svg", facecolor=fig.get_facecolor())
plt.close(fig)
print("Exported figures/workflow.png and figures/workflow.svg")
