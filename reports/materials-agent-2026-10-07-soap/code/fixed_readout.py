"""Training-only, fixed-readout representation ablation. No target release."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib
from importlib import metadata as import_metadata
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import time
import numpy as np

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
OLD = Path('C:/Users/28908/Codex/fung-research/materials-controlled-agent-2026-10-07')
KERNEL = Path('C:/Users/28908/Codex/fung-research/materials-fixed-test-2026-10-07/package/materials_accuracy_agent_2026-10-06')
PARAMETERS = dict(iterations=900, depth=6, learning_rate=.04,
                  l2_leaf_reg=8.0, loss_function='RMSE', subsample=.85)
ARMS = ('original66', 'linegraph90', 'soap90')
CODE = 'def fit(X_train, y_train):\n    return train_model("catboost", X_train, y_train, '+repr(PARAMETERS)+')\ndef predict(state, X_eval):\n    return state.predict(X_eval)\n'
EXPECTED = {
 'X42': '1d11a2df12975c22aef4cdaaa3e685a497f719b2e46e27e692e77bbe3350eb94',
 'X66': '7f299cfa5ab2930fff149523d0e57606f8269cf3a0486d482831e8a5d8784740',
 'X90': 'a86c9cfc46f4343f129193ab2f3e104a6959c8f85f02897bdce213f3537c2e8b',
 'y': 'def44e7b03e9bf30c26ab6ab2687ea3ed6ceb6ab3e5788667cd1d8ecda11ce13',
 'folds': '7b90165946ae0ebf6279e11512d74ec2ab1c8dec47c6f2a1bace558bbe4a2245',
}

def need(ok, message):
    if not ok: raise RuntimeError(message)

def safe(path):
    path=Path(path)
    need(path.resolve().is_relative_to(ROOT), 'Output outside new stage')
    need(not any('onedrive' in part.lower() for part in path.resolve().parts), 'OneDrive forbidden')
    for item in (path, *path.parents):
        if item.exists():
            need(not (getattr(item.lstat(), 'st_file_attributes', 0)&stat.FILE_ATTRIBUTE_REPARSE_POINT), 'Reparse ancestor forbidden')
    return path

def environment():
    folder=str(safe(ROOT/'tmp'))
    os.environ.update(TEMP=folder,TMP=folder,NUMBA_CACHE_DIR=folder,
       PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',
       OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    sys.path.insert(0,str(ROOT/'dependencies'))

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def array_sha(a): return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def utc(): return datetime.now(timezone.utc).isoformat()
def write_json(path,value):
    with safe(path).open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')

def training():
    with np.load(ROOT/'inputs/training.npz',allow_pickle=False) as z:
        values={k:z[k] for k in z.files}
    need(set(values)=={'X42','X66','X90','y','folds'},'Unexpected training payload')
    for key,digest in EXPECTED.items(): need(array_sha(values[key])==digest,'Known training numeric binding differs: '+key)
    ids=load(ROOT/'inputs/ids.json')
    need(len(ids)==2164 and len(set(ids))==2164,'Training identity count changed')
    canonical=json.dumps(ids,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    need(hashlib.sha256(canonical).hexdigest()=='a93272c84f100f446e466998dad45f77e9f3491ae758bf949e130285565e2a1e','Training ID order changed')
    need(np.array_equal(values['X42'],values['X66'][:,:42]) and np.array_equal(values['X66'],values['X90'][:,:66]),'Original input prefix changed')
    import pandas as pd
    meta=pd.read_csv(ROOT/'inputs/metadata.csv.gz')
    need(meta.material_id.tolist()==ids and meta.chemical_system.nunique()==2040,'Chemical identity mismatch')
    folds=values['folds']; need(folds.shape==(2164,3),'Three twofold partitions required')
    for p in range(3):
        need(set(np.unique(folds[:,p]))=={0,1},'Invalid fold labels')
        need(not set(meta.chemical_system[folds[:,p]==0])&set(meta.chemical_system[folds[:,p]==1]),'Chemical system leakage')
    return values,ids,meta

def prepare():
    for name in ('training.npz','ids.json','metadata.csv.gz'):
        dst=safe(ROOT/'inputs'/name);need(not dst.exists(),'Prepared file already exists')
        shutil.copyfile(OLD/'phaseB_inputs'/name,dst)
        need(sha(dst)==sha(OLD/'phaseB_inputs'/name),'Copy bytes differ')
    a,ids,meta=training()
    write_json(ROOT/'design/training_boundary_receipt.json',dict(status='PASS',utc=utc(),rows=len(ids),chemical_systems=2040,
      sources={str(OLD/'phaseB_inputs'/name):sha(OLD/'phaseB_inputs'/name) for name in ('training.npz','ids.json','metadata.csv.gz')},
      numeric_sha256={k:array_sha(v) for k,v in a.items()},scientific_fits=0,new_confirmation_labels_read=False))

def register():
    training()
    sys.path.insert(0,str(KERNEL));sys.path.insert(0,str(KERNEL/'dependencies'))
    trusted=importlib.import_module('predictor_runtime')
    need(Path(trusted.__file__).resolve()==(KERNEL/'predictor_runtime.py').resolve(),'Wrong preflight kernel')
    trusted.verify_dependency_lock(check_files=True)
    trusted.validate_predictor(CODE,1)  # Real signature/AST API validation before any fit or protocol freeze.
    receipt=load(ROOT/'inputs/soap_receipt.json')
    need(receipt['status']=='PASS' and receipt['target_values_accessed'] is False,'SOAP pure-input checks required')
    need(receipt['ordered_train_ids_sha256']=='a93272c84f100f446e466998dad45f77e9f3491ae758bf949e130285565e2a1e','SOAP identity order mismatch')
    raw=np.load(ROOT/'inputs/soap_raw.npy',allow_pickle=False)
    need(array_sha(raw)==receipt['matrix_numeric_sha256'],'SOAP numeric provenance mismatch')
    files=['runtime/fixed_readout.py','runtime/soap_representation.py',
           'inputs/training.npz','inputs/ids.json','inputs/metadata.csv.gz',
           'inputs/soap_raw.npy','inputs/soap_receipt.json','design/dependency_environment.json',
           'design/soap_generation_protocol.json','design/soap_generation_prelaunch_review.json',
           'design/soap_generation_execution_authorization.json','runtime/soap_generation_launch.json']
    protocol=dict(schema_version=1,phase='C_fixed_structure_ablation',registered_utc=utc(),
      files={n:sha(ROOT/n) for n in files},kernel_path=str(KERNEL),kernel_sha256=sha(KERNEL/'predictor_runtime.py'),
      kernel_source_hashes=load(OLD/'phaseA_protocol.json')['kernel_source_hashes'],
      training_rows=2164,chemical_systems=2040,partitions=3,folds=2,partition_seeds=[20261009,20261010,20261011],arms=list(ARMS),
      parameters=PARAMETERS,readout_seed=20261006,readout_code_sha256=hashlib.sha256(CODE.encode()).hexdigest(),
      soap_parameters=receipt['parameters'],soap_raw_dimensions=6016,
      preprocessing=dict(row_L2='targetless generator',scaler='StandardScaler fit current fold training only',
         pca_components=24,pca_solver='randomized',pca_iterated_power=4,pca_n_oversamples=10,
         pca_normalizer='QR',pca_whiten=False,pca_seed=20261007,append_to_original66=True),
      primary_comparison='soap90 versus original66',secondary_comparison='soap90 versus linegraph90',
      metrics=['MAE','RMSE','p99_absolute_error'],
      descriptive_uncertainty=dict(method='paired chemical-system bootstrap of row-wise mean of three OOF absolute errors',
          resamples=2000,seed=20261007,interval=[.025,.975],not_independent_confirmation=True),
      exploratory_signal_gate=dict(each_partition_mae_strictly_lower=True,mean_mae_ratio_max=.99,each_partition_rmse_ratio_max=1.02,
          each_partition_p99_ratio_max=1.02,paired_bootstrap_upper_max=0),
      selection='Single fixed SOAP configuration. No post-hoc representation or parameter selection; no model promotion.',
      budget=dict(native_readout_fits=18,unsupervised_scaler_fits=6,unsupervised_pca_fits=6,
          readout_worker_seconds=600,readout_worker_memory_mb=2048,total_seconds=14400,cpu_threads=1),
      data_boundary=dict(historical_training_targets_only=True,confirmation_labels_read=False,
         fresh_scoring_authorized=False,stability_labels_used=False),
      failure_rule='Stop and preserve any failed or unknown native fit. Do not restart or refund budget.')
    write_json(ROOT/'design/phaseC_protocol_v3.json',protocol)
    print(json.dumps(dict(status='REGISTERED',protocol_sha256=sha(ROOT/'design/phaseC_protocol_v3.json'))))

def verify_protocol():
    protocol=load(ROOT/'design/phaseC_protocol_v3.json')
    need(protocol['arms']==list(ARMS) and protocol['parameters']==PARAMETERS,'Fixed readout protocol changed')
    need(protocol['budget']['native_readout_fits']==18,'Budget changed')
    for name,digest in protocol['files'].items(): need(sha(ROOT/name)==digest,'Frozen source/input changed: '+name)
    need(sha(KERNEL/'predictor_runtime.py')==protocol['kernel_sha256'],'Trusted kernel changed')
    for name,digest in protocol['kernel_source_hashes'].items(): need(sha(name)==digest,'Frozen trusted dependency/source changed')
    env=load(ROOT/'design/dependency_environment.json')
    need(env['status']=='PASS','Real dependency validation required')
    for name,digest in env['file_hashes'].items(): need(sha(name)==digest,'Frozen numerical library bytes changed: '+name)
    for name,version in env['versions'].items():
        module=importlib.import_module(name)
        actual=import_metadata.version('scikit-learn' if name=='sklearn' else name)
        need(actual==version and str(Path(module.__file__).resolve())==str(Path(env['module_paths'][name]).resolve()),'Numerical library version/path changed: '+name)
    return protocol

def audit_native():
    records={'started':{},'completed':{},'failed':{}}
    with np.load(ROOT/'inputs/training.npz',allow_pickle=False) as z: folds=z['folds']
    expected={f'P{p}_F{f}_{arm}':dict(rows=int(np.sum(folds[:,p]!=f)),features=66 if arm=='original66' else 90)
              for p in range(3) for f in range(2) for arm in ARMS}
    for path in sorted((ROOT/'runtime').glob('*_native_fits.jsonl')):
        block_id=path.name.removesuffix('_native_fits.jsonl')
        need(block_id in expected,'Unexpected native block journal')
        for line in path.read_text(encoding='utf-8').splitlines():
            event=json.loads(line);phase=event['phase'];fid=event['fit_id']
            need(event['block_id']==block_id and fid==block_id+'_F001','Native block/fit identity mismatch')
            need(event['rows']==expected[block_id]['rows'] and event['features']==expected[block_id]['features'],'Native training rows or routed width mismatch')
            need(phase in records and fid not in records[phase],'Duplicate or unknown native event')
            if phase!='started':
                need(fid in records['started'],'Native finish without start')
                keys={k:v for k,v in event.items() if k not in ('phase','utc','error')}
                old={k:v for k,v in records['started'][fid].items() if k not in ('phase','utc','error')}
                need(keys==old,'Native metadata changed during fit')
            need(event['learner']=='catboost' and event['features'] in (66,90),'Unexpected learner/input width')
            for k,v in PARAMETERS.items(): need(event['parameters'][k]==v,'Readout parameter differs')
            need(event['parameters']['random_seed']==20261006 and event['parameters']['thread_count']==1,'Readout seed/threads differ')
            need(event['sample_weight_received'] is False,'Undeclared native weighting')
            records[phase][fid]=event
    unfinished=sorted(set(records['started'])-set(records['completed'])-set(records['failed']))
    reservations={}
    for path in (ROOT/'runtime').glob('*_reservation.json'):
        r=load(path);bid=r['block_id'];need(bid in expected and bid not in reservations,'Unexpected reservation')
        need(r['native_fit_reserved']==1 and r['training_rows']==expected[bid]['rows'] and r['features']==expected[bid]['features'],'Reservation budget/input mismatch')
        reservations[bid]=r
    need(all(e['block_id'] in reservations for e in records['started'].values()),'Native start without reservation')
    return dict(started=len(records['started']),completed=len(records['completed']),failed=len(records['failed']),
        reserved=len(reservations),unclosed_fit_ids=unfinished,completed_fit_ids=sorted(records['completed']))

def preserve_native_audit():
    try:return audit_native()
    except BaseException as exc:
        return dict(audit_error=repr(exc),journal_sha256={p.name:sha(p) for p in (ROOT/'runtime').glob('*_native_fits.jsonl')},
                    incomplete_status='Unknown until independent review; no retry authorized')

def metrics(y,pred):
    error=np.abs(y-pred)
    return dict(MAE=float(error.mean()),RMSE=float(np.sqrt(np.mean((y-pred)**2))),p99_absolute_error=float(np.quantile(error,.99)))

def run():
    from threadpoolctl import threadpool_limits
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    protocol=verify_protocol()
    review=load(ROOT/'design/phaseC_prelaunch_review_v4.json')
    need(review['status']=='PASS' and review['protocol_sha256']==sha(ROOT/'design/phaseC_protocol_v3.json'), 'Independent prelaunch receipt required')
    need(review['scientific_fits_performed']==0 and review['new_confirmation_labels_read'] is False,'Invalid prelaunch review')
    need(review['failure_count']==0 and review['source_input_hashes']==protocol['files'],'Prelaunch source/input binding incomplete')
    auth=load(ROOT/'design/phaseC_execution_authorization_v3.json')
    need(auth['protocol_sha256']==sha(ROOT/'design/phaseC_protocol_v3.json') and auth['review_sha256']==sha(ROOT/'design/phaseC_prelaunch_review_v4.json') and auth['source_input_hashes']==protocol['files'] and auth['native_fit_budget']==18 and auth['fresh_scoring_authorized'] is False,'Source-bound root execution authorization required')
    need(not (ROOT/'runtime/phaseC_launch.json').exists(),'Already launched: never restart science')
    a,ids,meta=training(); raw=np.load(ROOT/'inputs/soap_raw.npy',allow_pickle=False)
    need(raw.shape==(2164,6016) and np.isfinite(raw).all(),'Invalid targetless SOAP matrix')
    need(array_sha(raw)==load(ROOT/'inputs/soap_receipt.json')['matrix_numeric_sha256'],'SOAP runtime numeric provenance mismatch')
    sys.path.insert(0,str(KERNEL));sys.path.insert(0,str(KERNEL/'dependencies'))
    kernel=importlib.import_module('predictor_runtime');kernel.verify_dependency_lock(check_files=True)
    need(Path(kernel.__file__).resolve()==(KERNEL/'predictor_runtime.py').resolve(),'Unexpected kernel import')
    kernel.validate_predictor(CODE,1)
    start=time.monotonic(); outputs={arm:np.full((2164,3),np.nan) for arm in ARMS}
    write_json(ROOT/'runtime/phaseC_launch.json',dict(utc=utc(),pid=os.getpid(),protocol_sha256=sha(ROOT/'design/phaseC_protocol_v3.json'),review_sha256=sha(ROOT/'design/phaseC_prelaunch_review_v4.json'),authorization_sha256=sha(ROOT/'design/phaseC_execution_authorization_v3.json')))
    completed=0; encoders=0; blocks=[]
    try:
        with threadpool_limits(limits=1):
            for partition in range(3):
                for fold in range(2):
                    need(sha(ROOT/'design/phaseC_protocol_v3.json')==auth['protocol_sha256'],'Protocol modified during execution')
                    verify_protocol()
                    need(time.monotonic()-start<protocol['budget']['total_seconds'],'Total budget exhausted')
                    train=np.flatnonzero(a['folds'][:,partition]!=fold); evaluate=np.flatnonzero(a['folds'][:,partition]==fold)
                    encoder_id=f'P{partition}_F{fold}'
                    encoder_started=time.monotonic()
                    write_json(ROOT/'runtime'/f'{encoder_id}_encoder_start.json',dict(utc=utc(),training_rows=train.tolist(),evaluation_rows=evaluate.tolist(),evaluation_targets_received=False))
                    scaler=StandardScaler(); x=scaler.fit_transform(raw[train].astype(np.float64)); e=scaler.transform(raw[evaluate].astype(np.float64))
                    pca=PCA(n_components=24,svd_solver='randomized',iterated_power=4,n_oversamples=10,
                        power_iteration_normalizer='QR',whiten=False,random_state=20261007)
                    pca.fit(x);z=pca.transform(x);ze=pca.transform(e); encoders+=1
                    need(time.monotonic()-start<protocol['budget']['total_seconds'],'Budget exhausted in preprocessing')
                    with safe(ROOT/'inputs'/f'{encoder_id}_encoder.npz').open('xb') as f:
                        np.savez_compressed(f,train_rows=train,eval_rows=evaluate,mean=scaler.mean_,scale=scaler.scale_,
                          pca_mean=pca.mean_,components=pca.components_,explained_variance=pca.explained_variance_,
                          train_coordinates=z,eval_coordinates=ze)
                    write_json(ROOT/'runtime'/f'{encoder_id}_encoder_completed.json',dict(utc=utc(),encoder_sha256=sha(ROOT/'inputs'/f'{encoder_id}_encoder.npz'),
                      explained_variance_ratio_sum=float(pca.explained_variance_ratio_.sum()),training_rows_sha256=array_sha(train),evaluation_rows_sha256=array_sha(evaluate),evaluation_targets_received=False))
                    inputs={'original66':(a['X66'][train],a['X66'][evaluate]),'linegraph90':(a['X90'][train],a['X90'][evaluate]),
                       'soap90':(np.column_stack((a['X66'][train],z)),np.column_stack((a['X66'][evaluate],ze)))}
                    write_json(ROOT/'runtime'/f'{encoder_id}_preprocessing_receipt.json',dict(utc=utc(),wall_seconds=time.monotonic()-encoder_started,
                        source_training_soap_sha256=array_sha(raw[train]),source_evaluation_soap_sha256=array_sha(raw[evaluate]),
                        input_train_ids_sha256=hashlib.sha256(json.dumps([ids[i] for i in train],separators=(',',':')).encode()).hexdigest(),
                        input_eval_ids_sha256=hashlib.sha256(json.dumps([ids[i] for i in evaluate],separators=(',',':')).encode()).hexdigest(),
                        pca_training_target_values_received=False,scaler_training_target_values_received=False,
                        readout_inputs={name:dict(training=array_sha(pair[0]),evaluation=array_sha(pair[1])) for name,pair in inputs.items()}))
                    for arm in ARMS:
                        need(sha(ROOT/'design/phaseC_protocol_v3.json')==auth['protocol_sha256'],'Protocol modified during execution')
                        verify_protocol()
                        need(time.monotonic()-start<protocol['budget']['total_seconds'],'Total budget exhausted')
                        bid=encoder_id+'_'+arm; journal=ROOT/'runtime'/f'{bid}_native_fits.jsonl'
                        need(not journal.exists(),'Fit journal already exists')
                        xtrain,xeval=inputs[arm]
                        write_json(ROOT/'runtime'/f'{bid}_reservation.json',dict(utc=utc(),block_id=bid,native_fit_reserved=1,training_rows=len(train),features=xtrain.shape[1],protocol_sha256=auth['protocol_sha256']))
                        remaining=protocol['budget']['total_seconds']-(time.monotonic()-start)
                        response=kernel.run_training_block(CODE,xtrain,a['y'][train],xeval,
                          max_fits_per_block=1,event_path=safe(journal),block_id=bid,timeout_s=min(600,remaining),memory_mb=2048)
                        need(response['fit_started']==1 and response['fit_completed']==1,'Unexpected fit count')
                        completed+=1; outputs[arm][evaluate,partition]=response['prediction']
                        response['prediction']=response['prediction'].tolist()
                        write_json(ROOT/'results'/f'{bid}.json',response)
                        blocks.append(dict(block_id=bid,training_rows=len(train),evaluation_rows=len(evaluate),
                          fit_completed=1,wall_seconds=response['wall_seconds'],worker_seconds=response['worker_seconds']))
                        print(json.dumps(dict(status='BLOCK_COMPLETE',block=bid,completed=completed,total=18)),flush=True)
                        verify_protocol()
        need(completed==18 and encoders==6 and all(np.isfinite(p).all() for p in outputs.values()),'Incomplete fixed-readout experiment')
        audit=audit_native()
        need(audit['reserved']==18 and audit['started']==18 and audit['completed']==18 and audit['failed']==0 and not audit['unclosed_fit_ids'],'Native journals do not prove complete18 fits')
        need(len(list((ROOT/'runtime').glob('*_reservation.json')))==18,'Wrong reservation count')
        with safe(ROOT/'results/oof_predictions.npz').open('xb') as f: np.savez_compressed(f,**outputs)
        scores={arm:[metrics(a['y'],pred[:,p]) for p in range(3)] for arm,pred in outputs.items()}
        systems=meta.chemical_system.to_numpy(); unique=np.unique(systems)
        contrasts={}
        for reference in ('original66','linegraph90'):
            difference=(np.abs(a['y'][:,None]-outputs['soap90'])-np.abs(a['y'][:,None]-outputs[reference])).mean(axis=1)
            group_sums=np.array([difference[systems==s].sum() for s in unique]); group_counts=np.array([(systems==s).sum() for s in unique])
            rng=np.random.default_rng(20261007); draws=[]
            for _ in range(2000):
                indices=rng.integers(0,len(unique),len(unique));draws.append(float(group_sums[indices].sum()/group_counts[indices].sum()))
            contrasts[reference]=dict(mean_absolute_error_difference=float(difference.mean()),paired_chemical_bootstrap_95CI=np.quantile(draws,[.025,.975]).tolist())
        interval=contrasts['original66']['paired_chemical_bootstrap_95CI']
        means={arm:float(np.mean([m['MAE'] for m in item])) for arm,item in scores.items()}
        gates={'mean_mae_ratio':means['soap90']<=.99*means['original66'],'bootstrap_upper_below_zero':interval[1]<0}
        for p in range(3):
            gates[f'P{p}_MAE_lower']=scores['soap90'][p]['MAE']<scores['original66'][p]['MAE']
            for metric in ('RMSE','p99_absolute_error'):
                gates[f'P{p}_{metric}']=scores['soap90'][p][metric]<=1.02*scores['original66'][p][metric]
        result=dict(status='complete',finished_utc=utc(),protocol_sha256=sha(ROOT/'design/phaseC_protocol_v3.json'),
          native_fits_completed=completed,native_fit_audit=audit,scaler_fits_completed=encoders,pca_fits_completed=encoders,
          blocks=blocks,scores=scores,mean_MAE=means,primary_MAE_change_eV_per_atom=contrasts['original66']['mean_absolute_error_difference'],contrasts=contrasts,
          paired_chemical_bootstrap_95CI=interval,exploratory_signal_gate=dict(checks=gates,passed=all(gates.values())),
          new_confirmation_labels_read=False,promotion_allowed=False,experimental_LLM_calls=0,
          interpretation='Fixed representation diagnostics on reused training folds; not independent confirmation or Agent effectiveness.',wall_seconds=time.monotonic()-start)
        write_json(ROOT/'results/phaseC_outcome.json',result)
        print(json.dumps({k:v for k,v in result.items() if k not in ('blocks','scores')}),flush=True)
    except BaseException as exc:
        write_json(ROOT/'results/phaseC_failure.json',dict(utc=utc(),error=repr(exc),returned_completed_native_fits=completed,native_fit_audit=preserve_native_audit(),
          encoder_completions=encoders,no_restart=True,new_confirmation_labels_read=False))
        raise

if __name__=='__main__':
    environment()
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare','register','run'])
    command=parser.parse_args().command
    {'prepare':prepare,'register':register,'run':run}[command]()
