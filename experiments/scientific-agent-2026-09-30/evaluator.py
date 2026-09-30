"""Frozen numerical evaluation for the tool-using scientific-agent pilot.

No generated code is executed here. Development methods never parse sealed test
labels. final_test is a separate, once-only, explicitly authorized operation.
The scientific MCP server must expose only the development methods.
"""
from __future__ import annotations

import os
for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"
import argparse
import hashlib
import json
import re
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import HuberRegressor, LogisticRegression
from sklearn.metrics import (average_precision_score, balanced_accuracy_score,
                             confusion_matrix, f1_score, log_loss,
                             mean_absolute_error, mean_squared_error,
                             precision_score, recall_score, roc_auc_score)
from threadpoolctl import threadpool_limits

SEED = 20260930
EPSILON = 1e-6
HULL_TOLERANCE = 1e-8
MAX_CANDIDATES = 6
MAX_DESCRIPTORS = 64
TASKS = ("formation", "hull")
RAW_FEATURES = [
    "comp_n_elements", "comp_entropy", "comp_max_fraction",
    "comp_electronegativity_mean", "comp_electronegativity_std",
    "comp_electronegativity_min", "comp_electronegativity_max",
    "comp_electronegativity_range", "comp_atomic_radius_mean",
    "comp_atomic_radius_std", "comp_radius_cv", "comp_Z_mean", "comp_Z_std",
    "comp_fraction_Z001", "comp_fraction_Z005", "comp_fraction_Z006",
    "comp_fraction_Z007", "comp_fraction_Z008", "comp_fraction_Z009",
    "comp_fraction_Z015", "comp_fraction_Z016", "comp_fraction_Z017",
    "comp_halogen_fraction", "comp_chalcogen_fraction",
    "comp_alkali_alkaline_fraction", "comp_transition_fraction",
    "relaxed_min_distance_A", "relaxed_min_covalent_ratio",
    "relaxed_volume_per_atom_A3", "relaxed_covalent_sphere_volume_fraction",
]


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def read_csv(path):
    return pd.read_csv(path, float_precision="round_trip")


def primary(task, metrics):
    return metrics["MAE_eV_atom" if task == "formation" else "logloss"]


def metrics(task, truth, prediction):
    y, p = np.asarray(truth), np.asarray(prediction, dtype=float)
    if not len(y) or len(y) != len(p) or not np.isfinite(p).all():
        raise ValueError("Metrics require nonempty, aligned finite predictions")
    if task == "formation":
        return {"rows": len(y), "MAE_eV_atom": float(mean_absolute_error(y, p)),
                "RMSE_eV_atom": float(np.sqrt(mean_squared_error(y, p)))}
    p = np.clip(p, EPSILON, 1-EPSILON)
    labels = p >= .5
    tn, fp, fn, tp = confusion_matrix(y, labels, labels=[0, 1]).ravel()
    return {"rows": len(y), "logloss": float(log_loss(y, p, labels=[0, 1])),
            "AUC": float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None,
            "AP": float(average_precision_score(y, p)) if np.any(y) else None,
            "threshold": .5, "TP": int(tp), "FP": int(fp), "TN": int(tn), "FN": int(fn),
            "precision": float(precision_score(y, labels, zero_division=0)),
            "recall": float(recall_score(y, labels, zero_division=0)),
            "F1": float(f1_score(y, labels, zero_division=0)),
            "balanced_accuracy": float(balanced_accuracy_score(y, labels))}


def losses(task, truth, prediction):
    if task == "formation":
        return np.abs(np.asarray(truth)-prediction)
    p = np.clip(np.asarray(prediction), EPSILON, 1-EPSILON)
    y = np.asarray(truth)
    return -(y*np.log(p)+(1-y)*np.log1p(-p))


def paired_bootstrap(task, truth, proposed, control, systems, resamples=1000):
    delta = losses(task, truth, proposed)-losses(task, truth, control)
    groups, inverse = np.unique(np.asarray(systems, dtype=str), return_inverse=True)
    numerators = np.bincount(inverse, weights=delta)
    denominators = np.bincount(inverse)
    rng = np.random.default_rng(SEED)
    sampled = np.empty(resamples)
    for b in range(resamples):
        selected = rng.integers(0, len(groups), len(groups))
        sampled[b] = numerators[selected].sum()/denominators[selected].sum()
    lo, hi = np.quantile(sampled, [.025, .975])
    return {"rows": len(delta), "systems": len(groups), "selected_minus_control": float(delta.mean()),
            "lower95": float(lo), "upper95": float(hi), "resamples": resamples, "seed": SEED,
            "scope": "Paired system-cluster percentile interval conditional on fitted selected models; excludes search/training uncertainty."}


def fit_transform(x, names):
    """Train-only median imputation, missing indicators, scaling and affine dedup."""
    x = np.asarray(x, dtype=float)
    if np.isinf(x).any():
        raise ValueError("Infinite descriptors are forbidden; use NaN for undefined values")
    if np.isnan(x).all(axis=0).any():
        raise ValueError("At least one descriptor is entirely missing in training")
    medians = np.nanmedian(x, axis=0)
    indicator = np.flatnonzero(np.isnan(x).any(axis=0))
    filled = np.where(np.isnan(x), medians, x)
    if len(indicator):
        filled = np.column_stack([filled, np.isnan(x[:, indicator]).astype(float)])
    expanded = list(names)+[names[i]+"__missing" for i in indicator]
    mean, scale = filled.mean(axis=0), filled.std(axis=0)
    scale[scale == 0] = 1
    z = (filled-mean)/scale
    kept, dropped = [], []
    for i in range(z.shape[1]):
        if np.ptp(z[:, i]) <= 1e-12:
            dropped.append({"column": expanded[i], "reason": "train_constant"})
        elif any(np.allclose(z[:, i], z[:, j], rtol=0, atol=1e-12) or
                 np.allclose(z[:, i], -z[:, j], rtol=0, atol=1e-12) for j in kept):
            dropped.append({"column": expanded[i], "reason": "train_affine_duplicate"})
        else:
            kept.append(i)
    if not kept:
        raise ValueError("No nonconstant predictor remains")
    state = {"columns": list(names), "expanded_columns": expanded,
             "medians": medians.tolist(), "missing_indicator_indices": indicator.tolist(),
             "means": mean.tolist(), "scales": scale.tolist(), "kept_indices": kept,
             "dropped_columns": dropped}
    return np.ascontiguousarray(z[:, kept]), state


def transform(x, state):
    x = np.asarray(x, dtype=float)
    if x.ndim != 2 or x.shape[1] != len(state["columns"]) or np.isinf(x).any():
        raise ValueError("Descriptor matrix shape or finite-value validation failed")
    filled = np.where(np.isnan(x), state["medians"], x)
    idx = state["missing_indicator_indices"]
    if idx:
        filled = np.column_stack([filled, np.isnan(x[:, idx]).astype(float)])
    z = (filled-state["means"])/state["scales"]
    return np.ascontiguousarray(z[:, state["kept_indices"]])


def fit_model(task, x, y, names, hgb=False):
    z, pre = fit_transform(x, names)
    if task == "hull" and len(np.unique(y)) != 2:
        raise ValueError("Training hull labels must contain both classes")
    if hgb:
        cls = HistGradientBoostingRegressor if task == "formation" else HistGradientBoostingClassifier
        estimator = cls(max_iter=150, max_leaf_nodes=15, min_samples_leaf=20,
                        l2_regularization=10, learning_rate=.05, early_stopping=False, random_state=SEED)
    elif task == "formation":
        estimator = HuberRegressor(alpha=1, epsilon=1.35, max_iter=3000, tol=1e-6)
    else:
        estimator = LogisticRegression(C=1, solver="lbfgs", max_iter=10000, tol=1e-8, random_state=SEED)
    with threadpool_limits(limits=1), warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        estimator.fit(z, y)
    model = {"task": task, "kind": "hgb" if hgb else ("huber" if task == "formation" else "logistic"),
             "preprocessing": pre, "parameters": estimator.get_params(), "training_rows": len(y)}
    if not hgb:
        model["coefficients"] = np.asarray(estimator.coef_).ravel().tolist()
        model["intercept"] = float(np.asarray(estimator.intercept_).ravel()[0])
    return model, estimator


def predict(model, x, estimator=None):
    z = transform(x, model["preprocessing"])
    if model["kind"] == "hgb":
        if estimator is None:
            raise ValueError("HGB requires its saved estimator")
        with threadpool_limits(limits=1):
            p = estimator.predict(z) if model["task"] == "formation" else estimator.predict_proba(z)[:, 1]
    else:
        score = z @ np.asarray(model["coefficients"]) + model["intercept"]
        p = score if model["task"] == "formation" else expit(score)
    return np.asarray(p) if model["task"] == "formation" else np.clip(p, EPSILON, 1-EPSILON)


class Evaluator:
    def __init__(self, root_path):
        self.root = Path(root_path).resolve()
        self.data = self.root/"data"
        self.out = self.root/"evaluation"
        self.out.mkdir(parents=True, exist_ok=True)

    def _source_hashes(self):
        # Hashing sealed bytes establishes provenance; it does not parse targets.
        names = ["features.csv.gz", "development.csv.gz", "split_assignments.csv", "sealed_test.csv.gz"]
        return {name: sha(self.data/name) for name in names}

    def _development(self):
        features = read_csv(self.data/"features.csv.gz").set_index("material_id", verify_integrity=True)
        splits = read_csv(self.data/"split_assignments.csv").set_index("material_id", verify_integrity=True)
        dev = read_csv(self.data/"development.csv.gz").set_index("material_id", verify_integrity=True)
        if set(features.index) != set(splits.index):
            raise ValueError("Feature/split IDs differ")
        expected = splits.index[splits.split.isin(["train", "validation"])]
        if set(dev.index) != set(expected) or not set(dev.split).issubset({"train", "validation"}):
            raise ValueError("Development file must contain exactly train and validation IDs")
        if not dev.split.equals(splits.loc[dev.index, "split"]):
            raise ValueError("Development split mismatch")
        if not np.isfinite(features[RAW_FEATURES].to_numpy(float)).all():
            raise ValueError("All selected raw30 features must be finite before splitting")
        for key in ("chemical_system", "composition_signature"):
            if key not in splits:
                continue
            if splits.groupby(key).split.nunique().max() > 1:
                raise ValueError("Chemical system/composition crosses split roles")
        if not dev.chemical_system.equals(splits.loc[dev.index, "chemical_system"]):
            raise ValueError("Development chemical-system mismatch")
        for col in ["formation_energy_per_atom", "energy_above_hull"]:
            if not np.isfinite(dev[col]).all():
                raise ValueError("Invalid development target")
        dev = dev.sort_index()
        return features.loc[dev.index], dev

    def _assert_frozen_sources(self):
        manifest = load(self.out/"prepared.json")
        if manifest["source_hashes"] != self._source_hashes() or manifest["evaluator_sha256"] != sha(__file__):
            raise RuntimeError("Prepared data/evaluator changed; experiment refuses to continue")
        return manifest

    def _assert_development_open(self):
        if (self.out/"selection.json").exists():
            raise RuntimeError("Experiment frozen: no further development evaluation")

    def _fit_arm(self, arm, x, dev, names, hgb=False):
        directory = self.out/"models"/arm
        directory.mkdir(parents=True, exist_ok=False)
        train, valid = dev.split.eq("train").to_numpy(), dev.split.eq("validation").to_numpy()
        records = dev[["chemical_system", "split", "formation_energy_per_atom", "energy_above_hull"]].copy()
        summary = {"arm": arm, "tasks": {}, "descriptor_columns": list(names),
                   "training_rows": int(train.sum()), "validation_rows": int(valid.sum())}
        for task in TASKS:
            y = dev.formation_energy_per_atom.to_numpy() if task == "formation" else (dev.energy_above_hull.to_numpy() <= HULL_TOLERANCE).astype(int)
            model, estimator = fit_model(task, x[train], y[train], names, hgb)
            save(directory/f"{task}_model.json", model)
            joblib.dump(estimator, directory/f"{task}_estimator.joblib")
            p = predict(model, x, estimator)
            records[f"{task}_prediction"] = p
            records[f"{task}_loss"] = losses(task, y, p)
            summary["tasks"][task] = {"train": metrics(task, y[train], p[train]),
                                      "validation": metrics(task, y[valid], p[valid]),
                                      "effective_columns": len(model["preprocessing"]["kept_indices"])}
        records.to_csv(directory/"development_predictions.csv.gz", index_label="material_id")
        summary["missing_values"] = {name: {"train": int(np.isnan(x[train, i]).sum()),
                                               "validation": int(np.isnan(x[valid, i]).sum())}
                                     for i, name in enumerate(names) if np.isnan(x[:, i]).any()}
        save(directory/"metrics.json", summary)
        return summary

    def prepare(self):
        self._assert_development_open()
        if (self.out/"prepared.json").exists():
            self._assert_frozen_sources()
            return load(self.out/"development_summary.json")
        if (self.out/"PREPARE_STARTED.json").exists():
            raise RuntimeError("Previous prepare did not finish; preserve artifacts and investigate")
        save(self.out/"PREPARE_STARTED.json", {"at": utc()})
        features, dev = self._development()
        x = features[RAW_FEATURES].to_numpy(float)
        summaries = {arm: self._fit_arm(arm, x, dev, RAW_FEATURES, hgb=(arm == "hgb")) for arm in ["raw", "hgb"]}
        save(self.out/"development_summary.json", summaries)
        save(self.out/"prepared.json", {"at": utc(), "source_hashes": self._source_hashes(),
             "evaluator_sha256": sha(__file__), "raw_features": RAW_FEATURES,
             "training_ids": dev.index[dev.split.eq("train")].tolist(),
             "validation_ids": dev.index[dev.split.eq("validation")].tolist(),
             "claim_limit": "Validation is adaptive development, not independent confirmation."})
        return summaries

    def _validate_descriptors(self, descriptors, names, expected_ids):
        if not isinstance(descriptors, pd.DataFrame) or set(descriptors.columns) != {"material_id", *names}:
            raise ValueError("Expected DataFrame with exactly material_id and declared descriptor_names")
        if descriptors.columns.duplicated().any() or descriptors.material_id.duplicated().any():
            raise ValueError("Duplicate descriptor columns or material IDs")
        if set(descriptors.material_id) != set(expected_ids):
            raise ValueError("Descriptors must cover exactly the requested cohort, no extras")
        aligned = descriptors.set_index("material_id").loc[expected_ids, names]
        x = aligned.to_numpy(dtype=float)
        if np.isinf(x).any():
            raise ValueError("Infinite descriptor values forbidden")
        return aligned, x

    def evaluate_candidate(self, candidate_id, descriptors_df, specification):
        self._assert_development_open()
        self._assert_frozen_sources()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", str(candidate_id)) or candidate_id in {"raw", "hgb"}:
            raise ValueError("Invalid or reserved candidate ID")
        if not isinstance(specification, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(specification.get("code_sha", ""))):
            raise ValueError("Specification requires code_sha SHA256")
        names = specification.get("descriptor_names")
        if not isinstance(names, list) or not 1 <= len(names) <= MAX_DESCRIPTORS or len(set(names)) != len(names):
            raise ValueError("Require 1..64 distinct declared descriptor_names")
        if any(not isinstance(n, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", n) or n in RAW_FEATURES or n == "material_id" for n in names):
            raise ValueError("Invalid or colliding descriptor name")
        candidates = self.out/"candidates"
        candidates.mkdir(exist_ok=True)
        if len(list(candidates.iterdir())) >= MAX_CANDIDATES:
            raise RuntimeError("Candidate budget exhausted")
        directory = candidates/candidate_id
        directory.mkdir(exist_ok=False)
        save(directory/"specification.json", specification)
        save(directory/"status.json", {"state": "started", "at": utc()})
        try:
            features, dev = self._development()
            aligned, added = self._validate_descriptors(descriptors_df, names, dev.index)
            if np.isnan(added[dev.split.eq("train")]).all(axis=0).any():
                raise ValueError("Descriptor entirely missing in training")
            aligned.to_csv(directory/"development_descriptors.csv.gz", index_label="material_id")
            x = np.column_stack([features[RAW_FEATURES].to_numpy(float), added])
            summary = self._fit_arm(candidate_id, x, dev, RAW_FEATURES+names)
            summary["code_sha"] = specification["code_sha"]
            summary["status"] = "evaluated"
            summary["claim_limit"] = "Adaptive validation feedback; not an independent test or verified physical law."
            baseline = load(self.out/"models"/"raw"/"metrics.json")
            for task in TASKS:
                summary["tasks"][task]["validation_loss_change_vs_raw"] = primary(task, summary["tasks"][task]["validation"])-primary(task, baseline["tasks"][task]["validation"])
            save(directory/"result.json", summary)
            save(directory/"status.json", {"state": "evaluated", "at": utc()})
            return summary
        except Exception as exc:
            save(directory/"status.json", {"state": "failed", "at": utc(), "error": f"{type(exc).__name__}: {exc}"})
            raise

    def get_counterexamples(self, candidate_id, task, k=6):
        self._assert_development_open()
        self._assert_frozen_sources()
        if task not in TASKS or not isinstance(k, int) or not 1 <= k <= 6:
            raise ValueError("task formation/hull and integer k from1to6 required")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", str(candidate_id)):
            raise ValueError("Invalid candidate ID")
        if candidate_id not in {"raw", "hgb"}:
            status = load(self.out/"candidates"/candidate_id/"status.json")
            if status["state"] != "evaluated":
                raise ValueError("Candidate was not successfully evaluated")
        df = read_csv(self.out/"models"/candidate_id/"development_predictions.csv.gz")
        df = df[df.split.eq("validation")].sort_values([f"{task}_loss", "material_id"], ascending=[False, True]).head(k)
        return {"task": task, "candidate_id": candidate_id, "split": "validation",
                "claim_limit": "These labeled validation examples are adaptive development feedback.",
                "examples": df.to_dict(orient="records")}

    def freeze_selection(self, last_call_manifest):
        self._assert_development_open()
        prepared = self._assert_frozen_sources()
        if not isinstance(last_call_manifest, dict) or last_call_manifest.get("completed") is not True or last_call_manifest.get("audit_passed") is not True:
            raise ValueError("Completed agent-call and passing event-audit manifest required")
        available = [{"id": "raw", "n_descriptors": 0, "order": -1,
                      "metrics": load(self.out/"models"/"raw"/"metrics.json")}]
        candidates = self.out/"candidates"
        ordered = sorted(candidates.iterdir(), key=lambda p: load(p/"status.json")["at"]) if candidates.exists() else []
        for order, p in enumerate(ordered):
            if load(p/"status.json")["state"] == "evaluated":
                result = load(p/"result.json")
                available.append({"id": p.name, "n_descriptors": len(load(p/"specification.json")["descriptor_names"]), "order": order, "metrics": result})
        selected = {}
        for task in TASKS:
            best = min(primary(task, a["metrics"]["tasks"][task]["validation"]) for a in available)
            tied = [a for a in available if primary(task, a["metrics"]["tasks"][task]["validation"]) <= best+1e-12]
            winner = min(tied, key=lambda a: (a["n_descriptors"], a["order"]))
            selected[task] = {"candidate_id": winner["id"], "validation_loss": primary(task, winner["metrics"]["tasks"][task]["validation"]),
                              "n_descriptors": winner["n_descriptors"]}
        hashes = {}
        for path in sorted(self.out.rglob("*")):
            if path.is_file():
                hashes[path.relative_to(self.out).as_posix()] = sha(path)
        result = {"at": utc(), "selected": selected, "available": available, "last_call_manifest": last_call_manifest,
                  "source_hashes": prepared["source_hashes"], "evaluator_sha256": sha(__file__), "artifact_hashes": hashes,
                  "selection_rule": "Per-task minimum adaptive validation loss; ties1e-12 prefer fewer descriptors then earlier candidate. Raw eligible; HGB reference excluded from candidate selection.",
                  "final_test_opened": False}
        save(self.out/"selection.json", result)
        return result

    def final_test(self, test_descriptors, authorization_manifest, descriptor_provenance=None):
        """Root-only. test_descriptors maps selected IDs to frozen-code test frames.

        All models and target-free predictions are frozen and hashed before the
        separate sealed-label file is parsed. This is not an MCP agent method.
        """
        self._assert_frozen_sources()
        selection = load(self.out/"selection.json")
        if not isinstance(authorization_manifest, dict) or authorization_manifest.get("authorized") is not True:
            raise ValueError("Explicit final-test authorization manifest required")
        final = self.out/"final"
        final.mkdir(exist_ok=True)
        marker = final/"TEST_ACCESS_STARTED.json"
        if marker.exists():
            raise RuntimeError("Final-test access already started; no repeat evaluation")
        for name, expected in selection["artifact_hashes"].items():
            if sha(self.out/name) != expected:
                raise RuntimeError("Frozen development artifact changed: "+name)
        features = read_csv(self.data/"features.csv.gz").set_index("material_id", verify_integrity=True)
        splits = read_csv(self.data/"split_assignments.csv").set_index("material_id", verify_integrity=True)
        ids = splits.index[splits.split.eq("test")].sort_values()
        xraw = features.loc[ids, RAW_FEATURES].to_numpy(float)
        if not np.isfinite(xraw).all():
            raise ValueError("Nonfinite raw test descriptors")
        needed = {s["candidate_id"] for s in selection["selected"].values()}-{ "raw" }
        if set(test_descriptors) != needed or set(descriptor_provenance or {}) != needed:
            raise ValueError("Require exactly selected candidates' test matrices and code provenance")
        matrices = {"raw": xraw, "hgb": xraw}
        for candidate in sorted(needed):
            spec = load(self.out/"candidates"/candidate/"specification.json")
            if descriptor_provenance[candidate].get("code_sha") != spec["code_sha"]:
                raise ValueError("Frozen descriptor code hash mismatch")
            aligned, added = self._validate_descriptors(test_descriptors[candidate], spec["descriptor_names"], ids)
            aligned.to_csv(final/f"{candidate}_test_descriptors.csv.gz", index_label="material_id")
            matrices[candidate] = np.column_stack([xraw, added])
        predictions = pd.DataFrame({"chemical_system": splits.loc[ids, "chemical_system"]}, index=ids)
        for task in TASKS:
            for label, arm in [("selected", selection["selected"][task]["candidate_id"]), ("raw", "raw"), ("hgb", "hgb")]:
                model = load(self.out/"models"/arm/f"{task}_model.json")
                estimator = joblib.load(self.out/"models"/arm/f"{task}_estimator.joblib") if model["kind"] == "hgb" else None
                predictions[f"{task}_{label}"] = predict(model, matrices[arm], estimator)
        targetfree = final/"frozen_test_predictions.csv.gz"
        predictions.to_csv(targetfree, index_label="material_id")
        freeze = {"at": utc(), "selection_sha256": sha(self.out/"selection.json"),
                  "predictions_sha256": sha(targetfree), "descriptor_provenance": descriptor_provenance,
                  "test_descriptor_hashes": {p.name: sha(p) for p in final.glob("*_test_descriptors.csv.gz")}}
        save(final/"prediction_freeze.json", freeze)
        with marker.open("x", encoding="utf-8") as handle:
            json.dump({"at": utc(), "authorization": authorization_manifest, "prediction_freeze_sha256": sha(final/"prediction_freeze.json")}, handle, indent=2)
        targets = read_csv(self.data/"sealed_test.csv.gz").set_index("material_id", verify_integrity=True)
        if set(targets.index) != set(ids) or not targets.split.eq("test").all():
            raise ValueError("Sealed test ID/split mismatch")
        targets = targets.loc[ids]
        if not targets.chemical_system.equals(predictions.chemical_system):
            raise ValueError("Sealed test system mismatch")
        results = {"at": utc(), "selection": selection["selected"], "tasks": {},
                   "claim_limit": "Single fresh system-heldout test after adaptive validation; intervals conditional on frozen models. No matched broad descriptor-search control, so no isolated GPT-specific attribution."}
        for task in TASKS:
            y = targets.formation_energy_per_atom.to_numpy() if task == "formation" else (targets.energy_above_hull.to_numpy() <= HULL_TOLERANCE).astype(int)
            if not np.isfinite(targets[["formation_energy_per_atom", "energy_above_hull"]].to_numpy()).all():
                raise ValueError("Nonfinite test targets")
            preds = {arm: predictions[f"{task}_{arm}"].to_numpy() for arm in ["selected", "raw", "hgb"]}
            results["tasks"][task] = {"metrics": {arm: metrics(task, y, p) for arm, p in preds.items()},
                                     "paired_bootstrap": {arm: paired_bootstrap(task, y, preds["selected"], preds[arm], predictions.chemical_system) for arm in ["raw", "hgb"]}}
            predictions[f"{task}_truth"] = y
        predictions.to_csv(final/"test_predictions_with_targets.csv.gz", index_label="material_id")
        save(final/"test_results.json", results)
        return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "candidate", "counterexamples", "freeze", "final-test", "replay"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--candidate-id")
    parser.add_argument("--descriptors", type=Path)
    parser.add_argument("--specification", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--task", choices=TASKS)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--estimator", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    evaluator = Evaluator(args.root)
    if args.command == "prepare":
        result = evaluator.prepare()
    elif args.command == "candidate":
        result = evaluator.evaluate_candidate(args.candidate_id, read_csv(args.descriptors), load(args.specification))
    elif args.command == "counterexamples":
        result = evaluator.get_counterexamples(args.candidate_id, args.task)
    elif args.command == "freeze":
        result = evaluator.freeze_selection(load(args.manifest))
    elif args.command == "final-test":
        manifest = load(args.manifest)
        matrices = {k: read_csv(v["path"]) for k, v in manifest["test_descriptors"].items()}
        provenance = {k: {"code_sha": v["code_sha"]} for k, v in manifest["test_descriptors"].items()}
        result = evaluator.final_test(matrices, manifest["authorization"], provenance)
    else:
        model = load(args.model)
        frame = read_csv(args.descriptors)
        estimator = joblib.load(args.estimator) if args.estimator else None
        result_frame = frame[["material_id"]].copy()
        result_frame["prediction"] = predict(model, frame[model["preprocessing"]["columns"]].to_numpy(float), estimator)
        if args.output is None:
            raise ValueError("Replay requires --output")
        result_frame.to_csv(args.output, index=False)
        result = {"rows": len(frame), "output": str(args.output)}
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
