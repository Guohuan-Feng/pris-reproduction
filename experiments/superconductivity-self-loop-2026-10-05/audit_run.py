"""Independent, read-only audit of the authorized 20-round continuation.

Reads a consistent SQLite state/event snapshot and allowlisted training OOF
artifacts. It never imports the controller, adapter, evaluator, or fitted models,
never requests a model response, and never opens held-out target files.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3

import numpy as np
import pandas as pd


CID = re.compile(r'[A-Z][A-Z0-9_-]{0,31}\Z')
TRAIN_FILES = {'train.csv.gz', 'schema.json', 'fold_assignments.csv', 'data_audit.json'}
CANDIDATE_FILES = {'specification.json', 'result.json', 'oof_predictions.csv.gz'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def close(actual, expected, name):
    require(isinstance(actual, (int, float)) and math.isfinite(actual)
            and math.isclose(float(actual), float(expected), rel_tol=1e-10, abs_tol=1e-10),
            f'{name}: {actual!r} != independently derived {expected!r}')


def allowed_workbench(relative):
    parts = Path(relative).parts
    return (len(parts) == 1 and parts[0] in {'pipeline.py', 'prepare_data.py'}
            or len(parts) == 2 and parts[0] == 'data' and parts[1] in TRAIN_FILES
            or len(parts) == 3 and parts[0] == 'candidates' and CID.fullmatch(parts[1])
            and parts[2] in CANDIDATE_FILES)


def safe_path(root, relative):
    root = Path(root).resolve()
    path = root / relative
    require(not path.is_symlink() and path.is_file() and path.resolve().is_relative_to(root),
            'Missing/unsafe evidence path: ' + str(relative))
    return path


def unique_measured(cycles):
    seen = set()
    for cycle in cycles:
        result = cycle.get('evaluation', {})
        if result.get('status') == 'failed' or result.get('scientific_evidence_available') is False:
            continue
        if result.get('proposal_was_duplicate', result.get('reused', False)):
            continue
        if not isinstance(cycle.get('specification'), dict) or not isinstance(cycle.get('reflection'), dict):
            continue
        try:
            values = [result['metrics']['MAE_K'], result['metrics']['subgroups']['positive_tc']['MAE_K']]
            if all(isinstance(x, (int, float)) and math.isfinite(x) for x in values):
                seen.add(fingerprint(cycle['specification']))
        except (KeyError, TypeError):
            continue
    return seen


def basic_metrics(frame):
    weights = frame.weight.to_numpy(float)
    errors = frame.prediction.to_numpy(float) - frame.tc.to_numpy(float)
    if not len(frame):
        return {'rows': 0, 'groups': 0, 'weight_sum': 0., 'MAE_K': None,
                'RMSE_K': None, 'bias_K': None}
    require(np.isfinite(weights).all() and np.isfinite(errors).all() and (weights > 0).all(),
            'Nonfinite predictions/targets or nonpositive weights')
    return {'rows': len(frame), 'groups': int(frame.group.nunique()),
            'weight_sum': float(weights.sum()), 'MAE_K': float(np.average(np.abs(errors), weights=weights)),
            'RMSE_K': float(np.sqrt(np.average(errors ** 2, weights=weights))),
            'bias_K': float(np.average(errors, weights=weights))}


def independent_metrics(frame):
    value = basic_metrics(frame)
    value['subgroups'] = {'reported_zero': basic_metrics(frame[frame.tc == 0]),
                          'positive_tc': basic_metrics(frame[frame.tc > 0]),
                          'high_tc_ge40K': basic_metrics(frame[frame.tc >= 40])}
    return value


def compare_metrics(actual, expected, name):
    for key, value in expected.items():
        require(key in actual, name + ': missing ' + key)
        if isinstance(value, dict):
            compare_metrics(actual[key], value, name + '/' + key)
        elif value is None:
            require(actual[key] is None, name + '/' + key + ': expected null')
        else:
            close(actual[key], value, name + '/' + key)


def compact_metrics(value):
    return {'MAE_K': value.get('MAE_K'), 'subgroups': {
        name: {'MAE_K': subgroup.get('MAE_K')} for name, subgroup in value.get('subgroups', {}).items()}}


def compact_history(cycles):
    result = []
    for cycle in cycles[-8:]:
        evaluation, reflection = cycle.get('evaluation', {}), cycle.get('reflection', {})
        result.append({'candidate_id': cycle['candidate_id'], 'hypothesis': cycle.get('hypothesis'),
                       'revision_of': cycle.get('revision_of'), 'specification': cycle.get('specification'),
                       'metrics': compact_metrics(evaluation.get('metrics', {})),
                       'guard_eligible': evaluation.get('guard_eligible'),
                       'improved_incumbent': evaluation.get('improved_incumbent'),
                       'error': evaluation.get('error'), 'reflection': {
                           key: reflection.get(key) for key in ('hypothesis_status', 'summary', 'next_focus')}})
    return result


def normalize_decision(response):
    response = copy.deepcopy(response)
    if response.get('specification'):
        experts = response['specification']['experts']
        require(isinstance(experts, list) and len({x['route'] for x in experts}) == len(experts),
                'Malformed/duplicate raw expert routes')
        response['specification']['experts'] = {
            x['route']: {'model': x['model'], 'target': x['target']} for x in experts}
    return response


class Auditor:
    def __init__(self, root, allow_incomplete):
        self.root = Path(root).resolve()
        if not (self.root / 'memory.sqlite').exists() and (self.root / 'evidence/status.json').is_file():
            self.root = self.root / 'evidence'
        self.public = not (self.root / 'memory.sqlite').exists()
        self.candidate_prefix = 'candidates' if self.public else 'workbench/candidates'
        self.parent_prefix = 'parent_snapshot' if (self.root / 'parent_snapshot').is_dir() else 'lineage/parent'
        self.allow_incomplete = allow_incomplete
        self.hashes, self.source_hashes, self.candidates, self.calls = {}, {}, {}, {}
        if self.public:
            self.state = self.read('status.json')
            self.events = self.read('memory_export.json')
        else:
            database = safe_path(self.root, 'memory.sqlite')
            connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=30)
            try:
                connection.execute('BEGIN')
                require(connection.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'SQLite integrity failure')
                self.state = json.loads(connection.execute('SELECT payload FROM state WHERE id=1').fetchone()[0])
                self.events = [{'seq': row[0], 'at': row[1], 'kind': row[2], 'payload': json.loads(row[3])}
                               for row in connection.execute('SELECT seq,at,kind,payload FROM events ORDER BY seq')]
            finally:
                connection.close()
        self.lineage = self.read('lineage.json')
        self.parent = self.read(self.parent_prefix + '/status.json')
        self.parent_events = self.read(self.parent_prefix + '/memory_export.json')
        self.manifest = self.read('workbench_manifest.json')
        self.index = self.read('adapter_index.json')
        self.initial_references = {x['id']: x for x in
            self.read('calls/002_propose/frozen_context.json')['training_workbench']['known_specifications']}

    def read(self, relative, text=False):
        raw = safe_path(self.root, relative).read_bytes()
        self.hashes[relative] = hashlib.sha256(raw).hexdigest()
        return raw.decode('utf-8') if text else json.loads(raw.decode('utf-8'))

    def hash_file(self, relative):
        raw = safe_path(self.root, relative).read_bytes()
        self.hashes[relative] = hashlib.sha256(raw).hexdigest()
        return self.hashes[relative]

    def verify_lineage(self):
        require(self.lineage['format'] == 'tc-self-loop-continuation-v1', 'Unexpected lineage format')
        require(self.parent['status'] == 'stopped' and self.parent['attempts'] == 2
                and self.parent['llm_calls'] == 5 and len(unique_measured(self.parent['completed_cycles'])) == 2,
                'Parent is not the verified two-cycle state')
        require(fingerprint(self.parent) == self.lineage['parent_state_sha256']
                == self.state['continuation']['parent_state_sha256'], 'Parent state hash mismatch')
        require(self.state['completed_cycles'][:2] == self.parent['completed_cycles'], 'Inherited cycles changed')
        require(self.events[:len(self.parent_events)] == self.parent_events, 'Inherited journal changed')
        require([x['seq'] for x in self.events] == list(range(1, len(self.events) + 1)), 'Journal sequence gap')
        boundary = self.events[len(self.parent_events)]
        require(boundary['kind'] == 'run.continuation_authorized', 'Missing continuation authorization event')
        require(boundary['payload']['lineage_sha256'] == self.hashes['lineage.json'], 'Lineage document changed')
        require(self.state['config'] == self.lineage['new_config'] == boundary['payload']['new_config'],
                'Authorized configuration changed during continuation')
        policy = self.lineage['policy']
        require(policy['inherited_completed_unique_experiments'] == 2
                and policy['required_additional_completed_unique_experiments'] == 20
                and policy['required_total_completed_unique_experiments'] == 22,
                'Authorized minimum changed')
        require(self.state['config']['min_completed_experiments'] == 22, 'Completion floor differs from lineage')
        require(self.parent['best'] == self.lineage['initial_incumbent'] and self.parent['best']['id'] == 'A05',
                'Unexpected initial incumbent')
        for key, expected in self.lineage['inherited_counters'].items():
            require(self.parent[key] == expected, 'Inherited counter mismatch: ' + key)
        if not self.public:
            require(self.hash_file('lineage/parent/memory.sqlite') == self.lineage['parent_sqlite_backup_sha256'],
                    'Immutable parent database backup changed')
        # adapter_index.json is intentionally extended in the continuation.
        for relative, record in self.lineage['copied_artifacts'].items():
            if relative == 'adapter_index.json':
                continue
            if relative.startswith('workbench/'):
                require(allowed_workbench(relative[len('workbench/'):]), 'Forbidden copied workbench path')
            mapped = relative
            if self.public:
                if relative.startswith('workbench/candidates/'):
                    mapped = relative[len('workbench/'):]
                elif relative.startswith('lineage/parent/'):
                    mapped = self.parent_prefix + relative[len('lineage/parent'):]
                if not (self.root / mapped).is_file():
                    continue
            require(self.hash_file(mapped) == record['sha256'], 'Inherited artifact changed: ' + mapped)
        return self.events[len(self.parent_events) + 1:]

    def verify_training(self):
        source = None if self.public else Path(self.manifest['source_dir']).resolve()
        for relative, item in self.manifest['files'].items():
            require(allowed_workbench(relative), 'Manifest includes non-training artifact: ' + relative)
            require(re.fullmatch('[0-9a-f]{64}', item['sha256']), 'Invalid recorded training digest')
            require(self.lineage['copied_artifacts']['workbench/' + relative]['sha256'] == item['sha256'],
                    'Training provenance differs between original manifest and lineage')
            if self.public:
                digest = item['sha256']
                if relative.startswith('candidates/') and (self.root / relative).is_file():
                    require(self.hash_file(relative) == digest, 'Exported source candidate changed: ' + relative)
            else:
                require(self.hash_file('workbench/' + relative) == item['sha256'], 'Copied source changed: ' + relative)
                digest = hashlib.sha256(safe_path(source, relative).read_bytes()).hexdigest()
                require(digest == item['sha256'], 'Original frozen source changed: ' + relative)
            self.source_hashes[relative] = digest
        for relative, digest in self.index['evidence'].items():
            require(allowed_workbench(relative), 'Candidate index contains unsafe artifact')
            mapped = relative if self.public else 'workbench/' + relative
            require(self.hash_file(mapped) == digest, 'Indexed candidate evidence changed: ' + relative)
        if self.public:
            self.train = pd.read_csv(safe_path(self.root, 'candidates/L001/oof_predictions.csv.gz'), float_precision='round_trip')
            self.folds = self.train[['material_id', 'group', 'fold']].copy()
        else:
            data_dir = self.root / 'workbench/data'
            require({p.name for p in data_dir.iterdir() if p.is_file()} <= TRAIN_FILES,
                    'Isolated workbench contains a non-training data artifact')
            require(not (self.root / 'workbench/final').exists() and not (self.root / 'workbench/selection.json').exists(),
                    'Held-out evaluation artifact in adaptive workbench')
            self.train = pd.read_csv(data_dir / 'train.csv.gz', float_precision='round_trip')
            self.folds = pd.read_csv(data_dir / 'fold_assignments.csv')
            require(set(self.train.split) == {'train'}, 'Non-training row in adaptive inputs')
        require(len(self.train) == 3764 and self.train.material_id.is_unique
                and self.train.group.nunique() == 1117,
                'Unexpected training cohort')
        require(self.folds.material_id.tolist() == self.train.material_id.tolist()
                and self.folds.group.tolist() == self.train.group.tolist(), 'Training fold alignment changed')
        require(set(self.folds.fold) == {0, 1, 2} and self.folds.groupby('group').fold.nunique().max() == 1,
                'Connected groups cross OOF folds')

    def candidate(self, cid):
        require(isinstance(cid, str) and CID.fullmatch(cid), 'Invalid evidence candidate ID')
        if cid in self.candidates:
            return self.candidates[cid]
        base = self.candidate_prefix + '/' + cid + '/'
        if self.public and not (self.root / base / 'result.json').is_file():
            require(cid in self.initial_references and re.fullmatch(r'[GDRAC][0-9]+', cid)
                    and cid not in {'G01', 'A05'}, 'Required independently checkable candidate missing: ' + cid)
            prior = self.initial_references[cid]
            require(prior['fingerprint'] == fingerprint(prior['spec']), 'Inherited reference fingerprint mismatch')
            self.candidates[cid] = {'specification': prior['spec'], 'metrics': prior['metrics'],
                                    'fingerprint': prior['fingerprint'], 'independently_recomputed': False}
            return self.candidates[cid]
        result = self.read(base + 'result.json')
        spec = self.read(base + 'specification.json')
        require(result['candidate_id'] == cid and result['specification'] == spec, cid + ': ID/specification mismatch')
        for name, key in (('specification.json', 'specification_sha256'),
                          ('oof_predictions.csv.gz', 'oof_predictions_sha256')):
            require(self.hash_file(base + name) == result[key], cid + ': original evidence SHA mismatch')
        table = pd.read_csv(self.root / base / 'oof_predictions.csv.gz', float_precision='round_trip')
        require(len(table) == len(self.train) and table.material_id.is_unique, cid + ': invalid OOF coverage')
        for column in ('material_id', 'group', 'formula', 'chemical_system'):
            require(table[column].tolist() == self.train[column].tolist(), cid + ': OOF identity mismatch/' + column)
        for column in ('tc', 'weight'):
            require(np.array_equal(table[column].to_numpy(), self.train[column].to_numpy()), cid + ': OOF target/weight mismatch')
        require(np.array_equal(table.fold.to_numpy(), self.folds.fold.to_numpy()), cid + ': OOF folds changed')
        require(np.isfinite(table.prediction).all() and (table.prediction >= 0).all(), cid + ': invalid predictions')
        metrics = independent_metrics(table)
        compare_metrics(result['metrics'], metrics, cid + '/independent metrics')
        prediction_values = table.prediction.to_numpy(dtype='<f8', copy=True)
        # Numeric equality treats +0.0 and -0.0 alike. Other finite values stay exact.
        prediction_values[prediction_values == 0] = 0.
        self.candidates[cid] = {'result': result, 'specification': spec, 'metrics': metrics,
                                'fingerprint': fingerprint(spec), 'independently_recomputed': True,
                                'prediction_values': prediction_values,
                                'prediction_sha256': hashlib.sha256(prediction_values.tobytes()).hexdigest()}
        return self.candidates[cid]

    def equivalent_predictions(self, observations):
        """Describe observational equality; never changes configuration counting."""
        new_ids = {item['id'] for item in observations if item['status'] == 'measured'}
        considered = sorted(new_ids | {'A05', 'G01', 'L001', 'L002'})
        groups = {}
        for cid in considered:
            item = self.candidate(cid)
            digest = item['prediction_sha256']
            bucket = groups.setdefault(digest, [])
            if bucket:
                require(np.array_equal(item['prediction_values'], self.candidates[bucket[0]]['prediction_values']),
                        'Prediction digest collision; explicit arrays differ')
            bucket.append(cid)
        equivalent = []
        for digest, ids in sorted(groups.items()):
            if len(ids) < 2:
                continue
            specifications = {self.candidates[cid]['fingerprint'] for cid in ids}
            equivalent.append({'candidate_ids': ids, 'new_candidate_ids': sorted(set(ids) & new_ids),
                               'distinct_specification_count': len(specifications),
                               'different_configurations_same_predictions': len(specifications) > 1,
                               'aligned_prediction_sha256': digest})
        return {'scope': 'Exact aligned training OOF predictions among observed new candidates, A05, G01, L001 and L002; no refitting.',
                'comparison': 'Finite float64 values in verified material-ID order; signed zeros normalized; array equality checked.',
                'considered_candidate_ids': considered,
                'new_measured_candidates_considered': len(new_ids),
                'distinct_prediction_arrays_among_new_measured_candidates': len({self.candidates[cid]['prediction_sha256'] for cid in new_ids}),
                'equivalent_prediction_groups': equivalent,
                'counting_rule_unchanged': 'The authorized minimum counts distinct successful configurations, not unique prediction arrays or independent evidence.'}

    def verify_original_parent_unchanged(self):
        """Final runtime-only check of the full frozen parent tree."""
        parent = Path(self.lineage['parent_run']).resolve()
        expected = self.lineage['parent_file_sha256']
        require(fingerprint(expected) == self.lineage['parent_tree_sha256'], 'Recorded parent tree digest mismatch')
        actual = {}
        for path in sorted(parent.rglob('*')):
            require(not path.is_symlink(), 'Symlink appeared in original frozen parent')
            if not path.is_file():
                continue
            relative = path.relative_to(parent).as_posix()
            if relative in self.lineage['hash_exclusions']:
                continue
            require(path.resolve().is_relative_to(parent), 'Original parent file escaped its directory')
            actual[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        require(actual == expected, 'Original parent tree changed after continuation was forked')
        return {'verified': True, 'files_checked': len(actual), 'parent_tree_sha256': fingerprint(actual),
                'hash_exclusions': self.lineage['hash_exclusions']}

    def call(self, number, phase):
        name = f'{number:03d}_{phase}'
        folder = self.root / 'calls' / name
        context = self.read('calls/' + name + '/frozen_context.json')
        item = {'number': number, 'phase': phase, 'context': context, 'folder': name}
        if not (folder / 'receipt.json').exists():
            item['status'] = 'in_progress_or_unresolved'
            self.calls[number] = item
            return item
        receipt = self.read('calls/' + name + '/receipt.json')
        require(receipt.get('native_tool_events') == [], name + ': native tools were used')
        item['receipt'] = receipt
        if receipt.get('completed') is not True:
            item['status'] = 'failed_or_unresolved'
            self.calls[number] = item
            return item
        require(receipt['exit_code'] == 0 and receipt['errors'] == [], name + ': inconsistent completed receipt')
        events = [json.loads(line) for line in self.read('calls/' + name + '/stdout.jsonl', True).splitlines() if line.strip()]
        completions = [x for x in events if x.get('type') == 'turn.completed']
        require(len(completions) == 1 and completions == receipt['usage'], name + ': CLI/receipt completion mismatch')
        require(not any(x.get('type') in {'error', 'turn.failed'} for x in events), name + ': CLI error')
        items = [x['item'] for x in events if x.get('type') == 'item.completed']
        require(all(x.get('type') in {'agent_message', 'reasoning', 'error'} for x in items), name + ': unexpected native tool item')
        warnings = [x.get('message', '') for x in items if x.get('type') == 'error']
        require(all(text.startswith(('Under-development features enabled:', 'Exceeded skills context budget.'))
                    for text in warnings), name + ': unrecognized CLI diagnostic requires review')
        item['local_configuration_warnings'] = warnings
        response = self.read('calls/' + name + '/response.json')
        require(any(x.get('type') == 'agent_message' and json.loads(x['text']) == response for x in items),
                name + ': response differs from completed model message')
        normalized = normalize_decision(response)
        if (folder / 'decision.json').exists():
            require(self.read('calls/' + name + '/decision.json') == normalized, name + ': transformed decision mismatch')
            item['status'] = 'completed'
        else:
            item['status'] = 'completed_response_pending_consumption'
        item['decision'] = normalized
        self.calls[number] = item
        return item

    def verify_context(self, call, replay):
        context, phase = call['context'], call['phase']
        require(context['phase'] == phase and context['guard'] == self.state['guard'], 'Call context phase/guard mismatch')
        require(context['incumbent'] == replay['best'], 'Call received an incorrect incumbent')
        require(context['previous_reflection'] == replay['last_reflection'], 'Next call lacks the exact previous reflection')
        require(context['recent_cycles'] == compact_history(replay['cycles']), 'Compact measured history changed or is incomplete')
        close(context['minimum_MAE_gain_K'], self.state['config']['min_improvement_K'], 'Predeclared improvement threshold')
        policy = context['continuation_policy']
        completed = len(unique_measured(replay['cycles']))
        require(policy['required_successful_unique_cycles'] == 22
                and policy['completed_successful_unique_cycles'] == completed
                and policy['minimum_pending'] == (completed < 22), 'Model received incorrect completion-floor policy')
        budget = context['budget']
        require(budget['remaining_experiments'] == self.state['config']['max_experiments'] - replay['attempts']
                and budget['remaining_llm_calls'] == self.state['config']['max_llm_calls'] - replay['calls']
                and budget['stagnation'] == replay['stagnation'], 'Context budget/history counters mismatch')
        workbench = context['training_workbench']
        require(workbench['rows'] == 3764 and workbench['groups'] == 1117 and workbench['folds'] == 3,
                'Context reports a different training cohort')
        known_ids = []
        for known in workbench['known_specifications']:
            candidate = self.candidate(known['id'])
            require(known['spec'] == candidate['specification'] and known['fingerprint'] == candidate['fingerprint'],
                    'Known strategy specification/fingerprint mismatch')
            compare_metrics(known['metrics'], compact_metrics(candidate['metrics']), 'Context known/' + known['id'])
            known_ids.append(known['id'])
        require(len(known_ids) == len(set(known_ids)), 'Duplicate known candidate IDs in context')
        if phase == 'reflect':
            require(context['proposal'] == replay['proposal'] and context['observed_result'] == replay['observed'],
                    'Reflection lacks the exact executed proposal and measured result')

    def verify_observation(self, payload, replay):
        cid, result = payload['candidate_id'], payload['result']
        require(replay['proposal'] is not None and cid == replay['proposal']['candidate_id'], 'Observed experiment has no matching proposal')
        if not isinstance(result.get('metrics'), dict):
            require(result.get('status') == 'failed' and result.get('scientific_evidence_available') is False,
                    'Unmeasured experiment not explicitly marked failed')
            require(result['guard_eligible'] is False and result['improved_incumbent'] is False,
                    'Failed experiment claimed eligibility/improvement')
            replay['stagnation'] += 1
            return {'id': cid, 'status': 'failed', 'error': result.get('error'), 'counted': False}
        candidate = self.candidate(cid)
        require(candidate['specification'] == replay['proposal']['specification'] == result['spec'],
                cid + ': execution differs from model proposal')
        compare_metrics(result['metrics'], candidate['metrics'], cid + '/controller observation')
        evaluation = self.read('cycles/' + cid + '/evaluation.json')
        request = self.read('cycles/' + cid + '/request.json')
        require(request == {'candidate_id': cid, 'specification': replay['proposal']['specification']}, cid + ': worker request changed')
        require(all(result.get(key) == value for key, value in evaluation.items()), cid + ': worker result changed before assessment')
        prior = replay['proposal_call']['context']['training_workbench']['known_specifications']
        duplicate = candidate['fingerprint'] in {x['fingerprint'] for x in prior}
        require(result.get('proposal_was_duplicate', result.get('reused', False)) == duplicate,
                cid + ': duplicate classification disagrees with pre-proposal known strategies')
        require(bool(candidate['result'].get('adapter_reused')) == duplicate, cid + ': stored duplicate provenance disagrees')
        metrics = candidate['metrics']
        eligible = metrics['subgroups']['positive_tc']['MAE_K'] <= self.state['guard']['positive_MAE_K'] + 1e-12
        gain = replay['best']['MAE_K'] - metrics['MAE_K']
        improved = eligible and not duplicate and gain >= self.state['config']['min_improvement_K'] and gain > 1e-12
        require(result['guard_eligible'] == eligible and result['improved_incumbent'] == improved,
                cid + ': deterministic selection assessment differs from independent replay')
        close(result['MAE_gain_over_previous_incumbent_K'], gain, cid + '/incumbent gain')
        before = copy.deepcopy(replay['best'])
        if improved:
            replay['best'] = {'id': cid, 'MAE_K': metrics['MAE_K']}
            replay['stagnation'] = 0
        else:
            replay['stagnation'] += 1
        fits = result['candidate_total_regressor_fits']
        require(isinstance(fits, int) and fits >= 0, cid + ': invalid fit count')
        require(fits == candidate['result'].get('candidate_total_regressor_fits', candidate['result']['actual_model_fits']),
                cid + ': total candidate fit count mismatch')
        if duplicate:
            require(fits == result['actual_new_regressor_fits'] == 0, cid + ': duplicate spent new fitting work')
        else:
            require(fits == sum(x['fit_count'] for x in candidate['result']['fold_details']), cid + ': fold fit totals mismatch')
            require(result['actual_new_regressor_fits'] in (0, fits), cid + ': recovery fit accounting inconsistent')
        return {'id': cid, 'status': 'measured', 'duplicate_proposal': duplicate,
                'MAE_K': metrics['MAE_K'], 'positive_Tc_MAE_K': metrics['subgroups']['positive_tc']['MAE_K'],
                'guard_eligible': eligible, 'improved_incumbent': improved, 'gain_K': gain,
                'incumbent_before': before, 'incumbent_after': copy.deepcopy(replay['best']),
                'candidate_regressor_fits': fits, 'counted': not duplicate,
                'fingerprint': candidate['fingerprint']}

    def audit(self):
        new_events = self.verify_lineage()
        self.verify_training()
        guard = self.candidate('G01')['metrics']['subgroups']['positive_tc']['MAE_K']
        close(self.state['guard']['positive_MAE_K'], guard, 'Fixed G01 positive-Tc guard')
        close(self.parent['best']['MAE_K'], self.candidate('A05')['metrics']['MAE_K'], 'Initial A05 incumbent')
        replay = {'best': copy.deepcopy(self.parent['best']), 'stagnation': self.parent['stagnation'],
                  'attempts': self.parent['attempts'], 'calls': self.parent['llm_calls'],
                  'elapsed': self.parent['elapsed_seconds'], 'cycles': copy.deepcopy(self.parent['completed_cycles']),
                  'last_reflection': self.parent['last_reflection'], 'proposal': None, 'observed': None,
                  'proposal_call': None, 'last_call': None}
        observations, deferred = [], []
        for event in new_events:
            kind, payload = event['kind'], event['payload']
            if kind == 'runtime.elapsed':
                require(math.isfinite(payload['seconds']) and payload['seconds'] >= 0, 'Invalid charged duration')
                replay['elapsed'] += payload['seconds']
            elif kind == 'llm.reserved':
                require(payload['number'] == replay['calls'] + 1, 'Call reservation reset/gap')
                call = self.call(payload['number'], payload['phase'])
                self.verify_context(call, replay)
                replay['last_call'] = call
                replay['calls'] += 1
            elif kind == 'proposal.accepted':
                call = replay['last_call']
                require(call['phase'] == 'propose' and call.get('decision') is not None, 'Accepted proposal has no completed model decision')
                replay['attempts'] += 1
                require(payload == {**call['decision'], 'candidate_id': f'L{replay["attempts"]:03d}'},
                        'Accepted proposal differs from the model decision')
                replay.update(proposal=payload, proposal_call=call, observed=None)
            elif kind == 'experiment.started':
                require(replay['proposal'] is not None and payload['candidate_id'] == replay['proposal']['candidate_id'],
                        'Numerical experiment has no accepted proposal')
            elif kind == 'experiment.observed':
                require(replay['observed'] is None, 'Experiment result assessed twice')
                observations.append(self.verify_observation(payload, replay))
                replay['observed'] = payload['result']
            elif kind == 'cycle.completed':
                call = replay['last_call']
                require(call['phase'] == 'reflect' and call.get('decision') is not None, 'Cycle completed without a model reflection')
                proposal = replay['proposal']
                expected = {'candidate_id': proposal['candidate_id'], 'hypothesis': proposal.get('hypothesis'),
                            'revision_of': proposal.get('revision_of'), 'specification': proposal.get('specification'),
                            'evaluation': replay['observed'], 'reflection': call['decision']}
                require(payload == expected, 'Completed cycle does not preserve proposal/result/reflection')
                replay['cycles'].append(payload)
                replay.update(last_reflection=call['decision'], proposal=None, observed=None)
            elif kind == 'agent.stop_deferred':
                require(len(unique_measured(replay['cycles'])) < 22, 'Stop deferred after completion minimum')
                require(payload['completed'] == len(unique_measured(replay['cycles'])) and payload['minimum'] == 22,
                        'Deferred-stop minimum/counter mismatch')
                key = 'proposal' if payload['phase'] == 'propose' else 'reflection'
                require(payload[key] == replay['last_call'].get('decision'), 'Deferred stop does not match model decision')
                deferred.append({'seq': event['seq'], 'phase': payload['phase'], 'completed': payload['completed']})
            elif kind in ('run.stopped', 'run.resumed'):
                pass
            else:
                raise ValueError('Unrecognized post-lineage event requires explicit audit: ' + kind)
        require(replay['cycles'] == self.state['completed_cycles'], 'SQLite cycles differ from journal replay')
        require(replay['best'] == self.state['best'] and replay['stagnation'] == self.state['stagnation'],
                'Final incumbent/stagnation differ from deterministic journal replay')
        require(replay['attempts'] == self.state['attempts'] and replay['calls'] == self.state['llm_calls'],
                'Cumulative experiment/model-call counters changed')
        close(self.state['elapsed_seconds'], replay['elapsed'], 'Cumulative active runtime')
        require(replay['last_reflection'] == self.state['last_reflection'], 'Final reflection differs from consumed history')
        require(replay['proposal'] == self.state['pending_plan'] and replay['observed'] == self.state['pending_result'],
                'Pending numerical work differs from journal replay')

        counted = unique_measured(replay['cycles'])
        inherited = unique_measured(self.parent['completed_cycles'])
        additional = counted - inherited
        complete = (self.state['status'] == 'stopped' and len(counted) >= 22 and len(additional) >= 20
                    and all(self.state[x] is None for x in ('pending_call', 'pending_plan', 'pending_result')))
        if not self.allow_incomplete:
            require(complete, f'Continuation incomplete: {len(additional)} additional successful unique cycles; status={self.state["status"]}')
            require(self.state['stop_reason'] == 'minimum_completed_experiments_reached', 'Unexpected completed-run stop reason')
            require(not self.index.get('pending'), 'Final adapter still has pending numerical work')
            require(all(call['status'] == 'completed' for call in self.calls.values()), 'Unresolved/failed model reservation in final audit')
        if 'successful_unique_cycles' in self.state:
            require(self.state['successful_unique_cycles'] == len(counted), 'Exported success count disagrees with independent count')
        successful_calls = [call for call in self.calls.values() if call['status'].startswith('completed')]
        usage = {}
        for call in successful_calls:
            for key, value in call['receipt']['usage'][0]['usage'].items():
                usage[key] = usage.get(key, 0) + value
        prediction_equivalence = self.equivalent_predictions(observations)
        parent_recheck = self.verify_original_parent_unchanged() if complete and not self.public else {
            'verified': None, 'reason': 'Original machine paths are not accessed in public mode' if self.public
            else 'Full original-parent-tree check is deferred until final completion'}
        return {
            'audited_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
            'checks_passed': True, 'final_completion_verified': complete, 'allow_incomplete': self.allow_incomplete,
            'snapshot': {'state_sha256': fingerprint(self.state), 'journal_sha256': fingerprint(self.events),
                         'last_event_seq': self.events[-1]['seq'], 'status': self.state['status'],
                         'phase': self.state['phase'], 'stop_reason': self.state['stop_reason']},
            'inherited_successful_unique_cycles': len(inherited), 'additional_successful_unique_cycles': len(additional),
            'total_successful_unique_cycles': len(counted), 'new_completed_cycles_including_failed_or_duplicate': len(replay['cycles']) - 2,
            'new_attempts': replay['attempts'] - self.parent['attempts'], 'cumulative_attempts': replay['attempts'],
            'new_call_reservations': replay['calls'] - self.parent['llm_calls'], 'cumulative_call_reservations': replay['calls'],
            'new_successful_model_calls': len(successful_calls), 'new_successful_call_usage': usage,
            'call_status': [{key: item[key] for key in ('number', 'phase', 'folder', 'status')} for item in self.calls.values()],
            'initial_incumbent': self.parent['best'], 'final_or_current_incumbent': replay['best'],
            'fixed_positive_guard': self.state['guard'], 'required_MAE_gain_K': self.state['config']['min_improvement_K'],
            'new_candidate_regressor_fits': sum(x.get('candidate_regressor_fits', 0) for x in observations),
            'new_charged_active_seconds': replay['elapsed'] - self.parent['elapsed_seconds'],
            'cumulative_charged_active_seconds': replay['elapsed'], 'deferred_model_stops': deferred,
            'incumbent_and_observation_path': observations,
            'prediction_equivalence': prediction_equivalence,
            'original_parent_tree_final_recheck': parent_recheck,
            'candidate_records_checked': len(self.candidates),
            'independently_recomputed_candidate_ids': sorted(cid for cid, item in self.candidates.items() if item['independently_recomputed']),
            'prior_reference_ids_checked_against_inherited_context_only': sorted(cid for cid, item in self.candidates.items() if not item['independently_recomputed']),
            'local_cli_warning_counts': {str(number): len(item.get('local_configuration_warnings', [])) for number, item in self.calls.items()},
            'evidence_mode': 'public_export' if self.public else 'live_runtime_read_only_sqlite',
            'training_source_hash_check': 'Manifest/lineage linkage and included OOF bytes; original source paths are not accessed' if self.public else 'Original frozen-source and isolated-copy bytes checked against hashes',
            'method': 'Independent NumPy/pandas OOF metrics; full event replay and proposal/feedback/receipt/specification/hash checks. No evaluator imports or model calls.',
            'limitations': ['Adaptive reuse of previously observed training OOF; this is not an independent generalization test.',
                           'LLM decisions are confirmed against saved CLI traces; the audit does not prove a causal benefit of natural-language reasoning.',
                           'OOF coverage/grouping and predictions are checked; no refitting is performed.',
                           'Different configurations can yield identical predictions. Prediction-equivalence groups are reported separately and do not alter the predeclared configuration count. Rounds are not independent scientific evidence.',
                           'Public-export mode checks training provenance manifest linkage and inherited L001 cohort identity. Unbundled prior-reference metrics are checked against inherited model context; A05, G01 and all continuation candidates are independently recomputed.',
                           'During a preliminary audit, child artifacts may advance beyond the authoritative SQLite snapshot. Pending reservations are explicitly reported.'],
            'training_source_sha256': dict(sorted(self.source_hashes.items())),
            'run_evidence_sha256': dict(sorted(self.hashes.items())),
            'auditor_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-incomplete', action='store_true')
    args = parser.parse_args()
    report = Auditor(args.run_dir, args.allow_incomplete).audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('checks_passed', 'final_completion_verified',
          'additional_successful_unique_cycles', 'total_successful_unique_cycles', 'new_successful_model_calls',
          'new_candidate_regressor_fits', 'final_or_current_incumbent')}, indent=2))


if __name__ == '__main__':
    main()
