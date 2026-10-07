"""Persistent training-only evolving materials research. No fits on import."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime,timezone
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
WORK=ROOT.parent
PREVIOUS=WORK/'materials_structure_agent_2026-10-05_pilot'
OLD=WORK/'materials_adaptive_agent_2026-10-05_recovery2'
DEV=WORK/'materials_strategy_agent_2026-10-02/development'
STRUCTURES=WORK/'materials_agent_analysis_2026-10-01/data/structures.jsonl.gz'
STATE=ROOT/'state/research_state.json'
SOURCES=['backend.py','science_server.py','controller.py','finalize.py','representation_runtime.py','predictor_runtime.py','predictor_preflight.py','session_transport.py','decision_contract.py','audited_decision_interceptor.py','data_curator.py','runtime_config.json','carryover.json']


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
    return max(0,min(budget['max_fits_per_block'],(budget['base_fit_reservations']-s['counters']['base_fits_reserved']-11-2*later)//2))


def remaining_wall(scope='total'):
    launch=load(ROOT/'controller_launch.json')
    if launch is None:raise RuntimeError('Scientificcontrollerhasnotstarted')
    budget=load(ROOT/'protocol.json')['budget']
    cap=budget['search_wall_seconds'] if scope=='search' else budget['wall_seconds']
    remaining=cap-(time.monotonic()-launch['monotonic_start'])
    if remaining<=0:raise RuntimeError('Declaredscientificwallcap reached')
    return remaining


def remaining_session(attempt,decision_reserve_seconds=60):
    invocation=load(Path(attempt)/'invocation.json')
    if invocation is None:raise RuntimeError('ActualAgentinvocationreceiptmissing')
    elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(invocation['started_utc'])).total_seconds()
    remaining=invocation['hard_wall_seconds']-elapsed-decision_reserve_seconds
    if remaining<=0:raise RuntimeError('Agentsessionhasnoscientifictimeleft')
    return remaining


class Context:
    def __init__(self):
        import numpy as np
        import pandas as pd
        spec=importlib.util.spec_from_file_location('_evolving_frozen_pilot',PREVIOUS/'pilot_evaluation.py')
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;exec(compile((PREVIOUS/'pilot_evaluation.py').read_bytes(),str(PREVIOUS/'pilot_evaluation.py'),'exec'),module.__dict__)
        self.legacy,_=module.load_legacy(OLD/'evaluation.py','799aa512d7c049a24a0ae1848fd3228187aed8276be539d6bfdef343ad9b05b5')
        self.columns=list(self.legacy.FEATURES)
        raw=pd.read_csv(DEV/'features.csv.gz',float_precision='round_trip',index_col='material_id').sort_index()
        e04=pd.read_csv(DEV/'E04_descriptors.csv.gz',float_precision='round_trip',index_col='material_id').loc[raw.index]
        targets=pd.read_csv(DEV/'targets.csv.gz',float_precision='round_trip',usecols=['material_id','split','formation_energy_per_atom'],index_col='material_id').loc[raw.index]
        self.all_X=pd.concat([raw[self.columns[:30]],e04[self.columns[30:]]],axis=1)
        self.train_ids=targets.index[targets.split.eq('train')];self.validation_ids=targets.index[targets.split.eq('validation')]
        self.X=self.all_X.loc[self.train_ids];self.y=targets.loc[self.train_ids,'formation_energy_per_atom']
        # The controller/Agent receives no validation target or score during search.
        self.meta=raw.loc[self.train_ids,['formula','chemical_system','composition_signature']]
        self.old_oof=pd.read_csv(OLD/'experiments/E011/internal_oof_predictions.csv.gz',float_precision='round_trip',index_col='material_id').loc[self.train_ids]
        self.folds=self.old_oof.fold.astype(int)
        if len(self.train_ids)!=2164 or len(self.validation_ids)!=715 or not set(self.folds)=={0,1}:raise ValueError('Development boundary changed')
        for f in (0,1):
            if len(self.train_ids[self.folds.eq(f)])!=1082:raise ValueError('Savedfold cardinality changed')
            if set(self.meta.loc[self.folds.eq(f),'chemical_system']) & set(self.meta.loc[self.folds.ne(f),'chemical_system']):raise ValueError('Chemical systems cross OOF boundary')
        if not np.array_equal(self.y.to_numpy(),self.old_oof.truth.to_numpy()):raise ValueError('Round-trip training targets differ from frozen baseline')
        self._structures=None
    def structures(self,ids=None):
        if self._structures is None:
            with gzip.open(STRUCTURES,'rt',encoding='utf-8') as f:self._structures={r['material_id']:r for r in map(json.loads,f)}
        return [self._structures[i] for i in (ids if ids is not None else self.train_ids)]
    def matrix(self,blocks,ids=None):
        import pandas as pd
        ids=self.train_ids if ids is None else ids
        tables=[self.all_X.loc[ids]]
        for rid in blocks:
            entry=state()['representations'][rid]
            frame=pd.read_csv(ROOT/entry['matrix_path'],float_precision='round_trip',index_col='material_id')
            tables.append(frame.loc[ids])
        return pd.concat(tables,axis=1)


CTX=None
def context():
    global CTX
    if CTX is None:CTX=Context()
    return CTX


def initialize():
    if STATE.exists():raise RuntimeError('New stage cannot be reinitialized')
    ctx=context();baseline=load(OLD/'experiments/E011/result.json')
    fresh=load(ROOT/'fresh_cohort/prefit_manifest.json')
    if fresh is None:raise RuntimeError('Fresh target-independent cohort must be locked before initialization')
    carryover=load(ROOT/'carryover.json')
    if carryover is None or carryover['counters']['fit_started']!=0 or carryover['fresh_labels_accessed']:raise RuntimeError('Repairphasehistorymustshowknownzeroactualfits/sealedlabels')
    inputs=[DEV/'features.csv.gz',DEV/'targets.csv.gz',DEV/'E04_descriptors.csv.gz',STRUCTURES,OLD/'evaluation.py',OLD/'experiments/E011/result.json',OLD/'experiments/E011/internal_oof_predictions.csv.gz',OLD/'experiments/E011/validation_predictions.csv.gz',PREVIOUS/'descriptor_runtime.py',PREVIOUS/'pilot_evaluation.py',ROOT/'fresh_cohort/prefit_manifest.json']
    protocol={'schema_version':1,'registered_utc':now(),'scope':'Twenty adaptive Agent-authored representation/predictor candidates, selected ONLY by2164 training chemical-system OOF. Existing715 known validation and fresh1000 are evaluated only after selection freezes. No newDFT/synthesis, no Tc/old1000 reads.',
      'target':'formation_energy_per_atom','units':'eV/atom','selection_metric':'Training twofold OOF MAE only; deterministic tie-break candidate_id; do not return715 or fresh targets/metrics during search.',
      'input_parser':'round_trip for all original42 and savedbaseline targets/predictions; retains exact E011 numerical semantics.',
      'budget':{'completed_candidates':20,'max_sessions':23,'max_representation_submissions':30-carryover['counters']['representation_submissions'],'max_predictor_submissions':40-carryover['counters']['predictor_submissions'],'max_fits_per_block':6,'base_fit_reservations':256-carryover['counters']['base_fits_reserved'],'uncached_input_tokens':800000-carryover['counters']['uncached_input_tokens'],'output_tokens':120000-carryover['counters']['output_tokens'],'tool_calls':180-carryover['actual_tools'],'wall_seconds':10800-carryover['scientific_elapsed_seconds'],'search_wall_seconds':7200-carryover['scientific_elapsed_seconds'],'final_reserved_wall_seconds':3600,'descriptor_whole_seconds':240,'descriptor_worker_memory_mb':2048,'predictor_block_seconds':540},
      'representation_contract':'Agentwritescompute(structure) with4..32 declared intense features; no predetermined formulas. Numericinput-only/invariance/no-duplicates; up to3 approvedblocks may becombined withrawold42. Fits neverreceive evaluationtargets.',
      'predictor_contract':'Agentwritesfit(X_train,y_train)->state andpredict(state,X_eval). train_model exposed onlyduringfit; actualatomicfits loggedbefore/after, max6 perblock; inferencebatch/orderinvariance. ASTnumericguard plus resource-limitedworker, notgeneralOSsandbox.',
      'fit_accounting':'256 cap counts actual atomic trusted learner API .fit starts/reservations. Every Agent program fit invocation is separately counted (two perOOF comparison); arbitrary numeric parameter operations are governed by time/memory caps and are not universally identifiable as separate learned models.',
      'required_structure_exploration':'At least12 approved distinctnewrepresentationblocks sought within20experiments, unlessrejections/budget/failures prevent it; do notpadcountswithcachedreads/metadata.',
      'cached_baseline':{'id':'E011','validation':baseline['validation'],'OOF':baseline['OOF'],'selection_score':baseline['selection_score'],'new_search_fits':0},
      'OOF_candidate_gate':{'MAE_max':baseline['OOF']['MAE_eV_atom']*.995,'interpretation':'Schedulingthreshold, notsignificance; allnegativecandidatesremainvisible.'},
      'final_protocol':'ChoosebestcompleteOOF candidate before715/fresh evaluation; no post-evaluation edits. Savebaseline andchampion freshpredictions beforeunlockinglabels. Ifboth finalvalidationsnotimproved, dopromotenone.',
      'source_hashes':{n:sha(ROOT/n) for n in SOURCES},'input_hashes':{str(p.resolve()):sha(p) for p in inputs},'fresh_prefit_manifest_sha256':sha(ROOT/'fresh_cohort/prefit_manifest.json'),
      'training_ordered_IDs_sha256':jsha(list(ctx.train_ids)),'training_fold_IDs_sha256':jsha({str(i):int(v) for i,v in ctx.folds.items()})}
    protocol['prior_failed_phase']=carryover
    protocol['input_hashes'].update(carryover['prior_artifact_hashes'])
    dump(ROOT/'protocol.json',protocol,exclusive=True)
    dump(STATE,{'started_utc':now(),'protocol_sha256':sha(ROOT/'protocol.json'),'representations':{},'proposals':{},'experiments':{},'decisions':[],
      'counters':{'experiments':0,'investigations':0,'representation_submissions':0,'predictor_submissions':0,'base_fits_reserved':0,'fit_started':0,'fit_completed':0,'uncached_input_tokens':0,'output_tokens':0,'tool_calls':0},'active_operation':None,'stop_reason':None,'champion_frozen':False})
    return protocol


def assert_frozen():
    s=state();p=load(ROOT/'protocol.json')
    if sha(ROOT/'protocol.json')!=s['protocol_sha256']:raise RuntimeError('Protocolchanged')
    if any(sha(ROOT/n)!=h for n,h in p['source_hashes'].items()):raise RuntimeError('Frozenruntimechanged')
    if any(sha(Path(n))!=h for n,h in p['input_hashes'].items()):raise RuntimeError('Originalinputchanged')
    for entry in s['representations'].values():
        for name,h in entry['frozen_files'].items():
            if sha(ROOT/name)!=h:raise RuntimeError('Approvedrepresentationchanged')
    for entry in s['proposals'].values():
        for name,h in entry['frozen_files'].items():
            if sha(ROOT/name)!=h:raise RuntimeError('Registeredpredictorchanged')


def summary_context():
    s=state();server=load(ROOT/'state/server_state.json',{'tool_calls':0,'calls':[]})
    counters=dict(s['counters']);counters['tool_calls']=server['tool_calls']
    return {'counters':counters,'active_operation':s['active_operation'],'stop_reason':s['stop_reason'],'ledger_consistent':True,
      'candidate_fit_budget':{'max_affordable_fits_per_training_block':affordable_candidate_fit_cap(s),'reserved_final_capacity':11,'minimum_reserved_per_later_candidate':2,'no_fixed_learner_choice':'Author a substantiveprogramwithinthiscurrentcap; it maydeclinebelow6so20comparisonsandfinalbothremainpossible.'},
      'incomplete_scientific_calls':[r['evidence_id'] for r in server['calls'] if r['status']=='started'],
      'representations':{k:{'feature_names':v['feature_names'],'hypothesis':v['hypothesis'],'sha256':v['code_sha256'],'summary':v['summary']} for k,v in s['representations'].items()},
      'completed_results':{k:v['summary'] for k,v in s['experiments'].items() if v['status']=='complete'},
      'incomplete_results':{k:v['status'] for k,v in s['experiments'].items() if v['status']!='complete'},
      'last_decisions':s['decisions'][-2:],'budget':load(ROOT/'protocol.json')['budget'],
      'available_evidence_ids':[r['evidence_id'] for r in server['calls'] if r['status']=='complete']}


def diagnostics(pred):
    import numpy as np
    ctx=context();err=np.asarray(pred,float)-ctx.y.to_numpy();absolute=np.abs(err)
    result={'rows':len(err),'MAE_eV_atom':float(absolute.mean()),'RMSE_eV_atom':float(np.sqrt((err**2).mean())),
      'mean_prediction_minus_truth':float(err.mean()),'p90_abs_error':float(np.quantile(absolute,.9)),'p99_abs_error':float(np.quantile(absolute,.99)),
      'folds':{},'groups':{}}
    for f in (0,1):
        mask=ctx.folds.to_numpy()==f;result['folds'][str(f)]={'rows':int(mask.sum()),'MAE_eV_atom':float(absolute[mask].mean()),'mean_prediction_minus_truth':float(err[mask].mean())}
    for label,mask in {'nitrogen':ctx.X.comp_fraction_Z007.to_numpy()>0,'oxygen':ctx.X.comp_fraction_Z008.to_numpy()>0,'no_oxygen':ctx.X.comp_fraction_Z008.to_numpy()<=0,'ternary_plus':ctx.X.comp_n_elements.to_numpy()>=3}.items():
        result['groups'][label]={'rows':int(mask.sum()),'MAE_eV_atom':float(absolute[mask].mean()),'mean_prediction_minus_truth':float(err[mask].mean())}
    return result


def research_context():
    import predictor_runtime as p
    import representation_runtime as r
    ctx=context()
    return {'state':summary_context(),'baseline_training_OOF':diagnostics(ctx.old_oof.prediction.to_numpy()),
      'prior_findings':['Exact old42 E011 remains incumbent. Prior frozen4-bin localangles didnotimprove vs same-readercontrol. FixedRBFKRR wasworse. N/OmeanresidualRidge reducedNbiasbutworsenedMAE. These do not exclude richer structural information or other trainedprograms.','Previousstage failedbeforeanylearnerfit becauseofproductionmodulepath and storedself-imagediagonal contract mismatch. Sourceinterfacesarenowrepaired; previouscandidate remainsuntested, notnegative. Do notsubmitidenticalfailedcandidate again.'],
      'prior_failed_hypotheses':load(ROOT/'carryover.json')['failed_hypotheses'],
      'feature_column_order':ctx.columns,'representation_api':{'signature':'def compute(structure): return4..32declaredfinitefloats','fields':sorted(r.STRUCTURE_FIELDS),'numpy_functions':sorted(r.NP_NAMES),'numpy_linalg':sorted(r.NP_LINALG_NAMES),'math_functions':sorted(r.MATH_NAMES),'array_attributes':sorted(r.ARRAY_ATTRIBUTES),'safe_builtins':sorted(r.SAFE_BUILTINS),'helper':'closest_neighbors(structure) returnssequenceofpercenterperiodicvec3sequences, nearest12plusallties; fullneighbor_center/index/distance/image+latticeavailableforowninput-onlyperiodicradial/chemicalstatistics. material_id forbidden.','distance_matrix_convention':'Sourcepairmatricesmaystorepositivenearestperiodicself-imagediagonal; geometricfixturesmayusezero. Cellpairmatrixisnotitselfintensive. Prefercompleteperiodicneighborarrays forcellinvariantstatistics; all5invariancesstillrequired.','geometry_invariance':list(r.TRANSFORMATIONS),'worker_limits':'2048MB,20secperbatch,240secwhole2164matrix'},
      'predictor_api':{'signatures':['def fit(X_train,y_train): returnstate','def predict(state,X_eval): returnpredvector'],
        'helper':'train_model(kind,X_train,y_train,params) returnsmodelwith.predict(X). Onlyfitphasecantrain. Youwritepreprocessing,featureselection,grouping,composition/interactions,andblendinginsidecode. Fit seestrainingonly; predictcannotfit and mustbeinferencebatch/orderindependent.',
        'learners':p.MODEL_API,'max_fits_per_block':6,'raw42_first':True,'seed':20261002},
      'instructions':'Propose substantive falsifiable nextcandidate from trainingfeedback. Write yourownrepresentation andpredictorcode. Use availableexistingrepresentationblocks asappropriate; at least12 distinctapprovednewblocks sought across20actualexperiments. Submitrepresentationbeforepredictorbeforeevaluate. OneactualOOFcandidate percycle. No715/freshlabels/metricsduringsearch; scientificfail/unknownmustnotrerun. After20complete candidates stop; everynegative resultretained.'}


def submit_representation(code,feature_names,hypothesis,falsification):
    import numpy as np
    import pandas as pd
    import representation_runtime as runtime
    assert_frozen();s=state();p=load(ROOT/'protocol.json');ctx=context()
    if s['active_operation'] or s['stop_reason']:raise RuntimeError('Researchnotreadyfornewproposal')
    if s['counters']['representation_submissions']>=p['budget']['max_representation_submissions']:raise ValueError('Representationsubmissioncap')
    if min(len(hypothesis.strip()),len(falsification.strip()))<40:raise ValueError('Substantivehypothesis/falsificationrequired')
    number=s['counters']['representation_submissions']+1;rid=f'R{number:03d}';folder=ROOT/'representations'/rid;folder.mkdir(parents=True,exist_ok=False)
    (folder/'compute.py').write_text(code,encoding='utf-8');dump(folder/'proposal.json',{'code_sha256':runtime._code_hash(code),'feature_names':feature_names,'hypothesis':hypothesis,'falsification':falsification,'utc':now()},exclusive=True)
    s['counters']['representation_submissions']=number;s['active_operation']={'kind':'representation','id':rid};dump(STATE,s)
    try:
        invariant_receipt=ROOT/'runtime_receipts'/f'{rid}_invariance.json'
        whole_receipt=ROOT/'runtime_receipts'/f'{rid}_whole_compute.json'
        records=ctx.structures();validation=runtime.validate_proposal(code,feature_names,invariant_records=[records[i] for i in (0,1,100,300,700,1100,1500,2000)],timeout_s=20,memory_mb=2048,receipt_path=invariant_receipt)
        if not validation.accepted:raise ValueError('; '.join(validation.reasons))
        matrix,whole=runtime.compute_validated(code,records,feature_names=feature_names,original_feature_rows=ctx.X.to_numpy(),validation=validation,batch_size=64,timeout_s=20,memory_mb=2048,whole_compute_deadline_s=240,receipt_path=whole_receipt)
        if not whole.accepted:raise ValueError('; '.join(whole.reasons))
        # Do not count renamed, reordered old representation columns as new information.
        prior=[]
        for entry in s['representations'].values():prior.append(pd.read_csv(ROOT/entry['matrix_path'],float_precision='round_trip',index_col='material_id').loc[ctx.train_ids].to_numpy())
        previous=np.concatenate([ctx.X.to_numpy(),*prior],axis=1)
        normalized_old=(previous-previous.mean(axis=0))/np.where(previous.std(axis=0)>1e-14,previous.std(axis=0),1)
        normalized_new=(matrix-matrix.mean(axis=0))/np.where(matrix.std(axis=0)>1e-14,matrix.std(axis=0),1)
        novel=[not any(np.allclose(normalized_new[:,j],normalized_old[:,k],rtol=0,atol=1e-9) or np.allclose(normalized_new[:,j],-normalized_old[:,k],rtol=0,atol=1e-9) for k in range(previous.shape[1])) for j in range(matrix.shape[1])]
        if not any(novel):raise ValueError('Allcolumnsareaffinecopiesofold42/previousblocks; reuseinformationinstead')
        names=[f'{rid}_{n}' for n in feature_names];frame=pd.DataFrame(matrix,index=ctx.train_ids,columns=names);frame.index.name='material_id';frame.to_csv(folder/'train_features.csv.gz',float_format='%.17g',compression='gzip')
        summary={'rows':len(matrix),'columns':len(names),'novel_vs_previous_columns':sum(novel),'invariance':validation.metrics,'target_values_received_by_worker':False}
        frozen={str(path.relative_to(ROOT)).replace('\\','/'):sha(path) for path in (folder/'compute.py',folder/'proposal.json',invariant_receipt,whole_receipt,folder/'train_features.csv.gz')}
        s=state();s['representations'][rid]={'feature_names':names,'declared_feature_names':feature_names,'hypothesis':hypothesis,'falsification':falsification,'code_sha256':runtime._code_hash(code),'matrix_path':str((folder/'train_features.csv.gz').relative_to(ROOT)).replace('\\','/'),'frozen_files':frozen,'summary':summary};s['counters']['investigations']+=1;s['active_operation']=None;dump(STATE,s)
        return {'approved':True,'representation_id':rid,'summary':summary,'fits_performed':0}
    except Exception as exc:
        dump(folder/'rejection.json',{'reason':f'{type(exc).__name__}: {exc}','utc':now(),'fits_performed':0},exclusive=True)
        s=state();s['active_operation']=None;dump(STATE,s)
        return {'approved':False,'representation_id':rid,'reason':str(exc),'fits_performed':0,'revision_allowed_before_fit':True}


def submit_predictor(code,feature_blocks,max_fits_per_block,hypothesis,falsification,attempt):
    import predictor_runtime as runtime
    from predictor_preflight import validate_program_synthetic
    assert_frozen();s=state();ctx=context()
    if s['active_operation'] or s['stop_reason']:raise RuntimeError('Researchnotready')
    if not isinstance(feature_blocks,list) or len(feature_blocks)>3 or len(set(feature_blocks))!=len(feature_blocks) or any(r not in s['representations'] for r in feature_blocks):raise ValueError('Use0..3distinctapprovedfeatureblocks')
    if min(len(hypothesis.strip()),len(falsification.strip()))<40:raise ValueError('Substantivehypothesis/falsificationrequired')
    if any(v['attempt']==str(attempt) for v in s['proposals'].values()):raise RuntimeError('Onepredictorregistration percycle')
    if s['counters']['predictor_submissions']>=load(ROOT/'protocol.json')['budget']['max_predictor_submissions']:raise ValueError('Predictorsubmissioncap')
    submission=s['counters']['predictor_submissions']+1
    submitted=ROOT/'predictor_submissions'/f'S{submission:03d}';submitted.mkdir(parents=True,exist_ok=False)
    (submitted/'predictor.py').write_text(code,encoding='utf-8')
    dump(submitted/'request.json',{'feature_blocks':feature_blocks,'max_fits_per_block':max_fits_per_block,'hypothesis':hypothesis,'falsification':falsification,'attempt':str(attempt),'utc':now()},exclusive=True)
    s['counters']['predictor_submissions']=submission;dump(STATE,s)
    affordable=affordable_candidate_fit_cap(s)
    if not isinstance(max_fits_per_block,int) or max_fits_per_block>affordable:
        reason={'error':'Requestedfitcapexceedsremaining20candidate/finalcapacity','max_affordable_fits_per_training_block':affordable,'fits_performed':0,'scientific_fit_started':False}
        dump(submitted/'validation_rejection.json',reason,exclusive=True)
        return {'registered':False,'reason':reason,'revision_allowed_before_scientific_fit':True,'fits_performed':0}
    try:validation=runtime.validate_predictor(code,max_fits_per_block)
    except Exception as exc:
        reason={'error':f'{type(exc).__name__}: {exc}','fits_performed':0,'scientific_fit_started':False}
        dump(submitted/'validation_rejection.json',reason,exclusive=True)
        return {'registered':False,'reason':reason,'revision_allowed_before_scientific_fit':True,'fits_performed':0}
    synthetic=validate_program_synthetic(code,max_fits_per_block,ctx.matrix(feature_blocks).shape[1])
    dump(submitted/'synthetic_preflight.json',synthetic,exclusive=True)
    if not synthetic['accepted']:return {'registered':False,'reason':synthetic,'revision_allowed_before_scientific_fit':True,'fits_performed':0}
    semantic=hashlib.sha256(ast_dump(code).encode()).hexdigest();identity=jsha([semantic,feature_blocks,max_fits_per_block])
    if identity in load(ROOT/'carryover.json')['failed_candidate_identities']:raise ValueError('Identicalfailedpriorcandidatepreservedunrerun; proposenewscientificprogram/inputhypothesis')
    if any(v['identity']==identity for v in s['proposals'].values()):raise ValueError('Duplicatecandidateprogram/inputs; developnewsubstantivehypothesis')
    cid=f'C{len(s["proposals"])+1:03d}';folder=ROOT/'candidates'/cid;folder.mkdir(parents=True,exist_ok=False)
    (folder/'predictor.py').write_text(code,encoding='utf-8');registration={'candidate_id':cid,'registered_utc':now(),'feature_blocks':feature_blocks,'max_fits_per_block':max_fits_per_block,'reserved_OOF_fits':2*max_fits_per_block,'hypothesis':hypothesis,'falsification':falsification,'code_sha256':runtime.code_sha(code),'code_AST_sha256':semantic,'features':list(ctx.matrix(feature_blocks).columns),'validation':validation,'synthetic_program_preflight':synthetic,'input_representation_hashes':{r:s['representations'][r]['frozen_files'] for r in feature_blocks},'attempt':str(attempt),'selection':'trainingOOFonly'}
    dump(folder/'registration.json',registration,exclusive=True)
    frozen={str((folder/n).relative_to(ROOT)).replace('\\','/'):sha(folder/n) for n in ('predictor.py','registration.json')}
    s['proposals'][cid]={**registration,'identity':identity,'frozen_files':frozen};dump(STATE,s)
    return {'registered':True,'candidate_id':cid,'OOF_fit_reservation':2*max_fits_per_block,'code_sha256':runtime.code_sha(code),'features':registration['features'],'fits_performed':0}


def ast_dump(code):
    import ast
    return ast.dump(ast.parse(code),include_attributes=False)


def fit_counts(path):
    events=[json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()] if Path(path).exists() else []
    return {'fit_started':sum(r['phase']=='started' for r in events),'fit_completed':sum(r['phase']=='completed' for r in events),'fit_failed':sum(r['phase']=='failed' for r in events)}


def evaluate_candidate(candidate_id,attempt):
    import numpy as np
    import pandas as pd
    import predictor_runtime as runtime
    assert_frozen();s=state();p=load(ROOT/'protocol.json');ctx=context()
    if s['stop_reason'] or s['active_operation']:raise RuntimeError('Researchnotready')
    if candidate_id not in s['proposals'] or s['proposals'][candidate_id]['attempt']!=str(attempt):raise ValueError('Evaluateonlythiscyclepreregisteredcandidate')
    if candidate_id in s['experiments']:raise RuntimeError('Candidatealreadyattempted; no rerun')
    if s['counters']['experiments']>=20:raise RuntimeError('Twentycompletedcandidatecap')
    proposal=s['proposals'][candidate_id];reserve=2*proposal['max_fits_per_block']
    if s['counters']['base_fits_reserved']+reserve+11>p['budget']['base_fit_reservations']:raise RuntimeError('Fitcapincludingfinalarms exhausted')
    folder=ROOT/'experiments'/candidate_id;folder.mkdir(parents=True,exist_ok=False);started=time.monotonic()
    dump(folder/'reservation.json',{'candidate':candidate_id,'reserved_new_learner_fits':reserve,'utc':now(),'registration_sha256':sha(ROOT/'candidates'/candidate_id/'registration.json')},exclusive=True)
    s['counters']['base_fits_reserved']+=reserve;s['active_operation']={'kind':'OOF','candidate_id':candidate_id};s['experiments'][candidate_id]={'status':'started','reservation':reserve};dump(STATE,s)
    try:
        X=ctx.matrix(proposal['feature_blocks']);y=ctx.y.to_numpy();pred=np.full(len(X),np.nan);coverage=np.zeros(len(X),int);fold_receipts=[]
        code=(ROOT/'candidates'/candidate_id/'predictor.py').read_text(encoding='utf-8')
        for f in (0,1):
            train=np.flatnonzero(ctx.folds.to_numpy()!=f);test=np.flatnonzero(ctx.folds.to_numpy()==f)
            response=runtime.run_training_block(code,X.to_numpy()[train],y[train],X.to_numpy()[test],max_fits_per_block=proposal['max_fits_per_block'],event_path=folder/'fit_events_live.jsonl',block_id=f'{candidate_id}_OOF{f}',timeout_s=min(p['budget']['predictor_block_seconds'],remaining_wall('search'),remaining_session(attempt)/(2-f)),memory_mb=2048)
            pred[test]=response['prediction'];coverage[test]+=1
            fold_receipts.append({'fold':f,'train_IDs_sha256':jsha(list(ctx.train_ids[train])),'evaluation_IDs_sha256':jsha(list(ctx.train_ids[test])),'train_systems':len(set(ctx.meta.iloc[train].chemical_system)),'evaluation_systems':len(set(ctx.meta.iloc[test].chemical_system)),'evaluation_targets_received_by_worker':False,'actual_fits':response['fit_completed'],'worker_seconds':response['worker_seconds'],'inference_independence_checks':response['inference_independence_checks']})
        if not np.all(coverage==1) or not np.isfinite(pred).all():raise ValueError('IncompleteOOFcoverage')
        frame=pd.DataFrame({'material_id':ctx.train_ids,'fold':ctx.folds.to_numpy(),'truth':y,'prediction':pred});frame.to_csv(folder/'internal_oof_predictions.csv.gz',index=False,float_format='%.17g',compression='gzip')
        result={'candidate_id':candidate_id,'OOF':diagnostics(pred),'baseline_OOF_MAE':p['cached_baseline']['OOF']['MAE_eV_atom'],'OOF_schedule_gate_pass':float(np.abs(pred-y).mean())<=p['OOF_candidate_gate']['MAE_max'],'validation_score_returned':False,'fresh_targets_accessed':False,'actual_new_fits':fit_counts(folder/'fit_events_live.jsonl'),'folds':fold_receipts,'elapsed_seconds':time.monotonic()-started,'registered_hypothesis':proposal['hypothesis'],'falsification':proposal['falsification'],'code_sha256':proposal['code_sha256'],'feature_blocks':proposal['feature_blocks'],'scope':'Adaptive previouslyobserved trainingOOF only; notindependentconfirmation ormechanism.'}
        result['artifact_hashes']={'internal_oof_predictions.csv.gz':sha(folder/'internal_oof_predictions.csv.gz'),'fit_events_live.jsonl':sha(folder/'fit_events_live.jsonl'),'reservation.json':sha(folder/'reservation.json')}
        result['numeric_input_hashes']={'X_float64_little_endian':hashlib.sha256(np.asarray(X.to_numpy(),dtype='<f8').tobytes()).hexdigest(),'y_float64_little_endian':hashlib.sha256(np.asarray(y,dtype='<f8').tobytes()).hexdigest(),'ordered_IDs':jsha(list(ctx.train_ids))}
        dump(folder/'result.json',result,exclusive=True);s=state();s['experiments'][candidate_id]={'status':'complete','reservation':reserve,'summary':result};s['counters']['experiments']+=1
        counts=fit_counts(folder/'fit_events_live.jsonl')
        for k in ('fit_started','fit_completed'):s['counters'][k]+=counts[k]
        s['active_operation']=None;dump(STATE,s)
        return result
    except Exception as exc:
        counts=fit_counts(folder/'fit_events_live.jsonl');dump(folder/'failure.json',{'error':f'{type(exc).__name__}: {exc}','counts':counts,'utc':now(),'new_fit_retry_allowed':False},exclusive=True)
        s=state();s['experiments'][candidate_id]={'status':'failed_or_unknown','reservation':reserve,'counts':counts};s['stop_reason']='Scientificworkerfailed_or_unknown; preservenorefit'
        for k in ('fit_started','fit_completed'):s['counters'][k]+=counts[k]
        s['active_operation']=None;dump(STATE,s);raise
