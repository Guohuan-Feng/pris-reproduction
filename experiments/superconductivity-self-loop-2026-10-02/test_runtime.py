"""Persistence, exclusive ownership and cancellation tests using short local children."""
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from runtime import Store, exclusive, run_child, Cancelled, BudgetExpired, read_json, write_json


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='tc-runtime-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_state_and_event_are_one_transaction_and_reopen_cleanly(self):
        store = Store(self.root)
        store.save({'attempts': 1, 'elapsed_seconds': 2.5}, 'cycle.complete', {'id': 'L001'})
        with self.assertRaises(ValueError):
            store.save({'attempts': 2}, 'bad.event', {'not_finite': float('nan')})
        store.close()
        reopened = Store(self.root)
        try:
            self.assertEqual(reopened.state()['attempts'], 1)
            self.assertEqual([x['kind'] for x in reopened.history()], ['cycle.complete'])
            reopened.export()
            self.assertEqual(read_json(self.root / 'status.json'), reopened.state())
            self.assertEqual(read_json(self.root / 'memory_export.json'), reopened.history())
        finally:
            reopened.close()

    def test_second_owner_is_rejected_and_lock_reusable_after_release(self):
        lock = self.root / 'controller.lock'
        with exclusive(lock):
            with self.assertRaisesRegex(RuntimeError, 'active owner'):
                with exclusive(lock):
                    self.fail('Two controllers acquired the same run')
        with exclusive(lock):
            pass

    def test_lock_is_released_after_owner_process_crashes(self):
        script = ('import os,sys\nfrom runtime import exclusive\n'
                  'with exclusive(sys.argv[1]):\n os._exit(7)\n')
        result = subprocess.run([sys.executable, '-c', script, str(self.root / 'controller.lock')],
                                cwd=Path(__file__).parent, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 7)
        with exclusive(self.root / 'controller.lock'):
            pass

    def test_atomic_json_rejects_nonfinite_without_replacing_prior_value(self):
        target = self.root / 'state.json'
        write_json(target, {'value': 1})
        with self.assertRaises(ValueError):
            write_json(target, {'value': float('nan')})
        self.assertEqual(read_json(target), {'value': 1})

    def test_normal_child_exit_accounts_time_and_releases_lock(self):
        elapsed = []
        rc = run_child([sys.executable, '-c', 'print("done")'], self.root,
                       self.root / 'child', 5, tick=elapsed.append)
        self.assertEqual(rc, 0)
        self.assertGreater(sum(elapsed), 0.)
        self.assertIn('done', (self.root / 'child' / 'stdout.jsonl').read_text())
        with exclusive(self.root / 'child.lock'):
            pass

    def test_preexisting_stop_prevents_process_launch(self):
        (self.root / 'STOP').write_text('stop', encoding='utf-8')
        with self.assertRaises(Cancelled):
            run_child([sys.executable, '-c', 'raise Exception("must not run")'],
                      self.root, self.root / 'child', 5)
        self.assertFalse((self.root / 'child' / 'process.json').exists())

    def test_running_child_cancelled_promptly_and_elapsed_time_charged(self):
        folder = self.root / 'child'
        def cancel():
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not (folder / 'process.json').exists():
                time.sleep(.01)
            (self.root / 'STOP').write_text('stop', encoding='utf-8')
        thread = threading.Thread(target=cancel, daemon=True)
        thread.start()
        elapsed = []
        start = time.monotonic()
        try:
            with self.assertRaises(Cancelled):
                run_child([sys.executable, '-c', 'import time; time.sleep(30)'],
                          self.root, folder, 10, tick=elapsed.append)
        finally:
            thread.join(timeout=6)
        self.assertFalse(thread.is_alive())
        self.assertLess(time.monotonic() - start, 8.)
        self.assertGreater(sum(elapsed), 0., 'Cancelled work must consume cumulative time budget')
        with exclusive(self.root / 'child.lock'):
            pass

    def test_short_timeout_is_accounted_and_child_lock_released(self):
        elapsed = []
        with self.assertRaises(BudgetExpired):
            run_child([sys.executable, '-c', 'import time; time.sleep(30)'],
                      self.root, self.root / 'child', .05, tick=elapsed.append)
        self.assertGreater(sum(elapsed), 0.)
        with exclusive(self.root / 'child.lock'):
            pass


if __name__ == '__main__':
    unittest.main()
