"""Four new actual sessions; never resumes/replays the failed original session."""
from __future__ import annotations
import argparse,importlib.util,json,os,sys,time,uuid
from pathlib import Path
sys.dont_write_bytecode=True
SIDE=Path(__file__).resolve().parent;ROOT=SIDE.parent
sys.path.insert(0,str(SIDE));sys.path.insert(0,str(ROOT))
from guard import ContinuationGuard,ALLOWED_CANDIDATES,ALLOWED_ATTEMPTS,sha,load
import backend,controller

def extension_transport():
    spec=importlib.util.spec_from_file_location('registered_continuation_transport',SIDE/'session_transport.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def charge_usage(store,result,attempt,side,index,cid,relative,expected_sha):
    """Charge known actual transport usage before deciding success or failure."""
    s=store.state();s['counters']['uncached_input_tokens']+=result['uncached_input_tokens'];s['counters']['output_tokens']+=result['output_tokens'];store.dump(store.STATE,s)
    store.dump(side/f'usage_session_{index+1:02d}.json',{'manifest_sha256':expected_sha,'candidate_id':cid,'attempt':relative,'uncached_input_tokens':result['uncached_input_tokens'],'output_tokens':result['output_tokens'],'usage_complete':result['usage_complete'],'cumulative_uncached_input_tokens':s['counters']['uncached_input_tokens'],'cumulative_output_tokens':s['counters']['output_tokens'],'scientific_session_completed':result['completed'],'transport_result_sha256':sha(attempt/'transport_result.json')},exclusive=True)
    return s

def run(expected_sha):
    guard=ContinuationGuard(ROOT,expected_sha);guard.validate('driver_prelaunch');backend.assert_frozen()
    if (SIDE/'continuation_launch.json').exists():raise RuntimeError('Continuation already launched; no session retry')
    backend.dump(SIDE/'continuation_launch.json',{'schema_version':1,'started_utc':backend.now(),'manifest_sha256':expected_sha,'registry_sha256':sha(SIDE/'registry.json'),'execution_authorization_sha256':sha(SIDE/'execution_authorization.json'),'original_controller_launch_sha256':sha(ROOT/'controller_launch.json'),'original_controller_outcome_sha256':sha(ROOT/'controller_outcome.json'),'original_monotonic_start':load(ROOT/'controller_launch.json')['monotonic_start'],'planned_new_sessions':4,'quarantined_candidate':'C017','quarantined_evidence_id':'T0073','unknown_fit_charge':28,'no_scientific_retry':True},exclusive=True)
    os.environ['MATERIALS_CONTINUATION_MANIFEST_SHA256']=expected_sha
    transport=extension_transport();original_summary=backend.summary_context
    backend.summary_context=lambda:guard.scoped_context(original_summary())
    sessions=[];failure=None;completed_ids=[];last_guard=None
    try:
        for index,(cid,relative) in enumerate(zip(ALLOWED_CANDIDATES,ALLOWED_ATTEMPTS)):
            last_guard=guard.validate('session_pre:'+cid);s=backend.state();budget=load(ROOT/'protocol.json')['budget']
            attempt=ROOT/relative;attempt.mkdir(parents=True,exist_ok=False)
            request={'cycle_number':17+index,'phase':'prospective_accuracy_continuation','manifest_sha256':expected_sha,'expected_candidate_id':cid,'remaining_wall_seconds':budget['search_wall_seconds']-guard.elapsed(),'remaining_uncached_input_tokens':budget['uncached_input_tokens']-s['counters']['uncached_input_tokens'],'remaining_output_tokens':budget['output_tokens']-s['counters']['output_tokens'],'decision_token':uuid.uuid4().hex,'expected_fresh_science':'exactly one new '+cid+'; original registered two repeated partitions/four blocks','no_session_retry_after_scientific_activity':True,'quarantined_candidate':'C017','quarantined_call':'T0073','unknown_fit_capacity_charge':28}
            backend.dump(attempt/'session_request.json',request,exclusive=True)
            prompt=controller.task_prompt(request)+f'''\nREGISTERED PROSPECTIVE CONTINUATION: {expected_sha}\nThe original execution stopped after16 completed candidates in17 actual sessions. Original failed session/call T0073/C017 remains unresolved and is permanently quarantined: never evaluate it, retry it, select it, or count it as completed. It is retained verbatim as historical_quarantined_calls; the original global ledger fork is disclosed. Only this prospective new tail is audited consistent. Conservative28 unknown fits remain charged, no budget/wall reset. This session must author/evaluate exactly one wholly new programme/input candidate {cid} in {relative}, then save its actual evidence-based decision. Four new sessions C018-C021 seek total20 known completed/21 actual sessions; failed original17th remains failed. Existing structural interface blocker is unchanged: no claim of new approved structure blocks from future engineering repair. Any NEW unknown fit/call immediately stops all continuation; never retry.\n'''
            result=transport.run_one(ROOT,attempt,prompt,backend.summary_context,server_name='materials_accuracy',enabled_tools=controller.TOOLS,server_script=SIDE/'science_server_wrapper.py',model='gpt-6-astra',reasoning_effort='medium',session_wall_cap=1800,tool_timeout_seconds=1200)
            backend.dump(attempt/'transport_result.json',result,exclusive=True);sessions.append({'candidate_id':cid,'attempt':relative,**result})
            # Charge all actual reported usage even when the scientific session
            # fails; this is additive accounting, never an unknown-fit refund.
            s=charge_usage(backend,result,attempt,SIDE,index,cid,relative,expected_sha)
            if not result['usage_complete']:raise RuntimeError('Actual usage incomplete; stop without replay')
            if not result['completed'] or not result['scientific_activity_known'] or not result['decision_saved'] or result['experiments']!=1:raise RuntimeError('New actual session incomplete/unknown; no retry: '+str(result['failure_kind']))
            if s['experiments'].get(cid,{}).get('status')!='complete':raise RuntimeError('Expected new candidate did not complete')
            decision=load(attempt/'cycle_decision.json')
            if decision['action']!=('stop' if index==3 else 'continue'):raise RuntimeError('New cycle decision action mismatch')
            completed_ids.append(cid);last_guard=guard.validate('session_complete:'+cid)
            print(json.dumps({'phase':'prospective_candidate_complete','candidate_id':cid,'known_complete_candidates':s['counters']['experiments'],'new_actual_sessions':len(sessions),'total_actual_sessions':17+len(sessions),'known_fits_reserved':s['counters']['base_fits_reserved'],'unknown_fit_charge':28,'effective_fit_reservations':s['counters']['base_fits_reserved']+28,'input_tokens':s['counters']['uncached_input_tokens'],'output_tokens':s['counters']['output_tokens'],'elapsed_from_original_launch_seconds':guard.elapsed()},ensure_ascii=False),flush=True)
        if completed_ids!=ALLOWED_CANDIDATES or backend.state()['counters']['experiments']!=20:raise RuntimeError('Four new completed scientific candidates required')
        last_guard=guard.validate('continuation_success')
    except Exception as exc:
        failure=f'{type(exc).__name__}: {exc}'
    s=backend.state()
    guard_log=(SIDE/'guard_checks.jsonl').read_bytes()
    outcome={'schema_version':1,'completed':failure is None,'finished_utc':backend.now(),'manifest_sha256':expected_sha,'registry_sha256':sha(SIDE/'registry.json'),'new_actual_sessions':len(sessions),'new_normal_saved_decisions':sum(bool(r.get('completed') and r.get('decision_saved')) for r in sessions),'new_completed_candidate_ids':completed_ids,'total_actual_sessions':17+len(sessions),'total_normal_saved_decisions':16+sum(bool(r.get('completed') and r.get('decision_saved')) for r in sessions),'total_known_completed_candidates':s['counters']['experiments'],'known_fit_reservations':s['counters']['base_fits_reserved'],'known_fit_starts':s['counters']['fit_started'],'known_fit_completions':s['counters']['fit_completed'],'conservative_unknown_fit_charge':28,'effective_fit_reservations':s['counters']['base_fits_reserved']+28,'elapsed_from_original_launch_seconds':guard.elapsed(),'original_controller_outcome_preserved_failed':load(ROOT/'controller_outcome.json')['completed'] is False,'quarantined_candidate':'C017','quarantined_evidence_id':'T0073','quarantined_call_status':'started','unknown_scientific_retry_performed':False,'original_controller_outcome_sha256':sha(ROOT/'controller_outcome.json'),'guard_checks_sha256':sha(SIDE/'guard_checks.jsonl'),'guard_checks_prefix_bytes':len(guard_log),'guard_checks_prefix_lines':len(guard_log.splitlines()),'last_guard_receipt':last_guard,'failure':failure,'sessions':sessions,'counters':s['counters'],'fresh_labels_read':False,'metadata_write_retry_enabled':False,'selection_scope':'Same registered repeated training OOF only; explicit prospective isolation does not resolve original T0073 or add confirmation evidence.'}
    backend.dump(SIDE/'continuation_outcome.json',outcome,exclusive=True)
    if failure:raise RuntimeError(failure)
    return outcome

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest-sha',required=True)
    print(json.dumps(run(parser.parse_args().manifest_sha),ensure_ascii=False,allow_nan=False))
