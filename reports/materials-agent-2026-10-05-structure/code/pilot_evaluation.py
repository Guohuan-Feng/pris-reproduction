"""Explicit, fixed-fold formation-energy pilot evaluation; import never fits.

The frozen legacy module is loaded into a private namespace and is not edited.
Only evaluate() / fit_training_block() fit. No data loader, CLI, split generator,
hyperparameter search, residual correction, or confirmation-set access exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from typing import Callable

# Legacy scientific directories remain byte-preserved even if caller omits -B.
sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
from scipy.spatial.distance import pdist
from sklearn.kernel_ridge import KernelRidge
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

E011_SPEC = {
    "routing": "oxygen_presence", "global_estimator": "extra_trees",
    "blend_weight": 0.5,
    "expert_estimators": {"no_oxygen": "blend", "oxygen": "blend"},
    "min_train_per_group": 150, "shrinkage": 0.5,
    "feature_set": "full42", "training_weight": "uniform",
    "model_options": {
        "et_min_samples_leaf": 1, "et_max_features": 1.0,
        "hgb_loss": "squared_error", "hgb_max_leaf_nodes": 15,
        "hgb_min_samples_leaf": 20, "hgb_l2_regularization": 0,
        "hgb_learning_rate": 0.1,
    },
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_hash(value) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def load_legacy(path, expected_sha256: str | None = None):
    """Read a frozen evaluator, optionally enforcing its registered byte hash."""
    path = Path(path).resolve(strict=True)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError("Frozen legacy evaluator SHA256 mismatch")
    # The module has its own namespace. No legacy FEATURE_SETS or callback is patched.
    name = "_pilot_legacy_" + _json_hash([str(path), digest])[:20]
    if name not in sys.modules:
        module_spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[name] = module
        try:
            module_spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    return sys.modules[name], digest


class FitAudit:
    """One start and one completion per learner; callback may persist each event."""

    def __init__(self, callback: Callable[[dict], None] | None = None):
        self.callback = callback
        self.events: list[dict] = []
        self.counter = 0

    def emit(self, event: dict):
        self.events.append(event)
        if self.callback is not None:
            self.callback(dict(event))

    def fit(self, operation: Callable, metadata: dict):
        self.counter += 1
        fit_id = f"F{self.counter:04d}"
        start = {**metadata, "fit_id": fit_id, "event": "base_learner_fit",
                 "phase": "started", "utc": _utc()}
        self.emit(start)
        try:
            model = operation()
        except BaseException as exc:
            self.emit({**metadata, "fit_id": fit_id, "event": "base_learner_fit",
                       "phase": "failed", "utc": _utc(),
                       "error": f"{type(exc).__name__}: {exc}"})
            raise
        self.emit({**metadata, "fit_id": fit_id, "event": "base_learner_fit",
                   "phase": "completed", "utc": _utc()})
        return model


@dataclass
class FittedPilotTree:
    legacy: object
    feature_names: list[str]
    spec: dict
    global_models: dict
    expert_models: dict
    group_train_counts: dict
    training_summary: dict

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        old = self.legacy._feature_frame(X.loc[:, self.legacy.FEATURES])
        values = X.loc[:, self.feature_names].to_numpy(float)
        groups = self.legacy.route_labels(old, self.spec["routing"])
        with threadpool_limits(limits=1):
            global_prediction = self.legacy._predict_models(
                self.global_models, values, self.spec["blend_weight"])
            prediction = global_prediction.copy()
            route = np.full(len(X), "global", dtype=object)
            fallback = np.zeros(len(X), dtype=bool)
            reason = np.full(len(X), "", dtype=object)
            for group in self.legacy.GROUP_LABELS[self.spec["routing"]]:
                mask = groups == group
                if not mask.any():
                    continue
                if group not in self.expert_models:
                    fallback[mask] = True
                    route[mask] = "global_fallback"
                    reason[mask] = "train_group_below_minimum"
                else:
                    expert = self.legacy._predict_models(
                        self.expert_models[group], values[mask], self.spec["blend_weight"])
                    prediction[mask] = ((1 - self.spec["shrinkage"]) * expert
                                        + self.spec["shrinkage"] * global_prediction[mask])
                    route[mask] = f"expert:{group}:blend"
        if not np.isfinite(prediction).all():
            raise ValueError("Nonfinite tree predictions")
        return pd.DataFrame({"prediction": prediction, "input_group": groups,
                             "model_route": route, "fallback": fallback,
                             "fallback_reason": reason,
                             "expert_train_rows": [self.group_train_counts[g] for g in groups]},
                            index=X.index)


@dataclass
class FittedPilotKRR:
    legacy: object
    feature_names: list[str]
    scaler: StandardScaler
    model: KernelRidge
    target_mean: float
    training_summary: dict

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        values = X.loc[:, self.feature_names].to_numpy(float)
        with threadpool_limits(limits=1):
            prediction = self.model.predict(self.scaler.transform(values)) + self.target_mean
        if not np.isfinite(prediction).all():
            raise ValueError("Nonfinite KRR predictions")
        groups = self.legacy.route_labels(X.loc[:, self.legacy.FEATURES], "oxygen_presence")
        return pd.DataFrame({"prediction": prediction, "input_group": groups,
                             "model_route": "global:krr", "fallback": False,
                             "fallback_reason": "", "expert_train_rows": 0}, index=X.index)


class PilotEvaluator:
    def __init__(self, legacy_evaluation_path, g8_columns, no8_columns,
                 expected_legacy_sha256: str | None = None,
                 expected_counts: tuple[int, int] = (2164, 715),
                 e011_spec: dict | None = None):
        self.legacy, self.legacy_sha256 = load_legacy(
            legacy_evaluation_path, expected_legacy_sha256)
        self.e011_spec = self.legacy.validate_spec(e011_spec if e011_spec is not None else E011_SPEC)
        if self.e011_spec != self.legacy.validate_spec(E011_SPEC):
            raise ValueError("Provided frozen E011 spec differs from the registered tree baseline")
        self.old_columns = list(self.legacy.FEATURES)
        self.g8_columns = list(g8_columns)
        self.no8_columns = list(no8_columns)
        names = self.old_columns + self.g8_columns + self.no8_columns
        if (len(self.old_columns) != 42 or len(self.g8_columns) != 8
                or len(self.no8_columns) != 8 or len(set(names)) != 58
                or any(not isinstance(n, str) or not n.strip() for n in names)):
            raise ValueError("Require 42 old + 8 unique G8 + 8 unique NO8 feature names")
        self.feature_sets = {
            "old42": self.old_columns,
            "new50": self.old_columns + self.g8_columns,
            "new58": names,
        }
        if (len(expected_counts) != 2 or any(isinstance(n, bool) or
                not isinstance(n, int) or n < 2 for n in expected_counts)):
            raise ValueError("expected_counts must contain positive training/validation sizes")
        self.expected_counts = tuple(expected_counts)

    def validate_spec(self, spec: dict) -> dict:
        if (not isinstance(spec, dict) or set(spec) != {"estimator", "feature_set"}
                or spec["estimator"] not in ("e011_tree", "krr")
                or spec["feature_set"] not in self.feature_sets):
            raise ValueError("Use only estimator=e011_tree/krr and feature_set=old42/new50/new58")
        return {"estimator": spec["estimator"], "feature_set": spec["feature_set"]}

    def feature_frame(self, X: pd.DataFrame) -> pd.DataFrame:
        if (not isinstance(X, pd.DataFrame) or not X.index.is_unique
                or not X.columns.is_unique or set(X.columns) != set(self.feature_sets["new58"])):
            raise ValueError("X must have unique IDs and exactly the registered 58 columns")
        X = X.loc[:, self.feature_sets["new58"]]
        if not np.isfinite(X.to_numpy(float)).all():
            raise ValueError("Prepared old/new descriptor inputs must be finite")
        self.legacy._feature_frame(X.loc[:, self.old_columns])
        return X

    def fixed_folds(self, meta, train_idx, fixed_fold_ids: pd.Series):
        train = self.legacy._positions(train_idx, len(meta))
        wanted = meta.index[train]
        if (not isinstance(fixed_fold_ids, pd.Series) or not fixed_fold_ids.index.is_unique
                or set(fixed_fold_ids.index) != set(wanted) or len(fixed_fold_ids) != len(train)):
            raise ValueError("Frozen fold IDs must cover exactly the historical training IDs")
        labels = fixed_fold_ids.loc[wanted].to_numpy()
        if labels.dtype.kind not in "iu" or set(labels.tolist()) != {0, 1}:
            raise ValueError("Frozen fold values must be integers 0 and 1")
        folds = []
        for fold in (0, 1):
            a, b = train[labels != fold], train[labels == fold]
            self.legacy.check_split_boundaries(meta, a, b)
            folds.append((a, b))
        return folds, labels.astype(np.int64)

    def _checked_inputs(self, X, meta, train_idx, val_idx, fixed_fold_ids):
        X = self.feature_frame(X)
        self.legacy._meta_frame(meta, X.index)
        train = self.legacy._positions(train_idx, len(X))
        val = self.legacy._positions(val_idx, len(X))
        self.legacy.check_split_boundaries(meta, train, val)
        if (len(train), len(val)) != self.expected_counts or len(train) + len(val) != len(X):
            raise ValueError("Training/validation counts differ from the registered boundary")
        if "split" not in meta or not (meta.iloc[train].split.eq("train").all()
                                        and meta.iloc[val].split.eq("validation").all()):
            raise ValueError("Indices must retain the historical split membership")
        folds, labels = self.fixed_folds(meta, train, fixed_fold_ids)
        return X, train, val, folds, labels

    def estimate_learner_fits(self, X, meta, spec, train_idx, val_idx, fixed_fold_ids):
        spec = self.validate_spec(spec)
        X, train, val, folds, _ = self._checked_inputs(
            X, meta, train_idx, val_idx, fixed_fold_ids)
        positions = [("validation", train)] + [(f"OOF_{i}", a) for i, (a, b) in enumerate(folds)]
        blocks = []
        for role, a in positions:
            count = (1 if spec["estimator"] == "krr" else
                     self.legacy.estimate_fit_count(X.iloc[a].loc[:, self.old_columns], self.e011_spec))
            blocks.append({"role": role, "rows": len(a), "learner_fits": count})
        return {"total_learner_fits": sum(b["learner_fits"] for b in blocks),
                "blocks": blocks, "fitting_performed": False}

    def fit_training_block(self, X_train, y_train, meta_train, spec,
                           audit: FitAudit | None = None, block_role="training"):
        X = self.feature_frame(X_train)
        self.legacy._meta_frame(meta_train, X.index)
        y = self.legacy._target_array(y_train, X.index)
        if not len(y) or not np.isfinite(y).all():
            raise ValueError("Training targets must be finite and nonempty")
        spec = self.validate_spec(spec)
        names = self.feature_sets[spec["feature_set"]]
        values = X.loc[:, names].to_numpy(float)
        audit = audit if audit is not None else FitAudit()
        common = {"block_role": block_role, "block_id": block_role,
                  "training_rows": len(y), "features": len(names),
                  "training_id_sha256": _json_hash(X.index.astype(str).tolist()),
                  "feature_columns_sha256": _json_hash(names),
                  "training_weight": "uniform", "routing": "oxygen_presence"}
        summary = {**common, "feature_set": spec["feature_set"], "feature_columns": list(names),
                   "chemical_systems": int(meta_train.chemical_system.nunique()),
                   "uses_evaluation_rows_or_targets_for_fitting": False}
        if spec["estimator"] == "krr":
            with threadpool_limits(limits=1):
                scaler = StandardScaler().fit(values)
                scaled = scaler.transform(values)
                distances = pdist(scaled, metric="euclidean")
                median = float(np.median(distances)) if len(distances) else 0.0
                gamma = 1.0 / median**2 if median > 0 else 1.0
                target_mean = float(y.mean())
                model = audit.fit(lambda: KernelRidge(alpha=1.0, kernel="rbf", gamma=gamma)
                                  .fit(scaled, y - target_mean), common | {
                                      "learner": "krr", "role": "global", "routing": "global",
                                      "estimator_parameters": {"alpha": 1.0, "kernel": "rbf", "gamma": gamma},
                                      "target_mean": target_mean, "distance_median": median})
            summary.update({"fit_count": 1, "fitted_component_models": 1,
                            "alpha": 1.0, "kernel": "rbf", "gamma": gamma,
                            "distance_median": median,
                            "distance_definition": "all unordered distinct-row pairs, Euclidean after current-training StandardScaler; duplicate-row zero distances retained",
                            "zero_median_fallback": median == 0,
                            "target_mean": target_mean,
                            "scaler_mean": scaler.mean_.tolist(), "scaler_scale": scaler.scale_.tolist(),
                            "scaler_variance": scaler.var_.tolist(),
                            "scaler_training_rows": int(scaler.n_samples_seen_),
                            "preprocessing": "Current-training-only StandardScaler and target mean centering"})
            return FittedPilotKRR(self.legacy, list(names), scaler, model, target_mean, summary)

        old = X.loc[:, self.old_columns]
        groups = self.legacy.route_labels(old, "oxygen_presence")
        counts = {g: int(np.sum(groups == g)) for g in ("oxygen", "no_oxygen")}
        weight_summaries = {}

        def components(indices, estimator, role):
            block_meta = meta_train.iloc[indices]
            weights, weight_summaries[role] = self.legacy.training_sample_weights(block_meta, "uniform")
            models = {}
            for learner in ("hgb", "extra_trees"):
                if estimator not in (learner, "blend"):
                    continue
                hgb_parameters, et_parameters = self.legacy.model_parameters(self.e011_spec)
                metadata = common | {"learner": learner, "role": role,
                                     "training_rows": len(indices),
                                     "estimator_parameters": (hgb_parameters if learner == "hgb" else et_parameters),
                                     "e011_spec_sha256": _json_hash(self.e011_spec),
                                     "training_id_sha256": _json_hash(block_meta.index.astype(str).tolist())}
                fitted = audit.fit(lambda name=learner: self.legacy._fit_models(
                    values[indices], y[indices], name, self.e011_spec, weights,
                    fit_events=[], role=role), metadata)
                models[learner] = fitted[learner]
            return models

        with threadpool_limits(limits=1):
            global_models = components(np.arange(len(y)), "extra_trees", "global")
            experts = {g: components(np.flatnonzero(groups == g), "blend", g)
                       for g, count in counts.items() if count >= 150}
        count = len(global_models) + sum(len(models) for models in experts.values())
        if count != self.legacy.estimate_fit_count(old, self.e011_spec):
            raise RuntimeError("Tree component accounting differs from frozen E011")
        hgb, et = self.legacy.model_parameters(self.e011_spec)
        summary.update({"fit_count": count, "fitted_component_models": count,
                        "group_train_counts": counts, "fitted_expert_groups": sorted(experts),
                        "training_weights": weight_summaries, "e011_spec": self.e011_spec,
                        "hgb_parameters": hgb, "extra_trees_parameters": et,
                        "preprocessing": "Finite prepared inputs; frozen E011 input-only oxygen routing and uniform weights; only selected feature columns differ"})
        return FittedPilotTree(self.legacy, list(names), self.e011_spec, global_models,
                               experts, counts, summary)

    def diagnostics(self, X, truth, prediction):
        y, p = np.asarray(truth, float), np.asarray(prediction, float)
        self.legacy.regression_metrics(y, p)
        total_error = float(np.abs(y - p).sum())
        oxygen = X.comp_fraction_Z008.to_numpy(float) > 0
        nitrogen = X.comp_fraction_Z007.to_numpy(float) > 0
        masks = {"global": np.ones(len(y), dtype=bool), "oxygen": oxygen,
                 "no_oxygen": ~oxygen, "nitrogen": nitrogen, "no_nitrogen": ~nitrogen}
        result = {}
        for label, mask in masks.items():
            if not mask.any():
                result[label] = {"rows": 0, "MAE_eV_atom": None, "RMSE_eV_atom": None,
                                 "prediction_minus_truth_mean": None, "p90_abs_error": None,
                                 "p99_abs_error": None, "share_total_abs_error": 0.0}
                continue
            error = p[mask] - y[mask]
            result[label] = self.legacy.regression_metrics(y[mask], p[mask]) | {
                "prediction_minus_truth_mean": float(error.mean()),
                "p90_abs_error": float(np.quantile(np.abs(error), 0.9)),
                "p99_abs_error": float(np.quantile(np.abs(error), 0.99)),
                "share_total_abs_error": float(np.abs(error).sum() / total_error) if total_error else 0.0}
        return result

    def evaluate(self, X, y, meta, spec, train_idx, val_idx, fixed_fold_ids,
                 event_callback: Callable[[dict], None] | None = None):
        spec = self.validate_spec(spec)
        X, train, val, folds, labels = self._checked_inputs(
            X, meta, train_idx, val_idx, fixed_fold_ids)
        targets = self.legacy._target_array(y, X.index)
        reservation = self.estimate_learner_fits(X, meta, spec, train, val, fixed_fold_ids)
        audit, started = FitAudit(event_callback), time.perf_counter()
        summaries, fold_summaries = [], []

        def block(a, b, role):
            model = self.fit_training_block(X.iloc[a], targets[a], meta.iloc[a], spec, audit, role)
            # Evaluation truth is attached only after every training and prediction call.
            predicted = model.predict(X.iloc[b])
            predicted.insert(0, "chemical_system", meta.iloc[b].chemical_system.astype(str))
            predicted.insert(1, "truth", targets[b])
            predicted.index.name = "material_id"
            summaries.append(model.training_summary)
            return predicted

        validation = block(train, val, "validation")
        oof_parts = []
        for fold, (a, b) in enumerate(folds):
            prediction = block(a, b, f"OOF_{fold}")
            prediction["fold"] = fold
            oof_parts.append(prediction)
            fold_summaries.append({"fold": fold, "train_rows": len(a), "evaluation_rows": len(b),
                                   "train_id_sha256": _json_hash(X.index[a].astype(str).tolist()),
                                   "evaluation_id_sha256": _json_hash(X.index[b].astype(str).tolist()),
                                   "metrics": self.legacy.regression_metrics(prediction.truth, prediction.prediction),
                                   "diagnostics": self.diagnostics(X.iloc[b], prediction.truth, prediction.prediction)})
        oof = pd.concat(oof_parts).loc[X.index[train]]
        if not np.array_equal(oof.fold.to_numpy(), labels):
            raise RuntimeError("OOF output no longer matches registered fold IDs")
        completed = sum(e["phase"] == "completed" for e in audit.events)
        started_fits = sum(e["phase"] == "started" for e in audit.events)
        if completed != reservation["total_learner_fits"] or completed != started_fits:
            raise RuntimeError("Completed fit count differs from no-fit reservation")
        val_metrics = self.legacy.regression_metrics(validation.truth, validation.prediction)
        oof_metrics = self.legacy.regression_metrics(oof.truth, oof.prediction)
        result = {"spec": spec, "validation": val_metrics, "OOF": oof_metrics,
                  "selection_score": 0.5 * (val_metrics["MAE_eV_atom"] + oof_metrics["MAE_eV_atom"]),
                  "validation_diagnostics": self.diagnostics(X.iloc[val], validation.truth, validation.prediction),
                  "OOF_diagnostics": self.diagnostics(X.iloc[train], oof.truth, oof.prediction),
                  "validation_groups": self.legacy.group_mae_summaries(X.iloc[val].loc[:, self.old_columns], validation.truth, validation.prediction),
                  "fold_summaries": fold_summaries, "training_summary": {"blocks": summaries},
                  "learner_fits": completed, "fit_started": started_fits,
                  "fit_completed": completed, "fit_reservation": reservation,
                  "elapsed_seconds": time.perf_counter() - started,
                  "legacy_evaluation_sha256": self.legacy_sha256,
                  "fixed_fold_id_sha256": _json_hash([[str(i), int(v)] for i, v in fixed_fold_ids.loc[X.index[train]].items()]),
                  "scope": "Previously observed development formation-energy evaluation; not independent confirmation"}
        frozen_folds = {"fixed_fold_id_sha256": result["fixed_fold_id_sha256"],
                        "assignment_source": "supplied frozen legacy E011 training IDs; no fold generation",
                        "folds": [{"fold": i, "train_ids": X.index[a].astype(str).tolist(),
                                   "evaluation_ids": X.index[b].astype(str).tolist()}
                                  for i, (a, b) in enumerate(folds)]}
        return {"result": result, "predictions": validation, "oof_predictions": oof,
                "fit_events": audit.events, "folds": frozen_folds}


def save_evaluation(bundle: dict, output_dir) -> dict:
    """Explicit artifact write, refusing to replace any prior completed artifact."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    names = ("validation_predictions.csv.gz", "internal_oof_predictions.csv.gz",
             "result.json", "base_fit_events.jsonl", "folds.json")
    if any((directory / name).exists() for name in names):
        raise FileExistsError("Pilot artifacts already exist; no science result overwrite")
    for key, name in (("predictions", names[0]), ("oof_predictions", names[1])):
        bundle[key].to_csv(directory / name, index=True, index_label="material_id",
                           float_format="%.17g", compression={"method": "gzip", "mtime": 0})
    (directory / "base_fit_events.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False, allow_nan=False) + "\n" for e in bundle["fit_events"]),
        encoding="utf-8")
    (directory / "folds.json").write_text(
        json.dumps(bundle["folds"], ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8")
    # Result is written last: existence denotes a completely saved prediction bundle.
    (directory / "result.json").write_text(
        json.dumps(bundle["result"], ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8")
    return {name: {"path": str((directory / name).resolve()),
                   "sha256": hashlib.sha256((directory / name).read_bytes()).hexdigest()}
            for name in names}
