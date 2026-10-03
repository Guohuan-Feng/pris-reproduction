"""Isolated engineering repair; no target-bearing files are opened."""
from __future__ import annotations
import copy
import csv
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
from pymatgen.core import Lattice, Structure

HERE = Path(__file__).resolve().parent
FROZEN = HERE.parents[1] / 'scientific_tc_2026-10-01'
sys.path.insert(0, str(FROZEN))
from descriptor_runtime import compute, validate
from check_representation import structure_from_record, record_from_structure, variants

ATOL = 1e-8
RTOL = 1e-7
INVARIANT = 'new4_direction_anis_invariant'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def comparison(old, new, names):
    rows = []
    for name in names:
        a, b = old[name], new[name]
        agrees = a is None and b is None if a is None or b is None else bool(np.isclose(a, b, atol=ATOL, rtol=RTOL))
        rows.append({'feature': name, 'before': a, 'after': b, 'passes': agrees,
                     'absolute_difference': None if a is None or b is None else float(abs(a-b))})
    return rows

def transformed_checks(code, record):
    baseline = compute(code, [record])['rows'][0]
    names = [key for key in baseline if key != 'material_id']
    items = []
    for kind, changed, details in variants(structure_from_record(record)):
        rebuilt = record_from_structure(record['material_id'], changed)
        result = compute(code, [rebuilt])['rows'][0]
        items.append({'transformation': kind, 'details': details,
                      'original_sites': record['n_sites'], 'transformed_sites': rebuilt['n_sites'],
                      'original_edges': len(record['neighbor_distance']), 'transformed_edges': len(rebuilt['neighbor_distance']),
                      'comparisons': comparison(baseline, result, names)})
    return items

def main():
    started = time.perf_counter()
    code_path = HERE / 'repair_descriptor.py'
    old_path = FROZEN / 'experiments/E04/descriptor.py'
    code = code_path.read_text(encoding='utf-8')
    old_code = old_path.read_text(encoding='utf-8')
    validate(code)
    sources = [old_path, FROZEN/'descriptor_runtime.py', FROZEN/'check_representation.py',
               FROZEN/'data/split_assignments.csv', FROZEN/'data/descriptor_development.jsonl.gz',
               FROZEN/'data/descriptor_retrospective_test.jsonl.gz']
    before_hashes = {str(path.relative_to(FROZEN)).replace('\\', '/'): sha(path) for path in sources}
    with (FROZEN/'data/split_assignments.csv').open(encoding='utf-8', newline='') as stream:
        assignments = list(csv.DictReader(stream))
    split_by_id = {row['material_id']: row['split'] for row in assignments}
    train_ids = {mid for mid, role in split_by_id.items() if role == 'train'}
    all_records = []
    for name in ['descriptor_development.jsonl.gz', 'descriptor_retrospective_test.jsonl.gz']:
        with gzip.open(FROZEN/'data'/name, 'rt', encoding='utf-8') as stream:
            all_records.extend(json.loads(line) for line in stream)
    assert len(all_records) == len(assignments) == 5773
    assert {r['material_id'] for r in all_records} == set(split_by_id)
    assert not any(set(r) & {'tc', 'class', 'formula', 'group', 'parent_id'} for r in all_records)
    all_records.sort(key=lambda record: record['material_id'])
    repaired_rows, old_rows = [], []
    for offset in range(0, len(all_records), 100):
        batch = all_records[offset:offset+100]
        repaired_rows.extend(compute(code, batch)['rows'])
        old_rows.extend(compute(old_code, batch)['rows'])
    names = [key for key in repaired_rows[0] if key != 'material_id']
    assert len(names) == 12
    names11 = [name for name in names if name != INVARIANT]
    full = pd.DataFrame(repaired_rows)
    full.to_csv(HERE/'features12.csv.gz', index=False, compression={'method':'gzip','mtime':0})
    full[['material_id', *names11]].to_csv(HERE/'features11.csv.gz', index=False, compression={'method':'gzip','mtime':0})
    changes = []
    records_by_id = {record['material_id']:record for record in all_records}
    changed_ids = set()
    for old, repaired in zip(old_rows, repaired_rows):
        assert old['material_id'] == repaired['material_id']
        for item in comparison(old, repaired, names11):
            if not item['passes']:
                record = records_by_id[old['material_id']]
                distances = np.array(record['neighbor_distance'])
                assert not np.any(distances <= 3.5)
                assert item['before'] == 0.0 and item['after'] is None
                assert item['feature'] in {'new4_bondratio_mean','new4_bondratio_std','new4_Xgradient','new4_Zgradient'}
                changed_ids.add(old['material_id'])
                changes.append({'material_id': old['material_id'], 'reason':'No <= 3.5 A neighbors: undefined moment changed from zero placeholder to null.', **item})
    pools = {'ordered': [], 'disordered': []}
    for record in all_records:
        if record['material_id'] in train_ids and record['n_sites'] <= 50:
            structure = structure_from_record(record)
            pools['ordered' if structure.is_ordered else 'disordered'].append(record)
    chosen = [(kind, row) for kind in ['ordered', 'disordered'] for row in pools[kind][:4]]
    assert len(chosen) == 8
    representation = []
    old_replay = []
    cached = pd.read_csv(FROZEN/'experiments/E04/development_descriptors.csv.gz').set_index('material_id')
    for kind, record in chosen:
        old_values = compute(old_code, [record])['rows'][0]
        expected = {'material_id': record['material_id'], **cached.loc[record['material_id']].to_dict()}
        expected = {k: None if k != 'material_id' and not np.isfinite(v) else v for k,v in expected.items()}
        old_replay.append({'material_id': record['material_id'], 'comparisons':comparison(old_values, expected, [k for k in old_values if k!='material_id'])})
        representation.append({'material_id': record['material_id'], 'kind': kind,
                               'n_sites': record['n_sites'], 'checks': transformed_checks(code, record)})
    boundary = []
    for occupancy in [.1, .01]:
        low = record_from_structure('synthetic_low_occupancy_' + str(occupancy), Structure(Lattice.cubic(3), [{'Si':occupancy}], [[0,0,0]]))
        old_value = compute(old_code, [low])['rows'][0]
        fixed_value = compute(code, [low])['rows'][0]
        checks = transformed_checks(code, low)
        assert np.isclose(fixed_value['new4_nearest_mean'], 3, atol=ATOL)
        assert np.isclose(fixed_value['new4_bondratio_mean'], 3/(2*low['covalent_radii'][0]), atol=ATOL)
        assert np.isclose(fixed_value[INVARIANT], 0, atol=ATOL)
        boundary.append({'case':'low_absolute_occupancy', 'occupancy':occupancy,
                         'old_values':old_value, 'repaired_values':fixed_value, 'checks':checks})
    sparse = record_from_structure('synthetic_no_edges', Structure(Lattice.cubic(100), [{'Si':.1}], [[0,0,0]]))
    sparse_value = compute(code, [sparse])['rows'][0]
    expected_nulls = ['new4_bondratio_mean','new4_bondratio_std','new4_Xgradient','new4_Zgradient',INVARIANT,'new4_nearest_mean','new4_nearest_std']
    assert all(sparse_value[name] is None for name in expected_nulls)
    assert sparse_value['new4_bondcount32'] == sparse_value['new4_coord_std'] == 0
    boundary.append({'case':'no_periodic_edges_in_6_A', 'values':sparse_value, 'expected_nulls':expected_nulls, 'passes':True})
    for case, lattice, expected in [('collinear',Lattice.orthorhombic(3,100,100),1.0),
                                    ('planar',Lattice.orthorhombic(3,3,100),.25)]:
        analytic = record_from_structure('synthetic_direction_'+case, Structure(lattice, [{'Si':1}], [[0,0,0]]))
        value = compute(code, [analytic])['rows'][0]
        assert np.isclose(value[INVARIANT], expected, atol=ATOL)
        boundary.append({'case':'analytic_direction_'+case, 'expected_anisotropy':expected,
                         'values':value, 'checks':transformed_checks(code, analytic), 'passes':True})
    missing = record_from_structure('synthetic_missing_X', Structure(Lattice.cubic(3), [{'He':1}], [[0,0,0]]))
    missing_value = compute(code, [missing])['rows'][0]
    assert missing_value['new4_Xgradient'] is None
    unknown_radius = copy.deepcopy(chosen[0][1])
    unknown_radius['material_id'] = 'synthetic_missing_radius'
    unknown_radius['covalent_radii'] = [None]*unknown_radius['n_sites']
    unknown_radius['species_radius'] = [None]*len(unknown_radius['species_radius'])
    missing_radius_value = compute(code, [unknown_radius])['rows'][0]
    assert missing_radius_value['new4_bondratio_mean'] is None
    assert missing_radius_value['new4_bondratio_std'] is None
    assert all(value is None or isinstance(value, (float,str)) for value in missing_radius_value.values())
    boundary.append({'case':'unknown_X_and_radius_propagate_null', 'unknown_X_values':missing_value, 'unknown_radius_values':missing_radius_value, 'passes':True})
    rejected = []
    invalid = copy.deepcopy(chosen[0][1])
    invalid['species_occupancy'][0] = -1.0
    for case, records in [('negative_occupancy',[invalid]), ('duplicate_material_id',[chosen[0][1],chosen[0][1]])]:
        try:
            compute(code, records)
        except ValueError as exc:
            rejected.append({'case':case, 'exception':str(exc), 'passes':True})
        else:
            raise AssertionError(case+' was not rejected')
    flat = [item for record in representation for check in record['checks'] for item in check['comparisons']]
    boundary_flat = [item for case in boundary for check in case.get('checks',[]) for item in check['comparisons']]
    failures = [item for item in flat+boundary_flat if not item['passes']]
    original_replay_failures = [item for record in old_replay for item in record['comparisons'] if not item['passes']]
    after_hashes = {str(path.relative_to(FROZEN)).replace('\\','/'):sha(path) for path in sources}
    assert after_hashes == before_hashes
    summary = {'rows':len(full), 'descriptor_columns12':len(names), 'descriptor_columns11':len(names11),
               'training_structures_audited':len(chosen), 'training_representation_comparisons':len(flat),
               'synthetic_representation_comparisons':len(boundary_flat),
               'representation_failures':len(failures), 'old_descriptor_replay_failures':len(original_replay_failures),
               'shared_feature_value_changes_on_full_snapshot':len(changes),
               'shared_feature_changed_materials':len(changed_ids),
               'shared_feature_changed_materials_by_role':{role:sum(split_by_id[mid]==role for mid in changed_ids) for role in sorted(set(split_by_id.values()))},
               'unexpected_shared_feature_changes':0,
               'feature_null_counts':{name:int(full[name].isna().sum()) for name in names},
               'source_files_unchanged':after_hashes==before_hashes}
    audit = {'completed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
             'scope':'Engineering repair before V2 modeling. Eight TRAIN structures used for representation checks. All 5,773 target-free geometries used only for feature precomputation. No target-bearing CSV or historical test results opened.',
             'descriptor_design':{'normalization':'Every positive occupancy sum is used directly, with no lower bound clamp.',
                 'direction':'Q = sum(w * u u^T) / sum(w), u = displacement / actual positive edge distance; anisotropy = (3 tr(Q^2) - 1)/2, clipped only for floating error to [0,1]. Isotropic 0, collinear 1.',
                 'undefined_moments':'A moment with zero valid weight is null; coordination and bond counts can be zero. Missing radius propagates null through bond ratio; no unknown-species renormalization.',
                 'feature_count':'12 retains invariant anisotropy; 11 drops only that column.'},
             'selection_rule':'First four ordered and first four disordered TRAIN material IDs ascending, n_sites <= 50; no label selection.',
             'atol':ATOL, 'rtol':RTOL, 'source_sha256':before_hashes,
             'output_sha256':{name:sha(HERE/name) for name in ['repair_descriptor.py','features12.csv.gz','features11.csv.gz','prepare_and_audit.py']},
             'summary':summary, 'actual_common_feature_changes':changes,
             'training_representation':representation, 'original_descriptor_replay':old_replay,
             'synthetic_boundary_checks':boundary, 'invalid_input_checks':rejected,
             'limitations':['Finite representation transformations do not prove universal invariance.',
                 'Coordination at sharp 3.2/3.5 A boundaries can be sensitive to distance roundoff.',
                 'The radius/distance floor constants inherited in bond ratio/chemistry gradients are unchanged.',
                 'Previously viewed retrospective test is not fresh evidence; no predictive result claimed here.'],
             'elapsed_seconds':time.perf_counter()-started}
    (HERE/'audit.json').write_text(json.dumps(audit, indent=2, allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))
    assert not failures and not original_replay_failures

if __name__ == '__main__':
    main()
