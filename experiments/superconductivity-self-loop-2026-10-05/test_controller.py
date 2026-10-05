"""Behavioral controller tests: no model/network calls or expensive fits."""
import contextlib
import copy
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from controller import Controller, WorkerExecutor
from llm_client import CodexDecider
from runtime import BudgetExpired, Store, read_json, write_json


def spec(target='raw'):
    return {'input': 'composition', 'routing': 'global',
            'global': {'model': 'extra_trees', 'target': target}, 'experts': {}}


def metrics(mae=10., positive=12.):
    return {'MAE_K': mae, 'subgroups': {'positive_tc': {'MAE_K': positive}}}


def plan(target='log1p', revision='none'):
    return {'action': 'experiment', 'hypothesis': 'A transform reduces the error.',
            'falsification': 'Fail if the positive-Tc guard deteriorates.',
            'reason': 'Investigate the observed error distribution.',
            'revision_of': revision, 'specification': spec(target), 'stop_reason': ''}


def reflection(action='continue', focus='Revise the transform after the measured error.'):
    return {'hypothesis_status': 'inconclusive', 'summary': 'Measured the proposed model.',
            'next_action': action, 'next_focus': focus, 'stop_reason': '',
            'limitations': ['Training OOF development evidence only.']}


class FakeAdapter:
    def __init__(self):
        self.known = [{'id': 'G01', 'spec': spec(), 'metrics': metrics()}]

    def known_specifications(self):
        return copy.deepcopy(self.known)

    def context(self):
        return {'scope': 'training OOF only', 'known_specifications': self.known_specifications()}


class FakeDecider:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def __call__(self, phase, context, folder, timeout, tick):
        self.calls.append((phase, copy.deepcopy(context)))
        response = next(self.responses)
        if callable(response):
            return response(phase, context, folder, timeout, tick)
        return copy.deepcopy(response)


class FakeExecutor:
    def __init__(self, adapter, outcomes):
        self.adapter = adapter
        self.outcomes = iter(outcomes)
        self.calls = []

    def __call__(self, cid, specification, timeout, tick):
        self.calls.append((cid, copy.deepcopy(specification)))
        result = copy.deepcopy(next(self.outcomes))
        if isinstance(result.get('metrics'), dict):
            self.adapter.known.append({'id': cid, 'spec': specification, 'metrics': result['metrics']})
        return result


class SimulatedCrash(BaseException):
    pass


class ControllerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='tc-controller-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.adapter = FakeAdapter()

    def control(self, decider, executor, config=None):
        value = Controller(self.root, self.adapter, decider, executor, config)
        self.addCleanup(value.store.close)
        return value

    def run_quiet(self, control):
        with contextlib.redirect_stdout(io.StringIO()):
            return control.run()

    def test_two_autonomous_cycles_second_proposal_receives_measured_feedback(self):
        decider = FakeDecider([plan(), reflection(), plan('raw', 'L001'), reflection('stop')])
        executor = FakeExecutor(self.adapter, [{'metrics': metrics(9., 11.)}, {'metrics': metrics(8.5, 11.1)}])
        state = self.run_quiet(self.control(decider, executor))
        self.assertEqual([x[0] for x in decider.calls], ['propose', 'reflect', 'propose', 'reflect'])
        second = decider.calls[2][1]
        self.assertEqual(second['previous_reflection']['next_action'], 'continue')
        self.assertEqual(second['recent_cycles'][0]['metrics']['MAE_K'], 9.)
        self.assertEqual(second['incumbent']['id'], 'L001')
        self.assertEqual(state['best'], {'id': 'L002', 'MAE_K': 8.5})
        self.assertEqual((state['attempts'], state['llm_calls']), (2, 4))
        self.assertEqual(len(state['completed_cycles']), 2)
        self.assertEqual(state['status'], 'stopped')

    def test_crash_after_durable_decision_does_not_repeat_model_call(self):
        def persist_then_crash(phase, context, folder, timeout, tick):
            write_json(folder / 'decision.json', plan())
            raise SimulatedCrash()
        first = self.control(FakeDecider([persist_then_crash]), FakeExecutor(self.adapter, []))
        with self.assertRaises(SimulatedCrash):
            self.run_quiet(first)
        self.assertEqual(first.store.state()['llm_calls'], 1)
        resumed_decider = FakeDecider([reflection('stop')])
        resumed = self.control(resumed_decider, FakeExecutor(self.adapter, [{'metrics': metrics(9., 11.)}]))
        state = self.run_quiet(resumed)
        self.assertEqual([x[0] for x in resumed_decider.calls], ['reflect'])
        self.assertEqual((state['attempts'], state['llm_calls']), (1, 2))

    def test_completed_receipt_rehydrates_without_a_new_model_request(self):
        folder = self.root / 'calls' / '001_propose'
        write_json(folder / 'receipt.json', {'completed': True})
        response = plan()
        response['specification']['experts'] = []
        write_json(folder / 'response.json', response)
        client = CodexDecider(self.root, executable=sys.executable)
        with patch('llm_client.run_child', side_effect=AssertionError('Duplicate model call')):
            result = client('propose', {}, folder, 1, lambda _: None)
        self.assertEqual(result['specification']['experts'], {})

    def test_missing_executable_is_rejected_before_any_remote_call(self):
        missing = str(self.root / 'nonexistent-codex.exe')
        with patch('llm_client.run_child', side_effect=AssertionError('Remote call attempted')):
            with self.assertRaisesRegex(RuntimeError, 'executable unavailable'):
                CodexDecider(self.root, executable=missing)
        self.assertFalse((self.root / 'calls').exists())

    def test_unknown_interrupted_model_outcome_stops_without_retry(self):
        def uncertain_call(phase, context, folder, timeout, tick):
            write_json(folder / 'process.json', {'pid': 123456789})
            raise SimulatedCrash()
        first = self.control(FakeDecider([uncertain_call]), FakeExecutor(self.adapter, []))
        with self.assertRaises(SimulatedCrash):
            self.run_quiet(first)
        decider = FakeDecider([])
        state = self.run_quiet(self.control(decider, FakeExecutor(self.adapter, [])))
        self.assertEqual(state['status'], 'attention_required')
        self.assertIn('unknown outcome', state['stop_reason'])
        self.assertEqual(decider.calls, [])
        self.assertEqual(state['llm_calls'], 1)

    def test_completed_experiment_is_recovered_without_refitting(self):
        def complete_then_crash(cid, specification, timeout, tick):
            write_json(self.root / 'cycles' / cid / 'evaluation.json', {'metrics': metrics(9., 11.)})
            raise SimulatedCrash()
        first = self.control(FakeDecider([plan()]), complete_then_crash)
        with self.assertRaises(SimulatedCrash):
            self.run_quiet(first)
        self.assertEqual(first.store.state()['phase'], 'execute')
        executor = WorkerExecutor(self.root, self.root / 'unused-source')
        resumed = self.control(FakeDecider([reflection('stop')]), executor)
        with patch('controller.run_child', side_effect=AssertionError('Repeated numerical fit')):
            state = self.run_quiet(resumed)
        self.assertEqual(state['attempts'], 1)
        self.assertEqual(state['best']['id'], 'L001')
        self.assertEqual(len(state['completed_cycles']), 1)

    def test_duplicate_and_invalid_proposals_consume_budget_and_stagnate(self):
        invalid = plan()
        invalid.pop('hypothesis')
        decider = FakeDecider([plan(), reflection(), invalid, reflection()])
        executor = FakeExecutor(self.adapter, [{'metrics': metrics(), 'reused': True}])
        state = self.run_quiet(self.control(decider, executor, {'max_experiments': 10, 'patience': 2}))
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(state['stop_reason'], 'stagnation_limit_reached')
        self.assertEqual((state['attempts'], state['llm_calls'], state['stagnation']), (2, 4, 2))
        self.assertEqual(len(executor.calls), 1)
        self.assertFalse(state['completed_cycles'][1]['evaluation']['scientific_evidence_available'])

    def test_guard_failure_cannot_replace_incumbent_even_with_lower_mae(self):
        decider = FakeDecider([plan(), reflection('stop')])
        executor = FakeExecutor(self.adapter, [{'metrics': metrics(1., 13.)}])
        state = self.run_quiet(self.control(decider, executor))
        self.assertEqual(state['best']['id'], 'G01')
        self.assertFalse(state['completed_cycles'][0]['evaluation']['guard_eligible'])
        self.assertEqual(state['stagnation'], 1)

    def test_recovered_new_candidate_remains_an_improvement_despite_cache_reuse(self):
        decider = FakeDecider([plan(), reflection('stop')])
        recovered = {'metrics': metrics(9., 11.), 'reused': True,
                     'proposal_was_duplicate': False, 'actual_new_regressor_fits': 0,
                     'candidate_total_regressor_fits': 3}
        executor = FakeExecutor(self.adapter, [recovered])
        state = self.run_quiet(self.control(decider, executor))
        self.assertEqual(state['best'], {'id': 'L001', 'MAE_K': 9.})
        self.assertTrue(state['completed_cycles'][0]['evaluation']['improved_incumbent'])
        self.assertEqual(state['stagnation'], 0)

    def test_stop_file_prevents_any_new_call(self):
        decider = FakeDecider([])
        control = self.control(decider, FakeExecutor(self.adapter, []))
        (self.root / 'STOP').write_text('requested', encoding='utf-8')
        state = self.run_quiet(control)
        self.assertEqual(state['status'], 'paused')
        self.assertEqual(decider.calls, [])
        self.assertEqual((state['llm_calls'], state['attempts']), (0, 0))

    def test_cancel_at_cycle_boundary_resumes_with_cumulative_budgets(self):
        def reflection_and_cancel(phase, context, folder, timeout, tick):
            tick(2.5)
            (self.root / 'STOP').write_text('requested', encoding='utf-8')
            return reflection()
        first = self.control(FakeDecider([plan(), reflection_and_cancel]),
                             FakeExecutor(self.adapter, [{'metrics': metrics(9., 11.)}]),
                             {'max_experiments': 2, 'max_llm_calls': 4})
        state = self.run_quiet(first)
        self.assertEqual(state['status'], 'paused')
        self.assertEqual((state['attempts'], state['llm_calls'], state['elapsed_seconds']), (1, 2, 2.5))
        (self.root / 'STOP').unlink()
        resumed = self.control(FakeDecider([plan('raw', 'L001'), reflection()]),
                               FakeExecutor(self.adapter, [{'metrics': metrics(8.8, 11.)}]))
        resumed.s.update(status='running', stop_reason=None)
        resumed.persist('test.resume')
        state = self.run_quiet(resumed)
        self.assertEqual(state['stop_reason'], 'experiment_budget_exhausted')
        self.assertEqual((state['attempts'], state['llm_calls'], state['elapsed_seconds']), (2, 4, 2.5))

    def test_time_and_call_budget_survive_new_controller(self):
        first = self.control(FakeDecider([]), FakeExecutor(self.adapter, []), {'max_seconds': 3.})
        first.tick(2.8)
        resumed = self.control(FakeDecider([]), FakeExecutor(self.adapter, []))
        self.assertAlmostEqual(resumed.s['elapsed_seconds'], 2.8)
        with self.assertRaises(BudgetExpired):
            resumed.tick(.3)
        self.assertAlmostEqual(resumed.store.state()['elapsed_seconds'], 3.1)
        state = self.run_quiet(resumed)
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(state['llm_calls'], 0)
        with self.assertRaises(ValueError):
            Controller(self.root, self.adapter, FakeDecider([]), FakeExecutor(self.adapter, []), {'max_seconds': 100.})

    def test_call_budget_requires_space_for_both_proposal_and_reflection(self):
        decider = FakeDecider([plan(), reflection()])
        executor = FakeExecutor(self.adapter, [{'metrics': metrics(9., 11.)}])
        state = self.run_quiet(self.control(decider, executor, {'max_llm_calls': 3}))
        self.assertEqual(state['stop_reason'], 'insufficient_call_budget_for_proposal_and_reflection')
        self.assertEqual(state['llm_calls'], 2)
        self.assertEqual(len(state['completed_cycles']), 1)


if __name__ == '__main__':
    unittest.main()
