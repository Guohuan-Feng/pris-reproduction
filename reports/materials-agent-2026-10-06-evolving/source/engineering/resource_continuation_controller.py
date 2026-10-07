"""One registered input-token-only continuation after a natural settled cap stop.

No scientific module is imported by registration or boundary validation. Actual
continuation is an explicit separate command; it reuses the frozen controller
prompt/backend/server/transport without monkeypatching. Original files are never
replaced. An unknown session or scientific outcome consumes this one attempt.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_RELATIVE = 'reporting/resource_continuation_controller.py'
AMENDMENT = 'reporting/resource_amendment.json'
AMENDMENT_ANCHOR = 'reporting/resource_amendment.sha256'
LAUNCH = 'reporting/resource_continuation_launch.json'
OUTCOME = 'reporting/resource_continuation_outcome.json'
FAILURE = 'reporting/resource_continuation_failure.json'
SEARCH_RECEIPT = 'reporting/completed_search_receipt.json'
ACTIVATION_BOUNDARY = 'reporting/continuation_activation_boundary'
TOOLS = ['research_context','submit_representation','submit_predictor','evaluate_candidate','record_cycle_decision']
OLD_GLOBAL_INPUT = 800000
NEW_GLOBAL_INPUT = 1200000


class BoundaryError(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def jsha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def utc(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise BoundaryError('Timestamp must be timezone-aware')
    return parsed


def exclusive_bytes(path, raw):
    """Atomic exclusive publication; an existing launch/artifact never changes."""
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.parent/(path.name+'.pending_'+uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.link(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def exclusive(path, value):
    exclusive_bytes(path,(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8'))


def require(condition, reason):
    if not condition:
        raise BoundaryError(reason)


def integer(value, name):
    require(type(value) is int and value >= 0, 'Invalid nonnegative integer: '+name)
    return value


def frozen_sources(root, protocol):
    require(len(protocol['source_hashes']) == 13, 'Expected exactly thirteen frozen scientific sources')
    for relative, expected in protocol['source_hashes'].items():
        path = (root/relative).resolve()
        require(path.is_relative_to(root) and sha(path) == expected, 'Frozen scientific source binding differs: '+relative)


def no_final_started(root, state):
    require(not state.get('champion_frozen'), 'Champion already frozen')
    for relative in ('final/champion_frozen.json','final/reservation.json','final/prediction_receipt.json',
                     'final/result.json','fresh_cohort/label_release_receipt.json'):
        require(not (root/relative).exists(), 'Final freeze/prediction/release already started')


def create_amendment(root=DEFAULT_ROOT, *, draft=True):
    """Prepare a review draft, or exclusively register before the old cap is used."""
    root = Path(root).resolve()
    protocol = load(root/'protocol.json');carryover = load(root/'carryover.json')
    state_raw = (root/'state/research_state.json').read_bytes();state = json.loads(state_raw)
    frozen_sources(root,protocol);no_final_started(root,state)
    require(sha(root/'protocol.json') == state['protocol_sha256'], 'Original protocol anchor differs')
    prior = integer(carryover['counters']['uncached_input_tokens'],'prior input')
    require(prior == 23485 and protocol['budget']['uncached_input_tokens']+prior == OLD_GLOBAL_INPUT,
            'Original input-budget/carryover arithmetic differs')
    require(state['counters']['uncached_input_tokens'] < protocol['budget']['uncached_input_tokens'],
            'Amendment must be registered before initial input cap is exhausted')
    require(not (root/LAUNCH).exists() and not (root/OUTCOME).exists(), 'Continuation already attempted')
    unchanged_global = {'base_fit_reservations':256,'output_tokens':120000,'tool_calls':180,
                        'search_wall_seconds':7200,'wall_seconds':10800,'completed_candidates':20}
    inherited = {'base_fit_reservations':carryover['counters']['base_fits_reserved'],
                 'output_tokens':carryover['counters']['output_tokens'],'tool_calls':carryover['actual_tools'],
                 'search_wall_seconds':carryover['scientific_elapsed_seconds'],
                 'wall_seconds':carryover['scientific_elapsed_seconds'],'completed_candidates':0}
    require(all(math.isclose(protocol['budget'][key]+inherited[key],limit,rel_tol=0,abs_tol=1e-7)
                for key,limit in unchanged_global.items()), 'Other registered global resource caps differ')
    snapshot_relative = 'reporting/resource_registration_snapshot'+('.draft' if draft else '')+'.json'
    amendment = {'schema_version':1,'status':'review_draft' if draft else 'registered_before_initial_input_cap',
        'registered_utc':now(),'reason':'Honor the requested twenty substantive Agent experiments; input allowance was an internal compute budget.',
        'original_protocol_sha256':sha(root/'protocol.json'),'original_scientific_source_hashes':protocol['source_hashes'],
        'continuation_source_path':SOURCE_RELATIVE,'continuation_source_sha256':sha(root/SOURCE_RELATIVE),
        'registration_snapshot_path':snapshot_relative,'registration_snapshot_sha256':hashlib.sha256(state_raw).hexdigest(),
        'registration_counters':state['counters'],'original_global_uncached_input_cap':OLD_GLOBAL_INPUT,
        'amended_global_uncached_input_cap':NEW_GLOBAL_INPUT,'prior_failed_stage_uncached_input_tokens':prior,
        'original_phase_uncached_input_cap':protocol['budget']['uncached_input_tokens'],
        'amended_phase_uncached_input_cap':NEW_GLOBAL_INPUT-prior,
        'only_changed_resource':'uncached_input_tokens','unchanged_global_resource_caps':unchanged_global,
        'unchanged_phase_budget_except_input':{k:v for k,v in protocol['budget'].items() if k!='uncached_input_tokens'},
        'original_launch_path':'controller_launch.json','clock_rule':'Continue original monotonic_start; no timer reset or subtraction of maintenance/review wait.',
        'activation_rule':'Only original natural input-token-only cap failure at a complete settled boundary; at20 completed, no new session.',
        'scientific_semantics_unchanged':['Twenty candidates','same2164 chemical-system twofold OOF','same data/source/input manifest',
             'same representation/predictor API and atomic fit caps','same OOF-only selection and tie break','same known715/fresh1000 boundary',
             'same save-predictions-before-release','same three gates/bootstrap','all negative outcomes retained','no scientific retry'],
        'context_disclosure':'Original summary_context budget remains historical; the explicit prompt notice supersedes only its input-token allowance.'}
    destination = root/('reporting/resource_amendment.draft.json' if draft else AMENDMENT)
    require(not destination.exists() and not (root/snapshot_relative).exists(), 'Amendment registration/draft already exists')
    exclusive_bytes(root/snapshot_relative,state_raw)
    exclusive(destination,amendment)
    if not draft:
        exclusive_bytes(root/AMENDMENT_ANCHOR,(sha(destination)+'\n').encode('ascii'))
    return {'status':amendment['status'],'amendment_path':str(destination.relative_to(root)),
            'amendment_sha256':sha(destination),'continuation_source_sha256':amendment['continuation_source_sha256']}


def verify_amendment(root):
    root = Path(root).resolve();amendment = load(root/AMENDMENT);protocol = load(root/'protocol.json')
    require((root/AMENDMENT_ANCHOR).read_text(encoding='ascii').strip() == sha(root/AMENDMENT), 'Registered amendment anchor differs')
    require(amendment['status']=='registered_before_initial_input_cap', 'Only an exclusively registered amendment can be used')
    require(amendment['continuation_source_path']==SOURCE_RELATIVE and sha(root/SOURCE_RELATIVE)==amendment['continuation_source_sha256'],
            'Continuation code changed after registration')
    require(sha(root/'protocol.json')==amendment['original_protocol_sha256'], 'Original protocol changed')
    require(protocol['source_hashes']==amendment['original_scientific_source_hashes'], 'Original source list changed')
    frozen_sources(root,protocol)
    require(amendment['only_changed_resource']=='uncached_input_tokens' and amendment['original_global_uncached_input_cap']==OLD_GLOBAL_INPUT
            and amendment['amended_global_uncached_input_cap']==NEW_GLOBAL_INPUT, 'Amendment changed an unauthorized resource')
    prior = load(root/'carryover.json')['counters']['uncached_input_tokens']
    require(prior==23485==amendment['prior_failed_stage_uncached_input_tokens'], 'Prior input charge differs')
    require(amendment['original_phase_uncached_input_cap']==protocol['budget']['uncached_input_tokens']==OLD_GLOBAL_INPUT-prior
            and amendment['amended_phase_uncached_input_cap']==NEW_GLOBAL_INPUT-prior, 'Amended input arithmetic differs')
    require(amendment['unchanged_phase_budget_except_input']=={k:v for k,v in protocol['budget'].items() if k!='uncached_input_tokens'},
            'A resource other than input tokens changed')
    snapshot_path = (root/amendment['registration_snapshot_path']).resolve()
    require(snapshot_path.is_relative_to(root/'reporting') and sha(snapshot_path)==amendment['registration_snapshot_sha256'],
            'Pre-cap registration snapshot differs')
    registered = load(snapshot_path)
    require(registered['counters']==amendment['registration_counters'] and registered['protocol_sha256']==sha(root/'protocol.json')
            and registered['counters']['uncached_input_tokens']<protocol['budget']['uncached_input_tokens'], 'Registration was not before cap exhaustion')
    no_final_started(root,registered)
    return amendment,protocol


def cli_alive(process, invocation):
    """Read-only PID liveness; reuse after the old finished time is not its CLI."""
    pid = integer(process['pid'],'CLI pid');require(pid>0,'Invalid CLI PID')
    if os.name != 'nt':
        try:os.kill(pid,0)
        except ProcessLookupError:return False
        except PermissionError:raise BoundaryError('Unable to establish CLI quiescence')
        return True
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)];kernel.GetExitCodeProcess.restype=wintypes.BOOL
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4;kernel.GetProcessTimes.restype=wintypes.BOOL
    handle = kernel.OpenProcess(0x1000,False,pid)
    if not handle:
        require(ctypes.get_last_error()==87,'Unable to establish CLI quiescence')
        return False
    try:
        code = wintypes.DWORD()
        require(bool(kernel.GetExitCodeProcess(handle,ctypes.byref(code))),'Unable to read CLI exit status')
        if code.value != 259:return False
        creation,exit_time,kernel_time,user_time = (wintypes.FILETIME() for _ in range(4))
        require(bool(kernel.GetProcessTimes(handle,*[ctypes.byref(x) for x in (creation,exit_time,kernel_time,user_time)])),
                'Unable to distinguish an active CLI from reused PID')
        ticks=(creation.dwHighDateTime<<32)|creation.dwLowDateTime
        created=datetime.fromtimestamp((ticks-116444736000000000)/10000000,timezone.utc)
        return created <= utc(invocation['finished_utc'])
    finally:kernel.CloseHandle(handle)


def settled_boundary(root, *, process_checker=cli_alive):
    """Require all existing sessions/candidates/decisions/billing to be settled."""
    root = Path(root).resolve();state=load(root/'state/research_state.json');server=load(root/'state/server_state.json')
    no_final_started(root,state)
    require(state.get('active_operation') is None and state.get('stop_reason') is None, 'Active/stopped/unknown scientific state')
    n=integer(state['counters']['experiments'],'completed experiments')
    require(1<=n<=20 and len(state['experiments'])==n and all(entry['status']=='complete' for entry in state['experiments'].values()),
            'Every prior candidate must be complete, without failed/unknown science')
    require(len(state['proposals'])==n and set(state['proposals'])==set(state['experiments']), 'Unsettled registered predictor exists')
    calls=server['calls'];require(server['tool_calls']==len(calls)==state['counters']['tool_calls'], 'Server/science tool counter mismatch')
    require(all(row['status']=='complete' and row['tool'] in TOOLS for row in calls), 'Failed/unknown/uncompleted server call exists')
    ledger=lines(root/'state/server_ledger.jsonl');previous=None;started={};finished={}
    for event in ledger:
        require(event['previous_event_hash']==previous and event['event_hash']==jsha({k:v for k,v in event.items() if k!='event_hash'}),
                'Server ledger hash chain differs')
        previous=event['event_hash'];eid=event['evidence_id']
        target=started if event['event']=='tool_started' else finished if event['event']=='tool_finished' else None
        require(target is not None and eid not in target,'Unknown/repeated ledger event')
        target[eid]=event
    require(previous==server['last_event_hash'] and set(started)==set(finished)=={row['evidence_id'] for row in calls}, 'Unsettled server ledger')
    for row in calls:
        event=finished[row['evidence_id']]
        require(all(event.get(k)==v for k,v in row.items()) and event['response_sha256']==jsha(event['response']), 'Actual server response binding differs')
    attempts=sorted((root/'cycles').glob('cycle_*/attempt_*'))
    expected=[root/'cycles'/f'cycle_{i:03d}'/'attempt_001' for i in range(n)]
    require(attempts==expected and sorted((root/'cycles').glob('cycle_*'))==[p.parent for p in expected], 'Unexpected/gapped/existing extra cycle directory')
    totals={'uncached_input_tokens':0,'output_tokens':0};decisions=[];transport_hashes={};last_finished=None
    for i,attempt in enumerate(attempts):
        result=load(attempt/'transport_result.json');invocation=load(attempt/'invocation.json');request=load(attempt/'session_request.json')
        decision=load(attempt/'cycle_decision.json');audit=invocation['audit']
        require(result==invocation['result'] and invocation['completed'] is True and invocation['returncode']==0
                and invocation['timeout'] is False and bool(invocation.get('finished_utc')), 'CLI/transport has not normally finished')
        require(all(result.get(k) is True for k in ('completed','usage_complete','scientific_activity_known','cli_turn_completed','decision_saved','no_session_retry'))
                and result['experiments']==1 and result.get('failure_kind') is None and result.get('transport_error') is None
                and result.get('reconciliation_error') is None, 'Unsettled/failed transport or missing actual candidate')
        require(not process_checker(load(attempt/'process.json'),invocation), 'An original CLI remains active')
        require(audit['completed_events']==1 and not any(audit[k] for k in ('errors','foreign_tools','malformed_lines','invalid_usage')),
                'CLI audit is not complete and valid')
        for key in totals:
            value=integer(result[key],key);require(audit[key]==value, 'Token usage not reconciled with CLI audit');totals[key]+=value
        scoped=[row for row in calls if Path(row['attempt']).resolve()==attempt.resolve()]
        require(len(scoped)==result['research_tool_calls']==audit['tool_event_count'], 'Actual session tool count differs')
        scientific=[row for row in scoped if row['tool']=='evaluate_candidate']
        require(len(scientific)==1 and scientific[0]['evidence_id'] in decision['evidence_ids'], 'Decision lacks fresh actual candidate evidence')
        require(request['cycle_number']==i and decision['decision_token']==request['decision_token'] and decision['scientific_status'] in
                {'supported','unsupported','mixed','pending'} and decision['action']==('stop' if i==19 else 'continue'), 'Invalid cycle decision settlement')
        metadata=lines(attempt/'decision_metadata_attempts.jsonl')
        require(not any(event['event']=='metadata_unknown' for event in metadata), 'Unknown decision persistence')
        starts=[event['metadata_attempt'] for event in metadata if event['event']=='metadata_attempt_started']
        terminals={event['metadata_attempt'] for event in metadata if event['event'] in {'metadata_validation_failed','metadata_saved'}}
        require(1<=len(starts)<=2 and set(starts)<=terminals and sum(event['event']=='metadata_saved' for event in metadata)==1,
                'Decision metadata attempts not normally settled')
        require(invocation['before_counters']['experiments']==i and invocation['after_counters']['experiments']==i+1, 'Session experiment increment differs')
        decisions.append(decision);last_finished=invocation['finished_utc']
        transport_hashes[str((attempt/'transport_result.json').relative_to(root)).replace('\\','/')]=sha(attempt/'transport_result.json')
    require(decisions==state['decisions'] and all(totals[k]==state['counters'][k] for k in totals), 'State decisions or billing are not fully settled')
    fits_started=[];fits_completed=[]
    for cid,entry in state['experiments'].items():
        result=load(root/'experiments'/cid/'result.json')
        require(result['candidate_id']==cid and result['fresh_targets_accessed'] is False, 'Candidate result scope differs')
        events=lines(root/'experiments'/cid/'fit_events_live.jsonl')
        require(all(event['phase'] in {'started','completed'} for event in events), 'Failed/unknown scientific fit journal')
        fits_started.extend(event['fit_id'] for event in events if event['phase']=='started')
        fits_completed.extend(event['fit_id'] for event in events if event['phase']=='completed')
    require(len(set(fits_started))==len(fits_started) and sorted(fits_started)==sorted(fits_completed)
            and len(fits_started)==state['counters']['fit_started']==state['counters']['fit_completed'], 'Unsettled scientific fits')
    return {'completed_candidates':n,'state':state,'server':server,'transport_hashes':transport_hashes,
            'last_session_finished_utc':last_finished,'actual_Agent_sessions':len(attempts),'normal_saved_decisions':len(decisions)}


def token_stop_boundary(root, *, process_checker=cli_alive, monotonic_clock=time.monotonic):
    amendment,protocol=verify_amendment(root)
    outcome=load(root/'controller_outcome.json');launch=load(root/'controller_launch.json')
    if outcome.get('completed') is True:
        require(outcome['counters']['experiments']==20 and outcome['counters']['uncached_input_tokens']<=protocol['budget']['uncached_input_tokens'],
                'Original success record is not within its initial budget')
        return {'unused':True,'reason':'Original controller already completed20 within initial allowance'}
    failure=load(root/'controller_failure.json')
    boundary=settled_boundary(root,process_checker=process_checker);state=boundary['state'];budget=protocol['budget']
    require(outcome['counters']==failure['counters']==state['counters'] and outcome['actual_Agent_sessions']==boundary['actual_Agent_sessions']
            and outcome['normal_saved_decisions']==boundary['normal_saved_decisions'], 'Original cap-stop outcome/counters are not settled')
    error=outcome.get('failure');require(error==failure['error'], 'Original failure record differs')
    precheck=error=='RuntimeError: Declaredscientificresourcecap reached'
    postcheck=error=='RuntimeError: Actualtokenusage exceededcap; stopanddisclose'
    require(precheck or postcheck,'Original controller did not naturally stop solely at its token cap')
    tokens=state['counters']['uncached_input_tokens']
    require(tokens>=budget['uncached_input_tokens'] if precheck else tokens>budget['uncached_input_tokens'], 'No initial input-token cap exhaustion')
    require(state['counters']['output_tokens']<budget['output_tokens'] and state['counters']['tool_calls']<budget['tool_calls']
            and outcome['elapsed_seconds']<budget['search_wall_seconds'], 'More than input tokens caused the natural stop')
    require(utc(amendment['registered_utc'])<utc(outcome['finished_utc']), 'Amendment was registered after the natural stop')
    elapsed=monotonic_clock()-launch['monotonic_start']
    require(0<=elapsed<budget['search_wall_seconds'], 'Original search clock is exhausted or invalid; never reset it')
    require(tokens<=amendment['amended_phase_uncached_input_cap'], 'New input allowance already exceeded')
    require(boundary['completed_candidates']<=budget['max_sessions'], 'Original session ceiling exhausted')
    return {**boundary,'unused':False,'amendment':amendment,'protocol':protocol,'original_elapsed_seconds':elapsed}


def prompt_notice(amendment, amendment_sha):
    return ('\n\nTransparent preregistered compute-only amendment '+amendment_sha+': The original controller naturally stopped at its '
            'uncached-input-token allowance after fully settled completed experiments. Only global uncached input is increased from800000 '
            'to1200000 (this phase1176515 after prior23485). The historical budget in research_context remains the original registration; '
            'this notice supersedes ONLY that input allowance. All scientific data, folds, APIs, fit/output/tool/wall limits,20 candidates, '
            'selection, gates and sealed fresh-label protocol stay unchanged. Continue the next new candidate; never rerun prior scientific work.\n')


def original_exit_confirmation(root, evidence_path):
    """Require the parent's explicit record of its observed original exec exit.

    This is a parent observation binding, not a claim that metadata alone proves
    OS quiescence. The parent must first poll its original exec to completion.
    """
    require(evidence_path is not None,'Explicit original-controller exit evidence is required; parent must observe natural exec completion first')
    path=Path(evidence_path).resolve();require(path.is_relative_to(root/'reporting'),'Exit evidence must be a run-local reporting artifact')
    evidence=load(path)
    require(evidence.get('source')=='parent_exec_completed' and evidence.get('natural_exit_confirmed') is True
            and evidence.get('termination_performed') is False,'Parent has not explicitly confirmed the original natural exec exit')
    require(type(evidence.get('exec_session_id')) is int and evidence['exec_session_id']>0
            and type(evidence.get('exec_exit_code')) is int and evidence['exec_exit_code']!=0,'Original failed controller exec completion evidence is invalid')
    for key,relative in (('original_controller_launch_sha256','controller_launch.json'),
                         ('original_controller_outcome_sha256','controller_outcome.json'),
                         ('original_controller_failure_sha256','controller_failure.json')):
        require(evidence.get(key)==sha(root/relative),'Original exec observation artifact binding differs')
    require(utc(evidence['observed_utc'])>=utc(load(root/'controller_outcome.json')['finished_utc']),
            'Parent exit observation predates the natural controller outcome')
    return str(path.relative_to(root)).replace('\\','/'),sha(path)


def run_continuation(root=DEFAULT_ROOT, *, runner=None, backend_module=None, controller_module=None,
                     process_checker=cli_alive, monotonic_clock=time.monotonic, original_exit_evidence=None):
    root=Path(root).resolve()
    require(not any((root/relative).exists() for relative in (LAUNCH,OUTCOME,FAILURE,SEARCH_RECEIPT,ACTIVATION_BOUNDARY)), 'This one continuation was already attempted')
    initial=token_stop_boundary(root,process_checker=process_checker,monotonic_clock=monotonic_clock)
    if initial['unused']:return initial
    exit_relative,exit_sha=original_exit_confirmation(root,original_exit_evidence)
    amendment,protocol=initial['amendment'],initial['protocol'];budget=protocol['budget'];start_index=initial['completed_candidates']
    original_launch=load(root/'controller_launch.json');clock_start=original_launch['monotonic_start']
    boundary_raw={name:(root/relative).read_bytes() for name,relative in
         (('state.json','state/research_state.json'),('server_state.json','state/server_state.json'),('server_ledger.jsonl','state/server_ledger.jsonl'))}
    require(json.loads(boundary_raw['state.json'])['counters']==initial['state']['counters']
            and json.loads(boundary_raw['server_state.json'])==initial['server'],'Activation boundary changed before capture')
    boundary_bindings={}
    for name,raw in boundary_raw.items():
        relative=ACTIVATION_BOUNDARY+'/'+name;exclusive_bytes(root/relative,raw);boundary_bindings[relative]=sha(root/relative)
    exclusive(root/LAUNCH,{'started_utc':now(),'executed':start_index<20,'amendment_sha256':sha(root/AMENDMENT),
        'continuation_source_sha256':sha(root/SOURCE_RELATIVE),'original_controller_launch_sha256':sha(root/'controller_launch.json'),
        'original_controller_outcome_sha256':sha(root/'controller_outcome.json'),
        'original_controller_failure_sha256':sha(root/'controller_failure.json'),'start_cycle_index':start_index,
        'activation_boundary_snapshot_hashes':boundary_bindings,'activation_completed_candidates':start_index,
        'activation_counters':initial['state']['counters'],'activation_decision_prefix_sha256':jsha(initial['state']['decisions']),
        'activation_last_decision_sha256':jsha(initial['state']['decisions'][-1]),
        'activation_transport_prefix_hashes':initial['transport_hashes'],'activation_last_session_finished_utc':initial['last_session_finished_utc'],
        'original_controller_exit_evidence_path':exit_relative,'original_controller_exit_evidence_sha256':exit_sha,
        'original_controller_quiescence_basis':'Parent explicitly observed original exec completion; no process termination performed.',
        'original_monotonic_start':clock_start,'original_elapsed_seconds_at_activation':monotonic_clock()-clock_start,
        'no_clock_reset':True,'no_session_retry':True})
    sessions=[];error=None
    try:
        if start_index<20:
            if backend_module is None or controller_module is None or runner is None:
                sys.path.insert(0,str(root));sys.dont_write_bytecode=True
                backend_module=backend_module or importlib.import_module('backend')
                controller_module=controller_module or importlib.import_module('controller')
                runner=runner or importlib.import_module('session_transport').run_one
            require(Path(backend_module.ROOT).resolve()==root and Path(controller_module.ROOT).resolve()==root,
                    'Frozen backend/controller root differs')
            for cycle in range(start_index,budget['max_sessions']):
                verify_amendment(root);backend_module.assert_frozen()
                boundary=settled_boundary(root,process_checker=process_checker);state=boundary['state']
                if state['counters']['experiments']==20:break
                elapsed=monotonic_clock()-clock_start
                require(elapsed<budget['search_wall_seconds'] and state['counters']['uncached_input_tokens']<amendment['amended_phase_uncached_input_cap']
                        and state['counters']['output_tokens']<budget['output_tokens'] and state['counters']['tool_calls']<budget['tool_calls'],
                        'Registered continuation resource cap reached')
                attempt=root/'cycles'/f'cycle_{cycle:03d}'/'attempt_001'
                attempt.mkdir(parents=True,exist_ok=False)
                request={'cycle_number':cycle,'phase':'evolving_candidate','remaining_wall_seconds':budget['search_wall_seconds']-elapsed,
                    'remaining_uncached_input_tokens':amendment['amended_phase_uncached_input_cap']-state['counters']['uncached_input_tokens'],
                    'remaining_output_tokens':budget['output_tokens']-state['counters']['output_tokens'],'decision_token':uuid.uuid4().hex,
                    'expected_fresh_science':'one new candidate twofold trainingOOF','no_session_retry_after_scientific_activity':True,
                    'resource_amendment_sha256':sha(root/AMENDMENT),'continuation_launch_sha256':sha(root/LAUNCH)}
                exclusive(attempt/'session_request.json',request)
                prompt=controller_module.task_prompt(request)+prompt_notice(amendment,sha(root/AMENDMENT))
                result=runner(root,attempt,prompt,backend_module.summary_context,server_name='materials_evolving',enabled_tools=TOOLS,
                    server_script=root/'science_server.py',model='gpt-6-astra',reasoning_effort='medium',session_wall_cap=1800,tool_timeout_seconds=1200)
                exclusive(attempt/'transport_result.json',result);sessions.append(result)
                state=backend_module.state()
                state['counters']['uncached_input_tokens']+=integer(result['uncached_input_tokens'],'session input')
                state['counters']['output_tokens']+=integer(result['output_tokens'],'session output')
                backend_module.dump(backend_module.STATE,state)
                require(result['completed'] is True and result['experiments']==1, 'Actual continuation session did not complete one candidate; no retry')
                require(state['counters']['uncached_input_tokens']<=amendment['amended_phase_uncached_input_cap']
                        and state['counters']['output_tokens']<=budget['output_tokens'], 'Actual continuation tokens exceeded registered allowance')
                require(monotonic_clock()-clock_start<=budget['search_wall_seconds'], 'Original search wall cap exceeded')
        verify_amendment(root)
        complete=settled_boundary(root,process_checker=process_checker)
        require(complete['completed_candidates']==20,'Continuation ended before20 completed candidates')
        require(monotonic_clock()-clock_start<=budget['search_wall_seconds'],'Original search wall cap exceeded')
    except Exception as exc:
        error=f'{type(exc).__name__}: {exc}'
        exclusive(root/FAILURE,{'utc':now(),'error':error,'amendment_sha256':sha(root/AMENDMENT),
            'counters':load(root/'state/research_state.json')['counters'],'no_scientific_retry':True,'no_continuation_retry':True})
    outcome={'completed':error is None,'executed':start_index<20,'finished_utc':now(),'failure':error,
        'amendment_sha256':sha(root/AMENDMENT),'actual_Agent_sessions':len(sessions),
        'normal_saved_decisions':sum(result.get('decision_saved') is True for result in sessions),
        'total_actual_Agent_sessions':sum((attempt/'invocation.json').exists() for attempt in (root/'cycles').glob('cycle_*/attempt_*')),
        'counters':load(root/'state/research_state.json')['counters'],
        'elapsed_seconds_from_original_launch':monotonic_clock()-clock_start,'original_monotonic_start':clock_start,
        'no_scientific_retry':True,'no_continuation_retry':True,'initial_input_budget_was_exceeded':True}
    exclusive(root/OUTCOME,outcome)
    if error:raise BoundaryError(error)
    state_raw=(root/'state/research_state.json').read_bytes()
    exclusive_bytes(root/'reporting/completed_search_state.json',state_raw)
    bindings={relative:sha(root/relative) for relative in ('controller_launch.json','controller_outcome.json','controller_failure.json',
              AMENDMENT,LAUNCH,OUTCOME,SOURCE_RELATIVE,'reporting/completed_search_state.json')}
    bindings.update(complete['transport_hashes'])
    bindings.update(boundary_bindings);bindings[exit_relative]=exit_sha
    receipt={'schema_version':1,'status':'twenty_completed_under_registered_input_amendment','created_utc':now(),
        'bindings':bindings,'original_protocol_sha256':sha(root/'protocol.json'),'original_scientific_source_hashes':protocol['source_hashes'],
        'counters':outcome['counters'],'total_actual_Agent_sessions':complete['actual_Agent_sessions'],
        'normal_saved_decisions':complete['normal_saved_decisions'],'last_session_finished_utc':complete['last_session_finished_utc'],
        'search_finished_utc':outcome['finished_utc'],'elapsed_seconds_from_original_launch':outcome['elapsed_seconds_from_original_launch'],
        'original_monotonic_start':clock_start,'original_global_uncached_input_cap':OLD_GLOBAL_INPUT,
        'amended_global_uncached_input_cap':NEW_GLOBAL_INPUT,'amended_phase_uncached_input_cap':amendment['amended_phase_uncached_input_cap'],
        'extra_actual_Agent_sessions':len(sessions),'fresh_labels_accessed':False,'finalization_performed':False}
    exclusive(root/SEARCH_RECEIPT,receipt)
    return outcome


def completed_search_guard(root=DEFAULT_ROOT, *, process_checker=cli_alive):
    """Read-only gate for the parent to invoke BEFORE the unchanged finalizer."""
    root=Path(root).resolve();amendment,protocol=verify_amendment(root);receipt=load(root/SEARCH_RECEIPT)
    require(receipt['status']=='twenty_completed_under_registered_input_amendment','No amended completed-search receipt')
    for relative,expected in receipt['bindings'].items():
        path=(root/relative).resolve();require(path.is_relative_to(root) and sha(path)==expected,'Completed-search binding differs: '+relative)
    require(receipt['original_protocol_sha256']==sha(root/'protocol.json') and receipt['original_scientific_source_hashes']==protocol['source_hashes'],
            'Completed search protocol/source anchor differs')
    boundary=settled_boundary(root,process_checker=process_checker);outcome=load(root/OUTCOME)
    require(outcome['completed'] is True and boundary['completed_candidates']==20 and receipt['normal_saved_decisions']==20
            and receipt['total_actual_Agent_sessions']==20 and receipt['counters']==outcome['counters']==boundary['state']['counters'],
            'Twenty-candidate completed-search settlement differs')
    require(receipt['elapsed_seconds_from_original_launch']<=protocol['budget']['search_wall_seconds'] and receipt['original_monotonic_start']==
            load(root/'controller_launch.json')['monotonic_start'], 'Search timing was reset or exceeded')
    require(receipt['counters']['uncached_input_tokens']<=amendment['amended_phase_uncached_input_cap'] and receipt['fresh_labels_accessed'] is False,
            'Amended input/fresh boundary differs')
    return {'ready_for_unchanged_finalizer':True,'completed_search_receipt_sha256':sha(root/SEARCH_RECEIPT),'completed_candidates':20}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    parser.add_argument('--original-controller-exit-evidence',type=Path)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare-draft',action='store_true')
    mode.add_argument('--register-only',action='store_true')
    mode.add_argument('--continue-after-natural-token-stop',action='store_true')
    mode.add_argument('--verify-completed-search',action='store_true')
    args=parser.parse_args()
    if args.prepare_draft:result=create_amendment(args.root,draft=True)
    elif args.register_only:result=create_amendment(args.root,draft=False)
    elif args.verify_completed_search:result=completed_search_guard(args.root)
    else:result=run_continuation(args.root,original_exit_evidence=args.original_controller_exit_evidence)
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))
