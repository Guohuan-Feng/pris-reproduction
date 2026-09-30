"""Synthetic tests only; never load the experiment's sealed targets."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy.special import expit

import evaluator as ev


class EvaluatorTests(unittest.TestCase):
    def test_train_only_imputation_and_affine_dedup(self):
        x = np.array([[1, 2, np.nan], [2, 4, 5], [3, 6, 9], [4, 8, 13]], float)
        z, state = ev.fit_transform(x, ["a", "twice_a", "c"])
        self.assertEqual(state["medians"][2], 9)
        self.assertEqual(state["missing_indicator_indices"], [2])
        self.assertEqual(state["dropped_columns"], [{"column": "twice_a", "reason": "train_affine_duplicate"}])
        held = ev.transform(np.array([[1000, 2000, np.nan]], float), state)
        expected_filled = np.array([[1000, 2000, 9, 1]], float)
        expected = ((expected_filled-state["means"])/state["scales"])[:, state["kept_indices"]]
        np.testing.assert_array_equal(held, expected)
        with self.assertRaises(ValueError):
            ev.fit_transform(np.array([[1, np.nan], [2, np.nan]]), ["a", "b"])
        with self.assertRaises(ValueError):
            ev.fit_transform(np.array([[1, np.inf], [2, 1]]), ["a", "b"])

    def test_saved_linear_models_reconstruct_without_estimator(self):
        rng = np.random.default_rng(24)
        x = rng.normal(size=(180, 4))
        formation = 1.8*x[:, 0]-.6*x[:, 1]+rng.normal(scale=.1, size=len(x))
        hull = (rng.random(len(x)) < expit(x[:, 0]-x[:, 2])).astype(int)
        for task, y in [("formation", formation), ("hull", hull)]:
            model, estimator = ev.fit_model(task, x, y, ["a", "b", "c", "d"])
            saved = json.loads(json.dumps(model))
            z = ev.transform(x, saved["preprocessing"])
            score = z @ np.array(saved["coefficients"])+saved["intercept"]
            manual = score if task == "formation" else np.clip(expit(score), ev.EPSILON, 1-ev.EPSILON)
            np.testing.assert_array_equal(ev.predict(saved, x), manual)
            sklearn = estimator.predict(z) if task == "formation" else np.clip(estimator.predict_proba(z)[:, 1], ev.EPSILON, 1-ev.EPSILON)
            np.testing.assert_allclose(manual, sklearn, atol=1e-14, rtol=0)

    def test_hull_metrics_and_paired_group_bootstrap(self):
        y = np.array([1, 0, 1, 0])
        m = ev.metrics("hull", y, [.8, .7, .2, .1])
        self.assertEqual([m[k] for k in ["TP", "FP", "TN", "FN"]], [1, 1, 1, 1])
        self.assertAlmostEqual(m["logloss"], -np.mean(np.log([.8, .3, .2, .9])))
        ci = ev.paired_bootstrap("formation", np.zeros(4), np.ones(4), 2*np.ones(4), ["A", "A", "B", "C"])
        self.assertEqual(ci["selected_minus_control"], -1)
        self.assertEqual(ci["lower95"], -1)
        self.assertEqual(ci["upper95"], -1)

    def test_lifecycle_information_boundary_and_freeze(self):
        parent = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix="evaluator_synthetic_", dir=parent) as tmp:
            root = Path(tmp)
            self.assertTrue(root.resolve().is_relative_to(parent))
            data = root/"data"
            data.mkdir()
            rng = np.random.default_rng(713)
            n = 240
            ids = [f"mp-synthetic-{i:04}" for i in range(n)]
            raw = rng.normal(size=(n, 30))
            added = raw[:, 0]**2
            split = np.array(["train"]*160+["validation"]*40+["test"]*40)
            features = pd.DataFrame(raw, columns=ev.RAW_FEATURES)
            features.insert(0, "material_id", ids)
            features["chemical_system"] = [f"system-{i}" for i in range(n)]
            features["composition_signature"] = [f"composition-{i}" for i in range(n)]
            features["formula"] = "synthetic"
            features.to_csv(data/"features.csv.gz", index=False)
            splits = features[["material_id", "chemical_system", "composition_signature"]].copy()
            splits["split"] = split
            splits.to_csv(data/"split_assignments.csv", index=False)
            target = splits.copy()
            target["formation_energy_per_atom"] = 10*added+rng.normal(scale=.05, size=n)
            target["energy_above_hull"] = np.where(raw[:, 1] > 0, 0, .2)
            target[split != "test"].to_csv(data/"development.csv.gz", index=False)
            target[split == "test"].to_csv(data/"sealed_test.csv.gz", index=False)
            development_descriptors = pd.DataFrame({"material_id": np.array(ids)[split != "test"], "square": added[split != "test"]})
            test_descriptors = pd.DataFrame({"material_id": np.array(ids)[split == "test"], "square": added[split == "test"]})
            evaluator = ev.Evaluator(root)
            original_reader = ev.read_csv
            def no_test_read(path):
                self.assertNotEqual(Path(path).name, "sealed_test.csv.gz", "Development parsed test labels")
                return original_reader(path)
            with patch.object(ev, "read_csv", no_test_read):
                initial = evaluator.prepare()
                self.assertIn("raw", initial)
                specification = {"code_sha": "a"*64, "descriptor_names": ["square"], "hypothesis": "synthetic curvature"}
                result = evaluator.evaluate_candidate("C1", development_descriptors.iloc[::-1], specification)
                self.assertLess(result["tasks"]["formation"]["validation_loss_change_vs_raw"], 0)
                examples = evaluator.get_counterexamples("C1", "formation", 6)
                self.assertEqual(len(examples["examples"]), 6)
                self.assertTrue(all(e["split"] == "validation" for e in examples["examples"]))
                with self.assertRaises(ValueError):
                    evaluator.freeze_selection({"completed": True, "audit_passed": False})
                selection = evaluator.freeze_selection({"completed": True, "audit_passed": True, "source": "synthetic"})
                self.assertEqual(selection["selected"]["formation"]["candidate_id"], "C1")
                with self.assertRaises(RuntimeError):
                    evaluator.evaluate_candidate("C2", development_descriptors, specification)
                with self.assertRaises(ValueError):
                    evaluator.final_test({}, {"authorized": False})
            def require_prediction_freeze(path):
                if Path(path).name == "sealed_test.csv.gz":
                    self.assertTrue((root/"evaluation/final/prediction_freeze.json").exists())
                    self.assertTrue((root/"evaluation/final/frozen_test_predictions.csv.gz").exists())
                    self.assertTrue((root/"evaluation/final/TEST_ACCESS_STARTED.json").exists())
                return original_reader(path)
            needed = {v["candidate_id"] for v in selection["selected"].values()}-{"raw"}
            with patch.object(ev, "read_csv", require_prediction_freeze):
                final = evaluator.final_test({c: test_descriptors for c in needed}, {"authorized": True, "source": "synthetic-test-only"}, {c: {"code_sha": "a"*64} for c in needed})
            self.assertEqual(final["tasks"]["formation"]["metrics"]["selected"]["rows"], 40)
            with self.assertRaises(RuntimeError):
                evaluator.final_test({}, {"authorized": True})


if __name__ == "__main__":
    unittest.main(verbosity=2)
