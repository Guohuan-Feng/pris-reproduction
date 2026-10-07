"""Source-bound generation of training geometry features, with no target input."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib
from importlib import metadata
import json
import os
from pathlib import Path
import stat
import sys
import time
import numpy as np

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
PURE=Path('C:/Users/28908/Codex/fung-research/materials-controlled-agent-2026-10-07/design/train_structures2164_pure.jsonl.gz')
PURE_SHA='7c3845aff75ef9ae320ffb8db92d12c722f1a7c38524d67b77925d65712ee2bc'
ID_SHA='a93272c84f100f446e466998dad45f77e9f3491ae758bf949e130285565e2a1e'

def need(ok,message):
    if not ok: raise RuntimeError(message)
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def utc(): return datetime.now(timezone.utc).isoformat()
def safe(path):
    path=Path(path); resolved=path.resolve()
    need(resolved.is_relative_to(ROOT) and not any('onedrive' in p.lower() for p in resolved.parts),'Forbidden output')
    for p in (path,*path.parents):
        if p.exists():need(not getattr(p.lstat(),'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT,'Reparse ancestor')
    return path
def write(path,value):
    with safe(path).open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def environment():
    folder=str(safe(ROOT/'tmp'))
    os.environ.update(TEMP=folder,TMP=folder,NUMBA_CACHE_DIR=folder,PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    sys.path.insert(0,str(ROOT/'dependencies'))
def validate_environment():
    env=load(ROOT/'design/dependency_environment.json');need(env['status']=='PASS','Environment not validated')
    need(env['failure_count']==0 and env['base_NumPy_not_shadowed'] is True and env['target_values_accessed'] is False,'Invalid environment scope')
    need(sha(ROOT/'design/dependency_install_report.json')==env['pip_report_sha256'],'Install receipt changed')
    need(sha(ROOT/env['synthetic_receipt_path'])==env['synthetic_receipt_sha256'],'Synthetic receipt changed')
    smoke=load(ROOT/env['synthetic_receipt_path'])
    need(smoke['status']=='PASS' and smoke['failure_count']==0 and smoke['scientific_fits_performed']==0 and smoke['target_values_accessed'] is False,'Synthetic invariance not proven')
    need(smoke['source_sha256']==sha(ROOT/'runtime/soap_representation.py')==env['generator_source_sha256'],'Synthetic descriptor source differs')
    need(smoke['test_source_sha256']==sha(ROOT/smoke['test_source_path'])==env['synthetic_test_source_sha256'],'Synthetic checker source differs')
    for path,digest in env['file_hashes'].items(): need(sha(path)==digest,'Dependency bytes changed')
    for name,version in env['versions'].items():
        module=importlib.import_module(name)
        actual=metadata.version('scikit-learn' if name=='sklearn' else name)
        need(actual==version and Path(module.__file__).resolve()==Path(env['module_paths'][name]).resolve(),'Dependency import path/version changed')

def register():
    import soap_representation as soap
    need(Path(soap.__file__).resolve()==(ROOT/'runtime/soap_representation.py').resolve(),'Wrong descriptor import')
    validate_environment()
    need(sha(PURE)==PURE_SHA,'Pure training geometry source changed')
    ids=load(ROOT/'inputs/ids.json')
    need(len(ids)==2164 and len(set(ids))==2164,'Wrong pure row count')
    need(hashlib.sha256(json.dumps(ids,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()==ID_SHA,'Wrong training ID order')
    files={str(p):sha(p) for p in (Path(__file__),ROOT/'runtime/soap_representation.py',ROOT/'design/dependency_environment.json',ROOT/'design/dependency_install_report.json',ROOT/'design/soap_synthetic_smoke.json',ROOT/'design/soap_synthetic_preflight.py',ROOT/'inputs/ids.json',PURE)}
    value=dict(schema_version=1,registered_utc=utc(),phase='C_pure_periodic_geometry',source_input_hashes=files,
      parameters=soap.specification(),ordered_train_ids_sha256=ID_SHA,rows=2164,raw_dimensions=6016,
      budget=dict(cpu_threads=1,geometry_generation_seconds=3600),scientific_fits_allowed=0,
      training_target_values_received=False,new_confirmation_labels_read=False,
      outputs=['inputs/soap_raw.npy','inputs/soap_receipt.json'],failure_rule='Preserve failed evidence; no label-dependent exclusions or parameter changes.')
    write(ROOT/'design/soap_generation_protocol.json',value)
    print(json.dumps(dict(status='REGISTERED_PURE_PROTOCOL',protocol_sha256=sha(ROOT/'design/soap_generation_protocol.json'))),flush=True)

def run():
    import soap_representation as soap
    need(Path(soap.__file__).resolve()==(ROOT/'runtime/soap_representation.py').resolve(),'Wrong descriptor import')
    from threadpoolctl import threadpool_limits
    protocol_path=ROOT/'design/soap_generation_protocol.json'; p=load(protocol_path); digest=sha(protocol_path)
    review_path=ROOT/'design/soap_generation_prelaunch_review.json';review=load(review_path)
    auth=load(ROOT/'design/soap_generation_execution_authorization.json')
    need(review['status']=='PASS' and review['failure_count']==0 and review['protocol_sha256']==digest and review['source_input_hashes']==p['source_input_hashes'],'Pure prelaunch review required')
    need(review['scientific_fits_performed']==0 and review['new_confirmation_labels_read'] is False,'Invalid pure review')
    need(auth['protocol_sha256']==digest and auth['review_sha256']==sha(review_path) and auth['source_input_hashes']==p['source_input_hashes'] and auth['scientific_fits_allowed']==0,'Pure root authorization required')
    need(not (ROOT/'runtime/soap_generation_launch.json').exists(),'Already launched; preserve existing evidence')
    def frozen():
        need(sha(protocol_path)==digest,'Pure protocol changed')
        for name,h in p['source_input_hashes'].items():need(sha(name)==h,'Pure frozen source/input changed')
        need(soap.specification()==p['parameters'],'Descriptor parameters changed')
    frozen();validate_environment();ids=load(ROOT/'inputs/ids.json')
    with gzip.open(PURE,'rt',encoding='utf-8') as f:records=[json.loads(line) for line in f]
    need([r['material_id'] for r in records]==ids,'Pure training rows reordered')
    start=time.monotonic()
    write(ROOT/'runtime/soap_generation_launch.json',dict(utc=utc(),pid=os.getpid(),protocol_sha256=digest,review_sha256=sha(review_path),rows=2164,scientific_fits=0,training_target_values_received=False))
    def progress(done,total):
        frozen();need(time.monotonic()-start<3600,'Geometry generation budget exhausted')
        print(json.dumps(dict(status='PURE_SOAP_PROGRESS',completed=done,total=total)),flush=True)
    try:
        with threadpool_limits(limits=1):matrix,receipt=soap.compute_matrix(records,expected_ids=ids,progress_callback=progress)
        frozen();validate_environment()
        need(receipt['ordered_train_ids_sha256']==ID_SHA and matrix.shape==(2164,6016),'Generated boundary mismatch')
        with safe(ROOT/'inputs/soap_raw.npy').open('xb') as f:np.save(f,matrix,allow_pickle=False)
        receipt.update(protocol_sha256=digest,raw_file_sha256=sha(ROOT/'inputs/soap_raw.npy'),wall_seconds=time.monotonic()-start,finished_utc=utc(),scientific_fits_performed=0,experimental_LLM_calls=0,new_confirmation_labels_read=False)
        write(ROOT/'inputs/soap_receipt.json',receipt)
        print(json.dumps(dict(status='PURE_SOAP_COMPLETE',rows=2164,dimensions=6016,wall_seconds=receipt['wall_seconds'],scientific_fits=0,target_values_accessed=False)),flush=True)
    except BaseException as exc:
        write(ROOT/'runtime/soap_generation_failure.json',dict(utc=utc(),error=repr(exc),scientific_fits=0,target_values_accessed=False))
        raise

if __name__=='__main__':
    environment();parser=argparse.ArgumentParser();parser.add_argument('command',choices=['register','run'])
    {'register':register,'run':run}[parser.parse_args().command]()
