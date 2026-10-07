"""Prospectively registered isolation of exactly one historical unknown call.

No scientific retry, historical status repair, or budget refund is implemented.
All authoritative records stay raw; only the compact actionable-context list is
scoped to the new four-session execution extension.
"""
from __future__ import annotations
import hashlib,json,os,time
from datetime import datetime,timezone
from pathlib import Path

EXTENSION_NAMES=('guard.py','science_server_wrapper.py','driver.py','session_transport.py')
ALLOWED_CANDIDATES=['C018','C019','C020','C021']
ALLOWED_ATTEMPTS=[f'cycles/cycle_{n:03d}/attempt_001' for n in range(17,21)]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def jsha(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def need(condition,message):
    if not condition:raise RuntimeError('Continuation isolation: '+message)

class ContinuationGuard:
    def __init__(self,root,expected_manifest_sha256,*,require_authorization=True,telemetry=True):
        self.root=Path(root).resolve();self.side=self.root/'prospective_continuation'
        self.expected_sha=expected_manifest_sha256
        need(isinstance(self.expected_sha,str) and len(self.expected_sha)==64,'explicit manifest SHA required')
        self.require_authorization=require_authorization;self.telemetry=telemetry

    def elapsed(self):
        launch=load(self.root/'controller_launch.json')
        monotonic=time.monotonic()-launch['monotonic_start']
        utc=(datetime.now(timezone.utc)-datetime.fromisoformat(launch['started_utc'])).total_seconds()
        need(monotonic>=0 and utc>=0,'original wall clock unavailable or reversed')
        return max(monotonic,utc)

    def registered(self):
        need(sha(self.side/'manifest.json')==self.expected_sha,'manifest changed')
        m=load(self.side/'manifest.json');registry=load(self.side/'registry.json')
        need(m.get('schema_version')==1,'manifest schema')
        need(registry.get('manifest_sha256')==self.expected_sha,'registry manifest binding')
        names={'prospective_continuation/'+n for n in EXTENSION_NAMES}
        need(set(m['extension_source_hashes'])==names,'exact four extension sources required')
        need(registry['extension_source_hashes']==m['extension_source_hashes'],'registry source binding')
        need(registry['engineering_receipt_hashes']==m['engineering_receipt_hashes'],'registry engineering binding')
        for p,h in {**m['extension_source_hashes'],**m['engineering_receipt_hashes']}.items():
            need(sha(self.root/p)==h,'extension or engineering receipt changed: '+p)
        need(sha(self.side/'boundary/boundary_capture.json')==m['boundary_capture_sha256'],'boundary capture changed')
        capture=load(self.side/'boundary/boundary_capture.json')
        for p,h in capture['snapshot_hashes'].items():need(sha(self.side/'boundary'/p)==h,'boundary snapshot changed: '+p)
        need(m['allowed_candidates']==ALLOWED_CANDIDATES and m['allowed_attempts']==ALLOWED_ATTEMPTS,'new scope changed')
        q=m['quarantine']
        need(q['candidate_id']=='C017' and q['evidence_id']=='T0073' and q['conservative_fit_charge']==28,'single quarantine changed')
        p=load(self.root/'protocol.json')
        need(sha(self.root/'protocol.json')==m['protocol_sha256'],'original protocol changed')
        need(m['source_hashes']==p['source_hashes'] and len(m['source_hashes'])==14,'original fourteen sources changed')
        need(m['budget']==p['budget'],'budget changed or reset')
        for f,h in m['source_hashes'].items():need(sha(self.root/f)==h,'frozen source changed: '+f)
        for f,h in capture['original_file_hashes'].items():need(sha(self.root/f)==h,'failed historical artifact changed: '+f)
        for field in ('historical_result_hashes','prior_completed_artifact_hashes'):
            for f,h in m.get(field,{}).items():need(sha(self.root/f)==h,'completed historical artifact changed: '+f)
        need(len([k for k in m.get('prior_completed_artifact_hashes',m.get('historical_result_hashes',{})) if k.endswith('/result.json')])==16,'sixteen historical result hashes required')
        for folder in ('cycles/cycle_016/attempt_001','candidates/C017','predictor_submissions/S020'):
            expected={k for k in capture['original_file_hashes'] if k.startswith(folder+'/')}
            actual={str(x.relative_to(self.root)).replace('\\','/') for x in (self.root/folder).rglob('*') if x.is_file()}
            need(actual==expected,'new artifact in quarantined historical folder: '+folder)
        if self.require_authorization:
            auth=load(self.side/'execution_authorization.json');review=load(self.side/'prelaunch_review.json')
            need(auth['manifest_sha256']==self.expected_sha and auth['registry_sha256']==sha(self.side/'registry.json') and auth['prelaunch_review_sha256']==sha(self.side/'prelaunch_review.json'),'independent execution authorization mismatch')
            need(review.get('status')=='PASS' and review.get('manifest_sha256')==self.expected_sha and review.get('extension_source_hashes')==m['extension_source_hashes'],'prelaunch independent review mismatch')
            need(review.get('scientific_fits_performed')==0 and review.get('actual_LLM_calls')==0 and review.get('fresh_labels_read') is False and review.get('isolated_new_science_gate') is True,'prelaunch review gate not passed')
        return m,capture

    def validate(self,stage='boundary',*,allow_current_call=None,attempt=None,evaluate_candidate=None,reservation=0):
        m,capture=self.registered();old=load(self.side/'boundary/research_state.json');old_server=load(self.side/'boundary/server_state.json')
        s=load(self.root/'state/research_state.json');server=load(self.root/'state/server_state.json')
        need(server['calls'][:len(old_server['calls'])]==old_server['calls'],'old authoritative call records changed')
        need(server['tool_calls']==len(server['calls']) and old_server['tool_calls']==76,'authoritative call accounting')
        for collection in ('baselines','proposals','experiments','representations'):
            need(all(s[collection].get(k)==v for k,v in old[collection].items()),'old '+collection+' entries changed')
        need(s['decisions'][:len(old['decisions'])]==old['decisions'],'old decisions changed')
        dynamic={'counters','active_operation','stop_reason','decisions','proposals','experiments','representations'}
        need(all(s.get(k)==v for k,v in old.items() if k not in dynamic),'immutable research state fields changed')
        need(all(s['counters'][k]>=v for k,v in old['counters'].items()),'historical counter refund/reset')
        need(not s['stop_reason'] and not s['active_operation'],'new science failed or remains active/unknown')
        need('C017' not in s['experiments'] and not (self.root/'experiments/C017').exists(),'C017 experiment/reservation/worker forbidden forever')
        for p in ('fresh_cohort/label_release_receipt.json','fresh_cohort/targets_after_freeze.csv.gz','final/champion_frozen.json'):
            need(not (self.root/p).exists(),'fresh labels/champion freeze reached during search')
        added_calls=server['calls'][len(old_server['calls']):]
        unknown=[c['evidence_id'] for c in added_calls if c['status']=='started']
        need(unknown==([] if allow_current_call is None else [allow_current_call]),'new unfinished call is not quarantined: '+str(unknown))
        if allow_current_call:
            need(added_calls and added_calls[-1]['evidence_id']==allow_current_call,'only current serialized call may be active')
        need(all(c['status'] in ('complete','failed','started') for c in added_calls),'invalid new tool status')
        new_props=set(s['proposals'])-set(old['proposals']);new_exp=set(s['experiments'])-set(old['experiments'])
        need(new_props<=set(ALLOWED_CANDIDATES) and new_exp<=set(ALLOWED_CANDIDATES),'unregistered new candidate')
        for cid in new_props:
            index=ALLOWED_CANDIDATES.index(cid)
            need(Path(s['proposals'][cid]['attempt']).resolve()==(self.root/ALLOWED_ATTEMPTS[index]).resolve(),'candidate assigned to wrong actual session')
        need(all(s['experiments'][k]['status']=='complete' for k in new_exp),'new experiment failed/unknown')
        need(s['counters']['experiments']==16+len(new_exp),'known candidate accounting')
        added_reserved=sum(s['experiments'][k]['reservation'] for k in new_exp)
        need(s['counters']['base_fits_reserved']==492+added_reserved,'reservation accounting changed')
        known_started=sum(s['experiments'][k]['summary']['actual_new_fits']['fit_started'] for k in new_exp)
        known_completed=sum(s['experiments'][k]['summary']['actual_new_fits']['fit_completed'] for k in new_exp)
        need(s['counters']['fit_started']==492+known_started and s['counters']['fit_completed']==492+known_completed,'actual fit accounting changed')
        for cid in new_exp:
            result=s['experiments'][cid]['summary']
            need(result['actual_new_fits']['fit_failed']==0 and result['actual_new_fits']['fit_started']==result['actual_new_fits']['fit_completed'],'new actual fit failed/unknown')
        if attempt is not None:
            relative=str(Path(attempt).resolve().relative_to(self.root)).replace('\\','/')
            need(relative in ALLOWED_ATTEMPTS,'only four new attempts allowed')
            if evaluate_candidate is not None:
                expected=ALLOWED_CANDIDATES[ALLOWED_ATTEMPTS.index(relative)]
                need(evaluate_candidate==expected and evaluate_candidate in new_props and evaluate_candidate not in s['experiments'],'no old/other/repeated evaluation')
        budget=m['budget'];effective=s['counters']['base_fits_reserved']+28
        need(effective+reservation+budget['final_fit_reservation']<=budget['base_fit_reservations'],'effective fit cap includes unknown28 and final reserve')
        need(s['counters']['uncached_input_tokens']<=budget['uncached_input_tokens'] and s['counters']['output_tokens']<=budget['output_tokens'] and server['tool_calls']<=budget['tool_calls'],'original token/tool cap reached')
        actual_new=sum((self.root/a/'invocation.json').exists() for a in ALLOWED_ATTEMPTS)
        need(17+actual_new<=budget['max_sessions'] and actual_new<=4,'actual session cap reached')
        elapsed=self.elapsed();need(elapsed<budget['search_wall_seconds'],'original search wall cap reached')
        ledger=(self.root/'state/server_ledger.jsonl').read_bytes();n=capture['original_ledger_prefix_bytes']
        need(len(ledger)>=n and hashlib.sha256(ledger[:n]).hexdigest()==capture['original_ledger_prefix_sha256'],'historical ledger byte prefix changed')
        prefix=ledger[:n].splitlines();need(len(prefix)==151,'historical ledger line prefix changed')
        tail=[json.loads(x) for x in ledger[n:].splitlines() if x.strip()]
        head=m['original']['durable_head_event_hash'];pending={};finished={}
        for event in tail:
            digest=event['event_hash'];payload={k:v for k,v in event.items() if k!='event_hash'}
            need(digest==jsha(payload) and event['previous_event_hash']==head,'new tail hash chain/fork mismatch')
            head=digest;eid=event['evidence_id']
            need(eid not in {c['evidence_id'] for c in old_server['calls']},'historical tool replay in new ledger')
            if event['event']=='tool_started':
                need(eid not in pending and eid not in finished,'duplicate new start');pending[eid]=event
            elif event['event']=='tool_finished':
                need(eid in pending and eid not in finished,'new finish without unique start');finished[eid]=event;pending.pop(eid)
            else:raise RuntimeError('Continuation isolation: unrecognized tail event')
        need(server['last_event_hash']==head,'new durable head inconsistent with append ledger')
        need(set(pending)==set(unknown),'new ledger unfinished calls disagree with authoritative state')
        need(set(finished)=={c['evidence_id'] for c in added_calls if c['status']!='started'},'new finished calls disagree with authoritative state')
        for c in added_calls:
            if c['status']!='started':
                e=finished[c['evidence_id']]
                need(e['status']==c['status'] and e['response_sha256']==c['response_sha256'] and jsha(e['response'])==c['response_sha256'],'new actual response hash mismatch')
        receipt={'status':'PASS','stage':stage,'utc':datetime.now(timezone.utc).isoformat(),'manifest_sha256':self.expected_sha,'actionable_incomplete_call_ids':unknown,'raw_historical_unknown_status':'started','historical_ledger_global_consistent':False,'prospective_tail_consistent':True,'effective_fit_reservations':effective,'conservative_unknown_fit_charge':28,'known_fit_reservations':s['counters']['base_fits_reserved'],'known_completed_candidates':s['counters']['experiments'],'raw_tail_head':head,'elapsed_from_original_launch_seconds':elapsed}
        if self.telemetry:
            with (self.side/'guard_checks.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(receipt,ensure_ascii=False,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
        return receipt

    def scoped_context(self,original,*,allow_current_call=None):
        """Preserve full raw historical unknown while scoping actionable failures."""
        self.validate('scoped_context',allow_current_call=allow_current_call)
        value=json.loads(json.dumps(original,ensure_ascii=False,allow_nan=False))
        raw=load(self.side/'boundary/server_state.json')
        call=next(c for c in raw['calls'] if c['evidence_id']=='T0073')
        need(call['status']=='started','raw T0073 must remain unknown')
        value['historical_quarantined_calls']={'T0073':call}
        value['incomplete_scientific_calls']=[x for x in value['incomplete_scientific_calls'] if x not in ('T0073',allow_current_call)]
        value['current_serialized_tool_call']=allow_current_call
        value['historical_ledger_global_consistent']=False
        value['ledger_consistent']=True  # Only after full new-tail validation above.
        value['ledger_consistency_scope']='Registered prospective tail after durable T0076 only; historical T0074/T0073 fork remains unchanged and globally inconsistent.'
        value['prospective_continuation']={'manifest_sha256':self.expected_sha,'quarantined_candidate':'C017','quarantined_evidence_id':'T0073','raw_status':'started','unknown_fit_charge':28,'forbidden_forever':'evaluate/retry/select/count C017','allowed_new_candidates':ALLOWED_CANDIDATES,'original_failed_session_retained':True,'actual_metadata_retry_enabled':False}
        available=value['candidate_fit_budget']['max_affordable_fits_per_training_block']
        budget=value['budget'];s=load(self.root/'state/research_state.json')
        later=max(0,20-s['counters']['experiments']-1)
        effective=max(0,min(budget['max_fits_per_block'],(budget['base_fit_reservations']-s['counters']['base_fits_reserved']-28-budget['final_fit_reservation']-4*later)//4))
        value['candidate_fit_budget']['max_affordable_fits_per_training_block']=min(available,effective)
        value['candidate_fit_budget']['conservative_unknown_capacity_charge']=28
        return value
