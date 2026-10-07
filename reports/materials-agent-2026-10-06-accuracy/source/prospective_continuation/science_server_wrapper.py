"""Registered guarded loading of original immutable MCP science server."""
from __future__ import annotations
import os,runpy,sys
from pathlib import Path
sys.dont_write_bytecode=True
SIDE=Path(__file__).resolve().parent;ROOT=SIDE.parent
sys.path.insert(0,str(SIDE));sys.path.insert(0,str(ROOT))
from guard import ContinuationGuard

def install(namespace,guard):
    original_call=namespace['audited_call'];g=original_call.__globals__
    backend=g['backend'];original_summary=backend.summary_context
    # Compact context changes are a registered projection, never a disk rewrite.
    backend.summary_context=lambda:guard.scoped_context(original_summary())
    attempt=g['ATTEMPT']
    def guarded_call(name,arguments,operation):
        candidate=arguments.get('candidate_id') if name=='evaluate_candidate' else None
        reservation=0
        if candidate:
            proposal=backend.state()['proposals'].get(candidate,{})
            reservation=4*proposal.get('max_fits_per_block',7)
        guard.validate('before:'+name,attempt=attempt,evaluate_candidate=candidate,reservation=reservation)
        backend.assert_frozen()
        expected='T'+f'{backend.load(g["SERVER_STATE"])["tool_calls"]+1:04d}'
        def once():
            guard.validate('operation_before:'+name,allow_current_call=expected,attempt=attempt,evaluate_candidate=candidate,reservation=reservation)
            result=operation()
            # research_context's summary projection is computed during this
            # serialized current tool, so allow only this EID until it finishes.
            guard.validate('operation_after:'+name,allow_current_call=expected,attempt=attempt)
            return result
        result=original_call(name,arguments,once)
        guard.validate('after:'+name,attempt=attempt)
        backend.assert_frozen()
        return result
    g['audited_call']=guarded_call
    # research_context calls backend.summary_context during current tool;
    # the scoped reader must validate that one exact active serialized EID.
    def scoped_summary():
        server=backend.load(g['SERVER_STATE'])
        current=[c['evidence_id'] for c in server['calls'][76:] if c['status']=='started']
        return scoped_during_call(guard,original_summary(),current[0] if len(current)==1 else None)
    backend.summary_context=scoped_summary
    return namespace['mcp']

def scoped_during_call(guard,original,current):
    # scoped_context itself performs the same check with this explicit allowance.
    return guard.scoped_context(original,allow_current_call=current)

def main():
    attempt=Path(os.environ['MATERIALS_CYCLE_DIR']).resolve()
    from guard import load
    # CYCLE_DIR is explicitly present in the original MCP config environment;
    # do not depend on unspecified parent environment variable forwarding.
    expected=load(attempt/'session_request.json')['manifest_sha256']
    guard=ContinuationGuard(ROOT,expected)
    guard.validate('server_start',attempt=attempt)
    namespace=runpy.run_path(str(ROOT/'science_server.py'),run_name='materials_accuracy_original_server_guarded')
    install(namespace,guard).run(transport='stdio')

if __name__=='__main__':main()
