"""Minimum-round continuation tests; fake decisions/fits use real controller state."""
import contextlib
import copy
import io
import json
import math
from pathlib import Path
import tempfile
import unittest

from controller import Controller
import test_controller as fixtures


def unique_spec(number):
    """Generate distinct specifications inside the fixed experiment menu."""
    return {
        'input': 'composition_repaired' if number & 1 else 'composition',
        'routing': 'chemistry',
        'global': {'model': 'hist_gradient_boosting' if number & 2 else 'extra_trees',
                   'target': 'log1p' if number & 4 else 'raw'},
        'experts': {'cu_o': {'model': 'hist_gradient_boosting' if number & 8 else 'extra_trees',
                              'target': 'log1p' if number & 16 else 'raw'}},
    }


def proposal(number):
    value = fixtures.plan()
    value['specification'] = unique_spec(number)
    return value


def successful_measurement(mae=11., positive=11.):
    return {'metrics': fixtures.metrics(mae, positive), 'reused': False,
            'proposal_was_duplicate': False, 'actual_new_regressor_fits': 3,
            'candidate_total_regressor_fits': 3}


def measured_unique_cycles(state):
    """Independent expected counting rule, separate from controller code."""
    seen = set()
    for cycle in state['completed_cycles']:
        result = cycle['evaluation']
        metric = result.get('metrics', {}).get('MAE_K')
        if result.get('status') == 'failed' or result.get('scientific_evidence_available') is False:
            continue
        if not isinstance(metric, (int, float)) or not math.isfinite(metric):
            continue
        if result.get('proposal_was_duplicate', result.get('reused', False)):
            continue
        if not cycle.get('reflection'):
            continue
        seen.add(json.dumps(cycle['specification'], sort_keys=True, separators=(',', ':')))
    return len(seen)


class MinimumRoundTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='tc-minimum-round-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.adapter = fixtures.FakeAdapter()

    def control(self, decider, executor, config):
        control = Controller(self.root, self.adapter, decider, executor, config)
        self.addCleanup(control.store.close)
        return control

    def run_quiet(self, control):
        with contextlib.redirect_stdout(io.StringIO()):
            return control.run()

    def test_reflection_stop_and_stagnation_are_deferred_until_minimum(self):
        decider = fixtures.FakeDecider([
            proposal(0), fixtures.reflection('stop'), proposal(1), fixtures.reflection('continue')])
        executor = fixtures.FakeExecutor(self.adapter, [successful_measurement(), successful_measurement()])
        control = self.control(decider, executor,
                               {'min_completed_experiments': 2, 'max_experiments': 8, 'patience': 1})
        state = self.run_quiet(control)
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(measured_unique_cycles(state), 2)
        self.assertEqual((state['attempts'], state['llm_calls']), (2, 4))
        self.assertEqual(len(executor.calls), 2)
        self.assertEqual(state['stagnation'], 2)
        self.assertTrue(any('deferred' in event['kind'] for event in control.store.history()))

    def test_proposal_stop_spends_call_budget_but_not_a_measured_round(self):
        stop = fixtures.plan()
        stop.update(action='stop', specification=None, stop_reason='No improvement so far.')
        decider = fixtures.FakeDecider([
            stop, proposal(0), fixtures.reflection('stop'), proposal(1), fixtures.reflection('stop')])
        executor = fixtures.FakeExecutor(self.adapter, [successful_measurement(), successful_measurement()])
        control = self.control(decider, executor, {'min_completed_experiments': 2, 'max_experiments': 8, 'patience': 1})
        state = self.run_quiet(control)
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(measured_unique_cycles(state), 2)
        self.assertEqual(state['attempts'], 2)
        self.assertEqual(state['llm_calls'], 5)
        self.assertEqual(len(executor.calls), 2)

    def test_failed_and_duplicate_cycles_do_not_satisfy_minimum(self):
        decider = fixtures.FakeDecider([value for n in range(4)
                                       for value in (proposal(n), fixtures.reflection('stop'))])
        failure = {'status': 'failed', 'error': 'Simulated numerical failure',
                   'scientific_evidence_available': False}
        duplicate = {'metrics': fixtures.metrics(), 'reused': True,
                     'proposal_was_duplicate': True, 'actual_new_regressor_fits': 0}
        executor = fixtures.FakeExecutor(self.adapter,
                                        [failure, duplicate, successful_measurement(), successful_measurement()])
        state = self.run_quiet(self.control(decider, executor,
                                           {'min_completed_experiments': 2, 'max_experiments': 8, 'patience': 1}))
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(len(state['completed_cycles']), 4)
        self.assertEqual(measured_unique_cycles(state), 2)
        self.assertEqual((state['attempts'], state['llm_calls']), (4, 8))

    def test_inherited_two_plus_twenty_new_cycles_reach_22_without_reset(self):
        responses = [value for n in range(2, 22)
                     for value in (proposal(n), fixtures.reflection('stop'))]
        decider = fixtures.FakeDecider(responses)
        executor = fixtures.FakeExecutor(self.adapter, [successful_measurement() for _ in range(20)])
        control = self.control(decider, executor,
                               {'min_completed_experiments': 22, 'max_experiments': 42, 'max_llm_calls': 105,
                                'max_seconds': 14400., 'max_fit_seconds': 900., 'patience': 1})
        inherited = []
        for index in range(2):
            cid = f'L{index + 1:03d}'
            item = {'candidate_id': cid, 'specification': unique_spec(index),
                    'hypothesis': 'Inherited measured hypothesis.', 'revision_of': 'none',
                    'evaluation': successful_measurement(), 'reflection': fixtures.reflection('stop')}
            inherited.append(item)
            self.adapter.known.append({'id': cid, 'spec': unique_spec(index), 'metrics': fixtures.metrics(11., 11.)})
        control.s.update(completed_cycles=copy.deepcopy(inherited), attempts=2, llm_calls=5,
                         elapsed_seconds=223.108, stagnation=2, last_reflection=fixtures.reflection('stop'))
        control.persist('test.inherited_state', {'inherited_cycles': 2})
        state = self.run_quiet(control)
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(state['completed_cycles'][:2], inherited)
        self.assertEqual(measured_unique_cycles(state), 22)
        self.assertEqual(len(executor.calls), 20)
        self.assertEqual([cid for cid, _ in executor.calls], [f'L{n:03d}' for n in range(3, 23)])
        self.assertEqual((state['attempts'], state['llm_calls']), (22, 45))
        self.assertEqual(state['elapsed_seconds'], 223.108)
        self.assertEqual(len(decider.calls), 40)

    def test_guard_failure_is_a_measured_round_without_becoming_an_incumbent(self):
        decider = fixtures.FakeDecider([proposal(0), fixtures.reflection('continue')])
        executor = fixtures.FakeExecutor(self.adapter, [successful_measurement(mae=1., positive=13.)])
        state = self.run_quiet(self.control(decider, executor,
                                           {'min_completed_experiments': 1, 'max_experiments': 8, 'patience': 1}))
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(measured_unique_cycles(state), 1)
        self.assertEqual(state['best']['id'], 'G01')
        self.assertFalse(state['completed_cycles'][0]['evaluation']['guard_eligible'])

    def test_repeated_specification_cannot_count_twice_even_if_duplicate_flag_is_missing(self):
        decider = fixtures.FakeDecider([value for n in (0, 0, 1)
                                       for value in (proposal(n), fixtures.reflection('stop'))])
        executor = fixtures.FakeExecutor(self.adapter, [successful_measurement() for _ in range(3)])
        state = self.run_quiet(self.control(decider, executor,
                                           {'min_completed_experiments': 2, 'max_experiments': 8, 'patience': 1}))
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(measured_unique_cycles(state), 2)
        self.assertEqual(state['attempts'], 3)

    def test_no_scientific_evidence_flag_excludes_even_stale_finite_metrics(self):
        decider = fixtures.FakeDecider([value for n in (0, 1)
                                       for value in (proposal(n), fixtures.reflection('stop'))])
        stale = successful_measurement()
        stale['scientific_evidence_available'] = False
        executor = fixtures.FakeExecutor(self.adapter, [stale, successful_measurement()])
        state = self.run_quiet(self.control(decider, executor,
                                           {'min_completed_experiments': 1,
                                            'max_experiments': 8, 'patience': 1}))
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(measured_unique_cycles(state), 1)
        self.assertEqual(state['successful_unique_cycles'], 1)
        self.assertTrue(state['minimum_completed_met'])
        self.assertEqual(state['attempts'], 2)

    def test_hard_attempt_budget_can_stop_with_minimum_unmet(self):
        decider = fixtures.FakeDecider([value for n in range(3)
                                       for value in (proposal(n), fixtures.reflection('stop'))])
        failure = {'status': 'failed', 'error': 'Simulated fit error', 'scientific_evidence_available': False}
        executor = fixtures.FakeExecutor(self.adapter, [failure, failure, successful_measurement()])
        state = self.run_quiet(self.control(decider, executor,
                                           {'min_completed_experiments': 2, 'max_experiments': 3, 'patience': 1}))
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(state['stop_reason'], 'experiment_budget_exhausted')
        self.assertEqual(measured_unique_cycles(state), 1)
        self.assertEqual(state['attempts'], 3)

    def test_hard_llm_budget_can_stop_with_minimum_unmet(self):
        stop = fixtures.plan()
        stop.update(action='stop', specification=None, stop_reason='Request early stopping.')
        decider = fixtures.FakeDecider([stop, proposal(0), fixtures.reflection('stop')])
        executor = fixtures.FakeExecutor(self.adapter, [successful_measurement()])
        state = self.run_quiet(self.control(decider, executor,
                                           {'min_completed_experiments': 2, 'max_experiments': 8,
                                            'max_llm_calls': 4, 'patience': 1}))
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(state['stop_reason'], 'insufficient_call_budget_for_proposal_and_reflection')
        self.assertEqual(measured_unique_cycles(state), 1)
        self.assertEqual(state['llm_calls'], 3)

    def test_user_cancellation_precedes_minimum(self):
        decider = fixtures.FakeDecider([])
        control = self.control(decider, fixtures.FakeExecutor(self.adapter, []),
                               {'min_completed_experiments': 2, 'max_experiments': 8})
        (self.root / 'STOP').write_text('User requests pause.', encoding='utf-8')
        state = self.run_quiet(control)
        self.assertEqual(state['status'], 'paused')
        self.assertEqual(measured_unique_cycles(state), 0)
        self.assertEqual(decider.calls, [])


if __name__ == '__main__':
    unittest.main()
