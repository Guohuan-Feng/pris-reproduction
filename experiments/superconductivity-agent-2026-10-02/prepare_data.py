"""Prepare isolated V2 inputs; never opens the retrospective target partition."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

SEED = 20261002

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')

def prepare(root, source=None):
    root = Path(root).resolve()
    source = Path(source) if source else root.parent / 'scientific_tc_2026-10-01'
    out = root / 'data'
    out.mkdir(exist_ok=True)
    if (out / 'data_audit.json').exists():
        audit = json.loads((out / 'data_audit.json').read_text(encoding='utf-8'))
        for name, digest in audit['prepared_sha256'].items():
            if sha(out / name) != digest:
                raise ValueError('Prepared data changed: ' + name)
        return audit
    schema = json.loads((source / 'data/feature_schema.json').read_text(encoding='utf-8'))
    raw = schema['raw_features']
    structural = schema['structure_features']
    labels = pd.read_csv(source / 'data/development.csv.gz', float_precision='round_trip')
    if set(labels.split) != {'train', 'validation'}:
        raise ValueError('Only original training and validation are permitted')
    features = pd.read_csv(source / 'data/features.csv.gz', float_precision='round_trip')
    repaired = pd.read_csv(root / 'repair/features12.csv.gz', float_precision='round_trip')
    rep11 = pd.read_csv(root / 'repair/features11.csv.gz', float_precision='round_trip')
    repaired_names = [x for x in repaired if x != 'material_id']
    repaired11_names = [x for x in rep11 if x != 'material_id']
    assert len(raw) == 109 and len(structural) == 28 and len(repaired_names) == 12 and len(repaired11_names) == 11
    assert set(repaired11_names) < set(repaired_names)
    for table in (labels, features, repaired, rep11):
        if not table.material_id.is_unique:
            raise ValueError('Duplicate record ID')
    if set(features.material_id) != set(repaired.material_id) or set(repaired.material_id) != set(rep11.material_id):
        raise ValueError('Repaired feature record mismatch')
    if not set(labels.material_id).issubset(set(features.material_id)):
        raise ValueError('Development label IDs missing from source features')
    aligned12 = repaired.set_index('material_id')
    aligned11 = rep11.set_index('material_id').loc[aligned12.index]
    if not np.allclose(aligned12[repaired11_names].to_numpy(), aligned11.to_numpy(), equal_nan=True, rtol=0, atol=0):
        raise ValueError('11-column ablation differs from corresponding 12-column inputs')
    frame = labels.merge(features, on='material_id', how='left', validate='one_to_one').merge(repaired, on='material_id', how='left', validate='one_to_one')
    train = frame[frame.split == 'train'].sort_values('row_id').reset_index(drop=True)
    validation = frame[frame.split == 'validation'].sort_values('row_id').reset_index(drop=True)
    if len(train) != 3764 or len(validation) != 869:
        raise ValueError('Frozen partition counts changed')
    overlap = {key: len(set(train[key]) & set(validation[key])) for key in ['group', 'chemical_system', 'parent_id', 'canonical_composition']}
    if any(overlap.values()):
        raise ValueError('Development partition leakage')
    for key in ['chemical_system', 'parent_id', 'canonical_composition']:
        if train.groupby(key, dropna=False).group.nunique().max() != 1:
            raise ValueError('Strict grouping broken for ' + key)
    if not np.isfinite(train[['tc', 'weight']].to_numpy()).all() or (train.tc < 0).any() or (train.weight <= 0).any():
        raise ValueError('Invalid training labels or weights')
    folds = np.full(len(train), -1, dtype=int)
    fold_audit = []
    for fold, (fit_idx, held_idx) in enumerate(GroupKFold(n_splits=3, shuffle=True, random_state=SEED).split(train, groups=train.group)):
        folds[held_idx] = fold
        assert not set(train.group.iloc[fit_idx]) & set(train.group.iloc[held_idx])
        fit_held_overlap = {key: len(set(train[key].iloc[fit_idx]) & set(train[key].iloc[held_idx])) for key in ['group', 'chemical_system', 'parent_id', 'canonical_composition']}
        if any(fit_held_overlap.values()):
            raise ValueError('Cross-fold linked-identity overlap')
        fold_audit.append({'fold': fold, 'fit_rows': len(fit_idx), 'held_rows': len(held_idx), 'fit_groups': int(train.group.iloc[fit_idx].nunique()), 'held_groups': int(train.group.iloc[held_idx].nunique()), 'fit_held_overlap': fit_held_overlap})
    assert (folds >= 0).all()
    # Validation targets are quarantined here for the final evaluation. Feedback never opens these files.
    train.to_csv(out / 'train.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
    validation.drop(columns=['tc']).to_csv(out / 'validation_inputs.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
    validation[['material_id', 'tc']].to_csv(out / 'validation_labels.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
    pd.DataFrame({'material_id': train.material_id, 'group': train.group, 'fold': folds}).to_csv(out / 'fold_assignments.csv', index=False)
    new_schema = {'id': 'material_id', 'target': 'tc', 'weight': 'weight', 'group': 'group', 'composition': raw, 'repair12': repaired_names, 'repair11': repaired11_names, 'structure28': structural,
                  'excluded_predictor_metadata': list(labels.columns), 'seed': SEED, 'folds': 3,
                  'inputs': {'composition': raw, 'composition_repaired': raw + repaired_names, 'diagnostic_repair11': raw + repaired11_names, 'reference_structure28': raw + structural}}
    save(out / 'schema.json', new_schema)
    names = ['train.csv.gz', 'validation_inputs.csv.gz', 'validation_labels.csv.gz', 'fold_assignments.csv', 'schema.json']
    audit = {'scope': 'Original 3,764 training records provide all adaptive feedback. Original 869 validation records are quarantined for one post-freeze development evaluation. No retrospective labels read.',
             'train_rows': len(train), 'validation_rows': len(validation), 'train_groups': int(train.group.nunique()), 'validation_groups': int(validation.group.nunique()),
             'partition_overlap': overlap, 'folds': fold_audit,
             'source_sha256': {str(p.relative_to(source)): sha(p) for p in [source / 'data/development.csv.gz', source / 'data/features.csv.gz', source / 'data/feature_schema.json']},
             'repair_sha256': {str(p.relative_to(root)): sha(p) for p in [root / 'repair/features12.csv.gz', root / 'repair/features11.csv.gz']},
             'prepared_sha256': {name: sha(out / name) for name in names}}
    save(out / 'data_audit.json', audit)
    return audit

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--root', default=str(Path(__file__).parent))
    args = p.parse_args()
    print(json.dumps(prepare(args.root), indent=2))
