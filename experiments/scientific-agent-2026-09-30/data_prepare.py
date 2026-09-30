"""Prepare a target-independent, fresh MP scientific-agent cohort.

No model calls or evaluation. Test labels are written once, hashed as bytes,
and never reopened. All exposed structural records exclude source energies.
"""
from __future__ import annotations
import sys
sys.dont_write_bytecode=True
import gzip, hashlib, importlib.metadata, json, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd
from pymatgen.core import Composition, Structure
from pymatgen.entries.computed_entries import ComputedEntry
from pymatgen.analysis.molecule_structure_comparator import CovalentRadius
from sklearn.model_selection import GroupShuffleSplit

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=HERE/'data'
PRIOR=ROOT/'outputs/pris_incremental_rules_2026-09-30'
OLD=ROOT/'outputs/pris_mp_rules_2026-09-30/data'
RAW=ROOT/'work/mp_rule_pilot/raw'
CSV=RAW/'2025-02-01-mp-energies.csv.gz'
CSE=RAW/'2023-02-07-mp-computed-structure-entries.json.gz'
REF=RAW/'2023-02-07-mp-elemental-reference-entries.json.gz'
sys.path.insert(0,str(OLD))
from prepare_mp import composition_features, geometry
from stream_cse import iter_entries

SEED='scientific-agent-20260930-v1'
N=3600
CANDIDATE_BUFFER=400
TARGETS=['formation_energy_per_atom','energy_above_hull']
FEATURES=json.loads((PRIOR/'allowed_features.json').read_text(encoding='utf-8'))
FAMILIES={
 'comp_halogen_fraction':[9,17,35,53,85],
 'comp_chalcogen_fraction':[8,16,34,52,84],
 'comp_alkali_alkaline_fraction':[3,4,11,12,19,20,37,38,55,56,87,88],
 'comp_transition_fraction':list(range(21,31))+list(range(39,49))+list(range(72,81))}

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()

def dump(name,obj):
 (OUT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')

def seed(name):return int.from_bytes(hashlib.sha256((SEED+':'+name).encode()).digest()[:4],'little')

def system(comp):return '-'.join(sorted(e.symbol for e in comp.elements))

def signature(comp):
 return json.dumps(sorted((e.symbol,round(comp.get_atomic_fraction(e),10)) for e in comp.elements),separators=(',',':'))

def structural_record(mid,s):
 symbols=[site.specie.symbol for site in s]
 radii=np.array([CovalentRadius.radius[x] for x in symbols],dtype=float)
 matrix=np.asarray(s.distance_matrix,dtype=float)
 # A complete sphere of radius min(a,b,c) includes a shortest nonzero
 # lattice translation, even for skew cells. Its diagonal is explicitly
 # nonzero so one-site cells retain their closest physical self-image.
 _,lattice_distances,_,_=s.lattice.get_points_in_sphere([[0,0,0]],[0,0,0],min(s.lattice.abc)+1e-7,zip_results=False)
 self_distance=float(np.min(np.asarray(lattice_distances)[np.asarray(lattice_distances)>1e-8]))
 np.fill_diagonal(matrix,self_distance)
 center,other,images,distances=s.get_neighbor_list(6.0,numerical_tol=1e-8,exclude_self=True)
 order=np.lexsort((images[:,2],images[:,1],images[:,0],other,distances,center))
 center,other,images,distances=[np.asarray(x)[order] for x in [center,other,images,distances]]
 assert np.isfinite(matrix).all() and (matrix>0).all() and np.allclose(matrix,matrix.T,atol=1e-8)
 assert (distances>0).all() and (distances<=6.0+1e-8).all()
 assert not np.any((center==other)&np.all(images==0,axis=1))
 # Verify neighbor image convention independently against lattice vectors.
 cart=(s.frac_coords[other]+images-s.frac_coords[center])@s.lattice.matrix
 assert np.allclose(np.linalg.norm(cart,axis=1),distances,atol=1e-7,rtol=1e-8)
 en=[float(site.specie.X) if site.specie.X is not None and np.isfinite(site.specie.X) else None for site in s]
 rec={'material_id':mid,'n_sites':len(s),'volume':float(s.volume),
  'symbols':symbols,'frac_coords':s.frac_coords.tolist(),'lattice':s.lattice.matrix.tolist(),
  'distance_matrix':matrix.tolist(),'atomic_numbers':[int(site.specie.Z) for site in s],
  'electronegativities':en,'covalent_radii':radii.tolist(),
  'neighbor_center':center.astype(int).tolist(),'neighbor_index':other.astype(int).tolist(),
  'neighbor_distance':distances.tolist(),'neighbor_image':images.astype(int).tolist()}
 return rec,matrix,radii

def main():
 started=time.perf_counter();OUT.mkdir(parents=True,exist_ok=True)
 if (OUT/'dataset_manifest.json').exists():raise RuntimeError('Frozen dataset exists; refusing overwrite')
 assert len(FEATURES)==30 and len(set(FEATURES))==30
 meta_path=PRIOR/'data/source_identity_inventory.csv.gz'
 meta=pd.read_csv(meta_path)
 old_split=pd.read_csv(PRIOR/'data/split_assignments.csv',usecols=['material_id','chemical_system'])
 prior_ids=pd.read_csv(PRIOR/'data/excluded_prior_ids.csv',usecols=['material_id'])
 prior_systems=pd.read_csv(PRIOR/'data/excluded_chemical_systems.csv',usecols=['chemical_system'])
 excluded_ids=set(prior_ids.material_id)|set(old_split.material_id)
 excluded_systems=set(prior_systems.chemical_system)|set(old_split.chemical_system)
 energy_ids=set(pd.read_csv(CSV,usecols=['material_id']).material_id)
 assert meta.material_id.is_unique
 eligible=meta[meta.material_id.isin(energy_ids)&~meta.material_id.isin(excluded_ids)&~meta.chemical_system.isin(excluded_systems)&meta.is_ordered&meta.n_sites.le(60)&meta.within_Z1_94].copy()
 eligible['selection_sha256']=eligible.material_id.map(lambda m:hashlib.sha256((SEED+m).encode()).hexdigest())
 eligible=eligible.sort_values(['selection_sha256','material_id']).reset_index(drop=True)
 eligible['eligible_rank']=np.arange(1,len(eligible)+1)
 if len(eligible)<N+CANDIDATE_BUFFER:raise RuntimeError('Insufficient fresh eligible candidates')
 candidates=eligible.head(N+CANDIDATE_BUFFER).copy();candidate_ids=set(candidates.material_id)
 pd.DataFrame({'material_id':sorted(excluded_ids)}).to_csv(OUT/'excluded_prior_ids.csv',index=False)
 pd.DataFrame({'chemical_system':sorted(excluded_systems)}).to_csv(OUT/'excluded_chemical_systems.csv',index=False)
 candidates.to_csv(OUT/'candidate_ids.csv',index=False)
 rows={};source_entries={};rejections=[];seen=set()
 temporary=OUT/'_candidate_descriptors.jsonl.gz'
 print(json.dumps({'eligible_rows':len(eligible),'eligible_systems':int(eligible.chemical_system.nunique()),'candidate_prefix':len(candidates),'requested_complete_rows':N}),flush=True)
 with gzip.open(temporary,'wt',encoding='utf-8') as target:
  for mid,entry,_ in iter_entries(CSE):
   if mid not in candidate_ids:continue
   assert mid not in seen;seen.add(mid)
   with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    try:
     s=Structure.from_dict(entry['structure']);comp=s.composition.element_composition
     assert s.is_ordered and len(s)<=60
     assert comp.almost_equals(Composition(entry['composition']).element_composition,rtol=1e-8,atol=1e-8)
     values=composition_features(comp);values.update(geometry(s))
     for name,zs in FAMILIES.items():values[name]=float(sum(values[f'comp_fraction_Z{z:03d}'] for z in zs))
     values['comp_electronegativity_range']=values['comp_electronegativity_max']-values['comp_electronegativity_min']
     values['comp_radius_cv']=values['comp_atomic_radius_std']/values['comp_atomic_radius_mean'] if values['comp_atomic_radius_mean']>0 else np.nan
     missing=[f for f in FEATURES if not np.isfinite(values[f])]
     if missing:
      rejections.append({'material_id':mid,'reason':'nonfinite_original_30_features','features':missing});continue
     rec,matrix,radii=structural_record(mid,s)
     assert np.isclose(matrix.min(),values['relaxed_min_distance_A'],atol=1e-7)
     assert np.isclose((matrix/(radii[:,None]+radii[None,:])).min(),values['relaxed_min_covalent_ratio'],atol=1e-7)
     assert np.isclose(rec['volume']/rec['n_sites'],values['relaxed_volume_per_atom_A3'],atol=1e-8)
     rows[mid]={'material_id':mid,'formula':comp.reduced_formula,'chemical_system':system(comp),'composition_signature':signature(comp),**{f:values[f] for f in FEATURES}}
     ce=ComputedEntry.from_dict(entry)
     # This internal compatibility tuple is not exported as a descriptor.
     source_entries[mid]=(float(ce.energy_per_atom),dict(comp.get_el_amt_dict()),ce.parameters.get('run_type'))
     target.write(json.dumps(rec,separators=(',',':'),allow_nan=False)+'\n')
    except Exception as exc:
     # Data errors are fatal; only missing original descriptors are an
     # explicitly authorized eligibility filter.
     raise RuntimeError(f'Unexpected structural failure for {mid}: {exc}') from exc
   if len(seen)%500==0:print(f'Structure records checked {len(seen)}/{len(candidates)}; missing-feature exclusions {len(rejections)}',flush=True)
 assert seen==candidate_ids
 chosen=candidates[candidates.material_id.isin(rows)].head(N).copy()
 if len(chosen)!=N:raise RuntimeError('Candidate buffer insufficient; no silent sampling adaptation')
 # Every earlier hash-ranked record has been assessed before freezing IDs.
 last_rank=int(chosen.eligible_rank.max())
 assert set(candidates[candidates.eligible_rank.le(last_rank)].material_id)<=seen
 chosen.insert(1,'sampling_rank',np.arange(1,N+1));chosen.to_csv(OUT/'selected_ids.csv',index=False)
 df=pd.DataFrame([rows[mid] for mid in chosen.material_id])
 assert df.chemical_system.tolist()==chosen.chemical_system.tolist()
 assert df.material_id.is_unique and np.isfinite(df[FEATURES].to_numpy(float)).all()
 assert not set(df.material_id)&excluded_ids and not set(df.chemical_system)&excluded_systems
 outer,test=next(GroupShuffleSplit(n_splits=1,test_size=.2,random_state=seed('outer')).split(df,groups=df.chemical_system))
 tr,va=next(GroupShuffleSplit(n_splits=1,test_size=.25,random_state=seed('inner')).split(df.iloc[outer],groups=df.chemical_system.iloc[outer]))
 parts={'train':outer[tr],'validation':outer[va],'test':test}
 split=df[['material_id','chemical_system','composition_signature']].copy();split['split']=''
 for role,idx in parts.items():split.loc[idx,'split']=role
 overlap={}
 for a,b in [('train','validation'),('train','test'),('validation','test')]:
  overlap[f'{a}__{b}']={key:len(set(split.iloc[parts[a]][key])&set(split.iloc[parts[b]][key])) for key in ['material_id','chemical_system','composition_signature']}
 assert all(v==0 for pair in overlap.values() for v in pair.values())
 df.to_csv(OUT/'features.csv.gz',index=False)
 split.to_csv(OUT/'split_assignments.csv',index=False)
 role_of=dict(zip(split.material_id,split.split));descriptor_counts={'development':0,'test':0};neighbors=0
 with gzip.open(temporary,'rt',encoding='utf-8') as source,gzip.open(OUT/'descriptor_development.jsonl.gz','wt',encoding='utf-8') as dev,gzip.open(OUT/'descriptor_test.jsonl.gz','wt',encoding='utf-8') as tst:
  for line in source:
   rec=json.loads(line);mid=rec['material_id']
   if mid not in role_of:continue
   role='test' if role_of[mid]=='test' else 'development'
   (tst if role=='test' else dev).write(line);descriptor_counts[role]+=1;neighbors+=len(rec['neighbor_distance'])
 assert sum(descriptor_counts.values())==N and descriptor_counts['test']==len(test)
 temporary.unlink()  # Own temporary, literal verified path in this data directory.
 # Identities, descriptor eligibility and splits are now frozen. Source
 # target checks only validate completeness/compatibility; never replace IDs.
 source=pd.read_csv(CSV).set_index('material_id');assert source.index.is_unique
 assert np.isfinite(source.loc[df.material_id,TARGETS].to_numpy(float)).all(), 'Missing selected target: stop, no replacement'
 with gzip.open(REF,'rt',encoding='utf-8') as f:ref=json.load(f)
 refs={el:ComputedEntry.from_dict(e).energy_per_atom for el,e in ref.items()}
 max_energy_diff=0.;max_formation_diff=0.;formula_missing=0
 for mid in df.material_id:
  energy,amounts,run_type=source_entries[mid];row=source.loc[mid];comp=Composition(amounts)
  e_diff=energy-float(row.energy_per_atom)
  f_diff=energy-sum(n*refs[e] for e,n in amounts.items())/sum(amounts.values())-float(row.formation_energy_per_atom)
  assert abs(e_diff)<1e-6 and abs(f_diff)<1e-6 and run_type==row.energy_type
  max_energy_diff=max(max_energy_diff,abs(e_diff));max_formation_diff=max(max_formation_diff,abs(f_diff))
  if pd.isna(row.formula):formula_missing+=1
  else:assert comp.fractional_composition.almost_equals(Composition(row.formula).fractional_composition,rtol=1e-8,atol=1e-8)
 labels=split.merge(source[TARGETS],left_on='material_id',right_index=True,validate='one_to_one')
 labels[labels.split.ne('test')].to_csv(OUT/'development.csv.gz',index=False)
 labels[labels.split.eq('test')].to_csv(OUT/'sealed_test.csv.gz',index=False)
 old_schema=json.loads((PRIOR/'data/feature_schema.json').read_text(encoding='utf-8'))
 dump('feature_schema.json',{'features':FEATURES,'feature_count':30,'definitions':{f:old_schema['definitions'][f] for f in FEATURES},'id':'material_id','group':'chemical_system','split_column':'split','targets':{'formation_energy_per_atom':'eV/atom; released MP GGA/GGA+U, MP2020 convention','energy_above_hull':'native own-hull eV/atom; on-hull label is <=1e-8'},'feature_file':'features.csv.gz','development_targets':'development.csv.gz','sealed_test_targets':'sealed_test.csv.gz','missing_policy':'Exclude nonfinite original30 descriptors before splitting; never target-filter or replace after splitting.'})
 dump('descriptor_schema.json',{'record_id':'material_id','development_file':'descriptor_development.jsonl.gz','test_file':'descriptor_test.jsonl.gz','test_policy':'Must not be read by development server; available only after frozen selection. No energies or targets in either descriptor file.','cell':'Original supplied DFT-relaxed ordered cell; no standardization or idealization.','indexing':'Zero-based site indices. All site lists follow the same original site order.','fields':{
  'material_id':'Exact MP identity, string','n_sites':'Number of ordered sites, integer','volume':'Cell volume, angstrom^3','symbols':'Element symbols, length N','atomic_numbers':'Integer atomic numbers, length N','frac_coords':'N x3 fractional coordinates; Cartesian = fractional @ lattice','lattice':'3x3 row lattice vectors, angstrom','distance_matrix':'N xN nearest periodic pair distance in angstrom. Offdiag=min over lattice translations. Diag=shortest NONZERO lattice translation, not zero self distance. Does not encode image multiplicities and cannot alone define coordination.','electronegativities':'Pauling electronegativities from Pymatgen Element.X, length N; null if unknown. Aggregate original features renormalize available element values.','covalent_radii':'Pymatgen CovalentRadius.radius element table, angstrom, same table as original geometric features; not atomic_radius field.','neighbor_center':'Central site i for every directed periodic neighbor edge within6angstrom','neighbor_index':'Neighbor site j within original cell for each edge','neighbor_image':'Integer3-vector image of neighbor j: displacement=(frac[j]+image-frac[i])@lattice','neighbor_distance':'Distance in angstrom, same-length list as other neighbor fields; all images within6angstrom including nonzero self-images; zero-image same-site edge excluded.'},'neighbor_cutoff_A':6.0,'neighbor_numerical_tolerance_A':1e-8,'neighbor_limitation':'Complete finite-cutoff list, not unlimited-range electrostatics or arbitrary larger-cutoff coordination. Directed edge pairs and image multiplicities are retained.','source_has_targets':False})
 dump('feature_exclusions.json',{'candidate_prefix':len(candidates),'checked':len(seen),'missing_feature_exclusions':rejections,'excluded_before_selected_boundary':[r for r in rejections if r['material_id'] in set(candidates[candidates.eligible_rank.le(last_rank)].material_id)],'sampling_complete_prefix_last_rank':last_rank,'unexpected_failures':0})
 audit={'rows':N,'feature_count':30,'finite_feature_rows':N,'chemical_systems':int(df.chemical_system.nunique()),'split_counts':{r:{'rows':len(idx),'chemical_systems':int(df.iloc[idx].chemical_system.nunique())} for r,idx in parts.items()},'overlap':overlap,'prior_id_overlap':0,'prior_chemical_system_overlap':0,'descriptor_counts':descriptor_counts,'periodic_neighbor_edges':neighbors,'structure_composition_checks':N,'source_energy_compatibility_checks':N,'source_formula_missing':formula_missing,'max_abs_source_energy_difference_eV_atom':max_energy_diff,'max_abs_source_formation_difference_eV_atom':max_formation_diff,'target_summaries':'None computed, printed or exported. Test file not reopened after writing.','elapsed_seconds':time.perf_counter()-started}
 dump('preparation_audit.json',audit)
 sources=[CSV,CSE,REF,meta_path,PRIOR/'data/split_assignments.csv',PRIOR/'data/excluded_prior_ids.csv',PRIOR/'data/excluded_chemical_systems.csv',PRIOR/'allowed_features.json',OLD/'prepare_mp.py',OLD/'stream_cse.py']
 manifest={'dataset':'MP scientific-agent pilot','sampling_seed':SEED,'sampling':'SHA256(seed+material_id) rank; select first3600 with complete original30 features; missing-feature eligibility applied uniformly before any split. Candidate prefix inspected4000; every earlier hash rank checked. No target-value filtering.','ordered_maximum_original_sites':60,'seed_outer':seed('outer'),'seed_inner':seed('inner'),'nominal_group_fractions':{'train':.6,'validation':.2,'test':.2},'eligible_before_descriptor_check':len(eligible),'eligible_systems_before_descriptor_check':int(eligible.chemical_system.nunique()),'prior_excluded_ids':len(excluded_ids),'prior_excluded_systems':len(excluded_systems),'audit':audit,'source_release':'Matbench Discovery Figshare22715158v38; CC BY4.0','source_doi':'https://doi.org/10.6084/m9.figshare.22715158.v38','source_energy_convention':'MP GGA/GGA+U with released MP2020 references; native own-hull energy, not decomposition_enthalpy.','source_hashes':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in sources},'preparation_sha256':sha(Path(__file__)),'files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(OUT.iterdir()) if p.is_file()},'package_versions':{p:importlib.metadata.version(p) for p in ['numpy','pandas','pymatgen','scikit-learn']},'limitations':['Released DFT-relaxed snapshot, not live full MP or pre-DFT prediction.','Prior chemical-system exclusions cover old MP cohorts and mapped3DSC parents; unmapped COD/WBM physical overlaps and pretrained-model exposure not established.','Thermodynamic native-hull label does not prove synthesizability.','Finite6angstrom neighbor range; missing elemental electronegativity may occur as null in raw inputs.']}
 dump('dataset_manifest.json',manifest)
 print(json.dumps(audit,indent=2),flush=True)

if __name__=='__main__':main()
