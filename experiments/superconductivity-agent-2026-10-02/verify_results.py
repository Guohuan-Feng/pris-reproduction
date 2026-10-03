"""Independent numerical/manifest audit of frozen V2 evidence; never refits.

Run only after final/results.json exists. --skip-models is a public-evidence
mode: prediction replay and unavailable external first-pilot hashes are
explicitly omitted. Internal frozen evidence must still be present.
No historical target table is opened in either mode.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import random
import sys
sys.dont_write_bytecode = True

import numpy as np
import pandas as pd

ATOL = 1e-10
RTOL = 1e-11
SEED = 20261002
CHECKS = []
OMISSIONS = []
HASHED = set()

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def csv(path):
    return pd.read_csv(path, float_precision='round_trip')

def relative_path(root, relative):
    result = root / Path(str(relative).replace('\\','/'))
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError('Manifest path leaves its root: '+str(relative))
    return result

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            digest.update(chunk)
    HASHED.add(str(Path(path).resolve()))
    return digest.hexdigest()

def check(name, passes, **details):
    CHECKS.append({'check':name,'passes':bool(passes),**details})
    return bool(passes)

def same(name, actual, expected):
    if isinstance(expected, dict):
        if not check(name+'.keys', isinstance(actual,dict) and set(actual)==set(expected),
                     actual_keys=sorted(actual) if isinstance(actual,dict) else None, expected_keys=sorted(expected)):
            return
        for key in expected:
            same(name+'.'+str(key),actual[key],expected[key])
    elif isinstance(expected,list):
        if not check(name+'.length',isinstance(actual,list) and len(actual)==len(expected)):
            return
        for i,(a,b) in enumerate(zip(actual,expected)):
            same(name+'.'+str(i),a,b)
    elif isinstance(expected,(float,int)) and not isinstance(expected,bool):
        if actual is None:
            check(name,False,actual=actual,expected=expected)
        else:
            check(name,bool(np.isclose(float(actual),float(expected),atol=ATOL,rtol=RTOL)),actual=actual,expected=expected)
    else:
        check(name,actual==expected,actual=actual,expected=expected)

def check_hash(name,path,expected,optional=False,optional_reason=None):
    if not path.is_file():
        if optional:
            OMISSIONS.append({'check':name,'reason':optional_reason or 'External first-pilot source absent from portable public bundle.'})
        else:
            check(name,False,reason='Required file missing',path=str(path.name))
        return
    actual=sha(path)
    check(name,actual==expected,actual_sha256=actual,expected_sha256=expected)

def independent_metrics(frame,prediction):
    y=frame.tc.to_numpy(float)
    p=np.asarray(prediction,float)
    w=frame.weight.to_numpy(float)
    g=frame.group.astype(str).to_numpy()
    if len(y)!=len(p) or not np.isfinite(np.column_stack([y,p,w])).all() or np.any(y<0) or np.any(p<0) or np.any(w<=0):
        raise ValueError('Invalid targets, predictions, weights or alignment')
    def one(mask):
        selected=np.flatnonzero(mask)
        if not len(selected):
            return {'rows':0,'groups':0,'weight_sum':0.,'MAE_K':None,'RMSE_K':None,'MSLE_log1p':None,'bias_K':None}
        yy,pp,ww=y[selected],p[selected],w[selected]
        denominator=float(np.sum(ww))
        error=pp-yy
        return {'rows':len(selected),'groups':len(set(g[selected])), 'weight_sum':denominator,
            'MAE_K':float(np.sum(ww*np.abs(error))/denominator),
            'RMSE_K':float(np.sqrt(np.sum(ww*error**2)/denominator)),
            'MSLE_log1p':float(np.sum(ww*(np.log1p(pp)-np.log1p(yy))**2)/denominator),
            'bias_K':float(np.sum(ww*error)/denominator)}
    result=one(np.ones(len(y),bool))
    result['subgroups']={name:one(mask) for name,mask in
        [('reported_zero',y==0),('positive_tc',y>0),('high_tc_ge40K',y>=40)]}
    return result

def independent_bootstrap(frame,a,b,resamples):
    groups=frame.group.astype(str).to_numpy()
    y=frame.tc.to_numpy(float)
    w=frame.weight.to_numpy(float)
    delta=np.abs(y-np.asarray(a,float))-np.abs(y-np.asarray(b,float))
    names=sorted(set(groups))
    numerators=np.array([np.sum(w[groups==group]*delta[groups==group]) for group in names])
    denominators=np.array([np.sum(w[groups==group]) for group in names])
    rng=np.random.default_rng(SEED)
    draws=rng.integers(0,len(names),size=(resamples,len(names)))
    differences=np.sum(numerators[draws],axis=1)/np.sum(denominators[draws],axis=1)
    return {'MAE_difference_K':float(np.sum(numerators)/np.sum(denominators)),
            'conditional_95_percent_interval_K':np.quantile(differences,[.025,.975]).tolist(),
            'groups':len(names),'resamples':resamples}

def canonical(spec):
    return json.dumps(spec,sort_keys=True,separators=(',',':'))

def winner(ids,results):
    return min(ids,key=lambda cid:(results[cid]['metrics']['MAE_K'],results[cid]['actual_model_fits'],cid))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--source-root',type=Path)
    parser.add_argument('--skip-models',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    root=args.root.resolve()
    source=args.source_root.resolve() if args.source_root else root.parent/'scientific_tc_2026-10-01'
    result_path=root/'final/results.json'
    if not result_path.is_file():
        raise SystemExit('Wait for final/results.json and the final-ready signal; no verification has run.')
    result=load(result_path)
    selection=load(root/'selection.json')
    plan=load(root/'controls/plan.json')
    execution=load(root/'controls/execution.json')
    state=load(root/'agent/state.json')
    audit=load(root/'data/data_audit.json')
    repair=load(root/'repair/audit.json')
    schema=load(root/'data/schema.json')
    benchmark=load(root/'benchmark_results.json')
    invocation_path=root/'agent/recovered/invocation.json'
    if not invocation_path.is_file():invocation_path=root/'agent/invocation.json'
    invocation=load(invocation_path)
    final=csv(root/'final/predictions.csv.gz')
    before=csv(root/'final/predictions_before_labels.csv.gz')
    inputs=csv(root/'data/validation_inputs.csv.gz')
    train=csv(root/'data/train.csv.gz')
    folds=csv(root/'data/fold_assignments.csv')
    all_ids=selection['shared_global_ids']+selection['outside_menu_reference_ids']+selection['agent_ids']+selection['control_ids']
    results={cid:load(root/'candidates'/cid/'result.json') for cid in all_ids}
    replay=[]

    # Hash checks refer only to the already frozen search/model/input artifacts.
    check_hash('selection_sha256',root/'selection.json',result['selection_sha256'])
    check_hash('final_predictions_sha256',root/'final/predictions.csv.gz',result['predictions_sha256'])
    same('embedded_selection',result['selection'],selection)
    for name,digest in selection['frozen_sha256'].items():
        is_stderr=str(name).replace('\\','/').endswith('/stderr.log')
        check_hash('freeze.'+name,relative_path(root,name),digest,optional=args.skip_models and is_stderr,
                   optional_reason='Raw Agent stderr intentionally omitted from the public release; frozen hash retained, content not checked.')
    for name,digest in audit['prepared_sha256'].items():
        check_hash('prepared.'+name,root/'data'/name,digest)
    for name,digest in audit['repair_sha256'].items():
        check_hash('repair_features.'+name,relative_path(root,name),digest)
    for name,digest in repair['output_sha256'].items():
        check_hash('repair_output.'+name,root/'repair'/name,digest)
    for mapping,prefix in [(audit['source_sha256'],'v2_first_pilot_source'),(repair['source_sha256'],'repair_first_pilot_source')]:
        for name,digest in mapping.items():
            check_hash(prefix+'.'+name,relative_path(source,name),digest,optional=args.skip_models)
    check('repair.source_unchanged',repair['summary']['source_files_unchanged'])
    check('repair.representation_passes',repair['summary']['representation_failures']==0)
    for name,digest in invocation['precall_hashes'].items():
        check_hash('precommit.'+name,relative_path(root,name),digest)
    check_hash('plan.protocol_sha256',root/'PROTOCOL.md',plan['protocol_sha256'])
    check_hash('control_execution.plan_sha256',root/'controls/plan.json',execution['plan_sha256'])
    check('precall_plan_matches_execution',invocation['precall_hashes'].get('controls\\plan.json',invocation['precall_hashes'].get('controls/plan.json'))==execution['plan_sha256'])

    # Derive training folds and partition integrity without fitting anything.
    check('train_rows',len(train)==3764,actual=len(train))
    check('train_groups',train.group.nunique()==1117,actual=int(train.group.nunique()))
    check('validation_rows',len(final)==len(inputs)==869,actual=len(final))
    check('validation_groups',final.group.nunique()==280,actual=int(final.group.nunique()))
    check('train_ids_unique',train.material_id.is_unique)
    check('validation_ids_unique',final.material_id.is_unique)
    check('validation_inputs_have_no_target','tc' not in inputs)
    check('fold_alignment',folds.material_id.tolist()==train.material_id.tolist() and folds.group.tolist()==train.group.tolist())
    check('fold_values',set(folds.fold)=={0,1,2})
    check('group_within_one_fold',folds.groupby('group').fold.nunique().max()==1)
    for key in ['group','chemical_system','parent_id','canonical_composition']:
        check('partition_overlap.'+key,not(set(train[key])&set(inputs[key])))
        for fold in range(3):
            check('fold_overlap.'+str(fold)+'.'+key,not(set(train.loc[folds.fold!=fold,key])&set(train.loc[folds.fold==fold,key])))
    for input_name,names in schema['inputs'].items():
        check('no_predictor_metadata.'+input_name,not(set(names)&set(schema['excluded_predictor_metadata'])))

    # Recompute every available candidate's pooled and fold OOF statistics.
    for cid,scored in results.items():
        folder=root/'candidates'/cid
        spec=load(folder/'specification.json')
        table=csv(folder/'oof_predictions.csv.gz')
        same('candidate_spec.'+cid,scored['specification'],spec)
        check_hash('candidate_spec_hash.'+cid,folder/'specification.json',scored['specification_sha256'])
        check_hash('candidate_oof_hash.'+cid,folder/'oof_predictions.csv.gz',scored['oof_predictions_sha256'])
        same('candidate_sources.'+cid,scored['source_sha256'],audit['prepared_sha256'])
        check('oof_alignment.'+cid,table.material_id.tolist()==train.material_id.tolist() and table.fold.tolist()==folds.fold.tolist())
        for name in ['tc','weight','group']:
            check('oof_source_'+name+'.'+cid,np.array_equal(table[name].to_numpy(),train[name].to_numpy()))
        same('oof_metrics.'+cid,scored['metrics'],independent_metrics(table,table.prediction))
        total_fits=0
        for details in scored['fold_details']:
            fold=details['fold']
            mask=folds.fold==fold
            same('fold_held_metrics.'+cid+'.'+str(fold),details['held_metrics'],independent_metrics(table.loc[mask],table.loc[mask,'prediction']))
            check('fold_counts.'+cid+'.'+str(fold),details['fit_rows']==int((~mask).sum()) and details['held_rows']==int(mask.sum()) and
                  details['fit_groups']==train.loc[~mask,'group'].nunique() and details['held_groups']==train.loc[mask,'group'].nunique())
            intrinsic=1
            for route,info in details['training_routes'].items():
                configured=route in spec['experts']
                active=configured and info['training_rows']>=80 and info['training_groups']>=12
                check('expert_eligibility.'+cid+'.'+str(fold)+'.'+route,info['configured']==configured and info['active_expert']==active)
                intrinsic+=int(active)
            check('intrinsic_fold_fits.'+cid+'.'+str(fold),details['fit_count']==intrinsic,actual=details['fit_count'],expected=intrinsic)
            total_fits+=intrinsic
        check('intrinsic_total_fits.'+cid,scored['actual_model_fits']==total_fits,actual=scored['actual_model_fits'],expected=total_fits)
        same('oof_usage.'+cid,scored['prediction_usage'],{str(k):int(v) for k,v in table.used_model.value_counts().to_dict().items()})

    # Exact selection rules, including intrinsic-fit / lexical-ID ties and aliases.
    check('reference_bank_counts',len(selection['shared_global_ids'])==8 and len(selection['outside_menu_reference_ids'])==4)
    anchor=winner(selection['shared_global_ids'],results)
    check('shared_anchor',anchor==selection['best_shared_global']==benchmark['best_shared_global'])
    anchor_positive=results[anchor]['metrics']['subgroups']['positive_tc']['MAE_K']
    for arm,ids in [('agent',selection['agent_ids']),('automated_control',selection['control_ids'])]:
        chosen=selection[arm]
        guards={cid:results[cid]['metrics']['subgroups']['positive_tc']['MAE_K']<=anchor_positive+1e-12 for cid in ids}
        eligible=[cid for cid in ids if guards[cid]]
        expected=winner([anchor]+eligible,results)
        same('selection_guard.'+arm,chosen['guard_pass'],guards)
        same('eligible_ids.'+arm,chosen['eligible_ids'],eligible)
        check('selected_winner.'+arm,chosen['selected']==expected,actual=chosen['selected'],expected=expected)
        same('guard_anchor_positive.'+arm,chosen['positive_guard_MAE_K'],anchor_positive)
        check('guard_anchor_id.'+arm,chosen['positive_guard_anchor']==anchor)
        matches=canonical(results[expected]['specification'])==canonical(results[anchor]['specification'])
        for field in ['global_fallback_selected','selected_specification_matches_anchor']:
            same('selection_alias.'+arm+'.'+field,chosen[field],matches)
        same('selection_alias.'+arm+'.anchor_alias_selected',chosen['anchor_alias_selected'],matches and expected!=anchor)
    check('best_all_global_reference',selection['best_all_global_reference']==winner(selection['shared_global_ids']+selection['outside_menu_reference_ids'],results))
    check('best_outside_menu_reference',selection['best_outside_menu_reference']==winner(selection['outside_menu_reference_ids'],results))

    # Recreate the seed draw in memory, then verify exactly the attempted prefix.
    rng=random.Random(SEED)
    choices=[{'model':m,'target':t} for m in ['extra_trees','hist_gradient_boosting'] for t in ['raw','log1p']]
    generated=[]
    for i,routing in enumerate(['chemistry','kmeans3','chemistry','kmeans3','chemistry'],1):
        route_keys=['cu_o','fe_anion','other'] if routing=='chemistry' else ['cluster0','cluster1','cluster2']
        spec={'input':rng.choice(['composition','composition_repaired']),'routing':routing,
              'global':rng.choice(choices).copy(),'experts':{route:rng.choice(choices).copy() for route in route_keys}}
        generated.append({'id':f'C{i:02d}','specification':spec})
    same('seeded_control_plan',plan['candidates'],generated)
    check('seeded_plan_seed',plan['seed']==SEED and plan['attempts']==5)
    attempts=state['strategy_attempts']
    check('matched_attempt_count',1<=attempts<=5 and execution['attempted_configurations']==attempts and len(execution['results'])==attempts)
    check('agent_attempt_records',len(state['strategies'])==attempts)
    check('agent_completed_ids',selection['agent_ids']==[item['id'] for item in state['strategies'] if item['status']=='complete'])
    check('control_prefix_ids',[item['candidate_id'] for item in execution['results']]==[item['id'] for item in plan['candidates'][:attempts]])
    check('control_completed_ids',selection['control_ids']==execution['successful_ids']==[item['candidate_id'] for item in execution['results'] if item['status']=='complete'])
    for planned,record in zip(plan['candidates'],execution['results']):
        if record['status']=='complete':
            same('executed_control_spec.'+planned['id'],results[planned['id']]['specification'],planned['specification'])
    events=[json.loads(line) for line in (root/'agent/tool_events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    attempts_logged=[event for event in events if event['tool']=='run_strategy']
    check('agent_attempts_logged',len(attempts_logged)==attempts)
    check('agent_call_cap',len(events)==state['tool_calls']<=18)
    check('agent_invocation_completed',invocation['completed'] and not invocation['foreign_tool_events'])
    check('agent_invocation_counts',invocation['strategy_attempts']==attempts and invocation['scientific_processed_calls']==len(events))
    for event in events:
        check('agent_tool_before_freeze.'+str(event['number']),dt.datetime.fromisoformat(event['finished_utc'])<=dt.datetime.fromisoformat(selection['freeze_utc']))

    # Prediction persistence, followed by target access, is a controller log.
    journal=load(root/'final/access_journal.json')
    expected_events=['selection_and_code_frozen','all_models_fit_on_original_training_and_saved',
                     'all_validation_predictions_saved_before_target_access','validation_targets_first_opened_for_post_freeze_metrics']
    check('journal_event_order',[row['event'] for row in journal]==expected_events)
    dates=[dt.datetime.fromisoformat(row['utc']) for row in journal]
    check('journal_temporal_order',dates==sorted(dates) and dt.datetime.fromisoformat(selection['freeze_utc'])<=dates[0])
    check_hash('journal.selection_hash',root/'selection.json',journal[0]['selection_sha256'])
    check_hash('journal.prelabel_prediction_hash',root/'final/predictions_before_labels.csv.gz',journal[2]['predictions_sha256'])
    check('prelabel_table_target_absent','tc' not in before)
    check('before_after_predictions_identical',before.equals(final.drop(columns=['tc'])))
    check('final_input_alignment',final.material_id.tolist()==inputs.material_id.tolist())
    for name in ['group','weight','formula','chemical_system']:
        check('final_input_metadata.'+name,final[name].equals(inputs[name]))
    check('final_prediction_columns',set(final)-{'material_id','group','weight','formula','chemical_system','tc'}==set(all_ids))
    for cid in all_ids:
        same('validation_metrics.'+cid,result['metrics'][cid],independent_metrics(final,final[cid]))
    selected=selection['agent']['selected']
    comparison_ids={'agent_minus_shared_global':anchor,'agent_minus_automated_control':selection['automated_control']['selected'],
                    'agent_minus_best_all_global_reference':selection['best_all_global_reference'],
                    'agent_minus_best_outside_menu_reference':selection['best_outside_menu_reference']}
    for name,cid in comparison_ids.items():
        reported=result['paired_group_bootstrap'][name]
        expected=independent_bootstrap(final,final[selected],final[cid],reported['resamples'])
        same('bootstrap.'+name,{k:reported[k] for k in expected},expected)

    if args.skip_models:
        OMISSIONS.append({'check':'saved_final_model_hashes_and_prediction_replay','reason':'--skip-models explicitly omits large local joblib bundles. Numerical/selection/hash audit only.'})
    else:
        # Import only inference functions; never construct a Workbench or refit.
        sys.path.insert(0,str(root))
        import joblib
        from pipeline import predict_pipeline
        unique={}
        for cid in all_ids:
            info=result['models'][cid]
            path=relative_path(root,info['path'])
            check_hash('final_model_hash.'+cid,path,info['sha256'])
            bundle=joblib.load(path)
            check('model_spec.'+cid,canonical(bundle['specification'])==canonical(results[cid]['specification']))
            check('model_training_rows.'+cid,bundle['global']['training_rows']==3764)
            check('model_columns.'+cid,bundle['input_columns']==schema['inputs'][bundle['specification']['input']])
            pred,routes,used=predict_pipeline(bundle,inputs)
            difference=float(np.max(np.abs(pred-final[cid].to_numpy(float))))
            check('model_prediction_replay.'+cid,bool(np.allclose(pred,final[cid].to_numpy(float),atol=ATOL,rtol=RTOL)),maximum_absolute_difference_K=difference)
            same('model_route_usage.'+cid,result['prediction_usage'][cid]['routes'],{str(k):int(v) for k,v in pd.Series(routes).value_counts().to_dict().items()})
            same('model_usage.'+cid,result['prediction_usage'][cid]['models'],{str(k):int(v) for k,v in pd.Series(used).value_counts().to_dict().items()})
            intrinsic=1+len(bundle['experts'])
            check('final_fit_count.'+cid,bundle['fit_count']==info['fit_count']==intrinsic)
            unique.setdefault(canonical(bundle['specification']),intrinsic)
            replay.append({'candidate_id':cid,'maximum_absolute_difference_K':difference,'rows':len(pred)})
        check('unique_final_specifications',result['unique_final_model_specifications']==len(unique))
        check('actual_unique_final_model_fits',result['actual_final_model_fits']==sum(unique.values()))

    failed=[item for item in CHECKS if not item['passes']]
    output=args.output or root/'final/verification.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    report={'completed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'mode':'public_numeric_evidence_without_model_replay' if args.skip_models else 'full_local_saved_model_replay',
        'passed':not failed,'summary':{'checks':len(CHECKS),'failed_checks':len(failed),'hashed_files':len(HASHED),
            'candidate_results_verified':len(results),'validation_rows':len(final),'replayed_model_bundles':len(replay)},
        'failures':failed,'omissions':OMISSIONS,'replay':replay,'checks':CHECKS,
        'scope':'Independent arithmetic/manifest verification of saved training OOF and old-validation evidence. No refitting, no model changes, no historical targets opened.',
        'limitations':['Model replay uses the frozen inference implementation with saved estimators; metric/selection/bootstrap arithmetic is independently derived.',
            'The access journal records controller order; it is not a forensic audit of every possible process/file access.',
            'Passed reproducibility checks do not turn historically observed development data into an independent test.']}
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'mode':report['mode'],'summary':report['summary'],'failures':failed,'omissions':OMISSIONS},indent=2))
    return 0 if not failed else 1

if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Preserve an explicit fatal diagnostic without silently marking success.
        print(json.dumps({'passed':False,'fatal_exception':type(exc).__name__,'message':str(exc),
                          'last_checks':CHECKS[-5:]},indent=2),file=sys.stderr)
        raise
