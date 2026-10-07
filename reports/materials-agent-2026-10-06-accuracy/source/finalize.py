"""Freeze repeated-OOF selection, predict all three arms, then unlock confirmation."""
from __future__ import annotations
import gzip
import json
from pathlib import Path
import sys
import time
sys.dont_write_bytecode = True
import numpy as np
import pandas as pd
import backend
import data_curator
import predictor_runtime
import representation_runtime

ROOT = Path(__file__).resolve().parent
LEGACY_CODE = '''def fit(X_train,y_train):
    return train_model("e011",X_train,y_train,{})
def predict(state,X_eval):
    return state.predict(X_eval)
'''


def metric(truth, prediction):
    error = np.asarray(prediction) - np.asarray(truth)
    return {'rows': len(error), 'MAE_eV_atom': float(np.abs(error).mean()),
            'RMSE_eV_atom': float(np.sqrt(np.mean(error**2))),
            'mean_prediction_minus_truth': float(error.mean()),
            'p90_abs_error': float(np.quantile(np.abs(error), .9)),
            'p99_abs_error': float(np.quantile(np.abs(error), .99))}


def cluster_difference(truth, baseline, champion, systems):
    frame = pd.DataFrame({'system': np.asarray(systems),
                          'diff': np.abs(champion-truth)-np.abs(baseline-truth)})
    groups = frame.groupby('system', sort=True).agg(total=('diff', 'sum'), rows=('diff', 'size'))
    totals, counts = groups.total.to_numpy(), groups.rows.to_numpy()
    rng = np.random.default_rng(20261007)
    means = []
    for _ in range(2000):
        selected = rng.integers(0, len(groups), size=len(groups))
        means.append(float(totals[selected].sum()/counts[selected].sum()))
    return {'MAE_difference_champion_minus_baseline': float(frame['diff'].mean()),
            'cluster_bootstrap_95_percent_interval': np.quantile(means, [.025, .975]).tolist(),
            'bootstrap_unit': 'chemical_system', 'clusters': len(groups),
            'resamples': 2000, 'seed': 20261007,
            'interpretation': 'One fixed same-source confirmation cohort; no causal or universal physical claim.'}


def select_candidate(complete):
    eligible = {k: v for k, v in complete.items() if v['OOF_schedule_gate_pass']}
    pool = eligible if eligible else complete
    chosen = min(pool, key=lambda k: (pool[k]['OOF']['MAE_eV_atom'], k))
    return chosen, bool(eligible), sorted(eligible)


def align_fresh_inputs(features, metadata, columns):
    if 'material_id' not in metadata or metadata.material_id.isna().any() or not metadata.material_id.is_unique:
        raise ValueError('Invalid confirmation IDs')
    if len(features) != len(metadata) or len(metadata) != 3000:
        raise ValueError('Confirmation cardinality changed')
    features, metadata = features.copy(), metadata.copy()
    ids = pd.Index(metadata.material_id.tolist(), name='material_id')
    features.index = ids
    metadata = metadata.set_index('material_id')
    if not features.index.equals(metadata.index):
        raise ValueError('Confirmation ID alignment differs')
    return features.loc[:, columns], metadata


def build_representation_inputs(cid, ctx, fresh_X, structures_path):
    """Apply frozen functions without selecting features on either evaluation cohort."""
    state = backend.state()
    proposal = state['proposals'][cid]
    with gzip.open(structures_path, 'rt', encoding='utf-8') as f:
        fresh_structures = {r['material_id']: r for r in map(json.loads, f)}
    known_ids, fresh_ids = list(ctx.validation_ids), list(fresh_X.index)
    known_parts = [ctx.all_X.loc[known_ids]]
    fresh_parts = [fresh_X.loc[fresh_ids, ctx.original_columns]]
    inherited = backend.load(ROOT/'incumbent/representation_proposal.json')
    blocks = [('INHERITED_R004', ROOT/'incumbent/compute.py', inherited['feature_names'],
               list(ctx.X.columns[42:]), backend.sha(ROOT/'incumbent/compute.py'))]
    for rid in proposal['feature_blocks']:
        entry = state['representations'][rid]
        blocks.append((rid, ROOT/'representations'/rid/'compute.py', entry['declared_feature_names'],
                       entry['feature_names'], entry['code_sha256']))
    for rid, path, declared_names, names, code_sha in blocks:
        code = path.read_text(encoding='utf-8')
        for tag, records, parts, ids in (
            ('known_validation', ctx.structures(known_ids), known_parts, known_ids),
            ('fresh', [fresh_structures[i] for i in fresh_ids], fresh_parts, fresh_ids)):
            start, chunks, receipts = time.monotonic(), [], []
            for offset in range(0, len(records), 64):
                remaining = 240-(time.monotonic()-start)
                if remaining <= 0:
                    raise RuntimeError('Frozen evaluation representation deadline')
                values, receipt = representation_runtime.run_isolated(
                    code, records[offset:offset+64], feature_names=declared_names,
                    timeout_s=min(20, remaining, backend.remaining_wall()), memory_mb=2048)
                chunks.append(values)
                receipts.append(receipt)
            matrix = np.concatenate(chunks, axis=0)
            if time.monotonic()-start > 240 or matrix.shape != (len(records), len(names)) or not np.isfinite(matrix).all():
                raise RuntimeError('Invalid frozen evaluation representation')
            backend.dump(ROOT/'runtime_receipts'/f'{rid}_final_{tag}.json',
                         {'code_sha256': code_sha, 'rows': len(ids), 'columns': len(names),
                          'batch_receipts': receipts, 'elapsed_seconds': time.monotonic()-start,
                          'label_input': False, 'heldout_novelty_not_reselected': True}, exclusive=True)
            part = pd.DataFrame(matrix, index=ids, columns=names)
            part.index.name = 'material_id'
            part.to_csv(ROOT/'final'/f'{rid}_{tag}_features.csv.gz', float_format='%.17g', compression='gzip')
            parts.append(part)
    known = pd.concat(known_parts, axis=1)
    fresh = pd.concat(fresh_parts, axis=1)
    expected = list(ctx.matrix(proposal['feature_blocks']).columns)
    if list(known.columns) != expected or list(fresh.columns) != expected:
        raise ValueError('Frozen representation feature order differs from training')
    return known, fresh


def run():
    backend.assert_frozen()
    state, ctx = backend.state(), backend.context()
    folder = ROOT/'final'
    if folder.exists():
        raise RuntimeError('Final attempt already started; never retry or refit')
    complete = {k: v['summary'] for k, v in state['experiments'].items() if v['status'] == 'complete'}
    if len(complete) != 20 or state['active_operation'] or state['stop_reason']:
        raise RuntimeError('Final evaluation requires 20 settled candidates')
    selected, eligible_exists, eligible_ids = select_candidate(complete)
    proposal = state['proposals'][selected]
    protocol = backend.load(ROOT/'protocol.json')
    folder.mkdir()
    frozen = {'schema_version': 1, 'frozen_utc': backend.now(), 'candidate_id': selected,
              'selection': 'Minimum mean-repeat OOF MAE among eligible, then candidate ID; if none eligible, minimum all is diagnostic only.',
              'eligible_candidate_ids': eligible_ids, 'selected_is_eligible': eligible_exists,
              'OOF_result': complete[selected], 'OOF_gate_pass': bool(eligible_exists),
              'fresh_targets_accessed': False, 'model_code_sha256': proposal['code_sha256'],
              'model_file_byte_sha256': backend.sha(ROOT/'candidates'/selected/'predictor.py'),
              'registration_sha256': backend.sha(ROOT/'candidates'/selected/'registration.json'),
              'selection_result_sha256': backend.sha(ROOT/'experiments'/selected/'result.json'),
              'selection_OOF_predictions_sha256': backend.sha(ROOT/'experiments'/selected/'internal_oof_predictions.csv.gz'),
              'protocol_sha256': backend.sha(ROOT/'protocol.json'),
              'representation_hashes': proposal['input_representation_hashes'],
              'fresh_manifest_sha256': backend.sha(ROOT/'fresh_cohort/prefit_manifest.json'),
              'incumbent_artifact_hashes': protocol['incumbent_artifact_hashes'],
              'dependency_lock_sha256': backend.sha(ROOT/'environment/dependency_lock.json'),
              'incumbent_rule': 'Retain C018 unless eligible and new confirmation MAE improves with CI upper<0, RMSE and p99 nonworsening; known715 diagnostic only.'}
    backend.dump(folder/'champion_frozen.json', frozen, exclusive=True)
    frozen_sha = backend.sha(folder/'champion_frozen.json')
    reserve = 6+5+proposal['max_fits_per_block']
    if state['counters']['base_fits_reserved']+reserve > protocol['budget']['base_fit_reservations']:
        raise RuntimeError('Final fit reservation cap')
    backend.dump(folder/'reservation.json', {'reserved_trusted_learner_fits': reserve, 'baseline': 6,
                 'legacy_baseline': 5, 'champion': proposal['max_fits_per_block'],
                 'candidate_id': selected, 'utc': backend.now(), 'fresh_targets_accessed': False}, exclusive=True)
    state['champion_frozen'] = True
    state['counters']['base_fits_reserved'] += reserve
    state['active_operation'] = {'kind': 'final', 'candidate': selected}
    backend.dump(backend.STATE, state)
    started = time.monotonic()
    try:
        fresh_X, fresh_meta, structures_path, _ = data_curator.load_frozen_fresh_inputs(ROOT)
        fresh_X, fresh_meta = align_fresh_inputs(fresh_X, fresh_meta, ctx.original_columns)
        known_X, fresh_aug = build_representation_inputs(selected, ctx, fresh_X, structures_path)
        known_ids, fresh_ids = list(ctx.validation_ids), list(fresh_X.index)
        champion_eval = pd.concat([known_X, fresh_aug])
        fixed_eval = champion_eval.loc[:, list(ctx.X.columns)]
        legacy_eval = champion_eval.loc[:, ctx.original_columns]
        predictions, worker_receipts = {}, {}
        arms = [('baseline', (ROOT/'incumbent/predictor.py').read_text(encoding='utf-8'), ctx.X, fixed_eval, 6),
                ('legacy_baseline', LEGACY_CODE, ctx.old_X, legacy_eval, 5),
                ('champion', (ROOT/'candidates'/selected/'predictor.py').read_text(encoding='utf-8'),
                 ctx.matrix(proposal['feature_blocks']), champion_eval, proposal['max_fits_per_block'])]
        for arm, code, training, evaluation, cap in arms:
            response = predictor_runtime.run_training_block(code, training.to_numpy(), ctx.y.to_numpy(),
                        evaluation.to_numpy(), max_fits_per_block=cap, event_path=folder/'fit_events_live.jsonl',
                        block_id=f'FINAL_{arm}', timeout_s=min(protocol['budget']['predictor_block_seconds'],
                        backend.remaining_wall()), memory_mb=2048)
            pred = response['prediction']
            predictions[arm] = pred
            worker_receipts[arm] = {k: v for k, v in response.items() if k != 'prediction'}
            for cohort, ids, values in [('known_validation', known_ids, pred[:len(known_ids)]),
                                       ('fresh', fresh_ids, pred[len(known_ids):])]:
                pd.DataFrame({'material_id': ids, 'prediction': values}).to_csv(
                    folder/f'{arm}_{cohort}_predictions.csv.gz', index=False, float_format='%.17g', compression='gzip')
        replay = {}
        for arm, old in [('baseline', backend.EVOLVING/'final/champion_known_validation_predictions.csv.gz'),
                         ('legacy_baseline', backend.OLD/'experiments/E011/validation_predictions.csv.gz')]:
            cached = pd.read_csv(old, float_precision='round_trip', index_col='material_id').loc[known_ids]
            replay[arm] = float(np.max(np.abs(predictions[arm][:len(known_ids)]-cached.prediction.to_numpy())))
            if replay[arm] > 1e-12:
                raise RuntimeError(f'Historical baseline replay failed: {arm}; labels remain sealed')
        receipt = {'created_utc': backend.now(), 'frozen_champion_path': 'final/champion_frozen.json',
                   'frozen_champion_sha256': frozen_sha, 'fresh_manifest_sha256': frozen['fresh_manifest_sha256'],
                   'predictions': {arm: {'path': f'final/{arm}_fresh_predictions.csv.gz',
                    'sha256': backend.sha(folder/f'{arm}_fresh_predictions.csv.gz')} for arm in predictions},
                   'historical_known_baseline_replay_max_absolute_difference': replay,
                   'workers': worker_receipts, 'fresh_labels_accessed': False}
        backend.dump(folder/'prediction_receipt.json', receipt, exclusive=True)
        backend.remaining_wall()
        labels = data_curator.load_targets_after_freeze(frozen_sha, 'final/prediction_receipt.json', ROOT)
        fresh_y = labels.set_index('material_id').loc[fresh_ids, 'formation_energy_per_atom'].to_numpy()
        cached = pd.read_csv(backend.OLD/'experiments/E011/validation_predictions.csv.gz',
                             float_precision='round_trip', index_col='material_id').loc[known_ids]
        known_y = cached.truth.to_numpy()
        results = {arm: {'known_validation': metric(known_y, pred[:len(known_ids)]),
                        'fresh3000': metric(fresh_y, pred[len(known_ids):])} for arm, pred in predictions.items()}
        comparisons = {arm: cluster_difference(fresh_y, predictions[arm][len(known_ids):],
                        predictions['champion'][len(known_ids):], fresh_meta.loc[fresh_ids, 'chemical_system'].to_numpy())
                       for arm in ('baseline', 'legacy_baseline')}
        b, c = results['baseline']['fresh3000'], results['champion']['fresh3000']
        gates = {'training_eligible': bool(eligible_exists), 'fresh_MAE_improved': c['MAE_eV_atom'] < b['MAE_eV_atom'],
                 'fresh_cluster_CI_upper_negative': comparisons['baseline']['cluster_bootstrap_95_percent_interval'][1] < 0,
                 'fresh_RMSE_nonworsening': c['RMSE_eV_atom'] <= b['RMSE_eV_atom'],
                 'fresh_p99_nonworsening': c['p99_abs_error'] <= b['p99_abs_error']}
        counts = backend.fit_counts(folder/'fit_events_live.jsonl')
        supported = bool(all(gates.values()))
        result = {'schema_version': 1, 'candidate_id': selected, 'selected_is_eligible': eligible_exists,
                  'frozen_champion_sha256': frozen_sha, 'results': results, 'fresh_comparisons': comparisons,
                  'promotion_gates': gates, 'promotion_pass': supported,
                  'incumbent': 'chosenAgentprogram' if supported else 'C018', 'counts': counts,
                  'elapsed_seconds': time.monotonic()-started,
                  'fresh_scope': '3000 previously unobserved local IDs and chemical systems, same public MP release; no new DFT or synthesis.',
                  'known715_role': 'Previously observed historical regression diagnostic, not an independent confirmation or selection criterion.',
                  'fresh_prediction_receipt_sha256': backend.sha(folder/'prediction_receipt.json'),
                  'labels_release_receipt_sha256': backend.sha(ROOT/'fresh_cohort/label_release_receipt.json'),
                  'artifact_hashes': {p.name: backend.sha(p) for p in folder.iterdir()
                                     if p.is_file() and p.name != 'champion_frozen.json'}}
        backend.dump(folder/'result.json', result, exclusive=True)
        state = backend.state()
        for key in ('fit_started', 'fit_completed'):
            state['counters'][key] += counts[key]
        state['active_operation'] = None
        state['final_result'] = result
        backend.dump(backend.STATE, state)
        return result
    except Exception as exc:
        counts = backend.fit_counts(folder/'fit_events_live.jsonl')
        backend.dump(folder/'failure.json', {'error': f'{type(exc).__name__}: {exc}', 'counts': counts,
                     'utc': backend.now(), 'new_fit_retry_allowed': False}, exclusive=True)
        state = backend.state()
        for key in ('fit_started', 'fit_completed'):
            state['counters'][key] += counts[key]
        state['active_operation'] = None
        state['stop_reason'] = 'Final attempt failed or unknown; no refit/retry'
        backend.dump(backend.STATE, state)
        raise


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False, allow_nan=False))
