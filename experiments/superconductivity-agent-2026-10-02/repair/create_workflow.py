"""Render the prespecified V2 workflow; no performance values are included."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'figures'
OUT.mkdir(exist_ok=True)
FONT = FontProperties(fname='C:/Windows/Fonts/msyh.ttc')
matplotlib.rcParams.update({'svg.fonttype':'path', 'savefig.facecolor':'white'})

TEXT = '#172B40'
EDGE = '#748493'
BLUE = '#E9F2FA'
TEAL = '#EAF4F1'
PURPLE = '#F0ECF8'
GRAY = '#F2F4F6'

fig, ax = plt.subplots(figsize=(14,15), dpi=200)
ax.set_xlim(0,14)
ax.set_ylim(0,15)
ax.axis('off')
fig.subplots_adjust(left=.015,right=.985,bottom=.015,top=.985)

def text(x,y,label,size=15,ha='center',weight='normal',color=TEXT):
    return ax.text(x,y,label,fontsize=size,fontproperties=FONT,ha=ha,va='center',
                   color=color,weight=weight,linespacing=1.45,zorder=4)

def box(x,y,w,h,title,body='',fill=BLUE,title_size=18,body_size=14,dashed=False):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.018,rounding_size=0.07',
             facecolor=fill,edgecolor=EDGE,linewidth=1.0,linestyle='--' if dashed else '-',zorder=2))
    if body:
        text(x+w/2,y+h*.73,title,title_size,weight='bold')
        text(x+w/2,y+h*.32,body,body_size)
    else:
        text(x+w/2,y+h/2,title,title_size,weight='bold')

def arrow(points,color=EDGE,width=1.5,zorder=1):
    for a,b in zip(points[:-2],points[1:-1]):
        ax.plot([a[0],b[0]],[a[1],b[1]],color=color,linewidth=width,zorder=zorder)
    a,b=points[-2:]
    ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=17,
                               color=color,linewidth=width,shrinkA=0,shrinkB=3,zorder=zorder))

text(7,14.4,'超导方向 · 第二轮 Agent 建模决策',25,weight='bold')
text(7,13.91,'Superconductivity V2 | Prespecified workflow · 2026-10-02',17)

box(.6,12.55,8.3,.95,'Frozen TRAIN cohort / 冻结训练集',
    '3,764 records · 1,117 strict connected-component groups',body_size=15)
box(9.35,11.98,3.95,1.52,'Historical retrospective set',
    '1,140 records\nLabels unused in this V2 run',GRAY,title_size=15,body_size=14,dashed=True)

box(.6,11.05,8.3,1.05,'Fixed repaired inputs / 固定修复后的输入',
    '109 composition + 12 repaired descriptors\n11-descriptor ablation · 28 conventional structure reference',body_size=14)
arrow([(4.75,12.55),(4.75,12.10)])

box(.6,9.68,8.3,.93,'Shared 3-fold TRAIN OOF evaluator',
    'Strict-group folds · train-fold preprocessing · occupancy preserved',body_size=14)
arrow([(4.75,11.05),(4.75,10.61)])
text(11.33,10.58,'过去已分析过的历史数据\n不作为新的独立证据',14,color='#536575')

box(.6,8.30,12.7,.98,'Shared reference bank / 两个搜索臂共用的参考结果',
    '8 global pipelines + 4 diagnostic references · identical folds and scoring',TEAL,body_size=15)
arrow([(4.75,9.68),(4.75,9.28)])

box(.6,5.32,5.8,2.50,'',fill=PURPLE)
box(7.5,5.32,5.8,2.50,'',fill=GRAY)
text(3.5,7.48,'GPT Agent · ≤ 5 attempted pipelines',18,weight='bold')
text(10.4,7.48,'Seeded automated search',19,weight='bold')
text(10.4,7.08,'Same actual attempted-pipeline count',14)

box(1.02,6.30,4.55,.78,'Input · model · raw / log1p target',
    'Material routing / 按材料分组建模',fill='#FAF8FE',title_size=14,body_size=13)
box(1.02,5.63,4.55,.43,'OOF counterexamples → revise',fill='#FAF8FE',title_size=14)
arrow([(3.295,6.30),(3.295,6.06)],zorder=5)
arrow([(5.57,5.845),(5.98,5.845),(5.98,6.69),(5.57,6.69)],color='#8B7EA5',zorder=5)

box(7.92,6.14,4.96,.72,'Same allowed pipeline choices',
    'Input · model · target · routing',fill='#FAFBFC',title_size=15,body_size=14)
text(10.4,5.72,'Seed fixed in advance · no OOF adaptation',14)
arrow([(6.95,8.30),(6.95,8.03),(3.5,8.03),(3.5,7.82)])
arrow([(6.95,8.03),(10.4,8.03),(10.4,7.82)])

box(.6,3.79,12.7,.99,'OOF eligibility → select → freeze specifications',
    'Positive-Tc MAE guard · weighted OOF MAE · freeze both arms and reference choices',TEAL,body_size=15)
arrow([(3.5,5.32),(3.5,5.04),(6.95,5.04),(6.95,4.78)])
ax.plot([10.4,10.4,6.95],[5.32,5.04,5.04],color=EDGE,linewidth=1.5,zorder=1)

box(.6,1.92,4.74,1.20,'Refit on frozen TRAIN',
    'Fit chosen specifications\non all 3,764 training records',title_size=17,body_size=15)
box(6.34,1.57,6.96,1.90,'Evaluate old validation once after freeze',
    '869 records · previously observed development set\nDevelopment evidence; no independent-test claim',title_size=17,body_size=15)
arrow([(6.95,3.79),(6.95,3.62),(2.97,3.62),(2.97,3.12)])
arrow([(5.34,2.52),(6.34,2.52)])

text(7,.85,'旧验证集已被使用过；本轮只验证开发收益，不构成新的独立测试。',15)
text(7,.40,'Protocol figure only · no experimental results shown · 历史测试标签不参与本轮选择或评价',13,color='#536575')

fig.savefig(OUT/'workflow_v2.png',dpi=200)
fig.savefig(OUT/'workflow_v2.svg')
plt.close(fig)
print('figures/workflow_v2.png')
print('figures/workflow_v2.svg')
