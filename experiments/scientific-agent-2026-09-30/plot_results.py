"""Create publication/export-ready figures from the frozen test JSON."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
ROOT=Path(__file__).resolve().parent
results=json.loads((ROOT/'evaluation/final/test_results.json').read_text())
OUT=ROOT/'figures';OUT.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,ax=plt.subplots(2,2,figsize=(11.8,7.5),gridspec_kw={'height_ratios':[1.3,1]})
colors=['#84909C','#D99128','#2E698F']
for col,(task,label,unit) in enumerate([('formation','Formation energy','MAE (eV/atom)'),('hull','On-hull classification','Log loss')]):
    data=results['tasks'][task];metric='MAE_eV_atom' if task=='formation' else 'logloss'
    ys=[data['metrics'][key][metric] for key in ['raw','selected','hgb']]
    ax[0,col].bar(np.arange(3),ys,color=colors,width=.58)
    ax[0,col].set_xticks(np.arange(3),['Raw30','Raw30 + GPT\n12 descriptors','HGB (Raw30)'])
    ax[0,col].set_ylim(0,max(ys)*1.18);ax[0,col].set_ylabel(unit+'; lower is better')
    ax[0,col].set_title(label,loc='left',fontweight='bold')
    for i,y in enumerate(ys):ax[0,col].text(i,y+max(ys)*.025,f'{y:.4f}',ha='center')
    ax[0,col].grid(axis='y',alpha=.18);ax[0,col].set_axisbelow(True)
    bottom=ax[1,col];bottom.axvline(0,color='#68737D',linestyle='--',linewidth=1)
    for y,control in enumerate(['raw','hgb']):
        ci=data['paired_bootstrap'][control];point=ci['selected_minus_control']
        bottom.errorbar(point,y,xerr=[[point-ci['lower95']],[ci['upper95']-point]],fmt='o',color=colors[0 if control=='raw' else 2],capsize=5,linewidth=2)
    bottom.set_yticks([0,1],['GPT − Raw30','GPT − HGB']);bottom.set_ylim(1.65,-.65)
    bottom.set_xlabel('Difference in '+unit+' (negative favors GPT)')
    bottom.set_title('Paired chemical-system bootstrap: 95% interval',loc='left',fontsize=10)
    bottom.grid(axis='x',alpha=.18);bottom.set_axisbelow(True)
fig.suptitle('Tool-using GPT descriptor discovery: frozen independent test',x=.06,ha='left',fontsize=16,fontweight='bold')
fig.text(.06,.922,'721 Materials Project structures · 681 held-out chemical systems · same rows in all arms',fontsize=11,color='#465461')
fig.text(.06,.03,'Intervals: 1,000 paired system resamples, conditional on the fitted models.\nDFT-relaxed inputs; no new DFT, superconductivity test, or matched broad descriptor-search control.',fontsize=9,color='#465461')
fig.subplots_adjust(left=.10,right=.97,top=.84,bottom=.16,wspace=.35,hspace=.62)
for ext in ['png','svg','pdf']:fig.savefig(OUT/f'test_comparison.{ext}',dpi=180)
plt.close(fig)
