"""No-fit integrity, leakage, cache, and isolation tests for the adapter."""
from pathlib import Path
import builtins
import copy
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from workbench_adapter import Adapter, prepare_run, fingerprint, _sha, _save, _vendor

V2 = Path(__file__).resolve().parents[1] / "scientific_tc_2026-10-02"


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source, self.run = self.base / "frozen", self.base / "run"
        self.source.mkdir()
        (self.source / "data").mkdir()
        for name in ("pipeline.py", "prepare_data.py"):
            shutil.copyfile(V2 / name, self.source / name)
        self.pipe = _vendor(self.source)
        self.spec = {"input": "composition", "routing": "global", "global": {"model": "extra_trees", "target": "raw"}, "experts": {}}
        frame = pd.DataFrame({"material_id": ["m%d" % i for i in range(6)], "group": ["g%d" % i for i in range(6)],
                              "formula": ["f%d" % i for i in range(6)], "chemical_system": ["s%d" % i for i in range(6)],
                              "parent_id": ["p%d" % i for i in range(6)], "canonical_composition": ["c%d" % i for i in range(6)],
                              "split": ["train"] * 6, "tc": [0., 10., 20., 5., 40., 70.], "weight": [1.] * 6,
                              "comp_Z_mean": [1., 2., 3., 4., 5., 6.], "comp_fraction_Z029": [0., 1., 0., 0., 0., 0.],
                              "comp_fraction_Z008": [0., 1., 0., 0., 0., 0.]})
        self.frame = frame
        frame.to_csv(self.source / "data/train.csv.gz", index=False)
        pd.DataFrame({"material_id": frame.material_id, "group": frame.group, "fold": [0, 1, 2, 0, 1, 2]}).to_csv(self.source / "data/fold_assignments.csv", index=False)
        composition = ["comp_Z_mean", "comp_fraction_Z029", "comp_fraction_Z008"]
        schema = {"composition": composition, "excluded_predictor_metadata": ["tc", "material_id", "group", "formula", "split"],
                  "inputs": {key: composition for key in ("composition", "composition_repaired", "diagnostic_repair11", "reference_structure28")}}
        _save(self.source / "data/schema.json", schema)
        _save(self.source / "data/data_audit.json", {"prepared_sha256": {name: _sha(self.source / "data" / name) for name in ("train.csv.gz", "fold_assignments.csv", "schema.json")}})
        self._candidate("G01", self.spec)
        # Sentinels: any attempt to open these files will fail the leakage test.
        (self.source / "data/validation_inputs.csv.gz").write_text("forbidden")
        (self.source / "data/validation_labels.csv.gz").write_text("forbidden")
        (self.source / "final").mkdir()
        _save(self.source / "final/results.json", {"validation_secret_metric": 987654321})
        _save(self.source / "selection.json", {"validation_secret_metric": 987654321})
        _save(self.source / "benchmark_results.json", {"validation_secret_metric": 987654321})

    def tearDown(self):
        self.temp.cleanup()

    def _candidate(self, cid, spec, destination=None):
        root = destination if destination is not None else self.source
        folder = root / "candidates" / cid
        folder.mkdir(parents=True, exist_ok=True)
        _save(folder / "specification.json", spec)
        oof = self.frame[["material_id", "group", "tc", "weight", "formula", "chemical_system"]].copy()
        oof["fold"] = [0, 1, 2, 0, 1, 2]
        oof["prediction"] = [1., 9., 19., 6., 35., 60.]
        oof["route"] = "global"
        oof["used_model"] = "global"
        oof.to_csv(folder / "oof_predictions.csv.gz", index=False)
        result = {"candidate_id": cid, "specification": spec, "feedback_scope": "Original training fixed-group OOF only",
                  "metrics": self.pipe.metrics(oof.tc, oof.prediction, oof.weight, oof.group), "actual_model_fits": 3,
                  "elapsed_seconds": 1., "specification_sha256": _sha(folder / "specification.json"),
                  "oof_predictions_sha256": _sha(folder / "oof_predictions.csv.gz")}
        _save(folder / "result.json", result)
        return result

    def test_copy_and_all_feedback_never_opens_heldout_artifacts(self):
        builtin_open, io_open = builtins.open, io.open
        opened = []
        def guard(original):
            def wrapped(file, *args, **kwargs):
                if isinstance(file, (str, bytes, Path)):
                    name = str(file)
                    opened.append(name)
                    if any(token in name for token in ("validation_", "selection.json", "benchmark_results.json")) or Path(name).name == "results.json":
                        raise AssertionError("Heldout artifact opened: " + name)
                return original(file, *args, **kwargs)
            return wrapped
        with patch("builtins.open", guard(builtin_open)), patch("io.open", guard(io_open)):
            adapter = Adapter(self.run, self.source)
            context = adapter.context()
            cases = adapter.counterexamples("G01", 2)
            with patch.object(adapter._bench, "run_strategy", side_effect=AssertionError("A duplicate must not refit")):
                result = adapter.evaluate("S01", self.spec)
        self.assertTrue(opened)
        self.assertEqual(context["rows"], 6)
        self.assertEqual(context["guard"]["candidate_id"], "G01")
        self.assertEqual(result["actual_new_regressor_fits"], 0)
        self.assertTrue(result["reused"])
        self.assertEqual(len(cases["examples"]["overall"]), 2)
        self.assertNotIn("987654321", json.dumps([context, cases, result]))
        self.assertEqual({p.name for p in (self.run / "workbench/data").iterdir()}, {"train.csv.gz", "schema.json", "fold_assignments.csv", "data_audit.json"})
        for relative, item in adapter.manifest["files"].items():
            self.assertEqual(_sha(self.source / relative), item["sha256"])
            self.assertEqual(_sha(self.run / "workbench" / relative), item["sha256"])

    def test_duplicate_cache_resume_conflict_and_order_independent_hash(self):
        adapter = Adapter(self.run, self.source)
        first = adapter.evaluate("S01", self.spec)
        resumed = Adapter(self.run, self.source)
        with patch.object(resumed._bench, "run_strategy", side_effect=AssertionError("cache miss")):
            second = resumed.evaluate("S01", dict(reversed(list(self.spec.items()))))
        self.assertTrue(first["reused"] and second["reused"])
        self.assertTrue(first["proposal_was_duplicate"] and second["proposal_was_duplicate"])
        self.assertEqual(second["candidate_total_regressor_fits"], 0)
        self.assertEqual(second["actual_new_regressor_fits"], 0)
        self.assertEqual(fingerprint(self.spec), fingerprint(dict(reversed(list(self.spec.items())))))
        changed = copy.deepcopy(self.spec)
        changed["global"]["target"] = "log1p"
        with self.assertRaisesRegex(ValueError, "already used"):
            resumed.evaluate("S01", changed)

    def test_new_evaluation_uses_frozen_training_api_and_records_fit_cost(self):
        adapter = Adapter(self.run, self.source)
        new = copy.deepcopy(self.spec)
        new["global"]["target"] = "log1p"
        def fake_run(cid, spec):
            self.assertFalse((adapter.root / "final").exists())
            return self._candidate(cid, spec, adapter.root)
        with patch.object(adapter._bench, "prepare", side_effect=AssertionError("prepare forbidden")), \
             patch.object(adapter._bench, "freeze_and_evaluate", side_effect=AssertionError("freeze forbidden")), \
             patch.object(adapter._bench, "run_strategy", side_effect=fake_run) as run:
            result = adapter.evaluate("S02", new)
        self.assertEqual(run.call_count, 1)
        self.assertFalse(result["reused"])
        self.assertEqual(result["actual_new_regressor_fits"], 3)
        self.assertEqual(len(Adapter(self.run, self.source).known_specifications()), 2)

    def test_frozen_source_and_copy_mutations_are_rejected(self):
        prepare_run(self.run, self.source)
        copied = self.run / "workbench/data/schema.json"
        copied.write_text(copied.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "changed"):
            Adapter(self.run, self.source)
        shutil.copyfile(self.source / "data/schema.json", copied)
        (self.source / "pipeline.py").write_text((self.source / "pipeline.py").read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "changed"):
            Adapter(self.run, self.source)

    def test_completed_pending_result_recovers_after_interruption_without_refit(self):
        adapter = Adapter(self.run, self.source)
        new = copy.deepcopy(self.spec)
        new["global"]["target"] = "log1p"
        def interrupted_run(cid, spec):
            self._candidate(cid, spec, adapter.root)
            raise RuntimeError("simulated process interruption after evaluator persisted result")
        with patch.object(adapter._bench, "run_strategy", side_effect=interrupted_run):
            with self.assertRaisesRegex(RuntimeError, "interruption"):
                adapter.evaluate("S03", new)
        resumed = Adapter(self.run, self.source)
        with patch.object(resumed._bench, "run_strategy", side_effect=AssertionError("Completed result must not refit")):
            result = resumed.evaluate("S03", new)
        self.assertTrue(result["reused"])
        self.assertEqual(result["actual_new_regressor_fits"], 0)
        self.assertFalse(result["proposal_was_duplicate"])
        self.assertEqual(result["candidate_total_regressor_fits"], 3)
        self.assertEqual(resumed._index["pending"], {})
        self.assertEqual(resumed._bench._result("S03")["actual_model_fits"], 3)

    def test_parent_adapter_refreshes_worker_candidate_and_pending_recovery(self):
        parent = Adapter(self.run, self.source)
        worker = Adapter(self.run, self.source)
        new = copy.deepcopy(self.spec)
        new["global"]["target"] = "log1p"
        with patch.object(worker._bench, "run_strategy", side_effect=lambda cid, spec: self._candidate(cid, spec, worker.root)):
            worker.evaluate("L001", new)
        # The parent was instantiated before the worker produced any journal.
        context = parent.context()
        self.assertIn("L001", {item["id"] for item in context["known_specifications"]})
        self.assertEqual(parent.counterexamples("L001")["candidate_id"], "L001")
        recovered = parent.evaluate("L001", new)
        self.assertTrue(recovered["reused"])
        self.assertFalse(recovered["proposal_was_duplicate"])
        self.assertEqual(recovered["candidate_total_regressor_fits"], 3)
        other = copy.deepcopy(new)
        other["global"]["model"] = "hist_gradient_boosting"
        def interrupted(cid, spec):
            self._candidate(cid, spec, worker.root)
            raise RuntimeError("worker interrupted")
        with patch.object(worker._bench, "run_strategy", side_effect=interrupted):
            with self.assertRaises(RuntimeError):
                worker.evaluate("L002", other)
        # A living parent also sees and recovers a worker's completed pending
        # evaluation, without constructing a new Adapter or refitting anything.
        self.assertIn("L002", {item["id"] for item in parent.known_specifications()})
        self.assertEqual(parent._index["pending"], {})
        self.assertFalse(parent.evaluate("L002", other)["proposal_was_duplicate"])

    def test_new_evidence_mutation_rejected(self):
        adapter = Adapter(self.run, self.source)
        adapter.evaluate("S01", self.spec)
        result = self.run / "workbench/candidates/S01/result.json"
        result.write_text(result.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            adapter.context()

    def test_invalid_specs_and_ids_cannot_write_or_fit(self):
        adapter = Adapter(self.run, self.source)
        wrong = copy.deepcopy(self.spec)
        wrong["input"] = "diagnostic_repair11"
        for cid, spec in (("../oops", self.spec), ("G99", self.spec), ("S02", wrong)):
            with self.assertRaises(ValueError):
                adapter.evaluate(cid, spec)
        self.assertFalse((adapter.root / "candidates/S02").exists())

    def test_source_oof_alignment_rejected_even_with_matching_hash(self):
        path = self.source / "candidates/G01/oof_predictions.csv.gz"
        table = pd.read_csv(path)
        table.loc[0, "material_id"] = "not-in-training"
        table.to_csv(path, index=False)
        result_path = path.parent / "result.json"
        result = json.loads(result_path.read_text())
        result["oof_predictions_sha256"] = _sha(path)
        _save(result_path, result)
        with self.assertRaisesRegex(ValueError, "alignment"):
            Adapter(self.run, self.source)

    def test_source_metrics_are_recomputed_from_oof(self):
        path = self.source / "candidates/G01/result.json"
        result = json.loads(path.read_text())
        result["metrics"]["MAE_K"] = 0.
        _save(path, result)
        with self.assertRaisesRegex(ValueError, "metrics mismatch"):
            Adapter(self.run, self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
