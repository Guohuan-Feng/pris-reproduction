"""Agent-authored supervised programs with training/inference separation.

The trusted learner API records each actual sklearn fit. Import never fits.
Numeric AST limits and resource-bound process are not a general OS sandbox.
"""
from __future__ import annotations
import ast
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import re

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'dependencies'))
import numpy as np
import representation_runtime as numeric

OLD_RUNTIME = ROOT.parent / 'materials_structure_agent_2026-10-05_pilot/descriptor_runtime.py'
OLD_RUNTIME_SHA = 'c1d99ab97cce8adea015d41a88a9f98d9501aec4aaa6a735c1bcada81162fd06'
assert hashlib.sha256(OLD_RUNTIME.read_bytes()).hexdigest() == OLD_RUNTIME_SHA
spec = importlib.util.spec_from_file_location('_evolving_numeric_guard', OLD_RUNTIME)
guard = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = guard
spec.loader.exec_module(guard)

MODEL_API = {
    'e011': 'Frozen oxygen-routed old E011 learner; cost5 per block, first42 columns must remain raw old42. params empty.',
    'extra_trees': 'cost1; n_estimators100..600, min_samples_leaf1..64, max_features0.1..1; criterion squared_error.',
    'hgb': 'cost1; max_iter50..500, max_leaf_nodes3..63,min_samples_leaf5..100,learning_rate.01..0.3,l2_regularization0..100,loss squared_error/absolute_error.',
    'ridge': 'cost1; alpha .000001..10000; training-only standardization and intercept are always used.',
    'krr': 'cost1; alpha .000001..10000, gamma .000001..100; RBF, training-only standardization and y centering. sample_weight forbidden.',
    'catboost':'cost1; pinned1.2.10 CPU. iterations100..1200, depth3..9, learning_rate.01..0.2,l2_leaf_reg1..30,loss_function RMSE/MAE/Huber:delta=0.1..2,subsample.5..1. thread_count1,seed20261006,Bernoulli bootstrap,no files. Training-only sample_weight permitted.'}

DEPENDENCY_LOCK_SHA='97381b5db8b62e6f555f287ae2999cbd2cb2ca19246e3e17f75c5213ade61be9'
def verify_dependency_lock(check_files=False):
    path=ROOT/'environment/dependency_lock.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=DEPENDENCY_LOCK_SHA:raise RuntimeError('Pinned task dependency lock changed')
    receipt=json.loads(path.read_text(encoding='utf-8'))
    if check_files:
        for name,digest in receipt['task_dependency_file_hashes'].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Pinned task dependency bytes changed')
    return receipt


def code_sha(code):
    return hashlib.sha256(code.encode('utf-8')).hexdigest()

def array_receipt(values):
    array=np.asarray(values,dtype='<f8')
    return {'shape':list(array.shape),'dtype':'float64_little_endian','sha256':hashlib.sha256(array.tobytes(order='C')).hexdigest()}


def validate_predictor(code, max_fits_per_block):
    if not isinstance(code,str) or len(code.encode()) > 32768:
        raise ValueError('Predictor code must be <=32768 UTF8 bytes')
    if not isinstance(max_fits_per_block,int) or isinstance(max_fits_per_block,bool) or not 1 <= max_fits_per_block <= 7:
        raise ValueError('Declare max_fits_per_block1..7')
    tree = ast.parse(code)
    nodes = list(ast.walk(tree))
    if len(nodes)>6000: raise ValueError('Predictor AST too large')
    defs = {n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
    for name,args in (('fit',['X_train','y_train']),('predict',['state','X_eval'])):
        if name not in defs or [a.arg for a in defs[name].args.args] != args:
            raise ValueError(f'Submit def {name}({", ".join(args)})')
    functions = {n.name for n in nodes if isinstance(n,ast.FunctionDef)}
    for node in tree.body:
        if not isinstance(node,(ast.FunctionDef,ast.Import,ast.ImportFrom)):
            raise ValueError('Only imports and function definitions at module scope')
    forbidden = {'eval','exec','open','compile','getattr','setattr','delattr','globals','locals','vars','dir','type','object','input','print','help','breakpoint','memoryview','bytes','bytearray','super'}
    for node in nodes:
        if type(node) not in numeric.ALLOWED_NODE_TYPES: raise ValueError(f'AST construct {type(node).__name__} forbidden')
        if isinstance(node,(ast.Name,ast.arg)):
            name = node.id if isinstance(node,ast.Name) else node.arg
            if '__' in name or name in forbidden: raise ValueError(f'Forbidden name {name}')
            if isinstance(node,ast.Name) and isinstance(node.ctx,ast.Store) and name in ('np','math','train_model'):
                raise ValueError('Trusted names cannot be rebound')
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and '__' in node.value:
            raise ValueError('Dunder strings forbidden')
        if isinstance(node,ast.FunctionDef):
            if (node.decorator_list or node.args.vararg or node.args.kwarg or node.args.defaults or node.args.kw_defaults
                    or node.args.kwonlyargs or node.args.posonlyargs or node.returns or any(a.annotation for a in node.args.args)
                    or '__' in node.name or node.name in {'np','math','train_model'}):
                raise ValueError('Decorators/variadic/trusted function names forbidden')
        if isinstance(node,ast.Import):
            if any((a.name,a.asname) not in {('numpy','np'),('math',None),('math','math')} for a in node.names): raise ValueError('Only numpy/math imports')
        if isinstance(node,ast.ImportFrom):
            permitted=numeric.NP_NAMES if node.module=='numpy' else numeric.MATH_NAMES if node.module=='math' else set()
            if node.level or not permitted or any(a.name not in permitted or a.asname not in (None,a.name) for a in node.names): raise ValueError('Import outside numeric allowlist')
        if isinstance(node,ast.Attribute):
            path=guard._attribute_path(node)
            if '__' in node.attr: raise ValueError('Dunder attribute forbidden')
            if path and path[0]=='np':
                if path not in [['np',n] for n in numeric.NP_NAMES]+[['np','linalg']]+[['np','linalg',n] for n in numeric.NP_LINALG_NAMES]: raise ValueError('Numpy attribute outside allowlist')
            elif path and path[0]=='math':
                if len(path)!=2 or path[1] not in guard.MATH_NAMES: raise ValueError('Math attribute outside allowlist')
            elif node.attr not in guard.ARRAY_ATTRIBUTES | {'predict'}: raise ValueError('Only numeric array attributes and trusted model.predict')
        if isinstance(node,ast.Call):
            imported={a.name for n in nodes if isinstance(n,ast.ImportFrom) for a in n.names}
            if isinstance(node.func,ast.Name) and node.func.id not in set(guard.SAFE_BUILTINS)|functions|imported|{'train_model'}:
                raise ValueError(f'Call {node.func.id} outside numeric API')
            if not isinstance(node.func,(ast.Name,ast.Attribute)) or any(k.arg is None for k in node.keywords): raise ValueError('Indirect calls or expanded keywords forbidden')
        if isinstance(node,(ast.Assign,ast.AnnAssign,ast.AugAssign)):
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            if any(isinstance(p,ast.Attribute) for t in targets for p in ast.walk(t)): raise ValueError('Attribute mutation forbidden')
    return {'accepted':True,'code_sha256':code_sha(code),'ast_nodes':len(nodes),'max_fits_per_block':max_fits_per_block,'fits_performed':0}


class TrustedModel:
    def __init__(self,predict): self._predict=predict
    def predict(self,X):
        values=np.asarray(X,float)
        result=np.asarray(self._predict(values),float)
        if result.shape!=(len(values),) or not np.isfinite(result).all(): raise ValueError('Invalid model prediction')
        return result


class LearnerAPI:
    def __init__(self,max_fits,event_path,block_id,original_raw42=None):
        self.max_fits=max_fits;self.event_path=Path(event_path);self.block_id=block_id;self.started=0;self.completed=0;self.phase='fit'
        self.raw42_rows=None if original_raw42 is None else {tuple(row) for row in np.asarray(original_raw42,float)}
    def emit(self,item):
        item={**item,'block_id':self.block_id,'utc':time.time()}
        with self.event_path.open('a',encoding='utf-8') as f:
            f.write(json.dumps(item,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
    def fit(self,kind,X,y,params=None,sample_weight=None):
        if self.phase!='fit': raise ValueError('Training is prohibited during prediction')
        X=np.asarray(X,float);y=np.asarray(y,float);p=dict(params or {})
        if X.ndim!=2 or y.shape!=(len(X),) or not len(X) or X.shape[1]>160 or not np.isfinite(X).all() or not np.isfinite(y).all(): raise ValueError('Invalid current-training numeric arrays')
        if kind not in MODEL_API: raise ValueError('Unknown learner kind')
        weight=None
        if sample_weight is not None:
            weight=np.asarray(sample_weight,float)
            if weight.shape!=(len(X),) or not np.isfinite(weight).all() or np.any(weight<0) or not np.any(weight>0):raise ValueError('Training weights must be finite nonnegative rows with positive mass')
            with np.errstate(over='raise',invalid='raise',divide='raise'):
                mass=float(weight.mean())
                if not math.isfinite(mass) or mass<=0:raise ValueError('Training weight mean must be finite and positive')
                weight=weight/mass
            if not np.isfinite(weight).all() or not np.any(weight>0):raise ValueError('Invalid normalized training weights')
            if kind in ('e011','krr'):raise ValueError('Frozen E011 and KRR do not accept sample_weight')
        cost=5 if kind=='e011' else 1
        if self.started+cost>self.max_fits: raise ValueError('Declared learner budget exhausted before next fit')
        if kind=='e011':
            if p or X.shape[1]<42 or np.any(X[:,17]<0) or np.any(X[:,17]>1): raise ValueError('E011 requires raw first42 and emptyparams')
            if self.raw42_rows is not None and any(tuple(row) not in self.raw42_rows for row in X[:,:42]):
                raise ValueError('E011 first42 columns must exactly match rows from current original training block')
            oxygen=X[:,17]>0
            if any(np.sum(oxygen==label)<150 for label in (False,True)):
                raise ValueError('E011 five-fit contract requires >=150 per O group before any fit')
            global_model=self.fit_single('extra_trees',X,y,{'n_estimators':400,'min_samples_leaf':1,'max_features':1.0},seed=20261002)
            experts={}
            for label in (False,True):
                mask=oxygen==label
                if mask.sum()<150: raise ValueError('E011 five-fit contract requires >=150 per O group')
                h=self.fit_single('hgb',X[mask],y[mask],{'max_iter':150,'max_leaf_nodes':15,'min_samples_leaf':20,'learning_rate':.1,'l2_regularization':0,'loss':'squared_error'},seed=20261002)
                e=self.fit_single('extra_trees',X[mask],y[mask],{'n_estimators':400,'min_samples_leaf':1,'max_features':1.0},seed=20261002)
                experts[label]=(h,e)
            def prediction(values):
                result=global_model.predict(values)
                for label in (False,True):
                    mask=(values[:,17]>0)==label
                    if mask.any():
                        h,e=experts[label];result[mask]=.5*result[mask]+.25*h.predict(values[mask])+.25*e.predict(values[mask])
                return result
            return TrustedModel(prediction)
        return self.fit_single(kind,X,y,p,seed=20261002,sample_weight=weight)
    def fit_single(self,kind,X,y,p,seed,sample_weight=None):
        from sklearn.ensemble import ExtraTreesRegressor,HistGradientBoostingRegressor
        from sklearn.linear_model import Ridge
        from sklearn.kernel_ridge import KernelRidge
        from sklearn.preprocessing import StandardScaler
        from catboost import CatBoostRegressor
        factories={'extra_trees':(ExtraTreesRegressor,{'n_estimators':400,'min_samples_leaf':1,'max_features':1.0,'n_jobs':1,'random_state':seed}),
          'hgb':(HistGradientBoostingRegressor,{'max_iter':150,'max_leaf_nodes':15,'min_samples_leaf':20,'learning_rate':.1,'l2_regularization':0,'loss':'squared_error','early_stopping':False,'random_state':seed}),
          'ridge':(Ridge,{'alpha':10.0,'fit_intercept':True}),
          'krr':(KernelRidge,{'alpha':1.0,'kernel':'rbf','gamma':.01}),
          'catboost':(CatBoostRegressor,{'iterations':600,'depth':6,'learning_rate':.05,'l2_leaf_reg':5,'loss_function':'RMSE','subsample':.8,'bootstrap_type':'Bernoulli','thread_count':1,'random_seed':20261006,'allow_writing_files':False,'task_type':'CPU','verbose':False})}
        ranges={'extra_trees':{'n_estimators':(100,600),'min_samples_leaf':(1,64),'max_features':(.1,1)},
          'hgb':{'max_iter':(50,500),'max_leaf_nodes':(3,63),'min_samples_leaf':(5,100),'learning_rate':(.01,.3),'l2_regularization':(0,100),'loss':('squared_error','absolute_error')},
          'ridge':{'alpha':(1e-6,1e4)},'krr':{'alpha':(1e-6,1e4),'gamma':(1e-6,100)},
          'catboost':{'iterations':(100,1200),'depth':(3,9),'learning_rate':(.01,.2),'l2_leaf_reg':(1,30),'loss_function':('RMSE','MAE'),'subsample':(.5,1)}}
        if set(p)-set(ranges[kind]): raise ValueError('Undeclared model parameter')
        for name,value in p.items():
            domain=ranges[kind][name]
            if name=='loss_function':
                if value not in ('RMSE','MAE'):
                    match=re.fullmatch(r'Huber:delta=([0-9]+(?:\.[0-9]+)?)',value) if isinstance(value,str) else None
                    if not match or not .1<=float(match.group(1))<=2:raise ValueError('Unsupported CatBoost loss_function or Huber delta')
            elif name=='loss':
                if value not in domain: raise ValueError('Unsupported loss')
            elif isinstance(value,bool) or not isinstance(value,(int,float)) or not domain[0]<=value<=domain[1]: raise ValueError('Parameter outside bounded domain')
            if name in {'n_estimators','min_samples_leaf','max_iter','max_leaf_nodes','iterations','depth'} and not isinstance(value,int): raise ValueError('Integer model parameter required')
        factory,defaults=factories[kind];parameters={**defaults,**p}
        transformer=None;target_mean=0
        if kind in ('ridge','krr'):
            transformer=StandardScaler().fit(X,sample_weight=sample_weight) if sample_weight is not None else StandardScaler().fit(X);X=transformer.transform(X)
            if kind=='krr':target_mean=float(np.mean(y));y=y-target_mean
        self.started+=1;fit_id=f'{self.block_id}_F{self.started:03d}'
        metadata={'fit_id':fit_id,'learner':kind,'rows':len(y),'features':X.shape[1],'parameters':parameters,'sample_weight_received':sample_weight is not None,'sample_weight_sha256':None if sample_weight is None else hashlib.sha256(np.asarray(sample_weight,dtype='<f8').tobytes()).hexdigest()}
        self.emit({**metadata,'phase':'started'})
        try:
            model=factory(**parameters)
            model.fit(X,y,sample_weight=sample_weight) if sample_weight is not None else model.fit(X,y)
        except Exception as exc:
            self.emit({**metadata,'phase':'failed','error':f'{type(exc).__name__}: {exc}'});raise
        self.completed+=1;self.emit({**metadata,'phase':'completed'})
        return TrustedModel(lambda values:model.predict(transformer.transform(values) if transformer is not None else values)+target_mean)


def _worker():
    from threadpoolctl import threadpool_limits
    verify_dependency_lock(check_files=True)
    import catboost
    if catboost.__version__!='1.2.10':raise RuntimeError('Registered CatBoost version mismatch')
    payload=json.load(sys.stdin);code=payload['code'];validate_predictor(code,payload['max_fits'])
    X=np.asarray(payload['X_train'],float);y=np.asarray(payload['y_train'],float);E=np.asarray(payload['X_eval'],float)
    numeric_inputs={'X_train':array_receipt(X),'y_train':array_receipt(y),'X_eval':array_receipt(E),'evaluation_targets_received':False}
    X.setflags(write=False);y.setflags(write=False);E.setflags(write=False)
    api=LearnerAPI(payload['max_fits'],payload['event_path'],payload['block_id'],original_raw42=X[:,:42] if X.shape[1]>=42 else None)
    namespace={'__builtins__':{**guard.SAFE_BUILTINS,'__import__':guard._safe_import},'np':np,'math':math,'train_model':api.fit}
    started=time.perf_counter()
    with threadpool_limits(limits=1):
        exec(compile(code,'<agent_predictor>','exec'),namespace,namespace)
        fitted=namespace['fit'](X,y)
        if api.completed==0: raise ValueError('Fit must call trusted learner API at least once')
        api.phase='predict'
        pred=np.asarray(namespace['predict'](fitted,E),float)
        if pred.shape!=(len(E),) or not np.isfinite(pred).all(): raise ValueError('Invalid prediction vector')
        # Detect inference preprocessing which depends on other evaluation rows.
        probes=np.unique(np.linspace(0,len(E)-1,min(8,len(E))).astype(int))
        single=np.asarray([np.asarray(namespace['predict'](fitted,E[i:i+1]),float)[0] for i in probes])
        reverse=np.asarray(namespace['predict'](fitted,E[::-1]),float)[::-1]
        partition=np.concatenate([np.asarray(namespace['predict'](fitted,chunk),float) for chunk in np.array_split(E,min(7,len(E)))])
        if not np.allclose(single,pred[probes],rtol=0,atol=1e-10) or not np.allclose(reverse,pred,rtol=0,atol=1e-10) or not np.allclose(partition,pred,rtol=0,atol=1e-10): raise ValueError('Prediction must pass batch composition/order independence probes')
    print(json.dumps({'status':'ok','prediction':pred.tolist(),'fit_started':api.started,'fit_completed':api.completed,'worker_seconds':time.perf_counter()-started,'inference_independence_checks':len(probes)+2,'numeric_input_receipts':numeric_inputs},allow_nan=False))


def run_training_block(code,X_train,y_train,X_eval,*,max_fits_per_block,event_path,block_id,timeout_s=600,memory_mb=2048):
    validation=validate_predictor(code,max_fits_per_block)
    if not isinstance(timeout_s,(int,float)) or not .1<=timeout_s<=600 or not isinstance(memory_mb,int) or not 128<=memory_mb<=2048:
        raise ValueError('Predictor resource bounds timeout<=600sec, memory128..2048MB')
    X=np.asarray(X_train,float);y=np.asarray(y_train,float);E=np.asarray(X_eval,float)
    if X.ndim!=2 or E.ndim!=2 or not len(E) or not len(X) or X.shape[1]!=E.shape[1] or y.shape!=(len(X),) or not np.isfinite(X).all() or not np.isfinite(E).all() or not np.isfinite(y).all(): raise ValueError('Invalid supervised block')
    Path(event_path).parent.mkdir(parents=True,exist_ok=True)
    payload=json.dumps({'code':code,'X_train':X.tolist(),'y_train':y.tolist(),'X_eval':E.tolist(),'max_fits':max_fits_per_block,'event_path':str(Path(event_path).resolve()),'block_id':block_id},allow_nan=False).encode()
    if len(payload)>64*1024**2: raise ValueError('Worker payload exceeds64MiB')
    env={k:os.environ[k] for k in ('SystemRoot','WINDIR','TEMP','TMP','PATH') if k in os.environ}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    runtime=str(Path(__file__).resolve());site=str(Path(np.__file__).resolve().parent.parent)
    bootstrap=f'import sys,runpy;sys.path.insert(0,{site!r});sys.path.insert(0,{str(ROOT/"dependencies")!r});sys.argv=[{runtime!r},"--worker"];runpy.run_path({runtime!r},run_name="__main__")'
    kwargs={'stdin':subprocess.PIPE,'stdout':subprocess.PIPE,'stderr':subprocess.PIPE,'env':env,'cwd':str(ROOT)}
    if os.name=='nt':kwargs['creationflags']=subprocess.CREATE_NO_WINDOW
    else:kwargs['preexec_fn']=guard._posix_preexec(memory_mb,timeout_s)
    process=subprocess.Popen([getattr(sys,'_base_executable',None) or sys.executable,'-I','-B','-X','utf8','-c',bootstrap],**kwargs)
    job=None;started=time.perf_counter()
    try:
        if os.name=='nt':job=guard._WindowsJob(process,memory_mb,timeout_s)
        try:out,err=process.communicate(payload,timeout=timeout_s)
        except subprocess.TimeoutExpired:
            if job:job.close()
            process.kill();process.communicate();raise RuntimeError('Predictor worker timeout; preserve unknown fit evidence, never refit') from None
        if process.returncode:raise RuntimeError(f'Predictor worker failed exit{process.returncode}: {err.decode("utf-8",errors="replace")[-3000:]}')
        if len(out)>2*1024**2 or len(err)>128*1024:raise RuntimeError('Predictor worker output cap exceeded')
        response=json.loads(out.decode());response['prediction']=np.asarray(response['prediction'],float)
        expected_inputs={'X_train':array_receipt(X),'y_train':array_receipt(y),'X_eval':array_receipt(E),'evaluation_targets_received':False}
        if response.get('numeric_input_receipts')!=expected_inputs:raise RuntimeError('Actual worker numeric input hashes differ from submitted block')
        response['wall_seconds']=time.perf_counter()-started;response['validation']=validation
        if response['fit_started']!=response['fit_completed'] or not 1<=response['fit_completed']<=max_fits_per_block: raise RuntimeError('Incomplete/over-budget learner accounting')
        return response
    finally:
        if process.poll() is None:process.kill();process.wait()
        if job:job.close()


if __name__=='__main__' and '--worker' in sys.argv:
    _worker()
