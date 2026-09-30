"""After audit, freeze selection and execute one independent test (never an MCP tool)."""
from __future__ import annotations
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
import pandas as pd
from evaluator import Evaluator
from scientific_server import worker_compute

ROOT=Path(__file__).resolve().parent
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def main():
    call=ROOT/'agent/recovered/invocation.json'
    meta=load(call)
    if not meta.get('completed'):raise RuntimeError('Scientific discovery session is not complete')
    approval=ROOT/'FINAL_EVALUATION_AUTHORIZATION.json'
    auth=load(approval)
    if not auth.get('authorized') or auth.get('invocation_sha256')!=sha(call):raise RuntimeError('Root audit authorization does not match completed run')
    for name in ['evaluator.py','scientific_server.py','descriptor_runtime.py','PROTOCOL.md']:
        if meta['precall_hashes'][name]!=sha(ROOT/name):raise RuntimeError('Discovery source changed: '+name)
    evaluator=Evaluator(ROOT)
    selection=evaluator.freeze_selection({'completed':True,'audit_passed':True,'invocation_sha256':sha(call),'authorization_sha256':sha(approval),'tool_log_sha256':sha(ROOT/'agent/tool_events.jsonl')})
    needed={v['candidate_id'] for v in selection['selected'].values()}-{'raw'}
    # No generated function sees labels or identities, and the agent is finished.
    with gzip.open(ROOT/'data/descriptor_test.jsonl.gz','rt',encoding='utf-8') as stream:
        structures=list(map(json.loads,stream))
    frames={};provenance={}
    for eid in sorted(needed):
        codefile=ROOT/'experiments'/eid/'descriptor.py'
        spec=load(ROOT/'experiments'/eid/'specification.json')
        if sha(codefile)!=spec['code_sha']:raise RuntimeError('Descriptor source changed')
        computed=worker_compute(codefile.read_text(encoding='utf-8'),structures)
        if computed['descriptor_names']!=spec['descriptor_names']:raise RuntimeError('Descriptor schema changed on test')
        frames[eid]=pd.DataFrame(computed['rows'])
        provenance[eid]={'code_sha':sha(codefile),'runtime_sha256':sha(ROOT/'descriptor_runtime.py'),'structure_input_sha256':sha(ROOT/'data/descriptor_test.jsonl.gz')}
    results=evaluator.final_test(frames,auth,provenance)
    print(json.dumps(results,indent=2))

if __name__=='__main__':main()
