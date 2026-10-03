"""Reconcile a consumed but unrecorded infrastructure failure from original logs.

No search continuation or candidate/result changes. Original state is preserved.
"""
from pathlib import Path
import datetime as dt
import hashlib
import json

ROOT=Path(__file__).resolve().parent/'scientific_tc_2026-10-02'
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,o):p.write_text(json.dumps(o,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def main():
    invocation=ROOT/'agent/invocation.json'
    if (ROOT/'agent/recovered/invocation.json').exists():invocation=ROOT/'agent/recovered/invocation.json'
    if not load(invocation)['completed']:raise RuntimeError('Administrative reconciliation only after completed Agent session')
    if (ROOT/'selection.json').exists():raise RuntimeError('Already frozen; no record changes')
    p=ROOT/'agent/state.json';state=load(p)
    events=[json.loads(x) for x in (ROOT/'agent/tool_events.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    attempts=[x for x in events if x['tool']=='run_strategy']
    if len(attempts)!=state['strategy_attempts']:raise RuntimeError('Attempt counter/journal mismatch')
    missing=[];existing={x['id'] for x in state['strategies']}
    for index,event in enumerate(attempts,1):
        cid=f'A{index:02d}'
        if cid in existing:continue
        if event['status']!='error' or (ROOT/f'candidates/{cid}/result.json').exists():raise RuntimeError('Cannot reconstruct anything except logged failure before result')
        args=event['arguments']
        if not isinstance(args,dict):raise RuntimeError('Expected original structured arguments')
        error=event['response']['tool_result']['error']
        missing.append((cid,event,args,error))
    if not missing:print('No missing attempt records');return
    original=ROOT/'agent/state.original_before_reconciliation.json'
    if original.exists():raise RuntimeError('Reconciliation may only run once')
    original.write_bytes(p.read_bytes())
    for cid,event,args,error in missing:
        state['strategies'].append({'id':cid,'name':args['name'],'status':'failed','error':error,'administrative_reconstruction':True,'source_tool_event_number':event['number'],'no_model_fit':'failure before specification/fit, as recorded in tool journal'})
        save(ROOT/f'agent/{cid}_scientific_metadata.json',{'candidate_id':cid,**args,'started_utc':event['started_utc'],'finished_utc':event['finished_utc'],'status':'failed','error':error,'administrative_reconstruction':True,'source_tool_event_number':event['number']})
    state['strategies'].sort(key=lambda x:x['id']);save(p,state)
    save(ROOT/'agent/attempt_record_reconciliation.json',{'at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'purpose':'Complete factual attempt inventory after an infrastructure error interrupted state persistence. Search budget, successful specifications, numerical results, and original tool events unchanged. No new scientific session.','original_state_sha256':sha(original),'reconciled_state_sha256':sha(p),'tool_events_sha256':sha(ROOT/'agent/tool_events.jsonl'),'reconstructed_attempts':[{'id':cid,'source_tool_event_number':event['number'],'error':error} for cid,event,args,error in missing]})
    print(json.dumps({'reconciled_attempts':[x[0] for x in missing],'unchanged_attempt_count':state['strategy_attempts']},ensure_ascii=True))
if __name__=='__main__':main()
