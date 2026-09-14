"""Run selected inspected author figure functions, preserving reference inputs.

Only output-directory module variables are redirected. No numerical formulas,
thresholds, input aggregates, or plotting code are patched.
"""
from pathlib import Path
import argparse, csv, hashlib, importlib, json, os, subprocess, sys, time, traceback

BASE = Path(__file__).resolve().parents[1]
REPO = None
OUT = BASE / 'results' / 'author_figures'
JOBS = {
    'fig1': {'module':'paper_figs','function':'fig1','stem':'fig1_agentic_law_learning','level':'aggregate replot','notes':'Replots committed discovery-history/rule-space summaries; does not rerun autonomous discovery.'},
    'fig2': {'module':'paper_figs','function':'fig2','stem':'fig2_rules','level':'aggregate replot','notes':'Replots published rule/benchmark aggregates and transfer results; does not recompute the full benchmark.'},
    'fig3': {'module':'fig3_anatomy','function':'main','stem':'fig3_anatomy','level':'mixed: structure recompute + aggregate replot + published DFT values','notes':'Panel a recomputes the author-script illustrative MgAl2O4 structure and five fixed-seed perturbations. Other panels use committed aggregates and published E1 DFT values. This illustrative built-from-scratch spinel is not an external experimental test sample; no new DFT is run.'},
    'fig5': {'module':'fig6_deployment','function':'main','stem':'fig6_deployment','level':'aggregate replot + published DFT values','notes':'Main-text Fig. 5; author script exports historical filename fig6_deployment. Replots committed generator/MLIP aggregates and previously computed E2/E3 DFT values. Does not generate structures or run MLIP/DFT calculations.'},
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def child(key):
    sys.path.insert(0,str(REPO/'src'))
    os.environ['MPLBACKEND']='Agg'
    module=importlib.import_module(JOBS[key]['module'])
    # Both the function's own globals and imported save helpers can own OUT.
    import paper_figs
    paper_figs.OUT=OUT
    module.OUT=OUT
    getattr(module,JOBS[key]['function'])()
    if key=='fig3':
        values=json.loads((OUT/'fig3_anatomy_readings.json').read_text())
        rows=[]
        for mode,v in values.items():
            fired=module.verdicts(v,mode)
            rows.append({'variant':mode,'sample_type':'author-script illustrative spinel' if mode=='real' else 'author-script illustrative damaged spinel','fired_laws':'; '.join(k for k,_ in fired),'satisfied_all_applicable_laws':not bool(fired),**v})
        with (OUT/'fig3_structure_recompute.csv').open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    global REPO, OUT
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True,help='Full upstream checkout at the recorded commit')
    p.add_argument('--out',type=Path,default=OUT)
    p.add_argument('--child',choices=list(JOBS))
    p.add_argument('--only',nargs='+',choices=list(JOBS),default=['fig1','fig3','fig5'])
    args=p.parse_args()
    REPO=args.repo.resolve(); OUT=args.out.resolve()
    OUT.mkdir(parents=True,exist_ok=True)
    if args.child:
        child(args.child);return
    env=os.environ.copy()
    env['PYTHONUTF8']='1'
    env['MPLBACKEND']='Agg'
    keys=args.only or list(JOBS)
    manifest_path=OUT/'manifest.json'
    old=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    rows=[r for r in old.get('figures',[]) if r['id'] not in keys]
    for key in keys:
        t=time.time(); job=JOBS[key]; log=OUT/(key+'_run.log')
        with log.open('w',encoding='utf-8') as f:
            result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child',key,'--repo',str(REPO),'--out',str(OUT)],env=env,cwd=REPO,stdout=f,stderr=subprocess.STDOUT,timeout=180)
        files=[]
        for path in sorted(OUT.glob(job['stem']+'.*')):
            if path.is_file(): files.append({'path':path.name,'size':path.stat().st_size,'sha256':sha(path)})
        if key=='fig3' and (OUT/'fig3_anatomy_readings.json').exists():
            path=OUT/'fig3_anatomy_readings.json';files.append({'path':path.name,'size':path.stat().st_size,'sha256':sha(path)})
            path=OUT/'fig3_structure_recompute.csv'
            if path.exists(): files.append({'path':path.name,'size':path.stat().st_size,'sha256':sha(path)})
        row={**job,'id':key,'exit_code':result.returncode,'status':'success' if result.returncode==0 and files else 'failed','seconds':round(time.time()-t,3),'log':log.name,'source_script_sha256':sha(REPO/'src'/(job['module']+'.py')),'files':files}
        rows.append(row)
        print(json.dumps(row,ensure_ascii=False),flush=True)
        if result.returncode:
            print(log.read_text(encoding='utf-8')[-4000:],flush=True)
        (OUT/'manifest.json').write_text(json.dumps({'source_repository':'https://github.com/AI4QC/PRIS','source_commit':subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(),'execution_changes':'Only module OUT values redirected to output folder; original source files unmodified. Specific functions invoked so paper_figs.py implicit unrelated figures are not run.','figures':rows},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

    return 1 if any(r['exit_code'] for r in rows if r['id'] in keys) else 0

if __name__=='__main__':
    raise SystemExit(main())
