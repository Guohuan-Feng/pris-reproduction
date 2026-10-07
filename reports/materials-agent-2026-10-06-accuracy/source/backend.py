"""Frozen repeated chemical-system OOF scientific backend. No fits on import.

The controller authorizes exactly one fresh candidate per actual Agent session.
Previously revealed validation cohorts never enter this selection API.
"""
from __future__ import annotations
from datetime import datetime,timezone
import gzip,hashlib,importlib.util,json,os,sys,time
from pathlib import Path

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
WORK=ROOT.parent
PREVIOUS=WORK/'materials_structure_agent_2026-10-05_pilot'
EVOLVING=WORK/'materials_evolving_agent_2026-10-06_recovery1'
OLD=WORK/'materials_adaptive_agent_2026-10-05_recovery2'
DEV=WORK/'materials_strategy_agent_2026-10-02/development'
STRUCTURES=WORK/'materials_agent_analysis_2026-10-01/data/structures.jsonl.gz'
STATE=ROOT/'state/research_state.json'
SOURCES=['backend.py','science_server.py','controller.py','finalize.py','representation_runtime.py','predictor_runtime.py','predictor_preflight.py','session_transport.py','decision_contract.py','audited_decision_interceptor.py','data_curator.py','runtime_config.json']
PARTITION_SEEDS=(20261007,20261008)
BASELINE_IDS=('B_C018','B_E011')
CURRENT_INCUMBENT_CODE=(EVOLVING/'candidates/C018/predictor.py').read_text(encoding='utf-8')
LEGACY_E011_CODE='def fit(X_train,y_train):\n    return train_model("e011",X_train,y_train,{})\ndef predict(state,X_eval):\n    return state.predict(X_eval)\n'

def incumbent_artifact_hashes():
    paths=[EVOLVING/'candidates/C018/predictor.py',EVOLVING/'candidates/C018/registration.json',EVOLVING/'experiments/C018/result.json',EVOLVING/'representations/R004/compute.py',EVOLVING/'representations/R004/proposal.json',EVOLVING/'representations/R004/train_features.csv.gz']
    return {str(p.resolve()):sha(p) for p in paths}

def historical_representation_matrix_hashes():
    prepared=load(ROOT/'training_input_preparation.json')
    if prepared is not None:return dict(prepared['historical_representation_matrix_hashes'])
    old=load(EVOLVING/'state/research_state.json')
    return {str((EVOLVING/entry['matrix_path']).resolve()):sha(EVOLVING/entry['matrix_path']) for entry in old['representations'].values()}

def now():return datetime.now(timezone.utc).isoformat()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def jsha(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def load(path,default=None):return json.loads(Path(path).read_text(encoding='utf-8-sig')) if Path(path).exists() else default
def dump(path,value,exclusive=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if exclusive and path.exists():raise FileExistsError(str(path))
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');tmp.replace(path)
def append(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8') as f:f.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
def state():return load(STATE)

def affordable_candidate_fit_cap(s):
    budget=load(ROOT/'protocol.json')['budget']
    later=max(0,budget['completed_candidates']-s['counters']['experiments']-1)
    return max(0,min(budget['max_fits_per_block'],(budget['base_fit_reservations']-s['counters']['base_fits_reserved']-budget.get('final_fit_reservation',18)-4*later)//4))

def remaining_wall(scope='total'):
    launch=load(ROOT/'controller_launch.json')
    if launch is None:raise RuntimeError('Scientific controller has not started')
    budget=load(ROOT/'protocol.json')['budget'];cap=budget['search_wall_seconds'] if scope=='search' else budget['wall_seconds']
    remaining=cap-(time.monotonic()-launch['monotonic_start'])
    if remaining<=0:raise RuntimeError('Declared scientific wall cap reached')
    return remaining

def remaining_session(attempt,decision_reserve_seconds=60):
    invocation=load(Path(attempt)/'invocation.json')
    if invocation is None:raise RuntimeError('Actual Agent invocation receipt missing')
    elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(invocation['started_utc'])).total_seconds()
    remaining=invocation['hard_wall_seconds']-elapsed-decision_reserve_seconds
    if remaining<=0:raise RuntimeError('Agent session has no scientific time left')
    return remaining

class Context:
    def __init__(self):
        import numpy as np,pandas as pd
        spec=importlib.util.spec_from_file_location('_accuracy_frozen_pilot',PREVIOUS/'pilot_evaluation.py')
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
        exec(compile((PREVIOUS/'pilot_evaluation.py').read_bytes(),str(PREVIOUS/'pilot_evaluation.py'),'exec'),module.__dict__)
        self.legacy,_=module.load_legacy(OLD/'evaluation.py','799aa512d7c049a24a0ae1848fd3228187aed8276be539d6bfdef343ad9b05b5')
        self.original_columns=list(self.legacy.FEATURES)
        self.raw_columns=list(self.original_columns);self.columns=list(self.original_columns)
        raw=pd.read_csv(DEV/'features.csv.gz',float_precision='round_trip',index_col='material_id').sort_index()
        e04=pd.read_csv(DEV/'E04_descriptors.csv.gz',float_precision='round_trip',index_col='material_id').loc[raw.index]
        targets=pd.read_csv(DEV/'targets.csv.gz',float_precision='round_trip',usecols=['material_id','split','formation_energy_per_atom'],index_col='material_id').loc[raw.index]
        self.all_X=pd.concat([raw[self.original_columns[:30]],e04[self.original_columns[30:]]],axis=1)
        self.train_ids=targets.index[targets.split.eq('train')];self.validation_ids=targets.index[targets.split.eq('validation')]
        self.y=targets.loc[self.train_ids,'formation_energy_per_atom'];self.meta=raw.loc[self.train_ids,['formula','chemical_system','composition_signature']]
        fixed_path=ROOT/'incumbent/train_features.csv.gz'
        fixed=pd.read_csv(fixed_path if fixed_path.exists() else EVOLVING/'representations/R004/train_features.csv.gz',float_precision='round_trip',index_col='material_id').loc[self.train_ids]
        if fixed.shape!=(2164,24):raise ValueError('Frozen incumbent R004 matrix changed')
        self.old_X=self.all_X.loc[self.train_ids];self.X=pd.concat([self.old_X,fixed],axis=1);self.base_X=self.X;self.feature_columns=list(self.X.columns)
        if len(self.train_ids)!=2164 or len(self.validation_ids)!=715 or self.X.shape!=(2164,66):raise ValueError('Development boundary changed')
        self.folds=self._make_partitions()
        manifest=ROOT/'training_partitions.csv'
        if manifest.exists():
            frozen=pd.read_csv(manifest,index_col='material_id').loc[self.train_ids]
            if not frozen.equals(self.folds):raise ValueError('Registered repeated folds differ from deterministic protocol')
        self._structures=None
    def _make_partitions(self):
        import numpy as np,pandas as pd
        from sklearn.model_selection import GroupKFold
        arrays={}
        for repeat,seed in enumerate(PARTITION_SEEDS):
            folds=np.full(len(self.train_ids),-1,dtype=int);seen=np.zeros(len(folds),int)
            for fold,(train,test) in enumerate(GroupKFold(n_splits=2,shuffle=True,random_state=seed).split(self.X,self.y,self.meta.chemical_system)):
                if set(self.meta.iloc[train].chemical_system)&set(self.meta.iloc[test].chemical_system):raise ValueError('Chemical systems cross repeated fold')
                folds[test]=fold;seen[test]+=1
                if any(np.sum((self.old_X.iloc[train,17].to_numpy()>0)==label)<150 for label in (False,True)):raise ValueError('Repeated fold cannot support frozen E011 oxygen routes')
            if not np.all(seen==1):raise ValueError('Incomplete repeated fold assignment')
            arrays[f'repeat_{repeat}']=folds
        return pd.DataFrame(arrays,index=self.train_ids).rename_axis('material_id')
    def structures(self,ids=None):
        if self._structures is None:
            with gzip.open(STRUCTURES,'rt',encoding='utf-8') as f:self._structures={r['material_id']:r for r in map(json.loads,f)}
        return [self._structures[i] for i in (ids if ids is not None else self.train_ids)]
    def matrix(self,blocks,ids=None):
        import pandas as pd
        ids=self.train_ids if ids is None else ids
        if not set(ids)<=set(self.train_ids):raise ValueError('Search matrix exposes training IDs only; finalizer must create frozen heldout matrices separately')
        tables=[self.X.loc[ids]]
        for rid in blocks:
            entry=state()['representations'][rid]
            frame=pd.read_csv(ROOT/entry['matrix_path'],float_precision='round_trip',index_col='material_id');tables.append(frame.loc[ids])
        return pd.concat(tables,axis=1)

CTX=None
def context():
    global CTX
    if CTX is None:CTX=Context()
    return CTX

def prepare_training_inputs():
    """Zero-fit frozen-input preparation. Call once before protocol registration."""
    import shutil
    if (ROOT/'protocol.json').exists() or STATE.exists():raise RuntimeError('Cannot prepare inputs after registration')
    folder=ROOT/'incumbent';folder.mkdir(exist_ok=True)
    for source,dest in [(EVOLVING/'representations/R004/compute.py',folder/'compute.py'),(EVOLVING/'representations/R004/train_features.csv.gz',folder/'train_features.csv.gz'),(EVOLVING/'representations/R004/proposal.json',folder/'representation_proposal.json'),(EVOLVING/'candidates/C018/predictor.py',folder/'predictor.py')]:
        if dest.exists():
            if sha(dest)!=sha(source):raise RuntimeError('Existing incumbent input differs')
        else:shutil.copyfile(source,dest)
    ctx=context();path=ROOT/'training_partitions.csv'
    if path.exists():raise FileExistsError(str(path))
    ctx.folds.to_csv(path,index=True)
    receipt={'prepared_utc':now(),'scientific_fits':0,'actual_LLM_calls':0,'training_rows':2164,'default_feature_count':66,'partition_seeds':list(PARTITION_SEEDS),'ordered_IDs_sha256':jsha(list(ctx.train_ids)),'fold_assignment_sha256':jsha({str(i):[int(v) for v in row] for i,row in zip(ctx.train_ids,ctx.folds.to_numpy())}),'partition_manifest_sha256':sha(path),'input_hashes':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in folder.iterdir()},'historical_representation_matrix_hashes':historical_representation_matrix_hashes(),'baseline_fit_reservations':44,'heldout_targets_returned_to_Agent':False}
    dump(ROOT/'training_input_preparation.json',receipt,exclusive=True);return receipt

def initialize():
    """Create an empty science state AFTER the root registers all inputs/sources."""
    if STATE.exists():raise RuntimeError('New stage cannot be reinitialized')
    p=load(ROOT/'protocol.json')
    if p is None or load(ROOT/'fresh_cohort/prefit_manifest.json') is None:raise RuntimeError('Registered protocol and sealed fresh manifest required')
    ctx=context()
    dump(STATE,{'started_utc':now(),'protocol_sha256':sha(ROOT/'protocol.json'),'representations':{},'proposals':{},'baselines':{},'experiments':{},'decisions':[],
        'counters':{'experiments':0,'investigations':0,'representation_submissions':0,'predictor_submissions':0,'baseline_comparisons':0,'base_fits_reserved':0,'fit_started':0,'fit_completed':0,'uncached_input_tokens':0,'output_tokens':0,'tool_calls':0},'active_operation':None,'stop_reason':None,'champion_frozen':False},exclusive=True)
    assert_frozen();return {'initialized':True,'scientific_fits':0,'training_rows':len(ctx.train_ids)}

def assert_frozen():
    s=state();p=load(ROOT/'protocol.json')
    if not s or not p or sha(ROOT/'protocol.json')!=s['protocol_sha256']:raise RuntimeError('Registered protocol missing or changed')
    if any(sha(ROOT/n)!=h for n,h in p['source_hashes'].items()):raise RuntimeError('Frozen runtime changed')
    if any(sha(Path(n))!=h for n,h in p['input_hashes'].items()):raise RuntimeError('Original input changed')
    import predictor_runtime
    predictor_runtime.verify_dependency_lock(check_files=False)
    for entry in [*s['representations'].values(),*s['proposals'].values()]:
        for name,h in entry['frozen_files'].items():
            if sha(ROOT/name)!=h:raise RuntimeError('Approved program/input changed')

def compact_result(result):
    keys=('candidate_id','baseline_id','OOF','incumbent_OOF_MAE','OOF_schedule_gate_pass','selection_eligible','eligibility_components','actual_new_fits','registered_hypothesis','falsification','code_sha256','feature_blocks','scope','validation_score_returned','fresh_targets_accessed')
    compact={k:result[k] for k in keys if k in result}
    identity=result.get('candidate_id') or result.get('baseline_id')
    if identity:
        path=ROOT/('experiments' if result.get('candidate_id') else 'baselines')/identity/'result.json'
        if path.exists():compact['complete_result_sha256']=sha(path)
    return compact

def summary_context():
    s=state();server=load(ROOT/'state/server_state.json',{'tool_calls':0,'calls':[]});counters=dict(s['counters']);counters['tool_calls']=server['tool_calls']
    return {'counters':counters,'active_operation':s['active_operation'],'stop_reason':s['stop_reason'],'ledger_consistent':True,
        'candidate_fit_budget':{'max_affordable_fits_per_training_block':affordable_candidate_fit_cap(s),'OOF_training_blocks':4,'reserved_final_capacity':load(ROOT/'protocol.json')['budget'].get('final_fit_reservation',18)},
        'incomplete_scientific_calls':[r['evidence_id'] for r in server['calls'] if r['status']=='started'],
        'representations':{k:{'feature_names':v['feature_names'],'hypothesis':v['hypothesis'],'sha256':v['code_sha256'],'rows':v['summary']['rows'],'columns':v['summary']['columns'],'invariance_passed':True,'novel_columns':v['summary']['novel_vs_previous_columns']} for k,v in s['representations'].items()},
        'baselines':{k:compact_result(v['summary']) for k,v in s['baselines'].items() if v['status']=='complete'},
        'completed_results':{k:compact_result(v['summary']) for k,v in s['experiments'].items() if v['status']=='complete'},
        'completed_result_artifacts':{k:{'result_sha256':sha(ROOT/'experiments'/k/'result.json'),'OOF_predictions_sha256':sha(ROOT/'experiments'/k/'internal_oof_predictions.csv.gz')} for k,v in s['experiments'].items() if v['status']=='complete'},
        'incomplete_results':{k:v['status'] for k,v in s['experiments'].items() if v['status']!='complete'},'last_decisions':s['decisions'][-2:],'budget':load(ROOT/'protocol.json')['budget'],
        'available_evidence_ids':[r['evidence_id'] for r in server['calls'] if r['status']=='complete'],
        'presentation_contract':'Scientific compact projection is registered before launch. Full invariant worker logs/fold provenance/input hashes/complete responses remain immutable on disk.'}

def diagnostics(pred):
    import numpy as np
    ctx=context();values=np.asarray(pred,float)
    if values.shape!=(2,len(ctx.train_ids)) or not np.isfinite(values).all():raise ValueError('Require two complete OOF prediction vectors')
    err=values-ctx.y.to_numpy()[None,:];absolute=np.abs(err)
    result={'rows':int(absolute.size),'unique_materials':len(ctx.train_ids),'OOF_predictions_per_material':2,'MAE_eV_atom':float(absolute.mean()),'RMSE_eV_atom':float(np.sqrt((err**2).mean())),
        'mean_repeat_RMSE_eV_atom':float(np.sqrt((err**2).mean(axis=1)).mean()),'mean_prediction_minus_truth':float(err.mean()),'p90_abs_error':float(np.quantile(absolute,.9)),'p99_abs_error':float(np.quantile(absolute,.99)),'partitions':{},'folds':{},'groups':{},'metric_definition':'Pooled absolute errors of two repeated chemical-system 2-fold partitions; 4328 predictions, 2164 unique materials. Repeated blocks are not independent confirmations. Eligibility RMSE is the arithmetic mean of each repeat RMSE, distinct from pooled RMSE.'}
    for repeat in range(2):
        result['partitions'][str(repeat)]={'seed':PARTITION_SEEDS[repeat],'rows':len(ctx.train_ids),'MAE_eV_atom':float(absolute[repeat].mean()),'RMSE_eV_atom':float(np.sqrt((err[repeat]**2).mean())),'p99_abs_error':float(np.quantile(absolute[repeat],.99))}
        for fold in range(2):
            mask=ctx.folds.iloc[:,repeat].to_numpy()==fold;a=absolute[repeat,mask];e=err[repeat,mask]
            result['folds'][f'{repeat}:{fold}']={'rows':int(mask.sum()),'MAE_eV_atom':float(a.mean()),'RMSE_eV_atom':float(np.sqrt((e**2).mean())),'mean_prediction_minus_truth':float(e.mean()),'p99_abs_error':float(np.quantile(a,.99))}
    groups={'nitrogen':ctx.old_X.comp_fraction_Z007.to_numpy()>0,'oxygen':ctx.old_X.comp_fraction_Z008.to_numpy()>0,'no_oxygen':ctx.old_X.comp_fraction_Z008.to_numpy()<=0,'ternary_plus':ctx.old_X.comp_n_elements.to_numpy()>=3}
    for label,mask in groups.items():
        a=absolute[:,mask];e=err[:,mask];result['groups'][label]={'unique_materials':int(mask.sum()),'rows':int(a.size),'MAE_eV_atom':float(a.mean()),'RMSE_eV_atom':float(np.sqrt((e**2).mean())),'mean_prediction_minus_truth':float(e.mean()),'p99_abs_error':float(np.quantile(a,.99))}
    return result

def research_context():
    import predictor_runtime as p,representation_runtime as r
    ctx=context();s=state()
    if any(s['baselines'].get(k,{}).get('status')!='complete' for k in BASELINE_IDS):raise RuntimeError('Both actual new-fold baseline fits must complete before Agent research')
    return {'state':summary_context(),'prior_findings':['The previous20 candidates selected C018: fixed R00424 graph-neighbor descriptors + raw-target E0110.8 and signed-log-target HGB0.2. Previously released715 and1000 cohorts are known history and never new confirmations. Training OOF improvements were partly fold dependent; this new search evaluates two newly registered chemical-system partitions.','Old fixed angles, KRR, N/Omean residual and multiple other structure blocks were negative. These are historical training observations, not a ban on new scientific programs.'],
        'feature_column_order':ctx.feature_columns,'fixed_incumbent_structure_columns':ctx.feature_columns[42:],'representation_api':{'signature':'def compute(structure): return4..32 declared finite floats','fields':sorted(r.STRUCTURE_FIELDS),'numpy_functions':sorted(r.NP_NAMES),'numpy_linalg':sorted(r.NP_LINALG_NAMES),'math_functions':sorted(r.MATH_NAMES),'array_attributes':sorted(r.ARRAY_ATTRIBUTES),'safe_builtins':sorted(r.SAFE_BUILTINS),'helper':'closest_neighbors(structure) returns per-center periodic vectors, nearest12 plus ties; full neighbor center/index/distance/image arrays and lattice also available. material_id forbidden.','distance_matrix_convention':'Positive nearest-periodic-self diagonal or zero are allowed; prefer periodic edges for intensive statistics.','geometry_invariance':list(r.TRANSFORMATIONS),'worker_limits':'2048MB,20sec/batch,240sec whole2164 matrix'},
        'predictor_api':{'signatures':['def fit(X_train,y_train): return state','def predict(state,X_eval): return finite prediction vector'],'helper':'train_model(kind,X_train,y_train,params,sample_weight=None) returns .predict model. Only fit phase can train. Training arrays read-only; transform copies inside fit. No eval targets. E011/KRR accept no weights; ET/HGB/Ridge/CatBoost accept finite nonnegative weights normalized to mean1, with positive mass. All atomic fits counted.','learners':p.MODEL_API,'max_fits_per_block':7,'OOF_training_blocks':4,'raw42_first':True,'fixed66_default':True,'sklearn_seed':20261002,'catboost_seed':20261006},
        'instructions':'Author exactly one substantive new scientific program and/or new invariant structure block per actual cycle. Default fixed66 +0..2 newly approved blocks. Do not repeat exact program/input identity. All20 real candidates are retained. Select only by4328 repeated OOF pooledMAE; inspect partition/fold/tail/group consistency. No old715/old1000/new-confirmation scores returned. After tool delivery error do not refit: research_context is a read-only reconciliation of a known completed server result and records its full result hash. Stop on any unknown actual fit.'}

def submit_representation(code,feature_names,hypothesis,falsification):
    import numpy as np,pandas as pd,representation_runtime as runtime
    assert_frozen();s=state();p=load(ROOT/'protocol.json');ctx=context()
    if s['active_operation'] or s['stop_reason']:raise RuntimeError('Research not ready for proposal')
    if s['counters']['representation_submissions']>=p['budget']['max_representation_submissions']:raise ValueError('Representation submission cap')
    if min(len(hypothesis.strip()),len(falsification.strip()))<40:raise ValueError('Substantive hypothesis/falsification required')
    number=s['counters']['representation_submissions']+1;rid=f'R{number:03d}';folder=ROOT/'representations'/rid;folder.mkdir(parents=True,exist_ok=False)
    (folder/'compute.py').write_text(code,encoding='utf-8');dump(folder/'proposal.json',{'code_sha256':runtime._code_hash(code),'feature_names':feature_names,'hypothesis':hypothesis,'falsification':falsification,'utc':now()},exclusive=True)
    s['counters']['representation_submissions']=number;s['active_operation']={'kind':'representation','id':rid};dump(STATE,s)
    try:
        invariant_receipt=ROOT/'runtime_receipts'/f'{rid}_invariance.json';whole_receipt=ROOT/'runtime_receipts'/f'{rid}_whole_compute.json';records=ctx.structures()
        validation=runtime.validate_proposal(code,feature_names,invariant_records=[records[i] for i in (0,1,100,300,700,1100,1500,2000)],timeout_s=20,memory_mb=2048,receipt_path=invariant_receipt)
        if not validation.accepted:raise ValueError('; '.join(validation.reasons))
        matrix,whole=runtime.compute_validated(code,records,feature_names=feature_names,original_feature_rows=ctx.X.to_numpy(),validation=validation,batch_size=64,timeout_s=20,memory_mb=2048,whole_compute_deadline_s=240,receipt_path=whole_receipt)
        if not whole.accepted:raise ValueError('; '.join(whole.reasons))
        prior=[pd.read_csv(ROOT/v['matrix_path'],float_precision='round_trip',index_col='material_id').loc[ctx.train_ids].to_numpy() for v in s['representations'].values()]
        prior.extend(pd.read_csv(Path(path),float_precision='round_trip',index_col='material_id').loc[ctx.train_ids].to_numpy() for path in historical_representation_matrix_hashes())
        previous=np.concatenate([ctx.X.to_numpy(),*prior],axis=1);normalized_old=(previous-previous.mean(axis=0))/np.where(previous.std(axis=0)>1e-14,previous.std(axis=0),1);normalized_new=(matrix-matrix.mean(axis=0))/np.where(matrix.std(axis=0)>1e-14,matrix.std(axis=0),1)
        novel=[not any(np.allclose(normalized_new[:,j],normalized_old[:,k],rtol=0,atol=1e-9) or np.allclose(normalized_new[:,j],-normalized_old[:,k],rtol=0,atol=1e-9) for k in range(previous.shape[1])) for j in range(matrix.shape[1])]
        if not any(novel):raise ValueError('All columns affine copies of fixed66/new-stage blocks/the12 historical approved blocks')
        names=[f'{rid}_{n}' for n in feature_names];frame=pd.DataFrame(matrix,index=ctx.train_ids,columns=names);frame.index.name='material_id';frame.to_csv(folder/'train_features.csv.gz',float_format='%.17g',compression='gzip')
        summary={'rows':len(matrix),'columns':len(names),'novel_vs_previous_columns':sum(novel),'invariance':validation.metrics,'target_values_received_by_worker':False}
        frozen={str(path.relative_to(ROOT)).replace('\\','/'):sha(path) for path in (folder/'compute.py',folder/'proposal.json',invariant_receipt,whole_receipt,folder/'train_features.csv.gz')}
        s=state();s['representations'][rid]={'feature_names':names,'declared_feature_names':feature_names,'hypothesis':hypothesis,'falsification':falsification,'code_sha256':runtime._code_hash(code),'matrix_path':str((folder/'train_features.csv.gz').relative_to(ROOT)).replace('\\','/'),'frozen_files':frozen,'summary':summary};s['counters']['investigations']+=1;s['active_operation']=None;dump(STATE,s)
        return {'approved':True,'representation_id':rid,'summary':{'rows':len(matrix),'columns':len(names),'novel_vs_previous_columns':sum(novel),'invariance_passed':True},'source_sha256':runtime._code_hash(code),'complete_receipt_sha256':jsha(summary),'fits_performed':0}
    except Exception as exc:
        dump(folder/'rejection.json',{'reason':f'{type(exc).__name__}: {exc}','utc':now(),'fits_performed':0},exclusive=True);s=state();s['active_operation']=None;dump(STATE,s)
        return {'approved':False,'representation_id':rid,'reason':str(exc),'fits_performed':0,'revision_allowed_before_fit':True}

def ast_dump(code):
    import ast
    return ast.dump(ast.parse(code),include_attributes=False)

def submit_predictor(code,feature_blocks,max_fits_per_block,hypothesis,falsification,attempt):
    import predictor_runtime as runtime
    from predictor_preflight import validate_program_synthetic
    assert_frozen();s=state();ctx=context();p=load(ROOT/'protocol.json')
    if s['active_operation'] or s['stop_reason']:raise RuntimeError('Research not ready')
    if not isinstance(feature_blocks,list) or len(feature_blocks)>2 or len(set(feature_blocks))!=len(feature_blocks) or any(r not in s['representations'] for r in feature_blocks):raise ValueError('Use0..2 distinct approved new blocks plus fixed66')
    if min(len(hypothesis.strip()),len(falsification.strip()))<40:raise ValueError('Substantive hypothesis/falsification required')
    if any(v['attempt']==str(attempt) for v in s['proposals'].values()):raise RuntimeError('One predictor registration per cycle')
    if s['counters']['predictor_submissions']>=p['budget']['max_predictor_submissions']:raise ValueError('Predictor submission cap')
    submission=s['counters']['predictor_submissions']+1;submitted=ROOT/'predictor_submissions'/f'S{submission:03d}';submitted.mkdir(parents=True,exist_ok=False)
    (submitted/'predictor.py').write_text(code,encoding='utf-8');dump(submitted/'request.json',{'feature_blocks':feature_blocks,'max_fits_per_block':max_fits_per_block,'hypothesis':hypothesis,'falsification':falsification,'attempt':str(attempt),'utc':now()},exclusive=True);s['counters']['predictor_submissions']=submission;dump(STATE,s)
    try:
        if not isinstance(max_fits_per_block,int) or isinstance(max_fits_per_block,bool) or max_fits_per_block>affordable_candidate_fit_cap(s):raise ValueError('Requested fit cap exceeds current remaining candidate/final capacity')
        validation=runtime.validate_predictor(code,max_fits_per_block)
        synthetic=validate_program_synthetic(code,max_fits_per_block,ctx.matrix(feature_blocks).shape[1]);dump(submitted/'synthetic_preflight.json',synthetic,exclusive=True)
        if not synthetic['accepted']:return {'registered':False,'reason':synthetic,'revision_allowed_before_scientific_fit':True,'fits_performed':0}
        semantic=hashlib.sha256(ast_dump(code).encode()).hexdigest();identity=jsha([semantic,feature_blocks])
        if not feature_blocks and semantic==hashlib.sha256(ast_dump((ROOT/'incumbent/predictor.py').read_text(encoding='utf-8')).encode()).hexdigest():raise ValueError('Exact incumbent program already evaluated on these same partitions; cached baseline is not a fresh candidate')
        if any(v['identity']==identity for v in s['proposals'].values()):raise ValueError('Duplicate program/input identity; propose a new scientific mechanism')
        cid=f'C{len(s["proposals"])+1:03d}';folder=ROOT/'candidates'/cid;folder.mkdir(parents=True,exist_ok=False);(folder/'predictor.py').write_text(code,encoding='utf-8')
        registration={'candidate_id':cid,'registered_utc':now(),'feature_blocks':feature_blocks,'max_fits_per_block':max_fits_per_block,'reserved_OOF_fits':4*max_fits_per_block,'hypothesis':hypothesis,'falsification':falsification,'code_sha256':runtime.code_sha(code),'code_AST_sha256':semantic,'features':list(ctx.matrix(feature_blocks).columns),'validation':validation,'synthetic_program_preflight':synthetic,'input_representation_hashes':{r:s['representations'][r]['frozen_files'] for r in feature_blocks},'fixed_incumbent_matrix_sha256':sha(ROOT/'incumbent/train_features.csv.gz'),'attempt':str(attempt),'selection':'trainingOOFonly','selection_description':'4328 pooled errors, two repeated chemical-system2fold partitions; registered repeat/tail eligibility gate'}
        dump(folder/'registration.json',registration,exclusive=True);frozen={str((folder/n).relative_to(ROOT)).replace('\\','/'):sha(folder/n) for n in ('predictor.py','registration.json')};s['proposals'][cid]={**registration,'identity':identity,'frozen_files':frozen};dump(STATE,s)
        return {'registered':True,'candidate_id':cid,'OOF_fit_reservation':4*max_fits_per_block,'code_sha256':runtime.code_sha(code),'features':registration['features'],'fits_performed':0}
    except Exception as exc:
        reason={'error':f'{type(exc).__name__}: {exc}','fits_performed':0,'scientific_fit_started':False};dump(submitted/'validation_rejection.json',reason,exclusive=True)
        return {'registered':False,'reason':reason,'revision_allowed_before_scientific_fit':True,'fits_performed':0}

def fit_counts(path):
    events=[json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()] if Path(path).exists() else []
    return {'fit_started':sum(r['phase']=='started' for r in events),'fit_completed':sum(r['phase']=='completed' for r in events),'fit_failed':sum(r['phase']=='failed' for r in events)}

def numeric_inputs(X):
    import numpy as np
    ctx=context()
    return {'X_float64_little_endian':hashlib.sha256(np.asarray(X.to_numpy(),dtype='<f8').tobytes()).hexdigest(),'y_float64_little_endian':hashlib.sha256(np.asarray(ctx.y.to_numpy(),dtype='<f8').tobytes()).hexdigest(),'ordered_IDs':jsha(list(ctx.train_ids)),'fold_assignments_int64_little_endian':hashlib.sha256(np.asarray(ctx.folds.to_numpy(),dtype='<i8').tobytes()).hexdigest(),'fold_assignment_shape':list(ctx.folds.shape)}

def _run_repeated(program,X,cap,folder,label,attempt=None):
    import numpy as np,pandas as pd,predictor_runtime as runtime
    ctx=context();p=load(ROOT/'protocol.json');y=ctx.y.to_numpy();pred=np.full((2,len(X)),np.nan);coverage=np.zeros_like(pred,dtype=int);fold_receipts=[]
    for block in range(4):
        repeat,fold=divmod(block,2);assignment=ctx.folds.iloc[:,repeat].to_numpy();train=np.flatnonzero(assignment!=fold);test=np.flatnonzero(assignment==fold)
        timeout=min(p['budget']['predictor_block_seconds'],remaining_wall('search'))
        if attempt is not None:timeout=min(timeout,remaining_session(attempt)/(4-block))
        response=runtime.run_training_block(program,X.to_numpy()[train],y[train],X.to_numpy()[test],max_fits_per_block=cap,event_path=folder/'fit_events_live.jsonl',block_id=f'{label}_R{repeat}_F{fold}',timeout_s=timeout,memory_mb=2048)
        pred[repeat,test]=response['prediction'];coverage[repeat,test]+=1
        fold_receipts.append({'repeat':repeat,'fold':fold,'seed':PARTITION_SEEDS[repeat],'train_rows':len(train),'evaluation_rows':len(test),'train_IDs_sha256':jsha(list(ctx.train_ids[train])),'evaluation_IDs_sha256':jsha(list(ctx.train_ids[test])),'train_systems':len(set(ctx.meta.iloc[train].chemical_system)),'evaluation_systems':len(set(ctx.meta.iloc[test].chemical_system)),'evaluation_targets_received_by_worker':False,'actual_fits':response['fit_completed'],'worker_seconds':response['worker_seconds'],'inference_independence_checks':response['inference_independence_checks'],'numeric_input_receipts':response['numeric_input_receipts']})
    if not np.all(coverage==1) or not np.isfinite(pred).all():raise ValueError('Incomplete repeated OOF coverage')
    frame=pd.concat([pd.DataFrame({'material_id':ctx.train_ids,'repeat':r,'fold':ctx.folds.iloc[:,r].to_numpy(),'truth':y,'prediction':pred[r]}) for r in range(2)],ignore_index=True);frame.to_csv(folder/'internal_oof_predictions.csv.gz',index=False,float_format='%.17g',compression='gzip')
    return pred,fold_receipts

def initialize_baselines():
    """Only actual baseline evaluations, before any candidate Agent invocation."""
    assert_frozen();ctx=context();p=load(ROOT/'protocol.json');s=state()
    if s['baselines'] or s['proposals'] or s['counters']['experiments']:raise RuntimeError('Baseline stage already attempted; never refit')
    if s['active_operation'] or s['stop_reason']:raise RuntimeError('Scientific state not ready')
    baseline_codes={'B_C018':(ROOT/'incumbent/predictor.py').read_text(encoding='utf-8'),'B_E011':LEGACY_E011_CODE}
    for bid,cap in [('B_C018',6),('B_E011',5)]:
        s=state();reserve=4*cap;folder=ROOT/'baselines'/bid;folder.mkdir(parents=True,exist_ok=False);started=time.monotonic();code=baseline_codes[bid];(folder/'predictor.py').write_text(code,encoding='utf-8')
        if s['counters']['base_fits_reserved']+reserve+p['budget'].get('final_fit_reservation',18)>p['budget']['base_fit_reservations']:raise RuntimeError('Baseline fit cap exhausted')
        dump(folder/'reservation.json',{'baseline_id':bid,'reserved_new_learner_fits':reserve,'utc':now(),'program_sha256':hashlib.sha256(code.encode()).hexdigest()},exclusive=True)
        s['counters']['base_fits_reserved']+=reserve;s['baselines'][bid]={'status':'started','reservation':reserve};s['active_operation']={'kind':'baseline_OOF','baseline_id':bid};dump(STATE,s)
        try:
            X=ctx.X if bid=='B_C018' else ctx.old_X;pred,fold_receipts=_run_repeated(code,X,cap,folder,bid);counts=fit_counts(folder/'fit_events_live.jsonl')
            result={'baseline_id':bid,'OOF':diagnostics(pred),'actual_new_fits':counts,'folds':fold_receipts,'elapsed_seconds':time.monotonic()-started,'code_sha256':hashlib.sha256(code.encode()).hexdigest(),'features':list(X.columns),'numeric_input_hashes':numeric_inputs(X),'validation_score_returned':False,'fresh_targets_accessed':False,'scope':'Actual newly registered repeated training OOF baseline, not a new external confirmation.'}
            result['artifact_hashes']={n:sha(folder/n) for n in ['internal_oof_predictions.csv.gz','fit_events_live.jsonl','reservation.json','predictor.py']};dump(folder/'result.json',result,exclusive=True)
            s=state();s['baselines'][bid]={'status':'complete','reservation':reserve,'summary':result};s['counters']['baseline_comparisons']+=1
            for key in ('fit_started','fit_completed'):s['counters'][key]+=counts[key]
            s['active_operation']=None;dump(STATE,s)
        except Exception as exc:
            _preserve_failure(folder,bid,'baselines',reserve,exc);raise
    return {bid:compact_result(state()['baselines'][bid]['summary']) for bid in BASELINE_IDS}

def _preserve_failure(folder,identity,collection,reserve,exc):
    counts=fit_counts(folder/'fit_events_live.jsonl');dump(folder/'failure.json',{'error':f'{type(exc).__name__}: {exc}','counts':counts,'utc':now(),'new_fit_retry_allowed':False},exclusive=True)
    s=state();s[collection][identity]={'status':'failed_or_unknown','reservation':reserve,'counts':counts};s['stop_reason']='Scientific worker failed or unknown; preserve without refit'
    for key in ('fit_started','fit_completed'):s['counters'][key]+=counts[key]
    s['active_operation']=None;dump(STATE,s)

def evaluate_candidate(candidate_id,attempt):
    import numpy as np
    assert_frozen();s=state();p=load(ROOT/'protocol.json');ctx=context()
    if s['stop_reason'] or s['active_operation']:raise RuntimeError('Research not ready')
    if candidate_id not in s['proposals'] or s['proposals'][candidate_id]['attempt']!=str(attempt):raise ValueError('Evaluate only this cycle registered candidate')
    if candidate_id in s['experiments']:raise RuntimeError('Candidate already attempted; no rerun')
    if s['counters']['experiments']>=p['budget']['completed_candidates']:raise RuntimeError('Completed candidate cap')
    proposal=s['proposals'][candidate_id];reserve=4*proposal['max_fits_per_block']
    if s['counters']['base_fits_reserved']+reserve+p['budget'].get('final_fit_reservation',18)>p['budget']['base_fit_reservations']:raise RuntimeError('Fit cap including final arms exhausted')
    folder=ROOT/'experiments'/candidate_id;folder.mkdir(parents=True,exist_ok=False);started=time.monotonic();dump(folder/'reservation.json',{'candidate':candidate_id,'reserved_new_learner_fits':reserve,'utc':now(),'registration_sha256':sha(ROOT/'candidates'/candidate_id/'registration.json')},exclusive=True)
    s['counters']['base_fits_reserved']+=reserve;s['active_operation']={'kind':'OOF','candidate_id':candidate_id};s['experiments'][candidate_id]={'status':'started','reservation':reserve};dump(STATE,s)
    try:
        X=ctx.matrix(proposal['feature_blocks']);code=(ROOT/'candidates'/candidate_id/'predictor.py').read_text(encoding='utf-8');pred,fold_receipts=_run_repeated(code,X,proposal['max_fits_per_block'],folder,candidate_id,attempt);oof=diagnostics(pred);incumbent=s['baselines']['B_C018']['summary']['OOF']
        components=eligibility(oof,incumbent,p.get('OOF_candidate_gate',{}));gate=all(components.values())
        result={'candidate_id':candidate_id,'OOF':oof,'incumbent_OOF_MAE':incumbent['MAE_eV_atom'],'OOF_schedule_gate_pass':bool(gate),'selection_eligible':bool(gate),'eligibility_components':components,'validation_score_returned':False,'fresh_targets_accessed':False,'actual_new_fits':fit_counts(folder/'fit_events_live.jsonl'),'folds':fold_receipts,'elapsed_seconds':time.monotonic()-started,'registered_hypothesis':proposal['hypothesis'],'falsification':proposal['falsification'],'code_sha256':proposal['code_sha256'],'feature_blocks':proposal['feature_blocks'],'scope':'Adaptive repeated trainingOOF only. Previously seen evaluations are excluded; no independent scientific confirmation or mechanism.'}
        result['artifact_hashes']={n:sha(folder/n) for n in ['internal_oof_predictions.csv.gz','fit_events_live.jsonl','reservation.json']};result['numeric_input_hashes']=numeric_inputs(X)
        dump(folder/'result.json',result,exclusive=True);s=state();s['experiments'][candidate_id]={'status':'complete','reservation':reserve,'summary':result};s['counters']['experiments']+=1
        for key in ('fit_started','fit_completed'):s['counters'][key]+=result['actual_new_fits'][key]
        s['active_operation']=None;dump(STATE,s)
        return {**compact_result(result),'complete_result_sha256':sha(folder/'result.json'),'complete_prediction_sha256':sha(folder/'internal_oof_predictions.csv.gz'),'fit_reservation':reserve}
    except Exception as exc:_preserve_failure(folder,candidate_id,'experiments',reserve,exc);raise

def eligibility(oof,incumbent,policy):
    return {'repeat_0_MAE':oof['partitions']['0']['MAE_eV_atom']<=policy.get('each_repeat_MAE_ratio_max',.995)*incumbent['partitions']['0']['MAE_eV_atom'],
        'repeat_1_MAE':oof['partitions']['1']['MAE_eV_atom']<=policy.get('each_repeat_MAE_ratio_max',.995)*incumbent['partitions']['1']['MAE_eV_atom'],
        'mean_MAE':oof['MAE_eV_atom']<=policy.get('mean_MAE_ratio_max',.99)*incumbent['MAE_eV_atom'],
        'mean_repeat_RMSE':oof['mean_repeat_RMSE_eV_atom']<=policy.get('mean_repeat_RMSE_ratio_max',1.0)*incumbent['mean_repeat_RMSE_eV_atom'],
        'repeat_0_p99':oof['partitions']['0']['p99_abs_error']<=policy.get('each_repeat_p99_ratio_max',1.02)*incumbent['partitions']['0']['p99_abs_error'],
        'repeat_1_p99':oof['partitions']['1']['p99_abs_error']<=policy.get('each_repeat_p99_ratio_max',1.02)*incumbent['partitions']['1']['p99_abs_error']}
