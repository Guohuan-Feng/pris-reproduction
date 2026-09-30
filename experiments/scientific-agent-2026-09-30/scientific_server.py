"""Local scientific MCP tools. Discovery has no test-data endpoint."""
from __future__ import annotations
import datetime as dt
import functools
import gzip
import hashlib
import json
import os
from pathlib import Path
import site
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parents[1]
sys.path.insert(0,str(ROOT))
site.addsitedir(str(WORKSPACE/'work/scientific_agent_mcp_deps'))
import numpy as np
import pandas as pd
from mcp.server import MCPServer
from descriptor_runtime import FUNCTIONS, METHODS, BUILTINS, validate
from evaluator import Evaluator

def dump(path,obj):
    path=Path(path);temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temporary.replace(path)
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean(v) for v in x]
    if isinstance(x,np.generic):return clean(x.item())
    if isinstance(x,float) and not np.isfinite(x):return None
    return x

mcp=MCPServer('PRIS scientific workbench',version='1.0.0',instructions=
 'Only development data are available. Propose a hypothesis, author numerical descriptors, run bounded experiments, inspect counterexamples and revise. Validation is adaptive. Do not infer final-test performance.',log_level='WARNING')
LOCK=threading.RLock()
STATE=None
EVAL=None
RECORDS=None
FEATURES=None
DEV=None

def init():
    global STATE,EVAL,RECORDS,FEATURES,DEV
    if STATE is not None:return
    (ROOT/'agent').mkdir(exist_ok=True)
    STATE=load(ROOT/'agent/state.json') if (ROOT/'agent/state.json').exists() else {'tool_calls':0,'experiment_attempts':0,'experiments':[]}
    # Deliberately no descriptor_test or sealed_test reads in this server.
    with gzip.open(ROOT/'data/descriptor_development.jsonl.gz','rt',encoding='utf-8') as stream:
        RECORDS={r['material_id']:r for r in map(json.loads,stream)}
    DEV=pd.read_csv(ROOT/'data/development.csv.gz')
    FEATURES=pd.read_csv(ROOT/'data/features.csv.gz')
    FEATURES=FEATURES[FEATURES.material_id.isin(DEV.material_id)].copy()
    assert set(RECORDS)==set(DEV.material_id)==set(FEATURES.material_id)
    EVAL=Evaluator(ROOT)
    EVAL.prepare()

def tool(fn):
    @functools.wraps(fn)
    def wrapped(*args,**kwargs):
        with LOCK:
            init()
            if STATE['tool_calls']>=24:
                with (ROOT/'agent/rejected_tool_calls.jsonl').open('a',encoding='utf-8') as stream:
                    stream.write(json.dumps({'at':now(),'tool':fn.__name__,'reason':'processed-call budget exhausted'})+'\n')
                return {'error':'24 processed-tool-call budget exhausted. Return your final report now.'}
            STATE['tool_calls']+=1
            dump(ROOT/'agent/state.json',STATE)
            call={'number':STATE['tool_calls'],'tool':fn.__name__,'started_utc':now(),'arguments':kwargs or list(args)}
            start=time.monotonic()
            try:
                result=clean(fn(*args,**kwargs));call['status']='ok'
            except Exception as exc:
                result={'error':f'{type(exc).__name__}: {exc}'};call['status']='error'
            result={'tool_result':result,'remaining_tool_calls':24-STATE['tool_calls'],'remaining_experiment_attempts':6-STATE['experiment_attempts']}
            call.update(finished_utc=now(),elapsed_seconds=time.monotonic()-start,response=result)
            with (ROOT/'agent/tool_events.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(call,ensure_ascii=False,allow_nan=False)+'\n')
            dump(ROOT/'agent/state.json',STATE)
            return result
    return mcp.tool()(wrapped)

@tool
def describe_data() -> dict:
    """Inspect train-only statistics, model baselines, input schema and numerical Python API."""
    train=DEV[DEV.split=='train'].merge(FEATURES,on='material_id',suffixes=('','_feature'))
    names=load(ROOT/'data/feature_schema.json')
    if isinstance(names,dict):names=names.get('features',names.get('allowed_features'))
    stats={n:{'min':float(train[n].min()),'median':float(train[n].median()),'max':float(train[n].max()),'formation_correlation':float(train[n].corr(train.formation_energy_per_atom))} for n in names}
    baseline=EVAL.prepare()
    return {'task':'Formation energy regression and on-hull classification; DFT-relaxed MP structures.',
      'development_split_counts':DEV.split.value_counts().to_dict(),'baseline':baseline,
      'train_feature_statistics':stats,'validation_use':'Adaptive development only; no independent claims.',
      'structure_schema':{'symbols':'N element strings','n_sites':'integer N','volume':'cell Angstrom^3','lattice':'3x3 row lattice vectors, Angstrom','frac_coords':'Nx3 fractional coordinates','distance_matrix':'NxN closest periodic-image distance, diagonal shortest nonzero cell translation; NOT a complete neighbor list','atomic_numbers':'N integers','electronegativities':'N Pauling values; null where unknown','covalent_radii':'N Angstrom values','neighbor_center':'E central-site indices','neighbor_index':'E neighbor-site indices including repeated periodic images','neighbor_distance':'E distances in Angstrom, 0<d<=6; all periodic image multiplicities','neighbor_image':'Ex3 lattice-image translations if supplied'},
      'descriptor_contract':'Provide exactly def featurize(s): returning a consistent ordered dict of 1..12 scalar values. No imports/helper functions/files/labels. np is supplied. Use np.array(s[key],dtype=float) to convert null to NaN. Use periodic edge lists for coordination. Functions must generalize to any N. Missing scalars may be np.nan and will be imputed from train only. Infinite outputs fail.',
      'numpy_functions':FUNCTIONS,'numpy_constants':['nan','inf','pi'],'array_methods':sorted(METHODS),'python_builtins':list(BUILTINS),
      'allowed_control_flow':'Assignments, for loops, if, comprehensions, arithmetic, comparisons, dictionaries, slicing. No while/import/try/class/lambda/reflection.',
      'experiment_budget':6,'selection':'Per-task minimum validation MAE/logloss over raw baseline and successful candidates; code+models frozen before unseen test.'}

@tool
def inspect_records(material_ids: list[str]) -> dict:
    """Inspect up to three DEVELOPMENT records and labels; no test records are available."""
    if not 1<=len(material_ids)<=3:raise ValueError('Request one to three IDs')
    out=[]
    for mid in material_ids:
        if mid not in RECORDS:raise ValueError('ID unavailable in development data')
        r=RECORDS[mid]
        sample={k:v for k,v in r.items() if k not in ['neighbor_center','neighbor_index','neighbor_distance','neighbor_image','distance_matrix']}
        if r['n_sites']>12:
            sample={k:v[:12] if isinstance(v,list) and k not in ['lattice'] else v for k,v in sample.items()}
            sample['site_preview_truncated']=True
        sample['neighbor_count']=len(r['neighbor_center'])
        sample['neighbor_edge_preview']=[{k:r[k][i] for k in ['neighbor_center','neighbor_index','neighbor_distance']} for i in range(min(12,len(r['neighbor_center'])))]
        sample['development_labels']=DEV.set_index('material_id').loc[mid].to_dict()
        sample['raw_features']=FEATURES.set_index('material_id').loc[mid].to_dict()
        out.append(sample)
    return {'records':out}

def worker_compute(code,records,timeout=180):
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','TEMP','TMP'}}
    env.update(OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONIOENCODING='utf-8')
    proc=subprocess.run([sys.executable,str(ROOT/'descriptor_runtime.py')],input=json.dumps({'code':code,'records':records},allow_nan=False),text=True,encoding='utf-8',capture_output=True,env=env,timeout=timeout)
    if proc.returncode:raise RuntimeError(proc.stderr[-3000:])
    return json.loads(proc.stdout)

@tool
def run_experiment(name: str, hypothesis: str, scope: str, falsification: str, revision_of: str, code: str) -> dict:
    """Author and run new descriptor code, then fit raw30+descriptors on train and score validation.

    This consumes one of six attempts even if code fails. Write a mechanistic
    hypothesis, scope, falsification condition and prior experiment ID (or none).
    Numerical fitting is fixed; you control descriptors and their revisions.
    """
    if STATE['experiment_attempts']>=6:raise ValueError('Six-attempt budget exhausted')
    STATE['experiment_attempts']+=1
    dump(ROOT/'agent/state.json',STATE)
    eid=f"E{STATE['experiment_attempts']:02d}"
    folder=ROOT/'experiments'/eid;folder.mkdir(parents=True,exist_ok=False)
    (folder/'descriptor.py').write_text(code,encoding='utf-8')
    spec={'id':eid,'name':name,'hypothesis':hypothesis,'scope':scope,'falsification':falsification,'revision_of':revision_of,'code_sha':sha(folder/'descriptor.py'),'started_utc':now()}
    dump(folder/'specification.json',spec)
    try:
        if not all(isinstance(v,str) and 3<=len(v)<=4000 for v in [name,hypothesis,scope,falsification]):raise ValueError('Provide concise nonempty scientific metadata')
        validate(code)
        computed=worker_compute(code,list(RECORDS.values()))
        frame=pd.DataFrame(computed['rows']);spec['descriptor_names']=computed['descriptor_names']
        frame.to_csv(folder/'development_descriptors.csv.gz',index=False)
        result=EVAL.evaluate_candidate(eid,frame,spec)
        spec.update(status='complete',finished_utc=now())
        dump(folder/'specification.json',spec);dump(folder/'result.json',clean(result))
        STATE['experiments'].append({'id':eid,'name':name,'status':'complete','result':clean(result)})
        return {'experiment_id':eid,'descriptor_names':computed['descriptor_names'],'results':result}
    except Exception as exc:
        spec.update(status='failed',finished_utc=now(),error=f'{type(exc).__name__}: {exc}')
        dump(folder/'specification.json',spec)
        STATE['experiments'].append({'id':eid,'name':name,'status':'failed','error':spec['error']})
        return {'experiment_id':eid,'status':'failed','error':spec['error']}

@tool
def counterexamples(candidate_id: str, task: str, k: int = 6) -> dict:
    """Inspect up to six held-out DEVELOPMENT errors for formation or hull, then revise a hypothesis."""
    if task not in ['formation','hull'] or not 1<=k<=6:raise ValueError('task formation/hull, k1..6')
    return EVAL.get_counterexamples(candidate_id,task,k=k)

@tool
def compare_experiments() -> dict:
    """Compare all attempted experiments on adaptive validation; do not interpret as final test."""
    return {'baselines':EVAL.prepare(),'experiments':STATE['experiments']}

@tool
def record_conclusion(summary: str, supported_hypotheses: list[str], failed_hypotheses: list[str], limitations: list[str]) -> dict:
    """Record the agent's evidence-based development conclusion and failed/revised hypotheses."""
    result={'summary':summary,'supported_hypotheses':supported_hypotheses,'failed_hypotheses':failed_hypotheses,'limitations':limitations,'recorded_utc':now(),'evidence_scope':'adaptive development only'}
    dump(ROOT/'agent/conclusion.json',result)
    return {'saved':True,'instruction':'Return final concise scientific report. Do not claim unseen-test performance.'}

if __name__=='__main__':mcp.run(transport='stdio')
