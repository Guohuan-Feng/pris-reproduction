"""Bounded, train-only V2 model workbench. No historical test access."""
from __future__ import annotations
import os
for _name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_name] = '1'
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import time
import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits
from prepare_data import prepare as prepare_data, save, sha, SEED

MODELS = ('extra_trees', 'hist_gradient_boosting')
TARGETS = ('raw', 'log1p')
INPUTS = ('composition', 'composition_repaired')
ROUTES = {'chemistry': ('cu_o', 'fe_anion', 'other'), 'kmeans3': ('cluster0', 'cluster1', 'cluster2')}
PARAMETERS = {
    'extra_trees': {'n_estimators': 160, 'min_samples_leaf': 2, 'max_features': 1.0, 'random_state': SEED, 'n_jobs': 1},
    'hist_gradient_boosting': {'max_iter': 160, 'max_leaf_nodes': 15, 'min_samples_leaf': 20, 'learning_rate': .08, 'l2_regularization': 1., 'early_stopping': False, 'random_state': SEED}}

def utc():
    return datetime.now(timezone.utc).isoformat()

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def canonical(spec):
    return json.dumps(spec, sort_keys=True, separators=(',', ':'))

def validate_spec(spec, allow_reference=False):
    if not isinstance(spec, dict) or set(spec) != {'input', 'routing', 'global', 'experts'}:
        raise ValueError('Specification must contain exactly input, routing, global, experts')
    allowed_inputs = INPUTS + (('diagnostic_repair11', 'reference_structure28') if allow_reference else ())
    if spec['input'] not in allowed_inputs or spec['routing'] not in ('global', 'chemistry', 'kmeans3'):
        raise ValueError('Unknown input or routing')
    def config(config):
        if not isinstance(config, dict) or set(config) != {'model', 'target'} or config['model'] not in MODELS or config['target'] not in TARGETS:
            raise ValueError('Each model config requires model and target from the bounded menu')
    config(spec['global'])
    if not isinstance(spec['experts'], dict):
        raise ValueError('Experts must be a mapping')
    if spec['routing'] == 'global':
        if spec['experts']:
            raise ValueError('Global routing requires empty experts')
    elif not spec['experts'] or not set(spec['experts']).issubset(ROUTES[spec['routing']]):
        raise ValueError('Routed strategy requires at least one valid expert route')
    for item in spec['experts'].values():
        config(item)
    return json.loads(canonical(spec))

def fit_preprocessing(x, names):
    x = np.asarray(x, float)
    if x.ndim != 2 or x.shape[1] != len(names) or np.isinf(x).any() or len(x) == 0:
        raise ValueError('Invalid training feature matrix')
    all_missing = np.isnan(x).all(axis=0)
    medians = np.array([0. if all_missing[j] else np.nanmedian(x[:, j]) for j in range(x.shape[1])])
    indicators = np.flatnonzero(np.isnan(x).any(axis=0) & ~all_missing)
    filled = np.where(np.isnan(x), medians, x)
    if len(indicators):
        filled = np.column_stack([filled, np.isnan(x[:, indicators]).astype(float)])
    expanded = list(names) + [names[j] + '__missing' for j in indicators]
    keep = np.flatnonzero(np.ptp(filled, axis=0) > 1e-12)
    if not len(keep):
        raise ValueError('No variable training predictors')
    state = {'columns': list(names), 'expanded_columns': expanded, 'medians': medians.tolist(), 'missing_indicator_indices': indicators.tolist(), 'kept_indices': keep.tolist(),
             'all_missing_columns': [names[j] for j in np.flatnonzero(all_missing)], 'dropped_constant_columns': [expanded[j] for j in range(len(expanded)) if j not in keep]}
    return np.ascontiguousarray(filled[:, keep]), state

def transform(x, state):
    x = np.asarray(x, float)
    if x.ndim != 2 or x.shape[1] != len(state['columns']) or np.isinf(x).any():
        raise ValueError('Invalid prediction feature matrix')
    filled = np.where(np.isnan(x), np.asarray(state['medians']), x)
    idx = state['missing_indicator_indices']
    if idx:
        filled = np.column_stack([filled, np.isnan(x[:, idx]).astype(float)])
    return np.ascontiguousarray(filled[:, state['kept_indices']])

def inverse_target(pred, target):
    pred = np.asarray(pred, float)
    out = np.maximum(pred, 0) if target == 'raw' else np.expm1(np.maximum(pred, 0))
    if not np.isfinite(out).all():
        raise ValueError('Nonfinite model prediction')
    return out

def fit_estimator(x, y, w, names, config):
    z, state = fit_preprocessing(x, names)
    y, w = np.asarray(y, float), np.asarray(w, float)
    if not np.isfinite(y).all() or not np.isfinite(w).all() or np.any(y < 0) or np.any(w <= 0):
        raise ValueError('Invalid training target or weight')
    cls = ExtraTreesRegressor if config['model'] == 'extra_trees' else HistGradientBoostingRegressor
    estimator = cls(**PARAMETERS[config['model']])
    target = y if config['target'] == 'raw' else np.log1p(y)
    with threadpool_limits(limits=1):
        estimator.fit(z, target, sample_weight=w)
    return {'estimator': estimator, 'preprocessing': state, 'config': dict(config), 'training_rows': len(y)}

def predict_estimator(bundle, x):
    with threadpool_limits(limits=1):
        pred = bundle['estimator'].predict(transform(x, bundle['preprocessing']))
    return inverse_target(pred, bundle['config']['target'])

def chemistry_routes(frame):
    def fraction(z):
        name = 'comp_fraction_Z%03d' % z
        return frame[name].fillna(0).to_numpy() if name in frame else np.zeros(len(frame))
    cu_o = (fraction(29) > 1e-12) & (fraction(8) > 1e-12)
    fe_anion = (fraction(26) > 1e-12) & (sum(fraction(z) for z in [15, 33, 16, 34, 52]) > 1e-12)
    return np.where(cu_o, 'cu_o', np.where(fe_anion, 'fe_anion', 'other'))

def cluster_mapping(centers_z):
    order = sorted(range(len(centers_z)), key=lambda i: (float(centers_z[i]), i))
    return {old: 'cluster%d' % rank for rank, old in enumerate(order)}

def fit_router(frame, composition_names, routing):
    if routing in ('global', 'chemistry'):
        return {'routing': routing}
    x = frame[composition_names].to_numpy(float)
    medians = np.array([np.nanmedian(x[:, j]) if np.isfinite(x[:, j]).any() else 0. for j in range(x.shape[1])])
    x = np.where(np.isnan(x), medians, x)
    scaler = StandardScaler().fit(x)
    with threadpool_limits(limits=1):
        kmeans = KMeans(n_clusters=3, n_init=10, max_iter=300, random_state=SEED).fit(scaler.transform(x))
    centroids = scaler.inverse_transform(kmeans.cluster_centers_)
    z_idx = composition_names.index('comp_Z_mean')
    return {'routing': routing, 'columns': list(composition_names), 'medians': medians, 'scaler': scaler, 'kmeans': kmeans,
            'mapping': cluster_mapping(centroids[:, z_idx]), 'training_rows': len(frame), 'centroid_comp_Z_mean': centroids[:, z_idx].tolist()}

def route_labels(router, frame):
    if router['routing'] == 'global':
        return np.full(len(frame), 'global', dtype=object)
    if router['routing'] == 'chemistry':
        return chemistry_routes(frame)
    x = frame[router['columns']].to_numpy(float)
    x = np.where(np.isnan(x), router['medians'], x)
    with threadpool_limits(limits=1):
        labels = router['kmeans'].predict(router['scaler'].transform(x))
    return np.array([router['mapping'][int(label)] for label in labels])

def eligible_expert(rows, groups):
    return rows >= 80 and groups >= 12

def fit_pipeline(frame, schema, spec):
    spec = validate_spec(spec, allow_reference=True)
    names = schema['inputs'][spec['input']]
    x = frame[names].to_numpy(float)
    start = time.monotonic()
    global_model = fit_estimator(x, frame.tc, frame.weight, names, spec['global'])
    router = fit_router(frame, schema['composition'], spec['routing'])
    routes = route_labels(router, frame)
    experts, summaries = {}, {}
    fit_count = 1
    for route in (() if spec['routing'] == 'global' else ROUTES[spec['routing']]):
        idx = routes == route
        rows, groups = int(idx.sum()), int(frame.group[idx].nunique())
        configured = route in spec['experts']
        active = configured and eligible_expert(rows, groups)
        summaries[route] = {'training_rows': rows, 'training_groups': groups, 'configured': configured, 'active_expert': active,
                            'fallback_reason': None if active else ('unspecified_route' if not configured else 'insufficient_rows_or_groups')}
        if active:
            experts[route] = fit_estimator(x[idx], frame.tc.to_numpy()[idx], frame.weight.to_numpy()[idx], names, spec['experts'][route])
            fit_count += 1
    return {'specification': spec, 'input_columns': names, 'global': global_model, 'router': router, 'experts': experts,
            'training_routes': summaries, 'fit_count': fit_count, 'elapsed_fit_seconds': time.monotonic() - start}

def predict_pipeline(bundle, frame):
    x = frame[bundle['input_columns']].to_numpy(float)
    pred = predict_estimator(bundle['global'], x)
    routes = route_labels(bundle['router'], frame)
    used = np.full(len(frame), 'global_fallback', dtype=object)
    if bundle['specification']['routing'] == 'global':
        used[:] = 'global'
    for route, expert in bundle['experts'].items():
        idx = routes == route
        if idx.any():
            pred[idx] = predict_estimator(expert, x[idx])
            used[idx] = 'expert_' + route
    return pred, routes, used

def metrics(y, p, w, groups=None):
    y, p, w = [np.asarray(v, float) for v in (y, p, w)]
    if len(y) == 0 or len(y) != len(p) or len(y) != len(w) or not np.isfinite(np.column_stack([y, p, w])).all() or np.any(y < 0) or np.any(p < 0) or np.any(w <= 0):
        raise ValueError('Metrics require aligned finite nonnegative targets/predictions and positive weights')
    groups = np.arange(len(y)).astype(str) if groups is None else np.asarray(groups, str)
    if len(groups) != len(y):
        raise ValueError('Misaligned group vector')
    def one(mask):
        if not mask.any():
            return {'rows': 0, 'groups': 0, 'weight_sum': 0., 'MAE_K': None, 'RMSE_K': None, 'MSLE_log1p': None, 'bias_K': None}
        a, b, c = y[mask], p[mask], w[mask]
        return {'rows': int(mask.sum()), 'groups': int(len(np.unique(groups[mask]))), 'weight_sum': float(c.sum()),
                'MAE_K': float(np.average(np.abs(a - b), weights=c)), 'RMSE_K': float(np.sqrt(np.average((a - b) ** 2, weights=c))),
                'MSLE_log1p': float(np.average((np.log1p(a) - np.log1p(b)) ** 2, weights=c)), 'bias_K': float(np.average(b - a, weights=c))}
    result = one(np.ones(len(y), dtype=bool))
    result['subgroups'] = {name: one(mask) for name, mask in [('reported_zero', y == 0), ('positive_tc', y > 0), ('high_tc_ge40K', y >= 40)]}
    return result

def paired_bootstrap(y, p, comparison, weights, groups, resamples=1000):
    y, p, comparison, weights = [np.asarray(v, float) for v in (y, p, comparison, weights)]
    unique, idx = np.unique(np.asarray(groups, str), return_inverse=True)
    numerator = np.bincount(idx, weights=weights * (np.abs(y - p) - np.abs(y - comparison)))
    denominator = np.bincount(idx, weights=weights)
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, len(unique), size=(resamples, len(unique)))
    samples = numerator[draws].sum(axis=1) / denominator[draws].sum(axis=1)
    return {'MAE_difference_K': float(numerator.sum() / denominator.sum()), 'conditional_95_percent_interval_K': np.quantile(samples, [.025, .975]).tolist(), 'groups': len(unique), 'resamples': resamples,
            'scope': 'Conditional paired strict-group development bootstrap. Original validation was historically inspected and is not fresh independent evidence. Excludes model/search/training uncertainty.'}

def global_spec(input_name, model, target):
    return {'input': input_name, 'routing': 'global', 'global': {'model': model, 'target': target}, 'experts': {}}

class Workbench:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.data = self.root / 'data'
        self.candidates = self.root / 'candidates'
        self.candidates.mkdir(parents=True, exist_ok=True)

    def prepare(self):
        audit = prepare_data(self.root)
        self.schema = load(self.data / 'schema.json')
        self._training()
        benchmarks = []
        number = 0
        for input_name in INPUTS:
            for model in MODELS:
                for target in TARGETS:
                    number += 1
                    cid = 'G%02d' % number
                    self._run(cid, global_spec(input_name, model, target), allow_reference=True)
                    benchmarks.append(cid)
        refs = []
        for prefix, input_name in [('D', 'diagnostic_repair11'), ('R', 'reference_structure28')]:
            for number, target in enumerate(TARGETS, 1):
                cid = '%s%02d' % (prefix, number)
                self._run(cid, global_spec(input_name, 'extra_trees', target), allow_reference=True)
                refs.append(cid)
        shared = self._winner(benchmarks)
        save(self.root / 'benchmark_results.json', {'shared_global_ids': benchmarks, 'outside_menu_reference_ids': refs, 'best_shared_global': shared,
                                                   'selection_anchor': 'Single shared global with lowest weighted overall 3-fold OOF MAE; its positive-Tc MAE is the guard for both search arms.'})
        return {'data_audit': audit, 'benchmarks': self.compare()}

    def _training(self):
        prepared = load(self.data / 'data_audit.json')['prepared_sha256']
        for name in ['train.csv.gz', 'fold_assignments.csv', 'schema.json']:
            if name in prepared and sha(self.data / name) != prepared[name]:
                raise ValueError('Prepared feedback file changed: ' + name)
        if not hasattr(self, 'schema'):
            self.schema = load(self.data / 'schema.json')
        if not hasattr(self, 'train'):
            self.train = pd.read_csv(self.data / 'train.csv.gz', float_precision='round_trip')
            assignments = pd.read_csv(self.data / 'fold_assignments.csv')
            if assignments.material_id.tolist() != self.train.material_id.tolist() or assignments.group.tolist() != self.train.group.tolist():
                raise ValueError('Fold alignment changed')
            self.folds = assignments.fold.to_numpy(int)
            if set(self.folds) != {0, 1, 2} or self.train.groupby('group').apply(lambda g: len(set(self.folds[g.index])), include_groups=False).max() != 1:
                raise ValueError('Invalid strict group folds')

    def _result(self, cid):
        if not isinstance(cid, str) or not re.fullmatch(r'[A-Z][A-Z0-9_-]{0,31}', cid):
            raise ValueError('Invalid candidate ID')
        if not (self.candidates / cid / 'result.json').is_file():
            raise ValueError('Unknown or incomplete candidate')
        return load(self.candidates / cid / 'result.json')

    def _winner(self, ids):
        if not ids:
            raise ValueError('Empty candidate collection')
        return min(ids, key=lambda cid: (self._result(cid)['metrics']['MAE_K'], self._result(cid)['actual_model_fits'], cid))

    def describe(self):
        self._training()
        df = self.train
        chemistry = chemistry_routes(df)
        return {'feedback_scope': 'Original training only, fixed 3-fold strict-group OOF. Original validation targets unavailable to these tools; retrospective targets never accessed.',
                'rows': len(df), 'groups': int(df.group.nunique()), 'reported_zero_rows': int((df.tc == 0).sum()), 'positive_rows': int((df.tc > 0).sum()), 'high_tc_ge40_rows': int((df.tc >= 40).sum()),
                'tc_quantiles_K': {str(k): float(v) for k, v in df.tc.quantile([0, .25, .5, .75, .9, .99, 1]).items()},
                'composition_route_counts': {route: {'rows': int((chemistry == route).sum()), 'groups': int(df.group[chemistry == route].nunique())} for route in ROUTES['chemistry']},
                'menu': {'inputs': list(INPUTS), 'routing': ['global', 'chemistry', 'kmeans3'], 'models': list(MODELS), 'targets': list(TARGETS), 'route_keys': ROUTES, 'minimum_expert_rows': 80, 'minimum_expert_groups': 12},
                'routing_caveat': 'Composition presence rules and KMeans clusters are operational partitions, not verified physical superconductor families. KMeans fits only each fold-training subset; cluster names order that subset centroid comp_Z_mean and may describe different populations in different folds.',
                'fixed_model_parameters': PARAMETERS, 'shared_benchmarks': self.compare()['shared_benchmarks'],
                'excluded_predictor_metadata': self.schema['excluded_predictor_metadata']}

    def run_strategy(self, candidate_id, spec):
        if (self.root / 'selection.json').exists():
            raise RuntimeError('Adaptive search is closed after the evaluation freeze')
        if re.match(r'^[GDR][0-9]+$', candidate_id):
            raise ValueError('Benchmark IDs are reserved')
        return self._run(candidate_id, spec)

    def _run(self, candidate_id, spec, allow_reference=False):
        if not isinstance(candidate_id, str) or not re.fullmatch(r'[A-Z][A-Z0-9_-]{0,31}', candidate_id):
            raise ValueError('Invalid candidate ID')
        spec = validate_spec(spec, allow_reference=allow_reference)
        self._training()
        folder = self.candidates / candidate_id
        folder.mkdir(exist_ok=True)
        if (folder / 'result.json').exists():
            if canonical(load(folder / 'specification.json')) != canonical(spec):
                raise ValueError('Candidate ID already used for another specification')
            return load(folder / 'result.json')
        save(folder / 'specification.json', spec)
        start = time.monotonic()
        prediction = np.full(len(self.train), np.nan)
        route = np.full(len(self.train), '', dtype=object)
        used = np.full(len(self.train), '', dtype=object)
        fold_details = []
        fits = 0
        for fold in range(3):
            fit_idx, held_idx = self.folds != fold, self.folds == fold
            train, held = self.train[fit_idx], self.train[held_idx]
            assert not set(train.group) & set(held.group)
            bundle = fit_pipeline(train, self.schema, spec)
            p, r, u = predict_pipeline(bundle, held)
            prediction[held_idx], route[held_idx], used[held_idx] = p, r, u
            fits += bundle['fit_count']
            fold_details.append({'fold': fold, 'fit_rows': len(train), 'held_rows': len(held), 'fit_groups': int(train.group.nunique()), 'held_groups': int(held.group.nunique()),
                                 'fit_count': bundle['fit_count'], 'elapsed_fit_seconds': bundle['elapsed_fit_seconds'], 'training_routes': bundle['training_routes'],
                                 'router_centroid_comp_Z_mean': bundle['router'].get('centroid_comp_Z_mean'), 'prediction_usage': pd.Series(u).value_counts().to_dict(),
                                 'held_metrics': metrics(held.tc, p, held.weight, held.group)})
        if not np.isfinite(prediction).all():
            raise ValueError('OOF prediction incomplete')
        oof = self.train[['material_id', 'group', 'tc', 'weight', 'formula', 'chemical_system']].copy()
        oof['fold'], oof['prediction'], oof['route'], oof['used_model'] = self.folds, prediction, route, used
        oof.to_csv(folder / 'oof_predictions.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
        result = {'candidate_id': candidate_id, 'specification': spec, 'completed_utc': utc(), 'feedback_scope': 'Original training fixed-group OOF only',
                  'metrics': metrics(self.train.tc, prediction, self.train.weight, self.train.group), 'actual_model_fits': fits, 'elapsed_seconds': time.monotonic() - start,
                  'fold_details': fold_details, 'prediction_usage': pd.Series(used).value_counts().to_dict(), 'source_sha256': load(self.data / 'data_audit.json')['prepared_sha256'],
                  'specification_sha256': sha(folder / 'specification.json'), 'oof_predictions_sha256': sha(folder / 'oof_predictions.csv.gz')}
        save(folder / 'result.json', result)
        return result

    def compare(self):
        all_results = [load(p) for p in sorted(self.candidates.glob('*/result.json'))]
        summaries = [{'candidate_id': r['candidate_id'], 'specification': r['specification'], 'metrics': r['metrics'], 'actual_model_fits': r['actual_model_fits'], 'elapsed_seconds': r['elapsed_seconds']} for r in all_results]
        shared = [r for r in summaries if re.fullmatch(r'G\d+', r['candidate_id'])]
        outside = [r for r in summaries if re.fullmatch(r'[DR]\d+', r['candidate_id'])]
        candidates = [r for r in summaries if r not in shared and r not in outside]
        return {'shared_benchmarks': shared, 'outside_menu_references': outside, 'candidate_results': candidates,
                'best_shared_global': min(shared, key=lambda r: (r['metrics']['MAE_K'], r['candidate_id']))['candidate_id'] if shared else None,
                'validation_evaluated': (self.root / 'final/results.json').exists()}

    def counterexamples(self, cid, k=12):
        if not 1 <= int(k) <= 30:
            raise ValueError('k must be between 1 and 30')
        result = self._result(cid)
        table = pd.read_csv(self.candidates / cid / 'oof_predictions.csv.gz', float_precision='round_trip')
        table['absolute_error_K'] = np.abs(table.tc - table.prediction)
        table['signed_error_K'] = table.prediction - table.tc
        masks = {'overall': np.ones(len(table), dtype=bool), 'positive': table.tc > 0, 'zero': table.tc == 0, 'high_tc_ge40': table.tc >= 40}
        return {'scope': 'Training OOF counterexamples only', 'candidate_id': cid, 'metrics': result['metrics'],
                'examples': {name: table[mask].sort_values(['absolute_error_K', 'material_id'], ascending=[False, True]).head(int(k)).to_dict(orient='records') for name, mask in masks.items()},
                'route_metrics': {str(route): metrics(g.tc, g.prediction, g.weight, g.group) for route, g in table.groupby('route')}}

    def freeze_and_evaluate(self, agent_ids, control_ids):
        self._training()
        agent_ids, control_ids = list(agent_ids), list(control_ids)
        if len(set(agent_ids + control_ids)) != len(agent_ids + control_ids):
            raise ValueError('Search arm candidate IDs must be unique and disjoint')
        benchmark = load(self.root / 'benchmark_results.json')
        shared_ids = benchmark['shared_global_ids']
        reference_ids = benchmark['outside_menu_reference_ids']
        anchor = self._winner(shared_ids)
        anchor_positive = self._result(anchor)['metrics']['subgroups']['positive_tc']['MAE_K']
        def select(ids):
            guard = {cid: self._result(cid)['metrics']['subgroups']['positive_tc']['MAE_K'] <= anchor_positive + 1e-12 for cid in ids}
            eligible = [cid for cid in ids if guard[cid]]
            winner = self._winner([anchor] + eligible)
            matches_anchor = canonical(self._result(winner)['specification']) == canonical(self._result(anchor)['specification'])
            return {'selected': winner, 'global_fallback_selected': matches_anchor, 'selected_specification_matches_anchor': matches_anchor,
                    'anchor_alias_selected': matches_anchor and winner != anchor, 'positive_guard_anchor': anchor, 'positive_guard_MAE_K': anchor_positive, 'guard_pass': guard, 'eligible_ids': eligible,
                    'selection_metric': 'Weighted overall training OOF MAE with positive-Tc non-regression guard against the same shared global anchor'}
        all_ids = shared_ids + reference_ids + agent_ids + control_ids
        for cid in all_ids:
            self._result(cid)
        files = [self.root / 'pipeline.py', self.root / 'prepare_data.py', self.root / 'repair/repair_descriptor.py', self.root / 'repair/audit.json']
        files += list(self.data.glob('*'))
        for name, digest in load(self.data / 'data_audit.json')['prepared_sha256'].items():
            if sha(self.data / name) != digest:
                raise ValueError('Prepared data changed before freeze: ' + name)
        files += [self.candidates / cid / name for cid in all_ids for name in ('specification.json', 'result.json', 'oof_predictions.csv.gz')]
        # Include controller/protocol files that already exist, so the entire executed search is frozen.
        files += [p for p in self.root.glob('*') if p.is_file() and p.suffix in ('.py', '.md', '.json') and p.name != 'selection.json']
        files += [p for p in (self.root / 'agent').rglob('*') if p.is_file()]
        files += [p for p in (self.root / 'controls').rglob('*.json') if p.is_file()]
        files += [p for p in (self.root / 'repair').glob('*') if p.is_file()]
        files = sorted(set(files))
        selection = {'freeze_utc': utc(), 'scope': 'Post-search original-validation development diagnosis; no historical test labels opened',
                     'agent_ids': agent_ids, 'control_ids': control_ids, 'shared_global_ids': shared_ids, 'outside_menu_reference_ids': reference_ids,
                     'best_shared_global': anchor, 'best_all_global_reference': self._winner(shared_ids + reference_ids), 'best_outside_menu_reference': self._winner(reference_ids),
                     'agent': select(agent_ids), 'automated_control': select(control_ids), 'frozen_sha256': {str(p.relative_to(self.root)): sha(p) for p in files}}
        final = self.root / 'final'
        final.mkdir(exist_ok=True)
        selection_path = self.root / 'selection.json'
        if selection_path.exists():
            old = load(selection_path)
            # Repeated calls return the completed evaluation only if the frozen input remains identical.
            for key in ('agent_ids', 'control_ids', 'frozen_sha256'):
                if old[key] != selection[key]:
                    raise ValueError('Attempt to change already frozen selection')
            if (final / 'results.json').exists():
                return load(final / 'results.json')
            selection = old
        else:
            save(selection_path, selection)
        events = [{'event': 'selection_and_code_frozen', 'utc': utc(), 'selection_sha256': sha(selection_path)}]
        save(final / 'access_journal.json', events)
        bundles, cache = {}, {}
        model_paths = {}
        for cid in all_ids:
            spec = load(self.candidates / cid / 'specification.json')
            key = canonical(spec)
            if key not in cache:
                cache[key] = fit_pipeline(self.train, self.schema, spec)
            bundles[cid] = cache[key]
            path = final / 'models' / (cid + '.joblib')
            path.parent.mkdir(exist_ok=True)
            joblib.dump(bundles[cid], path, compress=3)
            model_paths[cid] = {'path': str(path.relative_to(self.root)), 'sha256': sha(path), 'fit_count': bundles[cid]['fit_count'], 'elapsed_fit_seconds': bundles[cid]['elapsed_fit_seconds'], 'training_routes': bundles[cid]['training_routes']}
        events.append({'event': 'all_models_fit_on_original_training_and_saved', 'utc': utc(), 'unique_specifications': len(cache)})
        save(final / 'access_journal.json', events)
        val = pd.read_csv(self.data / 'validation_inputs.csv.gz', float_precision='round_trip')
        if 'tc' in val or len(val) != 869 or set(val.group) & set(self.train.group):
            raise ValueError('Invalid isolated validation input')
        predictions = val[['material_id', 'group', 'weight', 'formula', 'chemical_system']].copy()
        usage = {}
        for cid in all_ids:
            p, routes, used = predict_pipeline(bundles[cid], val)
            predictions[cid] = p
            usage[cid] = {'routes': pd.Series(routes).value_counts().to_dict(), 'models': pd.Series(used).value_counts().to_dict()}
        predictions.to_csv(final / 'predictions_before_labels.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
        events.append({'event': 'all_validation_predictions_saved_before_target_access', 'utc': utc(), 'predictions_sha256': sha(final / 'predictions_before_labels.csv.gz')})
        save(final / 'access_journal.json', events)
        labels = pd.read_csv(self.data / 'validation_labels.csv.gz', float_precision='round_trip')
        if labels.material_id.tolist() != predictions.material_id.tolist():
            raise ValueError('Validation target alignment changed')
        predictions['tc'] = labels.tc
        predictions.to_csv(final / 'predictions.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
        events.append({'event': 'validation_targets_first_opened_for_post_freeze_metrics', 'utc': utc()})
        save(final / 'access_journal.json', events)
        scored = {cid: metrics(labels.tc, predictions[cid], val.weight, val.group) for cid in all_ids}
        selected_agent, selected_control = selection['agent']['selected'], selection['automated_control']['selected']
        comparisons = {name: paired_bootstrap(labels.tc, predictions[selected_agent], predictions[cid], val.weight, val.group) for name, cid in
                       [('agent_minus_shared_global', anchor), ('agent_minus_automated_control', selected_control), ('agent_minus_best_all_global_reference', selection['best_all_global_reference']), ('agent_minus_best_outside_menu_reference', selection['best_outside_menu_reference'])]}
        result = {'completed_utc': utc(), 'scope': selection['scope'], 'validation_rows': len(val), 'validation_groups': int(val.group.nunique()), 'selection': selection,
                  'metrics': scored, 'paired_group_bootstrap': comparisons, 'prediction_usage': usage, 'models': model_paths,
                  'unique_final_model_specifications': len(cache), 'actual_final_model_fits': sum(b['fit_count'] for b in cache.values()),
                  'target_access_protocol': 'Models and selection frozen, all validation predictions persisted, then validation targets opened. No validation refit or retrospective target access.',
                  'selection_sha256': sha(selection_path), 'predictions_sha256': sha(final / 'predictions.csv.gz')}
        save(final / 'results.json', result)
        return result

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--root', default=str(Path(__file__).parent))
    p.add_argument('--prepare', action='store_true')
    args = p.parse_args()
    bench = Workbench(args.root)
    print(json.dumps(bench.prepare() if args.prepare else bench.describe(), ensure_ascii=False, indent=2, allow_nan=False))
