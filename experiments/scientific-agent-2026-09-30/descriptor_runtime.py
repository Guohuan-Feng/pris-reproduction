"""Bounded numerical Python for agent-authored descriptors; not an OS sandbox.

The function receives a label-free structure only. No files, imports, subprocess,
network, reflection or arbitrary NumPy attributes are exposed. A worker timeout
limits accidental loops. Do not deploy this as a hostile-code security boundary.
"""
from __future__ import annotations
import ast
import json
import sys
from types import SimpleNamespace
import numpy as np

FUNCTIONS = ('array asarray abs sqrt exp log log1p maximum minimum clip where '
 'sum mean std var min max median quantile percentile sort argsort unique '
 'isfinite isnan nanmean nanstd nansum nanmin nanmax nanmedian '
 'concatenate stack column_stack bincount eye zeros ones full arange '
 'count_nonzero any all diff sign power round divide logical_and logical_or').split()
METHODS = set('get mean std var sum min max median any all astype reshape flatten ravel copy tolist append'.split())
BUILTINS = {k:v for k,v in dict(abs=abs,min=min,max=max,sum=sum,len=len,range=range,
 enumerate=enumerate,zip=zip,float=float,int=int,bool=bool,list=list,dict=dict,
 sorted=sorted,round=round).items()}
ALLOWED_NODES = {getattr(ast,n) for n in (
 'Module FunctionDef arguments arg Assign AugAssign Return If For Break Continue Pass Expr '
 'Name Load Store Constant Call keyword Attribute Subscript Slice List Tuple Dict '
 'ListComp DictComp GeneratorExp comprehension BinOp UnaryOp BoolOp Compare IfExp '
 'Add Sub Mult Div Pow Mod FloorDiv BitAnd BitOr UAdd USub Not Invert And Or '
 'Eq NotEq Lt LtE Gt GtE In NotIn Is IsNot').split()}
INPUT_KEYS = {'symbols','frac_coords','lattice','distance_matrix','atomic_numbers',
 'electronegativities','covalent_radii','neighbor_center','neighbor_index',
 'neighbor_distance','neighbor_image','n_sites','volume'}

def validate(code):
    if not isinstance(code,str) or len(code)>24000:
        raise ValueError('Code must be <=24000 characters')
    tree=ast.parse(code)
    if len(tree.body)!=1 or not isinstance(tree.body[0],ast.FunctionDef):
        raise ValueError('Provide exactly one function: def featurize(s): ...')
    fn=tree.body[0]
    if fn.name!='featurize' or fn.decorator_list or fn.returns:
        raise ValueError('Only undecorated featurize is accepted')
    if len(fn.args.args)!=1 or fn.args.args[0].arg!='s' or fn.args.defaults or fn.args.kw_defaults or fn.args.kwonlyargs or fn.args.vararg or fn.args.kwarg or fn.args.posonlyargs:
        raise ValueError('Function signature must be featurize(s)')
    for node in ast.walk(tree):
        if type(node) not in ALLOWED_NODES:
            raise ValueError(f'Unsupported Python node: {type(node).__name__}')
        if isinstance(node,ast.FunctionDef) and node is not fn:
            raise ValueError('No nested functions')
        if isinstance(node,(ast.Name,ast.arg)):
            name=node.id if isinstance(node,ast.Name) else node.arg
            if name.startswith('_'):
                raise ValueError('Private names are unavailable')
        if isinstance(node,ast.Attribute):
            if isinstance(node.ctx,ast.Store):
                raise ValueError('Attribute mutation is forbidden; numerical namespace is read-only')
            if node.attr.startswith('_') or node.attr not in set(FUNCTIONS)|METHODS|{'nan','inf','pi','shape','size'}:
                raise ValueError(f'Unsupported attribute: {node.attr}')
        if isinstance(node,ast.Call):
            if isinstance(node.func,ast.Name) and node.func.id not in BUILTINS:
                raise ValueError(f'Only numerical builtins are callable: {node.func.id}')
            if not isinstance(node.func,(ast.Name,ast.Attribute)):
                raise ValueError('Indirect calls are unavailable')
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and ('__' in node.value or len(node.value)>500):
            raise ValueError('Unsupported string constant')
    return tree

def compile_descriptor(code):
    tree=validate(code)
    numeric=SimpleNamespace(**{k:getattr(np,k) for k in FUNCTIONS},nan=np.nan,inf=np.inf,pi=np.pi)
    scope={'__builtins__':BUILTINS,'np':numeric}
    exec(compile(tree,'<agent_descriptor>','exec'),scope)
    return scope['featurize']

def compute(code,records):
    func=compile_descriptor(code)
    rows=[];names=None;errors=[]
    for record in records:
        s={k:v for k,v in record.items() if k in INPUT_KEYS}
        # JSON null site properties are explicitly mapped to NaN by np.array(dtype=float).
        with np.errstate(all='ignore'):
            result=func(s)
        if not isinstance(result,dict) or not 1<=len(result)<=12:
            raise ValueError('Return a dict of 1..12 scalar descriptors')
        current=list(result)
        if any(not isinstance(k,str) or not k.replace('_','').isalnum() or len(k)>64 or k.startswith('_') for k in current):
            raise ValueError('Use simple non-private descriptor names <=64 characters')
        if any(k in {'material_id','formula','chemical_system','composition_signature','split','formation_energy_per_atom','energy_above_hull'} or k.startswith(('comp_','relaxed_')) for k in current):
            raise ValueError('Descriptor names must not overwrite identity, targets or raw features')
        if names is None:names=current
        if names!=current:raise ValueError('All rows must return the same ordered descriptor names')
        values={}
        for k,v in result.items():
            val=float(v)
            if np.isinf(val):raise ValueError(f'Infinite descriptor {k} on {record["material_id"]}')
            values[k]=val if np.isfinite(val) else None
        rows.append({'material_id':record['material_id'],**values})
    return {'descriptor_names':names,'rows':rows,'errors':errors}

if __name__=='__main__':
    payload=json.load(sys.stdin)
    result=compute(payload['code'],payload['records'])
    json.dump(result,sys.stdout,allow_nan=False,separators=(',',':'))
