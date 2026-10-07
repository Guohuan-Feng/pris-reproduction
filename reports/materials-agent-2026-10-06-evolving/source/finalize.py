"""Freeze OOF-selected program and save predictions before fresh labels unlock."""
from __future__ import annotations
import gzip
import json
from pathlib import Path
import sys
import time
sys.dont_write_bytecode=True
import numpy as np
import pandas as pd
import backend
import data_curator
import representation_runtime
import predictor_runtime

ROOT=Path(__file__).resolve().parent
BASELINE_CODE='''def fit(X_train, y_train):
    return train_model("e011", X_train, y_train, {})

def predict(state, X_eval):
    return state.predict(X_eval)
'''


def metric(truth,prediction):
    error=np.asarray(prediction)-np.asarray(truth)
    return {'rows':len(error),'MAE_eV_atom':float(np.abs(error).mean()),'RMSE_eV_atom':float(np.sqrt((error**2).mean())),
      'mean_prediction_minus_truth':float(error.mean()),'p90_abs_error':float(np.quantile(np.abs(error),.9)),'p99_abs_error':float(np.quantile(np.abs(error),.99))}


def cluster_difference(truth,baseline,champion,systems):
    frame=pd.DataFrame({'system':np.asarray(systems),'diff':np.abs(champion-truth)-np.abs(baseline-truth)})
    groups=frame.groupby('system',sort=True).agg(total=('diff','sum'),rows=('diff','size'))
    rng=np.random.default_rng(20261006);means=[];totals=groups.total.to_numpy();counts=groups.rows.to_numpy()
    for _ in range(2000):
        selected=rng.integers(0,len(groups),size=len(groups));means.append(float(totals[selected].sum()/counts[selected].sum()))
    return {'MAE_difference_champion_minus_baseline':float(frame['diff'].mean()),'cluster_bootstrap_95_percent_interval':np.quantile(means,[.025,.975]).tolist(),
      'bootstrap_unit':'chemical_system','clusters':len(groups),'resamples':2000,'seed':20261006,
      'interpretation':'Negative difference favorschampion; intervaldescribes thisonefixedsame-sourceheldoutcohort, notuniversalphysicalvalidity.'}


def align_fresh_inputs(features,metadata,columns):
    if 'material_id' not in metadata or metadata.material_id.isna().any() or not metadata.material_id.is_unique:raise ValueError('FreshIDs invalid')
    if len(features)!=len(metadata):raise ValueError('Freshfeatures/metadata rowcount differs')
    features=features.copy();metadata=metadata.copy()
    features.index=pd.Index(metadata.material_id.tolist(),name='material_id')
    metadata=metadata.set_index('material_id',verify_integrity=True)
    if not features.index.equals(metadata.index):raise ValueError('FreshID alignment differs')
    return features.loc[:,columns],metadata


def build_representation_inputs(cid,ctx,fresh_X,structures_path):
    proposal=backend.state()['proposals'][cid]
    with gzip.open(structures_path,'rt',encoding='utf-8') as f:fresh_structures={r['material_id']:r for r in map(json.loads,f)}
    fresh_ids=list(fresh_X.index);validation_ids=list(ctx.validation_ids)
    val_parts=[ctx.all_X.loc[validation_ids]];fresh_parts=[fresh_X.loc[fresh_ids,ctx.columns]]
    for rid in proposal['feature_blocks']:
        entry=backend.state()['representations'][rid];code=(ROOT/'representations'/rid/'compute.py').read_text(encoding='utf-8')
        # Same frozen Agent representation, no label input, no independent redesign.
        for tag,records,old,parts,ids in (
          ('known_validation',ctx.structures(validation_ids),ctx.all_X.loc[validation_ids].to_numpy(),val_parts,validation_ids),
          ('fresh',[fresh_structures[i] for i in fresh_ids],fresh_X.loc[fresh_ids,ctx.columns].to_numpy(),fresh_parts,fresh_ids)):
            # Training established novelty/invariance. An evaluation cohort may
            # legitimately make a trained column constant or coincident with
            # another; apply the frozen function without new novelty selection.
            start=time.monotonic();chunks=[];batch_receipts=[]
            for offset in range(0,len(records),64):
                if time.monotonic()-start>=240:raise RuntimeError('Frozenheldoutrepresentationwholedeadline')
                values,receipt=representation_runtime.run_isolated(code,records[offset:offset+64],feature_names=entry['declared_feature_names'],timeout_s=min(20,240-(time.monotonic()-start),backend.remaining_wall()),memory_mb=2048)
                chunks.append(values);batch_receipts.append(receipt)
                if time.monotonic()-start>240:raise RuntimeError('Frozenheldoutrepresentationwholedeadline')
            matrix=np.concatenate(chunks,axis=0)
            if matrix.shape!=(len(records),len(entry['feature_names'])) or not np.isfinite(matrix).all():raise RuntimeError('Frozenheldoutrepresentationinvalidshape/values')
            backend.dump(ROOT/'runtime_receipts'/f'{rid}_final_{tag}.json',{'code_sha256':entry['code_sha256'],'rows':len(records),'columns':len(entry['feature_names']),'batch_receipts':batch_receipts,'elapsed_seconds':time.monotonic()-start,'label_input':False,'training_novelty_not_reselected':True},exclusive=True)
            part=pd.DataFrame(matrix,index=ids,columns=entry['feature_names']);part.index.name='material_id'
            part.to_csv(ROOT/'final'/f'{rid}_{tag}_features.csv.gz',float_format='%.17g',compression='gzip');parts.append(part)
    return pd.concat(val_parts,axis=1),pd.concat(fresh_parts,axis=1)


def run():
    backend.assert_frozen();s=backend.state();ctx=backend.context()
    folder=ROOT/'final';folder.mkdir(exist_ok=True)
    if (folder/'result.json').exists():return backend.load(folder/'result.json')
    if (folder/'reservation.json').exists():raise RuntimeError('Finalattemptalreadystarted; preservenorefitting')
    complete={k:v['summary'] for k,v in s['experiments'].items() if v['status']=='complete'}
    if len(complete)!=20 or s['active_operation'] or s['stop_reason']:raise RuntimeError('Finalevaluationrequires20completeknowncandidates')
    selected=min(complete,key=lambda k:(complete[k]['OOF']['MAE_eV_atom'],k));proposal=s['proposals'][selected]
    frozen={'schema_version':1,'frozen_utc':backend.now(),'candidate_id':selected,'selection':'MinimumtrainingOOFMAEamong20completednewprograms; tiecandidateID; allselectionbeforeknownvalidation/freshnewmetrics.',
      'OOF_result':complete[selected],'OOF_gate_pass':complete[selected]['OOF_schedule_gate_pass'],'fresh_targets_accessed':False,'model_code_sha256':proposal['code_sha256'],
      'model_file_byte_sha256':backend.sha(ROOT/'candidates'/selected/'predictor.py'),'registration_sha256':backend.sha(ROOT/'candidates'/selected/'registration.json'),
      'selection_result_sha256':backend.sha(ROOT/'experiments'/selected/'result.json'),'selection_OOF_predictions_sha256':backend.sha(ROOT/'experiments'/selected/'internal_oof_predictions.csv.gz'),
      'protocol_sha256':backend.sha(ROOT/'protocol.json'),'representation_hashes':proposal['input_representation_hashes'],
      'fresh_manifest_sha256':backend.sha(ROOT/'fresh_cohort/prefit_manifest.json'),'baseline_code_sha256':predictor_runtime.code_sha(BASELINE_CODE),
      'incumbent_rule':'Comparebestnewprogram evenifOOFgatefalse; retainE011unless finalreportedcriteriaimprove. Nochoice/tuningafterheldoutlabels.'}
    backend.dump(folder/'champion_frozen.json',frozen,exclusive=True);frozen_sha=backend.sha(folder/'champion_frozen.json')
    s['champion_frozen']=True;backend.dump(backend.STATE,s)
    fresh_X,fresh_meta,fresh_structures_path,fresh_manifest=data_curator.load_frozen_fresh_inputs(ROOT)
    fresh_X,fresh_meta=align_fresh_inputs(fresh_X,fresh_meta,ctx.columns)
    reserve=5+proposal['max_fits_per_block']
    if s['counters']['base_fits_reserved']+reserve>backend.load(ROOT/'protocol.json')['budget']['base_fit_reservations']:raise RuntimeError('Finalreservedfitcap')
    backend.dump(folder/'reservation.json',{'reserved_trusted_learner_fits':reserve,'baseline':5,'champion':proposal['max_fits_per_block'],'candidate_id':selected,'utc':backend.now(),'fresh_targets_accessed':False},exclusive=True)
    s['counters']['base_fits_reserved']+=reserve;s['active_operation']={'kind':'final','candidate':selected};backend.dump(backend.STATE,s)
    started=time.monotonic()
    try:
        val_X,fresh_aug=build_representation_inputs(selected,ctx,fresh_X,fresh_structures_path)
        known_ids=list(ctx.validation_ids);fresh_ids=list(fresh_X.index);eval_ids=known_ids+fresh_ids
        baseline_eval=pd.concat([ctx.all_X.loc[known_ids],fresh_X],axis=0)
        champion_eval=pd.concat([val_X,fresh_aug],axis=0)
        train_X=ctx.matrix(proposal['feature_blocks']);y=ctx.y.to_numpy()
        final_predictions={};worker_receipts={}
        for arm,code,training,evaluation,cap in (
          ('baseline',BASELINE_CODE,ctx.X,baseline_eval,5),
          ('champion',(ROOT/'candidates'/selected/'predictor.py').read_text(encoding='utf-8'),train_X,champion_eval,proposal['max_fits_per_block'])):
            response=predictor_runtime.run_training_block(code,training.to_numpy(),y,evaluation.to_numpy(),max_fits_per_block=cap,event_path=folder/'fit_events_live.jsonl',block_id=f'FINAL_{arm}',timeout_s=min(backend.load(ROOT/'protocol.json')['budget']['predictor_block_seconds'],backend.remaining_wall()),memory_mb=2048)
            pred=response['prediction'];final_predictions[arm]=pred
            worker_receipts[arm]={k:v for k,v in response.items() if k!='prediction'}
            pd.DataFrame({'material_id':known_ids,'prediction':pred[:715]}).to_csv(folder/f'{arm}_known_validation_predictions.csv.gz',index=False,float_format='%.17g',compression='gzip')
            pd.DataFrame({'material_id':fresh_ids,'prediction':pred[715:]}).to_csv(folder/f'{arm}_fresh_predictions.csv.gz',index=False,float_format='%.17g',compression='gzip')
        # Old numerical baseline must replay before fresh ground truth is accessed.
        cached=pd.read_csv(backend.OLD/'experiments/E011/validation_predictions.csv.gz',float_precision='round_trip',index_col='material_id').loc[known_ids]
        difference=float(np.max(np.abs(final_predictions['baseline'][:715]-cached.prediction.to_numpy())))
        if difference>1e-12:raise RuntimeError(f'ExactroundtripE011baseline replayfailed maxabs={difference}; freshlabelsremainsealed')
        prediction_receipt={'created_utc':backend.now(),'frozen_champion_path':'final/champion_frozen.json','frozen_champion_sha256':frozen_sha,
          'fresh_manifest_sha256':backend.sha(ROOT/'fresh_cohort/prefit_manifest.json'),
          'predictions':{arm:{'path':f'final/{arm}_fresh_predictions.csv.gz','sha256':backend.sha(folder/f'{arm}_fresh_predictions.csv.gz')} for arm in ('baseline','champion')},
          'known_baseline_replay_max_absolute_difference':difference,'workers':worker_receipts,'fresh_labels_accessed':False}
        backend.dump(folder/'prediction_receipt.json',prediction_receipt,exclusive=True)
        backend.remaining_wall()
        labels=data_curator.load_targets_after_freeze(frozen_sha,'final/prediction_receipt.json',ROOT).set_index('material_id').loc[fresh_ids]
        fresh_y=labels.formation_energy_per_atom.to_numpy();known_y=cached.truth.to_numpy()
        results={arm:{'known_validation':metric(known_y,pred[:715]),'fresh1000':metric(fresh_y,pred[715:])} for arm,pred in final_predictions.items()}
        comparison=cluster_difference(fresh_y,final_predictions['baseline'][715:],final_predictions['champion'][715:],fresh_meta.loc[fresh_ids,'chemical_system'].to_numpy())
        known_gain=results['champion']['known_validation']['MAE_eV_atom']<=results['baseline']['known_validation']['MAE_eV_atom']
        fresh_gain=results['champion']['fresh1000']['MAE_eV_atom']<results['baseline']['fresh1000']['MAE_eV_atom']
        supported=bool(frozen['OOF_gate_pass'] and known_gain and fresh_gain)
        result={'schema_version':1,'candidate_id':selected,'frozen_champion_sha256':frozen_sha,'results':results,'fresh_comparison':comparison,
          'OOF_schedule_gate_pass':frozen['OOF_gate_pass'],'known_validation_nonworsening':known_gain,'fresh_MAE_improved':fresh_gain,'promotion_pass':supported,
          'incumbent':'chosenAgentprogram' if supported else 'E011','counts':backend.fit_counts(folder/'fit_events_live.jsonl'),'elapsed_seconds':time.monotonic()-started,
          'fresh_scope':'1000 newlyheldout IDs/980systems excludedfrompriorregisteredlocalexperiments, samepublicMPrelease; notexternal-source ornewDFT/synthesis.',
          'engineering_limit':'Inferenceindependence/geometricchecksarefiniteprobes, notformalsecurityorphysicalproof. FitcountsaretrustedAPIlearners; Agentprogramtraininginvocationsseparate.',
          'fresh_prediction_receipt_sha256':backend.sha(folder/'prediction_receipt.json'),'labels_release_receipt_sha256':backend.sha(ROOT/'fresh_cohort/label_release_receipt.json'),
          'artifact_hashes':{p.name:backend.sha(p) for p in [folder/'fit_events_live.jsonl',folder/'reservation.json',*[folder/f'{arm}_{cohort}_predictions.csv.gz' for arm in ('baseline','champion') for cohort in ('known_validation','fresh')],*folder.glob('*_features.csv.gz')]}}
        backend.dump(folder/'result.json',result,exclusive=True)
        s=backend.state();counts=result['counts']
        for k in ('fit_started','fit_completed'):s['counters'][k]+=counts[k]
        s['active_operation']=None;s['final_result']=result;backend.dump(backend.STATE,s)
        return result
    except Exception as exc:
        counts=backend.fit_counts(folder/'fit_events_live.jsonl');backend.dump(folder/'failure.json',{'error':f'{type(exc).__name__}: {exc}','counts':counts,'utc':backend.now(),'new_fit_retry_allowed':False},exclusive=True)
        s=backend.state()
        for k in ('fit_started','fit_completed'):s['counters'][k]+=counts[k]
        s['active_operation']=None;s['stop_reason']='Finalunknown_or_failed; noprediction/learnerretry';backend.dump(backend.STATE,s);raise


if __name__=='__main__':
    print(json.dumps(run(),ensure_ascii=False,allow_nan=False))
