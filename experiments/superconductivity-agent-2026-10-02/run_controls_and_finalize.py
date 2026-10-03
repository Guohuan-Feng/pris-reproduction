"""Execute the precommitted automated prefix, then freeze/evaluate once."""
from pathlib import Path
import json
import time
from pipeline import Workbench
from prepare_data import sha, save

ROOT=Path(__file__).resolve().parent
def main():
    state=json.loads((ROOT/'agent/state.json').read_text(encoding='utf-8'))
    invocation=ROOT/'agent/invocation.json'
    if (ROOT/'agent/recovered/invocation.json').exists():invocation=ROOT/'agent/recovered/invocation.json'
    meta=json.loads(invocation.read_text(encoding='utf-8'))
    if not meta['completed'] or meta['foreign_tool_events']:raise RuntimeError('Agent session did not complete cleanly')
    for name,digest in meta['precall_hashes'].items():
        if sha(ROOT/name)!=digest:raise RuntimeError('Precommitted code/protocol/plan changed since invocation: '+name)
    n=state['strategy_attempts']
    if not 1<=n<=5:raise ValueError('Invalid attempt count')
    plan=json.loads((ROOT/'controls/plan.json').read_text(encoding='utf-8'))
    if plan['protocol_sha256']!=sha(ROOT/'PROTOCOL.md'):raise RuntimeError('Control plan protocol hash differs')
    bench=Workbench(ROOT);out=[];ids=[];start=time.monotonic()
    configs=plan['candidates']
    if len(configs)!=5:raise ValueError('Expected five precommitted configurations')
    for index,config in enumerate(configs[:n],1):
        cid=config['id']
        specification=config['specification']
        print(f'Control {cid} started',flush=True)
        t=time.monotonic()
        try:
            result=bench.run_strategy(cid,specification);ids.append(cid)
            out.append({'candidate_id':cid,'status':'complete','elapsed_seconds':time.monotonic()-t,'result':result})
        except Exception as exc:out.append({'candidate_id':cid,'status':'failed','error':f'{type(exc).__name__}: {exc}','elapsed_seconds':time.monotonic()-t})
        print(f'Control {cid} {out[-1]["status"]}',flush=True)
    save(ROOT/'controls/execution.json',{'attempted_configurations':n,'successful_ids':ids,'plan_sha256':sha(ROOT/'controls/plan.json'),'elapsed_seconds':time.monotonic()-start,'results':out,'budget_scope':'Matched attempted configurations, not fits/runtime/priors/distributions'})
    agent_ids=[item['id'] for item in state['strategies'] if item['status']=='complete']
    print('Searches complete; freezing both selections before validation',flush=True)
    result=bench.freeze_and_evaluate(agent_ids,ids)
    print(json.dumps({'agent':result['selection']['agent'],'automated_control':result['selection']['automated_control'],'validation_rows':result['validation_rows'],'bootstrap':result['paired_group_bootstrap']},indent=2),flush=True)
if __name__=='__main__':main()
