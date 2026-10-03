"""Training-OOF-only MCP interface for the bounded Tc pipeline search."""
from __future__ import annotations
import datetime as dt
import functools
import json
import os
from pathlib import Path
import site
import sys
import threading
import time

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
for folder in [ROOT.parents[1]/'work/scientific_agent_mcp_deps',Path('C:/Users/28908/Documents/Codex/2026-09-14/x20-hi-guohuan-this-paper-really/work/scientific_agent_mcp_deps')]:
    if folder.is_dir():site.addsitedir(str(folder))
for key in ['OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS']:os.environ[key]='1'
import numpy as np
from mcp.server import MCPServer
from pipeline import Workbench

def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,np.ndarray)):return [clean(v) for v in value]
    if isinstance(value,np.generic):return clean(value.item())
    if isinstance(value,float) and not np.isfinite(value):return None
    return value
def dump(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(clean(obj),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');tmp.replace(path)

mcp=MCPServer('Tc pipeline scientific workbench',version='2.0.0',instructions='Use only training out-of-fold evidence. Select fixed inputs, estimator, target transform and routing; inspect counterexamples and revise. No validation or retrospective targets are available. Composition templates and clusters do not establish physical material families.',log_level='WARNING')
LOCK=threading.RLock()
STATE=None
WB=None
def init():
    global STATE,WB
    if STATE is not None:return
    (ROOT/'agent').mkdir(exist_ok=True)
    p=ROOT/'agent/state.json'
    STATE=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'tool_calls':0,'strategy_attempts':0,'strategies':[]}
    WB=Workbench(ROOT)

def tool(fn):
    @functools.wraps(fn)
    def wrapped(*args,**kwargs):
        with LOCK:
            init()
            if STATE['tool_calls']>=18:return {'error':'18 processed-call budget exhausted; finish the report.'}
            STATE['tool_calls']+=1;dump(ROOT/'agent/state.json',STATE)
            event={'number':STATE['tool_calls'],'tool':fn.__name__,'started_utc':now(),'arguments':kwargs or list(args)}
            start=time.monotonic()
            try:result=clean(fn(*args,**kwargs));event['status']='ok'
            except Exception as exc:result={'error':f'{type(exc).__name__}: {exc}'};event['status']='error'
            response={'tool_result':result,'remaining_tool_calls':18-STATE['tool_calls'],'remaining_strategy_attempts':5-STATE['strategy_attempts']}
            event.update(finished_utc=now(),elapsed_seconds=time.monotonic()-start,response=response)
            with (ROOT/'agent/tool_events.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(event,ensure_ascii=False,allow_nan=False)+'\n')
            dump(ROOT/'agent/state.json',STATE)
            return response
    return mcp.tool()(wrapped)

@tool
def describe_data() -> dict:
    """Training cohort, fixed 3-fold OOF global references, action menu and route counts."""
    return WB.describe()

@tool
def run_strategy(name: str, hypothesis: str, falsification: str, revision_of: str, specification: dict) -> dict:
    """Try a fixed regression pipeline on training OOF; failures/duplicates consume one of five attempts.

    specification: input composition or composition_repaired; routing global,
    chemistry or kmeans3; global {model: extra_trees or hist_gradient_boosting,
    target: raw or log1p}; experts mapping route names to the same model/target
    pair. Chemistry routes cu_o, fe_anion, other; cluster routes cluster0..2.
    Unspecified or small routes use the global model. No hyperparameters can
    be changed. Supply a falsifiable predictive hypothesis and prior ID or none.
    """
    if STATE['strategy_attempts']>=5:raise ValueError('Five-attempt budget exhausted')
    STATE['strategy_attempts']+=1;cid=f"A{STATE['strategy_attempts']:02d}"
    dump(ROOT/'agent/state.json',STATE)
    metadata={'candidate_id':cid,'name':name,'hypothesis':hypothesis,'falsification':falsification,'revision_of':revision_of,'specification':specification,'started_utc':now()}
    dump(ROOT/'agent'/f'{cid}_scientific_metadata.json',metadata)
    try:
        if not all(isinstance(v,str) and 3<=len(v)<=4000 for v in [name,hypothesis,falsification]):raise ValueError('Scientific metadata must be concise nonempty strings')
        if revision_of.lower() not in ('none','') and revision_of not in {x['id'] for x in STATE['strategies']}:raise ValueError('revision_of must name an earlier attempted strategy or none')
        result=WB.run_strategy(cid,specification)
        item={'id':cid,'name':name,'status':'complete','result':result}
    except Exception as exc:
        item={'id':cid,'name':name,'status':'failed','error':f'{type(exc).__name__}: {exc}'}
    metadata.update(finished_utc=now(),status=item['status'])
    dump(ROOT/'agent'/f'{cid}_scientific_metadata.json',metadata)
    STATE['strategies'].append(clean(item));dump(ROOT/'agent/state.json',STATE)
    return item

@tool
def counterexamples(candidate_id: str, k: int = 6) -> dict:
    """Up to six TRAIN out-of-fold error cases; use them to revise a predictive hypothesis."""
    if not 1<=k<=6:raise ValueError('k must be 1..6')
    return WB.counterexamples(candidate_id,k)

@tool
def compare_strategies() -> dict:
    """Compare fixed references and attempted pipelines on pooled TRAIN OOF only."""
    return {'comparison':WB.compare(),'attempts':STATE['strategies']}

@tool
def record_conclusion(summary: str, supported_hypotheses: list[str], failed_hypotheses: list[str], limitations: list[str]) -> dict:
    """Record a conclusion grounded in training OOF, including failures and limits."""
    if len(summary)>8000:raise ValueError('Summary too long')
    dump(ROOT/'agent/conclusion.json',{'summary':summary,'supported_hypotheses':supported_hypotheses,'failed_hypotheses':failed_hypotheses,'limitations':limitations,'recorded_utc':now(),'scope':'Training OOF on previously observed public historical records'})
    return {'saved':True,'remaining_action':'Finish your concise report. Validation outcomes are unavailable.'}

if __name__=='__main__':mcp.run(transport='stdio')
