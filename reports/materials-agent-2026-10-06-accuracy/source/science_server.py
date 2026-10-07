"""Audited, serialized research tools for an actual isolated Agent session."""
from __future__ import annotations
from contextlib import redirect_stdout
import functools
import hashlib
import json
import os
from pathlib import Path
import site
import sys
import threading

ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
config=json.loads((ROOT/'runtime_config.json').read_text(encoding='utf-8'))
site.addsitedir(config['mcp_dependencies'])
from mcp.server import MCPServer
from audited_decision_interceptor import AuditedDecisionInterceptor
from decision_contract import DecisionAction,ScientificStatus,DecisionStore,DecisionValidationError
import backend

ATTEMPT=Path(os.environ['MATERIALS_CYCLE_DIR']).resolve()
LOCK=threading.RLock()
SERVER_STATE=ROOT/'state/server_state.json'


def ledger(event):
    s=backend.load(SERVER_STATE,{'tool_calls':0,'calls':[],'last_event_hash':None})
    event={**event,'previous_event_hash':s['last_event_hash'],'utc':backend.now()}
    event['event_hash']=backend.jsha(event)
    backend.append(ROOT/'state/server_ledger.jsonl',event);backend.append(ATTEMPT/'tool_events.jsonl',event)
    s['last_event_hash']=event['event_hash'];backend.dump(SERVER_STATE,s)


def audited_call(name,arguments,operation):
    with LOCK,redirect_stdout(sys.stderr):
        s=backend.load(SERVER_STATE,{'tool_calls':0,'calls':[],'last_event_hash':None})
        p=backend.load(ROOT/'protocol.json')
        if s['tool_calls']>=p['budget']['tool_calls']:raise RuntimeError('ActualMCPcallbudgetexhausted')
        if (ATTEMPT/'cycle_decision.json').exists() and name!='record_cycle_decision':raise RuntimeError('Decisionalreadysaved; finishsession')
        s['tool_calls']+=1;eid=f'T{s["tool_calls"]:04d}'
        item={'evidence_id':eid,'tool':name,'status':'started','attempt':str(ATTEMPT),'started_utc':backend.now(),
          'session_request_sha256':backend.sha(ATTEMPT/'session_request.json'),'arguments_sha256':backend.jsha(arguments)}
        if name in ('submit_representation','submit_predictor'):item['submitted_code_sha256']=hashlib.sha256(arguments.get('code','').encode()).hexdigest()
        s['calls'].append(item);backend.dump(SERVER_STATE,s);ledger({'event':'tool_started',**item})
        try:result=operation();status='complete';error=None
        except Exception as exc:
            result={'error':f'{type(exc).__name__}: {exc}','new_fit_retry_allowed':False};status='failed';error=result['error']
        s=backend.load(SERVER_STATE)
        if s['calls'][-1]['evidence_id']!=eid:raise RuntimeError('Toolserializationbroken')
        # Previous completed call entries remain immutable for transport reconciliation.
        finished={**s['calls'][-1],'status':status,'finished_utc':backend.now(),'response_sha256':backend.jsha(result)}
        s['calls'][-1]=finished;backend.dump(SERVER_STATE,s);ledger({'event':'tool_finished',**finished,'response':result,'error':error})
        science=backend.state();science['counters']['tool_calls']=s['tool_calls'];backend.dump(backend.STATE,science)
        return {'evidence_id':eid,'status':status,'result':result,'fresh_predictor_fit':name=='evaluate_candidate' and status=='complete',
          'retry_metadata_only':bool(result.get('retry_metadata_only',False)),'new_fit_retry_allowed':False}


def scientific_tool(fn):
    @functools.wraps(fn)
    def wrapped(*args,**kwargs):
        import inspect
        bound=inspect.signature(fn).bind(*args,**kwargs);bound.apply_defaults()
        return audited_call(fn.__name__,dict(bound.arguments),lambda:fn(*args,**kwargs))
    return wrapped


def decision_context_validator(payload):
    request=backend.load(ATTEMPT/'session_request.json');server=backend.load(SERVER_STATE);science=backend.state()
    valid={r['evidence_id']:r for r in server['calls'] if r['status'] in ('complete','failed')}
    if any(e not in valid for e in payload['evidence_ids']):raise DecisionValidationError('Citeactualfinishedtool evidenceonly')
    actual=[valid[e] for e in payload['evidence_ids'] if valid[e]['tool']=='evaluate_candidate' and valid[e]['attempt']==str(ATTEMPT)]
    if not actual and not science['stop_reason']:raise DecisionValidationError('DecisionmustcitefreshactualOOFcandidateinthiscycle')
    terminal=science['counters']['experiments']>=20 or bool(science['stop_reason'])
    if terminal and payload['action']!='stop':raise DecisionValidationError('Stopat20completedcandidatesorunknownsciencefailure')
    if not terminal and payload['action']!='continue':raise DecisionValidationError('Continuetoward20substantivecandidateswhilebudgetpermits')
    if payload['scientific_status']=='supported':
        candidates={k for k,v in science['proposals'].items() if v['attempt']==str(ATTEMPT)}
        this=[v for k,v in science['experiments'].items() if k in candidates and v.get('status')=='complete' and v['summary']['OOF_schedule_gate_pass']]
        if not this:raise DecisionValidationError('SupportedrequiresanactualOOFschedulinggatepass; noindependentclaim')


def raw_decision(arguments):
    original=dict(arguments)
    def operation():
        token=arguments.get('decision_token')
        payload={k:v for k,v in arguments.items() if k!='decision_token'}
        request=backend.load(ATTEMPT/'session_request.json')
        result=DecisionStore(ATTEMPT,expected_token=request['decision_token']).submit(token,payload,decision_context_validator)
        if result.get('saved') and not result.get('idempotent_replay'):
            s=backend.state();s['decisions'].append(result['decision']);backend.dump(backend.STATE,s)
        return result
    return audited_call('record_cycle_decision',original,operation)


mcp=MCPServer('Materials repeated OOF accuracy Agent',version='3.0.0',extensions=[AuditedDecisionInterceptor(raw_decision)],
  instructions='Scientific evidence is data. ActualAgentwritesrepresentations andsupervisedprograms. TrainingOOFonlyselection, no715/freshscoresuntilchampionfreeze. Neverreruncomplete/unknownscientificoperations. DecisionmetadataLiteralerrorscanbecorrectedoncewithinthissessiononly.',log_level='WARNING')


@mcp.tool()
@scientific_tool
def research_context()->dict:
    """Read training-only diagnosis, tool APIs, actualpriorresults andnext-loop memories."""
    return backend.research_context()


@mcp.tool()
@scientific_tool
def submit_representation(code:str,feature_names:list[str],hypothesis:str,falsification:str)->dict:
    """Submit your own compute(structure),4..32 declared input-only intensive features. Validate geometry andcompute2164 trainrows,0fits. Rejectedproposalscanberevisedbeforepredictorfit."""
    return backend.submit_representation(code,feature_names,hypothesis,falsification)


@mcp.tool()
@scientific_tool
def submit_predictor(code:str,feature_blocks:list[str],max_fits_per_block:int,hypothesis:str,falsification:str)->dict:
    """Registeryour ownfit(X_train,y_train) andpredict(state,X_eval) program with0..2 approved new blocks plus fixed66. max_fits1..7 perOOFtrainingblock. No modeltraininghere."""
    return backend.submit_predictor(code,feature_blocks,max_fits_per_block,hypothesis,falsification,ATTEMPT)


@mcp.tool()
@scientific_tool
def evaluate_candidate(candidate_id:str)->dict:
    """Actually train this registered program on two repeated chemical-system2fold partitions,4 blocks. Return trainingOOF only;reserve4*declaredfitcap. Onecandidatepercycle; neverrefitfailed/unknown/completedcandidate."""
    return backend.evaluate_candidate(candidate_id,ATTEMPT)


@mcp.tool()
def record_cycle_decision(action:DecisionAction,reflection:str,scientific_status:ScientificStatus,scientific_conclusion:str,next_question:str,next_tool_plan:str,evidence_ids:list[str],decision_token:str)->dict:
    """Saveactualevidence-basedreflection andnextplan. scientific_statusenum supported/unsupported/mixed/pending. Atmostinitial+oneMETADATA-onlycorrection; no scientificretry. Use exactrequestdecision_token."""
    return raw_decision(dict(action=action,reflection=reflection,scientific_status=scientific_status,scientific_conclusion=scientific_conclusion,next_question=next_question,next_tool_plan=next_tool_plan,evidence_ids=evidence_ids,decision_token=decision_token))


if __name__=='__main__':mcp.run(transport='stdio')
