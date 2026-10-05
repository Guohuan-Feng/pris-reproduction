"""No-fit tests for authorized continuation copies and immutable lineage."""
from pathlib import Path
import tempfile
import unittest

from fork_run import fork_run, sha, tree_hashes, UPDATES
from runtime import Store, exclusive, read_json, write_json


class ForkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.parent, self.child = self.root / "parent", self.root / "child"
        self.parent.mkdir()
        for name in ("controller.lock", "child.lock"):
            (self.parent / name).write_bytes(b"0")
        self.state = {"status": "stopped", "phase": "propose", "config": {"max_experiments": 2, "max_llm_calls": 6,
                      "max_seconds": 1200., "max_call_seconds": 240., "max_fit_seconds": 240., "patience": 4,
                      "min_improvement_K": .01, "model": "gpt-5.6-sol"},
                      "attempts": 2, "llm_calls": 5, "elapsed_seconds": 223.108, "stagnation": 2,
                      "best": {"id": "A05", "MAE_K": 7.75}, "guard": {"anchor": "G01", "positive_MAE_K": 8.83},
                      "last_reflection": {"next_action": "stop", "summary": "old budget exhausted"},
                      "stop_reason": "agent_stop", "pending_call": None, "pending_plan": None, "pending_result": None,
                      "completed_cycles": [{"candidate_id": "L00" + str(i), "specification": {"choice": i},
                                            "evaluation": {"metrics": {"MAE_K": 7.8}, "proposal_was_duplicate": False}}
                                           for i in (1, 2)]}
        store = Store(self.parent)
        store.save(self.state, "run.stopped", {"old": True})
        store.export()
        store.close()
        (self.parent / "workbench/data").mkdir(parents=True)
        (self.parent / "workbench/data/train.csv.gz").write_bytes(b"train-only-test-fixture")
        write_json(self.parent / "workbench_manifest.json", {"source_dir": str(self.root / "source"),
                   "files": {"data/train.csv.gz": {"sha256": sha(self.parent / "workbench/data/train.csv.gz")}}})
        write_json(self.parent / "adapter_index.json", {"version": 1, "evidence": {}, "pending": {}})
        for folder in ("calls/001_propose", "cycles/L001"):
            (self.parent / folder).mkdir(parents=True)
            write_json(self.parent / folder / "evidence.json", {"history": True})

    def tearDown(self):
        self.temp.cleanup()

    def test_fork_preserves_parent_counters_history_and_source_hashes(self):
        before = tree_hashes(self.parent)
        result = fork_run(self.parent, self.child, verify_adapter=False)
        self.assertEqual(before, tree_hashes(self.parent))
        self.assertFalse(result["controller_launched"])
        state = read_json(self.child / "status.json")
        for name in ("attempts", "llm_calls", "elapsed_seconds", "completed_cycles", "best", "last_reflection"):
            self.assertEqual(state[name], self.state[name])
        self.assertEqual(state["status"], "running")
        self.assertIsNone(state["stop_reason"])
        for name, value in UPDATES.items():
            self.assertEqual(state["config"][name], value)
        events = read_json(self.child / "memory_export.json")
        self.assertEqual(events[0]["kind"], "run.stopped")
        self.assertEqual(events[-1]["kind"], "run.continuation_authorized")
        self.assertEqual(events[-1]["payload"]["source_hashes"], before)
        self.assertEqual(sha(self.child / "lineage/parent/status.json"), before["status.json"])
        self.assertEqual(sha(self.child / "lineage.json"), events[-1]["payload"]["lineage_sha256"])
        with self.assertRaisesRegex(ValueError, "absent or empty"):
            fork_run(self.parent, self.child, verify_adapter=False)

    def test_active_owner_prevents_any_continuation(self):
        with exclusive(self.parent / "child.lock"):
            with self.assertRaisesRegex(RuntimeError, "active owner"):
                fork_run(self.parent, self.child, verify_adapter=False)
        self.assertFalse(self.child.exists())

    def test_non_training_manifest_artifact_is_rejected(self):
        manifest = read_json(self.parent / "workbench_manifest.json")
        manifest["files"]["data/validation_labels.csv.gz"] = {"sha256": "forbidden"}
        write_json(self.parent / "workbench_manifest.json", manifest)
        with self.assertRaisesRegex(ValueError, "non-training"):
            fork_run(self.parent, self.child, verify_adapter=False)
        self.assertFalse(self.child.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
