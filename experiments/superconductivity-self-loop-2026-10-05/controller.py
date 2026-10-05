"""Autonomous propose -> execute -> reflect -> revise loop with durable memory."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from runtime import Store,exclusive,read_json,write_json,run_child,Cancelled,BudgetExpired,utc
from llm_client import CodexDecider

SOURCE_PARENT=Path(__file__).resolve().parent.parent
DEFAULT_SOURCE=SOURCE_PARENT/'superconductivity-agent-2026-10-02'
if not DEFAULT_SOURCE.exists():DEFAULT_SOURCE=SOURCE_PARENT/'scientific_tc_2026-10-02'
DEFAULT_RUN=Path.home()/'tc-self-loop'/'runs'/'main'
DEFAULTS={'max_experiments':12,'min_completed_experiments':0,'max_llm_calls':30,'max_seconds':3600.,'max_call_seconds':240.,'max_fit_seconds':240.,'patience':4,'min_improvement_K':.01,'model':'gpt-5.6-sol'}

class WorkerExecutor:
    def __init__(self,root,source):self.root=Path(root);self.source=Path(source)
    def __call__(self,cid,spec,timeout,tick):
        folder=self.root/'cycles'/cid;folder.mkdir(parents=True,exist_ok=True)
        request=folder/'request.json';out=folder/'evaluation.json'
        write_json(request,{'candidate_id':cid,'specification':spec})
        if out.exists():return read_json(out)
        cmd=[sys.executable,'-X','utf8',str(Path(__file__).with_name('worker.py')),'--run',str(self.root),'--source',str(self.source),'--request',str(request),'--output',str(out)]
        rc=run_child(cmd,self.root,folder/'worker',timeout,tick=tick)
        if out.exists():return read_json(out)
        raise RuntimeError(f'Numerical worker exited {rc} without a persisted outcome')

class Controller:
    def __init__(self,root,adapter,decider,executor,config=None):
        self.root=Path(root);self.adapter=adapter;self.decider=decider;self.executor=executor
        self.store=Store(root);self.s=self.store.state()
        if self.s is None:
            cfg={**DEFAULTS,**(config or {})}
            if any(cfg[k]<=0 for k in ['max_experiments','max_llm_calls','max_seconds','max_call_seconds','max_fit_seconds','patience']):
                self.store.close();raise ValueError('Budgets and patience must be positive')
            if cfg['min_improvement_K']<0:
                self.store.close();raise ValueError('Improvement tolerance must be nonnegative')
            if not isinstance(cfg['min_completed_experiments'],int) or not 0<=cfg['min_completed_experiments']<=cfg['max_experiments']:
                self.store.close();raise ValueError('Minimum completed experiments must be an integer within the attempt budget')
            known=adapter.known_specifications();anchor=next(x for x in known if x['id']=='G01')
            positive=anchor['metrics']['subgroups']['positive_tc']['MAE_K']
            allowed=[x for x in known if x['spec']['input'] in ['composition','composition_repaired'] and x['metrics']['subgroups']['positive_tc']['MAE_K']<=positive+1e-12]
            incumbent=min(allowed,key=lambda x:(x['metrics']['MAE_K'],x['id']))
            self.s={'version':1,'created_utc':utc(),'status':'running','phase':'propose','config':cfg,'attempts':0,'llm_calls':0,'elapsed_seconds':0.,'stagnation':0,'best':{'id':incumbent['id'],'MAE_K':incumbent['metrics']['MAE_K']},'guard':{'anchor':'G01','positive_MAE_K':positive},'last_reflection':None,'pending_call':None,'pending_plan':None,'pending_result':None,'stop_reason':None,'completed_cycles':[]}
            self.persist('run.created',{'initial_incumbent':self.s['best'],'config':cfg})
        elif config is not None and any(self.s['config'].get(k)!=v for k,v in config.items()):
            self.store.close()
            raise ValueError('Existing run budgets/config are immutable; resume without overrides or create a new run')

    def persist(self,kind,payload=None):
        self.store.save(self.s,kind,payload);self.store.export()

    def tick(self,seconds):
        self.s['elapsed_seconds']+=seconds
        # SQLite is outside OneDrive. No replace-on-open state.json race.
        self.store.save(self.s,'runtime.elapsed',{'seconds':seconds})
        if self.s['elapsed_seconds']>=self.s['config']['max_seconds']:raise BudgetExpired('Cumulative run time exhausted')

    def stop(self,reason,status='stopped'):
        self.s.update(status=status,stop_reason=reason,successful_unique_cycles=self.completed_count(),minimum_completed_met=not self.minimum_pending());self.persist('run.stopped',{'reason':reason})

    def completed_count(self):
        """Count distinct successful measured configurations, including inherited cycles."""
        seen=set()
        for cycle in self.s['completed_cycles']:
            result=cycle.get('evaluation',{});metrics=result.get('metrics',{})
            if result.get('status')=='failed' or result.get('scientific_evidence_available') is False or result.get('proposal_was_duplicate',result.get('reused',False)):continue
            if not isinstance(cycle.get('specification'),dict) or not isinstance(cycle.get('reflection'),dict):continue
            try:
                if not all(math.isfinite(float(v)) for v in [metrics['MAE_K'],metrics['subgroups']['positive_tc']['MAE_K']]):continue
                seen.add(json.dumps(cycle['specification'],sort_keys=True,separators=(',',':')))
            except (KeyError,TypeError,ValueError):continue
        return len(seen)

    def minimum_pending(self):
        return self.completed_count()<self.s['config'].get('min_completed_experiments',0)

    def remaining(self,kind):
        return max(.01,min(self.s['config'][kind],self.s['config']['max_seconds']-self.s['elapsed_seconds']))

    def context(self,phase):
        workbench=self.adapter.context()
        def compact_metrics(metrics):
            return {'MAE_K':metrics.get('MAE_K'),'subgroups':{k:{'MAE_K':v.get('MAE_K')} for k,v in metrics.get('subgroups',{}).items()}}
        for known in workbench.get('known_specifications',[]):known['metrics']=compact_metrics(known['metrics'])
        recent=[]
        for cycle in self.s['completed_cycles'][-8:]:
            result=cycle.get('evaluation',{});reflection=cycle.get('reflection',{})
            recent.append({'candidate_id':cycle['candidate_id'],'hypothesis':cycle.get('hypothesis'),'revision_of':cycle.get('revision_of'),'specification':cycle.get('specification'),'metrics':compact_metrics(result.get('metrics',{})),'guard_eligible':result.get('guard_eligible'),'improved_incumbent':result.get('improved_incumbent'),'error':result.get('error'),'reflection':{k:reflection.get(k) for k in ['hypothesis_status','summary','next_focus']}})
        policy={'required_successful_unique_cycles':self.s['config'].get('min_completed_experiments',0),'completed_successful_unique_cycles':self.completed_count(),'minimum_pending':self.minimum_pending(),'stop_policy':'Before the required total, model/stagnation stops are deferred. Failed and duplicate attempts do not count. Operator stop and resource limits always apply. The previous run stop does not end this authorized continuation.'}
        c={'phase':phase,'objective':'Improve pooled weighted training OOF MAE over the best known guard-eligible model, without worsening the fixed G01 positive-Tc guard. Choose the next informative untried experiment autonomously until the authorized minimum is met.','scope':'Continuing development on previously observed training folds. No validation/scoring endpoint.','guard':self.s['guard'],'incumbent':self.s['best'],'minimum_MAE_gain_K':self.s['config']['min_improvement_K'],'continuation_policy':policy,'budget':{'remaining_experiments':self.s['config']['max_experiments']-self.s['attempts'],'remaining_llm_calls':self.s['config']['max_llm_calls']-self.s['llm_calls'],'stagnation':self.s['stagnation'],'patience':self.s['config']['patience']},'training_workbench':workbench,'recent_cycles':recent,'previous_reflection':self.s['last_reflection']}
        if phase=='reflect':c.update(proposal=self.s['pending_plan'],observed_result=self.s['pending_result'])
        return c

    def ask(self,phase):
        pending=self.s['pending_call']
        if pending is None:
            if self.s['llm_calls']>=self.s['config']['max_llm_calls']:raise BudgetExpired('Cumulative LLM call budget exhausted')
            number=self.s['llm_calls']+1;folder=self.root/'calls'/f'{number:03d}_{phase}'
            folder.mkdir(parents=True,exist_ok=True)
            context=self.context(phase);write_json(folder/'frozen_context.json',context)
            self.s['llm_calls']=number;self.s['pending_call']={'phase':phase,'folder':str(folder),'started_utc':utc()}
            self.persist('llm.reserved',{'number':number,'phase':phase})
        else:
            if pending['phase']!=phase:raise RuntimeError('Pending call/phase mismatch')
            folder=Path(pending['folder']);context=read_json(folder/'frozen_context.json')
        decision_file=folder/'decision.json'
        if decision_file.exists():decision=read_json(decision_file)
        elif (folder/'receipt.json').exists() and read_json(folder/'receipt.json').get('completed'):
            # Decider rehydrates a fully persisted response without another model call.
            decision=self.decider(phase,context,folder,self.remaining('max_call_seconds'),self.tick)
            write_json(decision_file,decision)
        elif (folder/'process.json').exists():
            # Never blindly repeat a potentially billed call after a crash.
            raise RuntimeError('Interrupted model call has unknown outcome. Inspect the call artifacts; no automatic duplicate model request was made.')
        else:
            decision=self.decider(phase,context,folder,self.remaining('max_call_seconds'),self.tick)
            write_json(decision_file,decision)
        return decision

    def run(self):
        if self.s['status']!='running':return self.s
        try:
            while self.s['status']=='running':
                if (self.root/'STOP').exists():raise Cancelled('User stop requested')
                if self.s['elapsed_seconds']>=self.s['config']['max_seconds']:raise BudgetExpired('Cumulative run time exhausted')
                phase=self.s['phase']
                if phase=='propose':
                    if self.s['config'].get('min_completed_experiments',0)>0 and not self.minimum_pending():
                        self.stop('minimum_completed_experiments_reached');break
                    if self.s['attempts']>=self.s['config']['max_experiments']:
                        self.stop('experiment_budget_exhausted');break
                    if self.s['stagnation']>=self.s['config']['patience'] and not self.minimum_pending():
                        self.stop('stagnation_limit_reached');break
                    if self.s['pending_call'] is None and self.s['llm_calls']+2>self.s['config']['max_llm_calls']:
                        self.stop('insufficient_call_budget_for_proposal_and_reflection');break
                    proposal=self.ask('propose')
                    if not isinstance(proposal,dict):raise ValueError('Proposal must be an object')
                    if proposal.get('action')=='stop':
                        if self.minimum_pending():
                            self.s['pending_call']=None;self.persist('agent.stop_deferred',{'phase':'propose','proposal':proposal,'minimum':self.s['config']['min_completed_experiments'],'completed':self.completed_count()});continue
                        self.s['pending_call']=None;self.stop('agent_stop: '+str(proposal.get('stop_reason') or proposal.get('reason')));break
                    self.s['attempts']+=1;cid=f'L{self.s["attempts"]:03d}'
                    self.s.update(pending_plan={**proposal,'candidate_id':cid},pending_call=None,phase='execute')
                    self.persist('proposal.accepted',self.s['pending_plan'])
                elif phase=='execute':
                    proposal=self.s['pending_plan'];cid=proposal['candidate_id']
                    self.persist('experiment.started',{'candidate_id':cid})
                    try:
                        if proposal.get('action')!='experiment' or not isinstance(proposal.get('specification'),dict):raise ValueError('Invalid experiment proposal')
                        if not all(isinstance(proposal.get(k),str) and len(proposal[k])>=3 for k in ['hypothesis','falsification','reason']):raise ValueError('Missing scientific hypothesis/falsification/reason')
                        if proposal.get('revision_of') not in ['none','']+[x['id'] for x in self.adapter.known_specifications()]:raise ValueError('Unknown revision parent')
                        result=self.executor(cid,proposal['specification'],self.remaining('max_fit_seconds'),self.tick)
                    except (Cancelled,BudgetExpired):raise
                    except Exception as exc:result={'status':'failed','error':f'{type(exc).__name__}: {exc}','scientific_evidence_available':False}
                    result=self.assess(result)
                    self.s.update(pending_result=result,phase='reflect')
                    self.persist('experiment.observed',{'candidate_id':cid,'result':result})
                elif phase=='reflect':
                    reflection=self.ask('reflect')
                    if not isinstance(reflection,dict) or reflection.get('next_action') not in ['continue','stop']:raise ValueError('Invalid reflection action')
                    cid=self.s['pending_plan']['candidate_id'];result=self.s['pending_result']
                    cycle={'candidate_id':cid,'hypothesis':self.s['pending_plan'].get('hypothesis'),'revision_of':self.s['pending_plan'].get('revision_of'),'specification':self.s['pending_plan'].get('specification'),'evaluation':result,'reflection':reflection}
                    self.s['completed_cycles'].append(cycle)
                    self.s.update(last_reflection=reflection,pending_call=None,pending_plan=None,pending_result=None,phase='propose')
                    self.persist('cycle.completed',cycle)
                    print(json.dumps({'cycle':cid,'MAE_K':result.get('metrics',{}).get('MAE_K'),'incumbent':self.s['best'],'agent_next_action':reflection['next_action'],'next_focus':reflection.get('next_focus')},ensure_ascii=False),flush=True)
                    if self.s['config'].get('min_completed_experiments',0)>0 and not self.minimum_pending():self.stop('minimum_completed_experiments_reached')
                    elif reflection['next_action']=='stop':
                        if self.minimum_pending():self.persist('agent.stop_deferred',{'phase':'reflect','candidate_id':cid,'reflection':reflection,'minimum':self.s['config']['min_completed_experiments'],'completed':self.completed_count()})
                        else:self.stop('agent_stop: '+str(reflection.get('stop_reason') or reflection.get('summary')))
                else:raise RuntimeError('Unknown state-machine phase')
        except Cancelled as exc:self.stop(str(exc),'paused')
        except BudgetExpired as exc:self.stop(str(exc))
        except Exception as exc:self.stop(f'{type(exc).__name__}: {exc}','attention_required')
        return self.s

    def assess(self,result):
        result=dict(result);m=result.get('metrics')
        if not isinstance(m,dict):
            result.update(guard_eligible=False,improved_incumbent=False);self.s['stagnation']+=1;return result
        positive=m['subgroups']['positive_tc']['MAE_K']
        eligible=positive<=self.s['guard']['positive_MAE_K']+1e-12
        gain=self.s['best']['MAE_K']-m['MAE_K']
        duplicate=result.get('proposal_was_duplicate',result.get('reused',False))
        improved=eligible and not duplicate and gain>=self.s['config']['min_improvement_K'] and gain>1e-12
        result.update(guard_eligible=eligible,improved_incumbent=improved,MAE_gain_over_previous_incumbent_K=gain)
        if improved:self.s['best']={'id':self.s['pending_plan']['candidate_id'],'MAE_K':m['MAE_K']};self.s['stagnation']=0
        else:self.s['stagnation']+=1
        return result

def main():
    p=argparse.ArgumentParser(description='Persistent self-looping Tc research controller')
    p.add_argument('command',choices=['run','resume','status','stop']);p.add_argument('--run-dir',type=Path,default=DEFAULT_RUN);p.add_argument('--source-dir',type=Path,default=DEFAULT_SOURCE)
    p.add_argument('--max-experiments',type=int);p.add_argument('--min-completed-experiments',type=int);p.add_argument('--max-llm-calls',type=int);p.add_argument('--max-seconds',type=float);p.add_argument('--patience',type=int);p.add_argument('--min-improvement-K',dest='min_improvement_K',type=float);p.add_argument('--model');p.add_argument('--codex-executable')
    args=p.parse_args();root=args.run_dir.expanduser().resolve();args.source_dir=args.source_dir.expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    if args.command=='stop':(root/'STOP').write_text(utc(),encoding='utf-8');print('Cancellation requested');return
    if args.command=='status':
        store=Store(root);s=store.state();print(json.dumps(s,ensure_ascii=False,indent=2));store.close();return
    with exclusive(root/'controller.lock'):
        # An orphaned child keeps this OS lock; do not duplicate unfinished work.
        with exclusive(root/'child.lock'):pass
        from workbench_adapter import prepare_run,Adapter
        prepare_run(root,args.source_dir.resolve());adapter=Adapter(root,args.source_dir.resolve())
        cfg={k:getattr(args,k) for k in ['max_experiments','min_completed_experiments','max_llm_calls','max_seconds','patience','min_improvement_K','model'] if getattr(args,k) is not None}
        existing=Store(root);state=existing.state();existing.close()
        if args.command=='run' and state is not None:raise RuntimeError('Run exists; use resume to retain budgets/history')
        if args.command=='resume' and state is None:raise RuntimeError('No existing run to resume')
        model=state['config']['model'] if state else cfg.get('model',DEFAULTS['model'])
        control=Controller(root,adapter,CodexDecider(root,model,args.codex_executable),WorkerExecutor(root,args.source_dir.resolve()),cfg if cfg else None)
        if args.command=='resume' and control.s['status'] in ['paused','attention_required']:
            if (root/'STOP').exists():(root/'STOP').unlink()
            control.s.update(status='running',stop_reason=None);control.persist('run.resumed',{'budgets_retained':True})
        state=control.run();control.store.close()
        print(json.dumps({k:state[k] for k in ['status','stop_reason','phase','attempts','llm_calls','elapsed_seconds','best','stagnation']},ensure_ascii=False,indent=2))
        if state['status']=='attention_required':raise SystemExit(2)

if __name__=='__main__':main()
