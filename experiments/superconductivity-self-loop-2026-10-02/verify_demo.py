"""Independently verify the published two-cycle self-loop demonstration.

This checker never imports or calls the experiment's evaluator, controller,
adapter, models, or model service.  It recalculates metrics from saved OOF rows
and cross-checks the persisted decision/evidence chain.  It does not establish
independent predictive generalization or prove that natural-language reasoning
caused a particular choice.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


CALLS = ('002_propose', '003_reflect', '004_propose', '005_reflect')
CANDIDATES = ('L001', 'L002')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(actual, expected, context):
    require(isinstance(actual, (int, float)) and math.isfinite(actual),
            context + ': missing/nonfinite numeric value')
    require(math.isclose(float(actual), float(expected), rel_tol=1e-10, abs_tol=1e-10),
            f'{context}: {actual!r} != independently recomputed {expected!r}')


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)


def normalized_response(value):
    value = copy.deepcopy(value)
    if value.get('specification') is not None:
        experts = value['specification']['experts']
        require(isinstance(experts, list), 'Raw model proposal experts must be a list')
        require(len({x['route'] for x in experts}) == len(experts), 'Duplicate expert in raw response')
        value['specification']['experts'] = {
            x['route']: {'model': x['model'], 'target': x['target']} for x in experts}
    return value


def basic_metrics(frame):
    error = frame.prediction.to_numpy(float) - frame.tc.to_numpy(float)
    weight = frame.weight.to_numpy(float)
    require(len(frame) > 0 and np.isfinite(error).all() and np.isfinite(weight).all(),
            'OOF metrics require finite, nonempty rows')
    require((weight > 0).all(), 'OOF weights must be positive')
    return {'rows': len(frame), 'groups': int(frame.group.nunique()),
            'weight_sum': float(weight.sum()),
            'MAE_K': float(np.average(np.abs(error), weights=weight)),
            'RMSE_K': float(np.sqrt(np.average(error ** 2, weights=weight))),
            'bias_K': float(np.average(error, weights=weight))}


def independent_metrics(frame):
    value = basic_metrics(frame)
    value['subgroups'] = {
        'reported_zero': basic_metrics(frame.loc[frame.tc == 0]),
        'positive_tc': basic_metrics(frame.loc[frame.tc > 0]),
        'high_tc_ge40K': basic_metrics(frame.loc[frame.tc >= 40]),
    }
    return value


def compare_metrics(actual, expected, context):
    for key, value in expected.items():
        require(key in actual, context + ': missing metric ' + key)
        if isinstance(value, dict):
            compare_metrics(actual[key], value, context + '/' + key)
        else:
            close(actual[key], value, context + '/' + key)


def verify(evidence):
    evidence = Path(evidence).resolve()
    files = {}

    def read(relative, as_json=True):
        path = evidence / relative
        require(path.is_file(), 'Missing evidence file: ' + relative)
        raw = path.read_bytes()
        files[relative] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw.decode('utf-8')) if as_json else raw.decode('utf-8')

    state = read('status.json')
    memory = read('memory_export.json')
    require(state['status'] == 'stopped', 'Demonstration is not complete/stopped')
    require(state['phase'] == 'propose', 'Unexpected terminal phase')
    require(state['attempts'] == state['config']['max_experiments'] == 2, 'Expected two budgeted attempts')
    require(state['llm_calls'] == 5, 'Expected five spent reservations including local preflight failure')
    require(state['stagnation'] == 2, 'Expected two non-improving experiments')
    require(all(state[key] is None for key in ('pending_call', 'pending_plan', 'pending_result')),
            'Run retains unfinished work')
    require([x['candidate_id'] for x in state['completed_cycles']] == list(CANDIDATES),
            'Expected exactly two completed cycles in order')
    require(state['best']['id'] == 'A05', 'Expected prior A05 incumbent to be retained')
    require(state['guard']['anchor'] == 'G01', 'Unexpected fixed positive-Tc guard')

    require([x['seq'] for x in memory] == list(range(1, len(memory) + 1)), 'Event journal sequence gap')
    require(all(dt.datetime.fromisoformat(memory[i]['at']) <= dt.datetime.fromisoformat(memory[i + 1]['at'])
                for i in range(len(memory) - 1)), 'Event journal time runs backwards')
    reserved = [x for x in memory if x['kind'] == 'llm.reserved']
    require([x['payload']['number'] for x in reserved] == [1, 2, 3, 4, 5], 'Reservations were reset or duplicated')
    require([x['payload']['phase'] for x in reserved] == ['propose', 'propose', 'reflect', 'propose', 'reflect'],
            'Unexpected reservation phase sequence')
    repairs = [x for x in memory if x['kind'] == 'development.preflight_repaired']
    require(len(repairs) == 1 and repairs[0]['payload']['remote_turn_started'] is False
            and repairs[0]['payload']['reservation_retained'] == 1,
            'Missing retained local-preflight-failure audit event')
    startup = read('startup_repair.json')
    require(startup == repairs[0]['payload'], 'Startup repair record and journal disagree')
    startup_stderr = read('calls/001_propose/stderr.log', False)
    require('Error loading config.toml' in startup_stderr and 'nonzero usize' in startup_stderr
            and 'skills.max_context_tokens' in startup_stderr, 'Local config rejection evidence missing')
    require(files['calls/001_propose/stderr.log'] == startup['stderr_sha256'],
            'Original startup diagnostic hash mismatch')
    require(not read('calls/001_propose/stdout.jsonl', False).strip(),
            'Failed local startup unexpectedly contains CLI turn events')
    created = [x for x in memory if x['kind'] == 'run.created']
    require(len(created) == 1 and created[0]['payload']['initial_incumbent'] == state['best'],
            'Incumbent changed despite reported non-improvements')
    cycle_events = [x for x in memory if x['kind'] == 'cycle.completed']
    require([x['payload'] for x in cycle_events] == state['completed_cycles'], 'Journal and exported cycles disagree')
    first_proposal_seq = next(x['seq'] for x in memory if x['kind'] == 'proposal.accepted')
    last_cycle_seq = cycle_events[-1]['seq']
    require(not any(x['kind'] in ('run.stopped', 'run.resumed', 'development.preflight_repaired')
                    for x in memory if first_proposal_seq < x['seq'] < last_cycle_seq),
            'The measured two-cycle chain contains an intervening stop/manual repair')
    elapsed = sum(x['payload']['seconds'] for x in memory if x['kind'] == 'runtime.elapsed')
    close(state['elapsed_seconds'], elapsed, 'Cumulative charged runtime')
    require(0 < elapsed <= state['config']['max_seconds'], 'Runtime exceeds configured cumulative budget')

    contexts, decisions, receipts = {}, {}, {}
    for name in CALLS:
        folder = 'calls/' + name + '/'
        context = contexts[name] = read(folder + 'frozen_context.json')
        decision = decisions[name] = read(folder + 'decision.json')
        response = read(folder + 'response.json')
        receipt = receipts[name] = read(folder + 'receipt.json')
        schema = read(folder + 'schema.json')
        require(set(schema['required']).issubset(response), name + ': response lacks required fields')
        require(set(response).issubset(schema['properties']), name + ': response includes unrecognized fields')
        require(normalized_response(response) == decision, name + ': persisted decision differs from model response')
        require(context['phase'] == name.split('_', 1)[1], name + ': wrong context phase')
        require(context['guard'] == state['guard'] and context['incumbent'] == state['best'],
                name + ': objective/guard/incumbent changed')
        require(receipt['completed'] is True and receipt['exit_code'] == 0, name + ': unsuccessful model receipt')
        require(receipt['native_tool_events'] == [] and receipt['errors'] == [], name + ': unexpected native tools/errors')
        events = [json.loads(line) for line in read(folder + 'stdout.jsonl', False).splitlines() if line.strip()]
        completed = [x for x in events if x.get('type') == 'turn.completed']
        require(len(completed) == 1 and completed == receipt['usage'], name + ': receipt and CLI completion disagree')
        require(not any(x.get('type') in ('error', 'turn.failed') for x in events), name + ': CLI reported failure')
        tool_events = [x['item'] for x in events if x.get('type') == 'item.completed'
                       and x.get('item', {}).get('type') not in ('agent_message', 'reasoning', 'error')]
        require(tool_events == [], name + ': native tool execution detected')
        require(any(x.get('type') == 'item.completed' and x.get('item', {}).get('type') == 'agent_message'
                    and json.loads(x['item']['text']) == response for x in events),
                name + ': saved response not found in the completed CLI agent message')

    require(decisions['003_reflect']['next_action'] == 'continue', 'First reflection did not request continuation')
    require(contexts['004_propose']['previous_reflection'] == decisions['003_reflect'],
            'Second proposal did not receive the exact first reflection')
    require(contexts['004_propose']['recent_cycles'][-1] == state['completed_cycles'][0],
            'Second proposal lacks first measured cycle feedback')
    require(decisions['005_reflect']['next_action'] == 'stop'
            and state['last_reflection'] == decisions['005_reflect'], 'Terminal reflection is inconsistent')
    require(decisions['002_propose']['specification'] != decisions['004_propose']['specification'],
            'Second experiment repeats first specification')
    require('L001' in decisions['004_propose']['hypothesis'], 'Second hypothesis does not identify prior experiment evidence')

    rows, fits = {}, 0
    candidate_prefix = 'candidates' if (evidence / 'candidates').is_dir() else 'workbench/candidates'
    for index, cid in enumerate(CANDIDATES):
        proposal_name, reflection_name = CALLS[index * 2:index * 2 + 2]
        proposal, reflection = decisions[proposal_name], decisions[reflection_name]
        cycle = state['completed_cycles'][index]
        request = read('cycles/' + cid + '/request.json')
        evaluation = read('cycles/' + cid + '/evaluation.json')
        prefix = candidate_prefix + '/' + cid + '/'
        specification, result = read(prefix + 'specification.json'), read(prefix + 'result.json')
        for item in (request, result, evaluation):
            require(item['candidate_id'] == cid, cid + ': candidate ID mismatch')
        require(request['specification'] == specification == result['specification']
                == proposal['specification'] == cycle['specification'] == evaluation['spec'],
                cid + ': proposed/executed/recorded specifications differ')
        require(cycle['reflection'] == reflection and cycle['hypothesis'] == proposal['hypothesis'],
                cid + ': cycle proposal/reflection mismatch')
        require(contexts[reflection_name]['observed_result'] == cycle['evaluation'],
                cid + ': reflection did not receive the actual assessed result')
        for key, value in evaluation.items():
            require(cycle['evaluation'][key] == value, cid + ': numerical outcome changed before reflection')
        for relative, expected in ((prefix + 'specification.json', result['specification_sha256']),
                                   (prefix + 'oof_predictions.csv.gz', result['oof_predictions_sha256'])):
            data = (evidence / relative).read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            require(digest == expected, cid + ': candidate artifact hash mismatch')
            files[relative] = digest
        table = pd.read_csv(evidence / prefix / 'oof_predictions.csv.gz', float_precision='round_trip')
        require(len(table) == 3764 and table.material_id.is_unique and not table.material_id.isna().any(),
                cid + ': incomplete or duplicated OOF rows')
        require(table.group.nunique() == 1117 and not table.group.isna().any(), cid + ': group count mismatch')
        require(set(table.fold) == {0, 1, 2} and table.groupby('group').fold.nunique().max() == 1,
                cid + ': connected group appears in multiple folds')
        require(np.isfinite(table[['tc', 'prediction', 'weight']].to_numpy(float)).all()
                and (table.tc >= 0).all() and (table.prediction >= 0).all(), cid + ': invalid numeric OOF values')
        computed = independent_metrics(table)
        compare_metrics(result['metrics'], computed, cid + '/candidate')
        compare_metrics(evaluation['metrics'], computed, cid + '/evaluation')
        compare_metrics(cycle['evaluation']['metrics'], computed, cid + '/state')
        rows[cid] = table
        require(computed['subgroups']['positive_tc']['MAE_K'] <= state['guard']['positive_MAE_K'],
                cid + ': positive guard failed')
        require(computed['MAE_K'] > state['best']['MAE_K'], cid + ': expected non-improvement disagrees with rows')
        assessed = cycle['evaluation']
        require(assessed['guard_eligible'] is True and assessed['improved_incumbent'] is False,
                cid + ': deterministic assessment incorrectly claims gain')
        close(assessed['MAE_gain_over_previous_incumbent_K'], state['best']['MAE_K'] - computed['MAE_K'],
              cid + ': incumbent delta')
        require(reflection['hypothesis_status'] == 'not_supported', cid + ': reflection contradicts no-gain conclusion')
        require(not evaluation['reused'] and not evaluation['proposal_was_duplicate'], cid + ': expected newly fitted experiment')
        count = evaluation['actual_new_regressor_fits']
        require(count == evaluation['candidate_total_regressor_fits'] == result['actual_model_fits']
                == sum(x['fit_count'] for x in result['fold_details']), cid + ': regressor fit accounting mismatch')
        require(count == (9, 12)[index], cid + ': unexpected number of fits')
        fits += count

    require(rows['L001'][['material_id', 'group', 'tc', 'weight', 'fold']].equals(
            rows['L002'][['material_id', 'group', 'tc', 'weight', 'fold']]), 'The two experiments use different OOF cohorts/folds')
    require(fits == 21, 'Expected 21 total new regressor fits')
    first_context = contexts['002_propose']
    references = {x['id']: x for x in first_context['training_workbench']['known_specifications']}
    close(references['A05']['metrics']['MAE_K'], state['best']['MAE_K'], 'Recorded A05 incumbent reference')
    close(references['G01']['metrics']['subgroups']['positive_tc']['MAE_K'],
          state['guard']['positive_MAE_K'], 'Recorded G01 positive guard reference')

    summary = read('run_summary.json')
    require(summary['completed_cycles'] == 2 and summary['reserved_calls'] == 5
            and summary['pre_remote_config_failures'] == 1 and summary['new_regressor_fits'] == 21,
            'Public run summary misstates execution counts')
    require(summary['successful_model_calls'] == list(CALLS) and summary['incumbent'] == state['best'],
            'Public run summary misstates model calls/incumbent')
    close(summary['active_child_seconds'], state['elapsed_seconds'], 'Public active runtime summary')
    usage = {}
    for receipt in receipts.values():
        for key, count in receipt['usage'][0]['usage'].items():
            usage[key] = usage.get(key, 0) + count
    require(summary['usage'] == usage, 'Public token totals disagree with completed receipts')
    require([x['id'] for x in summary['cycles']] == list(CANDIDATES), 'Public cycle summary order mismatch')
    for item in summary['cycles']:
        computed = independent_metrics(rows[item['id']])
        close(item['weighted_OOF_MAE_K'], computed['MAE_K'], item['id'] + '/public OOF MAE')
        close(item['positive_Tc_MAE_K'], computed['subgroups']['positive_tc']['MAE_K'],
              item['id'] + '/public positive-Tc MAE')
        require(item['guard_eligible'] is True and item['improved_incumbent'] is False,
                'Public summary incorrectly claims scientific gain')

    for cid, proposal_name, reflection_name in zip(CANDIDATES, CALLS[::2], CALLS[1::2]):
        for kind in ('proposal.accepted', 'experiment.started', 'experiment.observed', 'cycle.completed'):
            matching = [x for x in memory if x['kind'] == kind and x['payload']['candidate_id'] == cid]
            require(len(matching) == 1, cid + ': missing or duplicated ' + kind)
        sequence = [next(x['seq'] for x in memory if x['kind'] == kind and x['payload']['candidate_id'] == cid)
                    for kind in ('proposal.accepted', 'experiment.started', 'experiment.observed', 'cycle.completed')]
        require(sequence == sorted(sequence), cid + ': propose/execute/reflect causal order is inconsistent')

    return {
        'verified_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'passed': True,
        'verification_method': 'Independent NumPy/pandas weighted metrics and persisted artifact cross-checks; no evaluator or model imports/calls.',
        'completed_cycles': 2, 'successful_model_calls': 4, 'spent_call_reservations': 5,
        'recorded_local_preflight_rejections': 1, 'new_regressor_fits': fits,
        'charged_active_seconds': state['elapsed_seconds'], 'incumbent_retained': state['best'],
        'successful_call_usage': usage,
        'fixed_positive_guard': state['guard'],
        'recomputed': {cid: independent_metrics(frame) for cid, frame in rows.items()},
        'both_candidates_guard_eligible': True, 'new_scientific_gain_demonstrated': False,
        'autonomous_feedback_chain_verified': True,
        'limitations': [
            'This verifies the saved two-cycle engineering demonstration and metric consistency, not independent generalization.',
            'Only two proposed configurations were evaluated. The full fixed action menu was not exhausted; the model phrase "exhausted fixed menu" is unsupported.',
            'A05 and G01 reference numbers are checked against initial supplied OOF memory; this checker does not refit those reference models.',
            'One local configuration rejection is retained in the audit journal; successful remote calls are evidenced by four completed CLI traces.',
        ],
        'evidence_sha256': dict(sorted(files.items())),
        'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=Path(__file__).resolve().parent / 'evidence')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'demo_verification.json')
    args = parser.parse_args()
    report = verify(args.evidence)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('passed', 'completed_cycles', 'successful_model_calls',
          'spent_call_reservations', 'new_regressor_fits', 'incumbent_retained', 'new_scientific_gain_demonstrated')}, indent=2))


if __name__ == '__main__':
    main()
