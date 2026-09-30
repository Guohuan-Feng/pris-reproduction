"""Package the completed, audited experiment without runtime environments."""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import zipfile

ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def main():
    assert load(ROOT/'audit_final.json')['passed']
    names=['numpy','pandas','scipy','scikit-learn','pymatgen','joblib','threadpoolctl','matplotlib']
    versions={n:importlib.metadata.version(n) for n in names};versions['mcp']='2.2.0'
    (ROOT/'requirements.txt').write_text('\n'.join(f'{k}=={v}' for k,v in versions.items())+'\n',encoding='utf-8')
    dump(ROOT/'environment.json',{'python':platform.python_version(),'platform':platform.platform(),'direct_dependencies':versions,'mcp_installation':'Isolated --target work/scientific_agent_mcp_deps; original numerical environment was not modified.'})
    calls=[load(ROOT/'agent/invocation.json'),load(ROOT/'agent/recovered/invocation.json')]
    usage=[]
    for call in calls:
        u=call['usage_events'][0]['usage'];usage.append({'infrastructure_recovery':call.get('infrastructure_recovery',False),'scientific_completed':call['completed'],'elapsed_seconds':call['elapsed_seconds'],**u})
    totals={k:sum(x.get(k,0) for x in usage) for k in ['input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens','reasoning_output_tokens']}
    dump(ROOT/'USAGE_SUMMARY.json',{'sessions':usage,'totals':totals,'scientific_tool_calls':14,'descriptor_experiments':5,'reasoning_tokens_are_subset_of_output':True,'cached_tokens_are_subset_of_input':True,'authentication':'Existing ChatGPT/Codex login; no professor project API key used.','exclusions':'Parent conversation and internal helper-agent usage are not included. Dollar cost cannot be inferred from these subscription CLI events.','budget':'6 descriptor attempts,24 processed tools,900 seconds per working run; no monetary cap.'})
    deps=['outputs/pris_mp_rules_2026-09-30/data/prepare_mp.py','outputs/pris_mp_rules_2026-09-30/data/stream_cse.py']
    deps+=['outputs/pris_incremental_rules_2026-09-30/'+n for n in ['allowed_features.json','data/feature_schema.json','data/source_identity_inventory.csv.gz','data/split_assignments.csv','data/excluded_prior_ids.csv','data/excluded_chemical_systems.csv']]
    with zipfile.ZipFile(ROOT/'source_dependencies.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name in deps:archive.write(WORKSPACE/name,name)
    dump(ROOT/'SOURCE_DEPENDENCIES.json',{'paths_relative_to_original_workspace':{n:sha(WORKSPACE/n) for n in deps},'archive_sha256':sha(ROOT/'source_dependencies.zip'),'contains_original_source_archives':False})
    files=[p for p in ROOT.rglob('*') if p.is_file() and not any(part in {'__pycache__','.pytest_cache'} for part in p.parts) and p.suffix not in ['.pyc','.tmp'] and p.name not in ['PACKAGE_MANIFEST.json','PACKAGE_VERIFICATION.json']]
    missing=[];links=0
    for p in files:
        if p.suffix!='.md':continue
        text=p.read_text(encoding='utf-8')
        for url in re.findall(r'\]\(([^)]+)\)',text):
            url=url.split('#',1)[0]
            if not url or '://' in url or url.startswith('mailto:'):continue
            links+=1
            if not (p.parent/url).exists():missing.append([p.relative_to(ROOT).as_posix(),url])
    if missing:raise RuntimeError('Missing local document links: '+str(missing))
    dump(ROOT/'PACKAGE_MANIFEST.json',{'files':{p.relative_to(ROOT).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(files)},'local_markdown_links_checked':links,'excluded':'Python caches and external environments/dependencies; full original MP raw archives are available at cited URLs.'})
    archive_path=ROOT.parent/'PRIS_tool_using_scientific_agent_2026-09-30.zip'
    with zipfile.ZipFile(archive_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for p in files+[ROOT/'PACKAGE_MANIFEST.json']:archive.write(p,p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        for name,entry in load(ROOT/'PACKAGE_MANIFEST.json')['files'].items():assert hashlib.sha256(archive.read(name)).hexdigest()==entry['sha256']
    verification={'archive':archive_path.name,'archive_sha256':sha(archive_path),'archive_bytes':archive_path.stat().st_size,'payload_files':len(files),'all_payload_hashes_verified':True,'zip_crc_verified':True,'local_markdown_links_checked':links}
    dump(ROOT/'PACKAGE_VERIFICATION.json',verification)
    print(json.dumps(verification,indent=2))

if __name__=='__main__':main()
