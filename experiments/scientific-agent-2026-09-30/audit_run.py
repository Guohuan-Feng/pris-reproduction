"""Independent provenance, information-boundary and numerical replay audit.

Development mode never parses test labels or raw test structures. Final mode
requires an existing completed final-test record and explicit --authorize-final.
This script does not import evaluator.py or invoke any scientific-agent tool.
"""
from __future__ import annotations
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:
 os.environ[key]='1'
import argparse, ast, hashlib, json, sys
from pathlib import Path
from datetime import datetime, timezone
import joblib
import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.metrics import average_precision_score, roc_auc_score
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parent
CHECKS=[]
NOTES=[]
EPS=1e-6
TOOLS={'describe_data','inspect_records','run_experiment','counterexamples','compare_experiments','record_conclusion'}

def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def csv(p):return pd.read_csv(p,float_precision='round_trip')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def lines(p):return [json.loads(s) for s in Path(p).read_text(encoding='utf-8').splitlines() if s.strip()] if Path(p).exists() else []
def check(name,ok,details=None):
 row={'name':name,'passed':bool(ok)}
 if details is not None:row['details']=details
 CHECKS.append(row)
 return bool(ok)
def close(name,a,b,atol=1e-10,rtol=1e-10):
 a=np.asarray(a,dtype=float);b=np.asarray(b,dtype=float)
 same=a.shape==b.shape
 return check(name,same and np.allclose(a,b,atol=atol,rtol=rtol,equal_nan=True),{'maximum_absolute_difference':float(np.nanmax(np.abs(a-b))) if same and a.size else None,'absolute_tolerance':atol})

def task_loss(task,y,p):
 if task=='formation':return np.abs(y-p)
 p=np.clip(p,EPS,1-EPS)
 return -(y*np.log(p)+(1-y)*np.log1p(-p))

def metrics(task,y,p):
 y=np.asarray(y);p=np.asarray(p)
 if task=='formation':return {'rows':len(y),'MAE_eV_atom':float(np.mean(np.abs(y-p))),'RMSE_eV_atom':float(np.sqrt(np.mean((y-p)**2)))}
 p=np.clip(p,EPS,1-EPS);q=p>=.5
 tp=int(np.sum(q&(y==1)));fp=int(np.sum(q&(y==0)));tn=int(np.sum(~q&(y==0)));fn=int(np.sum(~q&(y==1)))
 precision=tp/(tp+fp) if tp+fp else 0.;recall=tp/(tp+fn) if tp+fn else 0.
 specificity=tn/(tn+fp) if tn+fp else 0.
 return {'rows':len(y),'logloss':float(np.mean(task_loss(task,y,p))),'AUC':float(roc_auc_score(y,p)) if len(np.unique(y))==2 else None,'AP':float(average_precision_score(y,p)) if np.any(y) else None,'threshold':.5,'TP':tp,'FP':fp,'TN':tn,'FN':fn,'precision':precision,'recall':recall,'F1':2*precision*recall/(precision+recall) if precision+recall else 0.,'balanced_accuracy':(recall+specificity)/2}

def compare_metrics(name,actual,expected):
 check(name+'/metric_keys',set(actual)==set(expected))
 for key,value in actual.items():
  if key not in expected:continue
  if value is None:check(name+'/'+key,expected[key] is None)
  else:close(name+'/'+key,value,expected[key],atol=2e-10)

def independent_preprocessing(train,names):
 med=np.nanmedian(train,axis=0)
 indicators=np.flatnonzero(np.isnan(train).any(axis=0))
 filled=np.where(np.isnan(train),med,train)
 if len(indicators):filled=np.column_stack((filled,np.isnan(train[:,indicators]).astype(float)))
 mu=filled.mean(axis=0);scale=filled.std(axis=0);scale[scale==0]=1
 z=(filled-mu)/scale;keep=[];expanded=names+[names[i]+'__missing' for i in indicators]
 for i in range(z.shape[1]):
  if np.ptp(z[:,i])<=1e-12:continue
  if any(np.allclose(z[:,i],sign*z[:,j],atol=1e-12,rtol=0) for j in keep for sign in [-1,1]):continue
  keep.append(i)
 return {'medians':med,'missing_indicator_indices':indicators,'means':mu,'scales':scale,'kept_indices':keep,'expanded_columns':expanded}

def transformed(x,pre):
 filled=np.where(np.isnan(x),np.asarray(pre['medians']),x)
 idx=pre['missing_indicator_indices']
 if len(idx):filled=np.column_stack((filled,np.isnan(x[:,idx]).astype(float)))
 return np.ascontiguousarray(((filled-pre['means'])/pre['scales'])[:,pre['kept_indices']])

def reconstruct(model,x,estimator_path):
 z=transformed(x,model['preprocessing'])
 if model['kind']=='hgb':
  estimator=joblib.load(estimator_path)
  with threadpool_limits(limits=1):p=estimator.predict(z) if model['task']=='formation' else estimator.predict_proba(z)[:,1]
 else:
  score=z@np.asarray(model['coefficients'])+model['intercept']
  p=score if model['task']=='formation' else expit(score)
 return p if model['task']=='formation' else np.clip(p,EPS,1-EPS)

def extract_tool_result(item):
 """Only decode explicit observed MCP result blocks, never infer execution."""
 result=item.get('result')
 if isinstance(result,dict):
  if isinstance(result.get('structuredContent'),dict):return result['structuredContent']
  for block in result.get('content',[]):
   if block.get('type')=='text':
    try:return json.loads(block['text'])
    except (ValueError,TypeError):pass
 return None

def audit_events(agent,allow_incomplete):
 server_dir=ROOT/'agent'
 invocation=load(agent/'invocation.json');events=lines(agent/'events.jsonl');server=lines(server_dir/'tool_events.jsonl')
 check('invocation/prompt_hash',sha(agent/'prompt.txt')==invocation['prompt_sha256'])
 for relative,expected in invocation.get('precall_hashes',{}).items():
  path=ROOT/relative
  check('invocation/frozen_source/'+relative,path.exists() and sha(path)==expected)
 completed=[e for e in events if e.get('type')=='turn.completed']
 check('invocation/single_completed_turn',len(completed)==1 or (allow_incomplete and len(completed)==0))
 if not allow_incomplete:check('invocation/completed',invocation.get('completed') is True)
 check('invocation/prompt_disallows_test','You cannot access test data' in (agent/'prompt.txt').read_text(encoding='utf-8'))
 items=[e['item'] for e in events if e.get('type')=='item.completed']
 mcp=[i for i in items if i.get('type')=='mcp_tool_call']
 other=[i for i in items if i.get('type') not in ['agent_message','reasoning','error','mcp_tool_call']]
 warnings=[i.get('message','') for i in items if i.get('type')=='error']
 check('events/no_foreign_executed_tools',not other and all(i.get('server')=='pris_science' and i.get('tool') in TOOLS for i in mcp),[i.get('type') for i in other])
 if warnings:NOTES.append({'startup_warning_items':warnings})
 rejected=lines(server_dir/'rejected_tool_calls.jsonl')
 check('events/processed_cap',len(server)<=24)
 check('events/serial_processed_numbers',[e['number'] for e in server]==list(range(1,len(server)+1)))
 # A running transcript can have one pending call; full completion must match.
 check('events/server_transcript_count',len(mcp)==len(server)+len(rejected) if not allow_incomplete else abs(len(mcp)-len(server)-len(rejected))<=1,{'completed_mcp_calls':len(mcp),'processed_server_calls':len(server),'budget_rejections':len(rejected)})
 for index,(observed,saved) in enumerate(zip(mcp,server)):
  check(f'events/{index+1}/tool',observed.get('tool')==saved['tool'])
  arguments=observed.get('arguments',{})
  if isinstance(arguments,str):arguments=json.loads(arguments)
  check(f'events/{index+1}/arguments',arguments==saved['arguments'] or (arguments=={} and saved['arguments']==[]))
  returned=extract_tool_result(observed)
  check(f'events/{index+1}/returned_result',returned==saved['response'],{'parsed_explicit_response':returned is not None})
 attempts=[e for e in server if e['tool']=='run_experiment']
 check('events/experiment_attempt_cap',len(attempts)<=6)
 if (server_dir/'state.json').exists():
  state=load(server_dir/'state.json')
  check('events/state_call_count',state['tool_calls']==len(server))
  check('events/state_attempt_count',state['experiment_attempts']==len(attempts))
 capabilities=[];lineage=[]
 dev_ids=set(csv(ROOT/'data/development.csv.gz').material_id)
 validation_ids=set(csv(ROOT/'data/development.csv.gz').query("split == 'validation'").material_id)
 previous={};counterexample_calls=[]
 for event in server:
  tool=event['tool'];args=event['arguments'];result=event['response']['tool_result']
  if tool=='inspect_records' and event['status']=='ok':
   ids={r['material_id'] for r in result['records']};check(f'boundary/inspect/{event["number"]}',ids<=dev_ids)
  if tool=='counterexamples' and event['status']=='ok':
   ids={r['material_id'] for r in result['examples']};check(f'boundary/counterexamples/{event["number"]}',ids<=validation_ids)
   frame=csv(ROOT/'evaluation/models'/args['candidate_id']/'development_predictions.csv.gz')
   expected=frame[frame.split.eq('validation')].sort_values([args['task']+'_loss','material_id'],ascending=[False,True]).head(args.get('k',6))
   check(f'counterexamples/{event["number"]}/ranked_IDs',[r['material_id'] for r in result['examples']]==expected.material_id.tolist())
   for field in ['formation_energy_per_atom','energy_above_hull','formation_prediction','hull_prediction']:
    close(f'counterexamples/{event["number"]}/'+field,[r[field] for r in result['examples']],expected[field])
   counterexample_calls.append({'number':event['number'],'candidate_id':args['candidate_id'],'task':args['task'],'rows':len(ids)})
  if tool!='run_experiment':continue
  eid=result.get('experiment_id');check(f'experiment/{eid}/assigned_id',eid==f'E{len(previous)+1:02d}')
  directory=ROOT/'experiments'/eid;spec=load(directory/'specification.json');code=(directory/'descriptor.py').read_text(encoding='utf-8')
  check(f'experiment/{eid}/authored_code',code==args['code'])
  check(f'experiment/{eid}/code_hash',sha(directory/'descriptor.py')==spec['code_sha'])
  syntax=ast.parse(code)
  check(f'experiment/{eid}/single_descriptor_function',len(syntax.body)==1 and isinstance(syntax.body[0],ast.FunctionDef) and syntax.body[0].name=='featurize')
  check(f'experiment/{eid}/no_imports',not any(isinstance(n,(ast.Import,ast.ImportFrom)) for n in ast.walk(syntax)))
  if spec.get('status')=='complete':check(f'experiment/{eid}/descriptor_budget',1<=len(spec['descriptor_names'])<=12)
  for key in ['name','hypothesis','scope','falsification','revision_of']:check(f'experiment/{eid}/metadata/{key}',spec[key]==args[key])
  parent=spec['revision_of'];has_parent=parent in previous
  check(f'experiment/{eid}/lineage',has_parent or str(parent).lower() in ['none','', 'null','n/a','raw'])
  prior_feedback=[c for c in counterexample_calls if c['number']<event['number']]
  lineage.append({'experiment_id':eid,'revision_of':parent,'status':spec.get('status'),'code_sha256':spec['code_sha'],'prior_observed_counterexample_calls':prior_feedback,'prior_parent_counterexample_calls':[c for c in prior_feedback if has_parent and c['candidate_id']==parent],'code_changed_from_parent':code!=previous[parent]['code'] if has_parent else None,'hypothesis':spec['hypothesis']})
  previous[eid]={'code':code,'spec':spec}
 for tool in sorted(TOOLS):
  matched=[e for e in server if e['tool']==tool]
  capabilities.append({'capability_tool':tool,'observed_processed_calls':len(matched),'event_numbers':[e['number'] for e in matched],'observed':bool(matched)})
 startup=None
 if agent!=server_dir:
  initial=load(server_dir/'invocation.json');initial_events=lines(server_dir/'events.jsonl')
  initial_calls=[e for e in initial_events if e.get('item',{}).get('type')=='mcp_tool_call']
  check('recovery/initial_zero_scientific_calls',len(initial_calls)==0)
  check('recovery/initial_failed_completion',initial.get('completed') is False)
  check('recovery/initial_prompt_preserved',sha(server_dir/'prompt.txt')==initial['prompt_sha256'])
  check('recovery/initial_runner_preserved',sha(server_dir/'initial_run_agent.py')==initial['precall_hashes']['run_agent.py'])
  check('recovery/initial_protocol_preserved',sha(server_dir/'initial_PROTOCOL.md')==initial['precall_hashes']['PROTOCOL.md'])
  startup={'scientific_tool_calls':len(initial_calls),'completed':initial.get('completed'),'usage_events':initial.get('usage_events',[]),'transcript_sha256':sha(server_dir/'events.jsonl'),'interpretation':'Infrastructure failure before any scientific experiment, preserved separately from the working discovery session.'}
 return {'invocation_completed':invocation.get('completed',False),'processed_calls':len(server),'experiment_attempts':len(attempts),'budget_rejections':len(rejected),'observed_capabilities':capabilities,'experiment_lineage':lineage,'counterexample_calls':counterexample_calls,'transcript_sha256':sha(agent/'events.jsonl'),'server_events_sha256':sha(server_dir/'tool_events.jsonl') if (server_dir/'tool_events.jsonl').exists() else None,'preserved_startup_failure':startup}

def development_numeric():
 base=ROOT/'evaluation';prep=load(base/'prepared.json');manifest=load(ROOT/'data/dataset_manifest.json')
 check('numerical/evaluator_hash',sha(ROOT/'evaluator.py')==prep['evaluator_sha256'])
 for name,expected in prep['source_hashes'].items():
  if name=='sealed_test.csv.gz':check('sources/sealed_hash_manifest_only',expected==manifest['files'][name]['sha256'])
  else:check('sources/'+name,sha(ROOT/'data'/name)==expected)
 features=csv(ROOT/'data/features.csv.gz').set_index('material_id');splits=csv(ROOT/'data/split_assignments.csv').set_index('material_id');dev=csv(ROOT/'data/development.csv.gz').set_index('material_id').sort_index()
 check('boundary/development_IDs',set(dev.index)==set(splits.index[splits.split.ne('test')]))
 check('boundary/development_roles',dev.split.equals(splits.loc[dev.index,'split']))
 check('boundary/prepared_train_IDs',list(dev.index[dev.split.eq('train')])==prep['training_ids'])
 check('boundary/prepared_validation_IDs',list(dev.index[dev.split.eq('validation')])==prep['validation_ids'])
 for group in ['chemical_system','composition_signature']:check('boundary/disjoint_'+group,splits.groupby(group).split.nunique().max()==1)
 raw=prep['raw_features'];check('numerical/raw30',len(raw)==30 and np.isfinite(features[raw].to_numpy()).all())
 # The runtime strips IDs and all labels before calling agent code. This
 # checks the explicit input whitelist, not a hostile-process security claim.
 runtime=ast.parse((ROOT/'descriptor_runtime.py').read_text(encoding='utf-8'))
 whitelists=[n.value for n in runtime.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='INPUT_KEYS' for t in n.targets)]
 if check('boundary/runtime_input_whitelist_present',len(whitelists)==1):
  input_keys=ast.literal_eval(whitelists[0])
  check('boundary/runtime_no_ID_or_target_inputs',not input_keys&{'material_id','formula','split','chemical_system','formation_energy_per_atom','energy_above_hull','energy','energy_per_atom'})
 train=dev.split.eq('train').to_numpy();valid=~train
 summaries={}
 for folder in sorted((base/'models').iterdir()):
  if not (folder/'metrics.json').exists():continue
  arm=folder.name;stored=csv(folder/'development_predictions.csv.gz').set_index('material_id').loc[dev.index];summary=load(folder/'metrics.json')
  x=features.loc[dev.index,raw].copy()
  if arm not in ['raw','hgb']:
   spec=load(base/'candidates'/arm/'specification.json');added=csv(base/'candidates'/arm/'development_descriptors.csv.gz').set_index('material_id').loc[dev.index]
   check(f'numerical/{arm}/descriptor_IDs',set(added.index)==set(dev.index))
   check(f'numerical/{arm}/descriptor_names',list(added.columns)==spec['descriptor_names'])
   check(f'numerical/{arm}/code_provenance',spec['code_sha']==sha(ROOT/'experiments'/arm/'descriptor.py'))
   x=pd.concat([x,added],axis=1)
  matrix=x.to_numpy(float);pre=independent_preprocessing(matrix[train],list(x.columns))
  for task in ['formation','hull']:
   model=load(folder/f'{task}_model.json');mp=model['preprocessing']
   check(f'numerical/{arm}/{task}/training_rows',model['training_rows']==int(train.sum()))
   check(f'numerical/{arm}/{task}/column_names',mp['columns']==list(x.columns))
   for key in ['medians','means','scales','kept_indices','missing_indicator_indices']:close(f'numerical/{arm}/{task}/train_only_{key}',pre[key],mp[key])
   p=reconstruct(model,matrix,folder/f'{task}_estimator.joblib')
   close(f'numerical/{arm}/{task}/serialized_predictions',p,stored[f'{task}_prediction'])
   y=dev.formation_energy_per_atom.to_numpy() if task=='formation' else (dev.energy_above_hull.to_numpy()<=1e-8).astype(int)
   close(f'numerical/{arm}/{task}/row_losses',task_loss(task,y,p),stored[f'{task}_loss'])
   for role,mask in [('train',train),('validation',valid)]:compare_metrics(f'numerical/{arm}/{task}/{role}',metrics(task,y[mask],p[mask]),summary['tasks'][task][role])
  summaries[arm]=summary
 return summaries

def audit_final(summaries):
 base=ROOT/'evaluation';final=base/'final';selection=load(base/'selection.json');freeze=load(final/'prediction_freeze.json');marker=load(final/'TEST_ACCESS_STARTED.json');result=load(final/'test_results.json')
 check('final/authorized',marker['authorization'].get('authorized') is True)
 check('final/prediction_before_targets',datetime.fromisoformat(freeze['at'])<=datetime.fromisoformat(marker['at']))
 check('final/selection_before_prediction',datetime.fromisoformat(selection['at'])<=datetime.fromisoformat(freeze['at']))
 check('final/selection_hash',sha(base/'selection.json')==freeze['selection_sha256'])
 check('final/frozen_prediction_hash',sha(final/'frozen_test_predictions.csv.gz')==freeze['predictions_sha256'])
 check('final/prediction_freeze_hash',sha(final/'prediction_freeze.json')==marker['prediction_freeze_sha256'])
 for name,expected in selection['artifact_hashes'].items():check('final/development_frozen/'+name,sha(base/name)==expected)
 for name,expected in freeze['test_descriptor_hashes'].items():check('final/test_descriptor_hash/'+name,sha(final/name)==expected)
 available=selection['available']
 for task in ['formation','hull']:
  losskey='MAE_eV_atom' if task=='formation' else 'logloss'
  best=min(a['metrics']['tasks'][task]['validation'][losskey] for a in available)
  winner=min([a for a in available if a['metrics']['tasks'][task]['validation'][losskey]<=best+1e-12],key=lambda a:(a['n_descriptors'],a['order']))
  check('final/'+task+'/validation_selection',winner['id']==selection['selected'][task]['candidate_id'])
 targets=csv(ROOT/'data/sealed_test.csv.gz').set_index('material_id').sort_index()
 predictions=csv(final/'frozen_test_predictions.csv.gz').set_index('material_id').sort_index()
 with_targets=csv(final/'test_predictions_with_targets.csv.gz').set_index('material_id').loc[predictions.index]
 features=csv(ROOT/'data/features.csv.gz').set_index('material_id').loc[predictions.index];raw=load(base/'prepared.json')['raw_features']
 check('final/test_IDs',targets.index.equals(predictions.index) and targets.split.eq('test').all())
 check('final/test_systems',targets.chemical_system.equals(predictions.chemical_system))
 check('final/frozen_predictions_target_free',not any(c in predictions for c in ['formation_truth','hull_truth','formation_energy_per_atom','energy_above_hull']))
 for task in ['formation','hull']:
  y=targets.formation_energy_per_atom.to_numpy() if task=='formation' else (targets.energy_above_hull.to_numpy()<=1e-8).astype(int)
  close('final/'+task+'/truth',y,with_targets[task+'_truth'])
  for label in ['selected','raw','hgb']:
   arm=selection['selected'][task]['candidate_id'] if label=='selected' else label
   x=features[raw].copy();folder=base/'models'/arm
   if arm not in ['raw','hgb']:
    added=csv(final/f'{arm}_test_descriptors.csv.gz').set_index('material_id').loc[predictions.index]
    spec=load(base/'candidates'/arm/'specification.json')
    x=pd.concat([x,added[spec['descriptor_names']]],axis=1)
    check(f'final/{arm}/frozen_code',sha(ROOT/'experiments'/arm/'descriptor.py')==spec['code_sha']==freeze['descriptor_provenance'][arm]['code_sha'])
   p=reconstruct(load(folder/f'{task}_model.json'),x.to_numpy(float),folder/f'{task}_estimator.joblib')
   close(f'final/{task}/{label}/prediction',p,predictions[f'{task}_{label}'])
   close(f'final/{task}/{label}/same_saved_prediction',p,with_targets[f'{task}_{label}'])
   compare_metrics(f'final/{task}/{label}/metrics',metrics(task,y,p),result['tasks'][task]['metrics'][label])
  for control in ['raw','hgb']:
   delta=task_loss(task,y,predictions[task+'_selected'].to_numpy())-task_loss(task,y,predictions[task+'_'+control].to_numpy())
   systems,inverse=np.unique(predictions.chemical_system.to_numpy(str),return_inverse=True)
   numer=np.bincount(inverse,weights=delta);denom=np.bincount(inverse);rng=np.random.default_rng(20260930)
   draws=rng.integers(0,len(systems),(1000,len(systems)));values=numer[draws].sum(axis=1)/denom[draws].sum(axis=1)
   low,high=np.quantile(values,[.025,.975]);reported=result['tasks'][task]['paired_bootstrap'][control]
   close(f'final/{task}/{control}/paired_bootstrap',[delta.mean(),low,high],[reported['selected_minus_control'],reported['lower95'],reported['upper95']])
   check(f'final/{task}/{control}/bootstrap_metadata',reported['resamples']==1000 and reported['systems']==len(systems) and reported['rows']==len(delta) and reported['seed']==20260930)

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['development','final'],default='development');parser.add_argument('--agent-dir',type=Path,default=ROOT/'agent/recovered' if (ROOT/'agent/recovered/invocation.json').exists() else ROOT/'agent');parser.add_argument('--allow-incomplete',action='store_true');parser.add_argument('--authorize-final',action='store_true');parser.add_argument('--out',type=Path);args=parser.parse_args()
 if args.stage=='final' and (not args.authorize_final or not (ROOT/'evaluation/final/test_results.json').exists()):raise RuntimeError('Final audit requires explicit authorization and completed existing test')
 observed=audit_events(args.agent_dir,args.allow_incomplete)
 summaries=development_numeric()
 if args.stage=='final':audit_final(summaries)
 failures=[c for c in CHECKS if not c['passed']]
 result={'stage':args.stage,'at':datetime.now(timezone.utc).isoformat(),'passed':not failures and not args.allow_incomplete,'complete_agent_session_required':not args.allow_incomplete,'checks':CHECKS,'check_count':len(CHECKS),'failures':failures,'observed_evidence':observed,'notes':NOTES,'scope':'Independent scalar metric/preprocessing/serialized-model replay; observed process evidence is not an OS-level proof against hostile-code access. No evaluator functions imported.','test_labels_parsed':args.stage=='final'}
 path=args.out or ROOT/f'audit_{args.stage}.json';path.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
 print(json.dumps({'passed':result['passed'],'checks':len(CHECKS),'failures':failures,'stage':args.stage,'processed_calls':observed['processed_calls'],'experiment_attempts':observed['experiment_attempts']},indent=2))
 if failures:sys.exit(1)

if __name__=='__main__':main()
