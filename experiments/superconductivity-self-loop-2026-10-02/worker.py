"""One numerical action in a child process; no model-selection decisions here."""
from pathlib import Path
import argparse
from runtime import read_json,write_json
from workbench_adapter import Adapter

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--request',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    request=read_json(a.request)
    try:
        adapter=Adapter(a.run,a.source);out=adapter.evaluate(request['candidate_id'],request['specification'])
        out['counterexamples']=adapter.counterexamples(request['candidate_id'],k=3)
    except Exception as exc:out={'status':'failed','error':f'{type(exc).__name__}: {exc}','scientific_evidence_available':False}
    write_json(a.output,out)
