"""Registered adaptive regression evaluation for input-routed materials strategies.

Importing this module performs no I/O or fitting. X is a pandas DataFrame with
the frozen raw30 + historical E04 columns. Positional indices always refer to
the same aligned X/y/meta rows. Only explicit run/cv CLI actions fit models.
"""
from __future__ import annotations

import os
for _thread_name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_thread_name, "1")

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

SEED = 20261002
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
E04_FEATURES = [
    "log_volume_per_atom", "log_edges6_per_atom", "smooth_coord_mean",
    "contact_q_mean", "site_field_abs_mean", "site_field_abs_std",
    "site_ionic_load_mean", "site_ionic_load_std", "en_coord_correlation",
    "contact_en_assortativity", "contact_radius_mismatch_mean", "strain_ionic_coupling",
]
FEATURES = RAW_FEATURES + E04_FEATURES
TARGETS = ("formation_energy_per_atom", "energy_above_hull")
GROUP_LABELS = {
    "global": ("global",),
    "oxygen_presence": ("oxygen", "no_oxygen"),
    "n_elements": ("1_2", "3", "4_plus"),
    "anion_family": ("oxygen", "halogen", "other_chalcogen", "other"),
}
ESTIMATORS = ("hgb", "extra_trees", "blend")
HGB_PARAMS = dict(max_iter=150, max_leaf_nodes=15, min_samples_leaf=20,
                  l2_regularization=10, learning_rate=0.05,
                  early_stopping=False, random_state=SEED)
ET_PARAMS = dict(n_estimators=400, min_samples_leaf=2, max_features=1.0,
                 n_jobs=1, random_state=SEED)
MODEL_OPTION_DOMAINS = {
    "et_min_samples_leaf": (1, 2, 4, 8),
    "et_max_features": (0.5, 0.75, 1.0),
    "hgb_loss": ("squared_error", "absolute_error"),
    "hgb_max_leaf_nodes": (15, 31),
    "hgb_min_samples_leaf": (10, 20),
    "hgb_l2_regularization": (0, 10),
    "hgb_learning_rate": (0.05, 0.1),
}
DEFAULT_MODEL_OPTIONS = {
    "et_min_samples_leaf": 2, "et_max_features": 1.0,
    "hgb_loss": "squared_error", "hgb_max_leaf_nodes": 15,
    "hgb_min_samples_leaf": 20, "hgb_l2_regularization": 10,
    "hgb_learning_rate": 0.05,
}
FEATURE_SETS = {"full42": FEATURES, "raw30": RAW_FEATURES}
TRAINING_WEIGHTS = ("uniform", "chemical_system_balanced")
# Host audit hook only. Events contain no targets and never supply model inputs.
FIT_EVENT_CALLBACK = None


def validate_spec(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise ValueError("Strategy specification must be an object")
    allowed = {"routing", "global_estimator", "blend_weight", "expert_estimators",
               "min_train_per_group", "shrinkage", "feature_set", "model_options",
               "training_weight"}
    if set(spec) - allowed:
        raise ValueError(f"Unknown strategy fields: {sorted(set(spec) - allowed)}")
    route, estimator = spec.get("routing"), spec.get("global_estimator")
    if route not in GROUP_LABELS or estimator not in ESTIMATORS:
        raise ValueError("Invalid routing or global_estimator")
    weight = spec.get("blend_weight", 0.5)
    minimum, shrinkage = spec.get("min_train_per_group", 100), spec.get("shrinkage", 0)
    if isinstance(weight, bool) or weight not in (0.25, 0.5, 0.75):
        raise ValueError("blend_weight must be 0.25, 0.5 or 0.75")
    if isinstance(minimum, bool) or minimum not in (100, 150):
        raise ValueError("min_train_per_group must be 100 or 150")
    if isinstance(shrinkage, bool) or shrinkage not in (0, 0.25, 0.5):
        raise ValueError("shrinkage must be the global weight 0, 0.25 or 0.5")
    experts = spec.get("expert_estimators", {})
    if not isinstance(experts, dict) or set(experts) - set(GROUP_LABELS[route]):
        raise ValueError("expert_estimators must use fixed labels for this routing")
    if any(value not in ESTIMATORS for value in experts.values()):
        raise ValueError("Expert estimators must be hgb, extra_trees or blend")
    if route == "global" and experts:
        raise ValueError("Global strategies have no expert estimators")
    feature_set = spec.get("feature_set", "full42")
    training_weight = spec.get("training_weight", "uniform")
    if feature_set not in FEATURE_SETS or training_weight not in TRAINING_WEIGHTS:
        raise ValueError("Invalid feature_set or training_weight")
    options = spec.get("model_options", {})
    if not isinstance(options, dict) or set(options) - set(MODEL_OPTION_DOMAINS):
        raise ValueError("Unknown model_options")
    options = DEFAULT_MODEL_OPTIONS | options
    for key, value in options.items():
        if isinstance(value, bool) or value not in MODEL_OPTION_DOMAINS[key]:
            raise ValueError(f"Invalid model option {key}: {value!r}")
    options = {key: (str(value) if key == "hgb_loss" else
                    int(value) if key.endswith(("samples_leaf", "leaf_nodes", "regularization")) else
                    float(value)) for key, value in options.items()}
    return {"routing": route, "global_estimator": estimator, "blend_weight": float(weight),
            "expert_estimators": dict(sorted(experts.items())),
            "min_train_per_group": int(minimum), "shrinkage": float(shrinkage),
            "feature_set": feature_set, "training_weight": training_weight,
            "model_options": options}


def fixed_catalogue() -> dict[str, dict]:
    """The frozen six ordinary-search candidates; not the whole Agent space."""
    return {f"{route}_{backend}": validate_spec({"routing": route, "global_estimator": backend})
            for route in ("global", "oxygen_presence", "n_elements")
            for backend in ("hgb", "extra_trees")}


def normalize_spec(spec: dict) -> dict:
    """Public normalization alias for the orchestration layer."""
    return validate_spec(spec)


def _feature_frame(X: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(X, pd.DataFrame) or not X.index.is_unique:
        raise ValueError("X must be a DataFrame with unique material IDs")
    if set(X.columns) != set(FEATURES) or len(X.columns) != len(FEATURES):
        raise ValueError("X must contain exactly the frozen 42 feature columns")
    ordered = X.loc[:, FEATURES]
    values = ordered.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Frozen prepared features must be finite; no label-based replacement")
    arity = ordered.comp_n_elements.to_numpy(float)
    if np.any(arity < 1) or not np.allclose(arity, np.round(arity), rtol=0, atol=1e-10):
        raise ValueError("comp_n_elements must be a positive integer-valued input")
    for name in ("comp_fraction_Z008", "comp_halogen_fraction", "comp_chalcogen_fraction"):
        fraction = ordered[name].to_numpy(float)
        if np.any(fraction < 0) or np.any(fraction > 1 + 1e-10):
            raise ValueError(f"Invalid input atomic fraction: {name}")
    return ordered


def route_labels(X: pd.DataFrame, routing: str) -> np.ndarray:
    """Pure single-row input routing: no y, residuals, split or material ID."""
    X = _feature_frame(X)
    if routing not in GROUP_LABELS:
        raise ValueError("Unknown routing")
    if routing == "global":
        return np.full(len(X), "global", dtype=object)
    oxygen = X.comp_fraction_Z008.to_numpy(float) > 0
    if routing == "oxygen_presence":
        return np.where(oxygen, "oxygen", "no_oxygen")
    if routing == "n_elements":
        arity = X.comp_n_elements.to_numpy(float)
        return np.where(arity <= 2, "1_2", np.where(arity == 3, "3", "4_plus"))
    # Operational element-presence hierarchy, not an oxidation-state assignment.
    # The frozen raw aggregate tables include At (halogen) and Po (chalcogen).
    halogen = X.comp_halogen_fraction.to_numpy(float) > 0
    chalcogen = X.comp_chalcogen_fraction.to_numpy(float) > 0
    return np.where(oxygen, "oxygen", np.where(halogen, "halogen",
                    np.where(chalcogen, "other_chalcogen", "other")))


def _meta_frame(meta: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
    if not isinstance(meta, pd.DataFrame) or not meta.index.equals(index):
        raise ValueError("meta must be a DataFrame aligned exactly with X")
    if not index.is_unique or "chemical_system" not in meta.columns:
        raise ValueError("Unique material IDs and chemical_system are required")
    if "material_id" in meta and not np.array_equal(meta.material_id.astype(str).to_numpy(), index.astype(str).to_numpy()):
        raise ValueError("meta material_id column does not match its aligned index")
    systems = meta.chemical_system
    if systems.isna().any() or systems.astype(str).str.strip().eq("").any():
        raise ValueError("Missing chemical_system")
    return meta


def _positions(indices, size: int) -> np.ndarray:
    raw = np.asarray(indices)
    if raw.ndim != 1 or raw.dtype.kind not in "iu" or not len(raw):
        raise ValueError("Indices must be a nonempty one-dimensional integer array")
    pos = raw.astype(np.int64, copy=False)
    if len(np.unique(pos)) != len(pos) or pos.min() < 0 or pos.max() >= size:
        raise ValueError("Duplicate or out-of-range positional indices")
    return pos


def check_split_boundaries(meta: pd.DataFrame, train_idx, eval_idx) -> None:
    _meta_frame(meta, meta.index)
    train = _positions(train_idx, len(meta))
    evaluate = _positions(eval_idx, len(meta))
    if np.intersect1d(train, evaluate).size:
        raise ValueError("Training/evaluation material overlap")
    train_systems = set(meta.chemical_system.iloc[train].astype(str))
    eval_systems = set(meta.chemical_system.iloc[evaluate].astype(str))
    if train_systems & eval_systems:
        raise ValueError("Training/evaluation chemical-system overlap")


def make_group_folds(meta: pd.DataFrame, n_splits: int = 2, indices=None):
    """Deterministic GroupKFold, no shuffling/targets; returns full-row positions."""
    _meta_frame(meta, meta.index)
    if isinstance(n_splits, bool) or n_splits not in (2, 3, 5):
        raise ValueError("Use a registered 2, 3 or 5 folds")
    selected = np.arange(len(meta), dtype=np.int64) if indices is None else _positions(indices, len(meta))
    systems = meta.chemical_system.iloc[selected].astype(str).to_numpy()
    if len(np.unique(systems)) < n_splits:
        raise ValueError("Insufficient chemical systems for GroupKFold")
    result = []
    for train_local, eval_local in GroupKFold(n_splits=n_splits).split(np.zeros(len(selected)), groups=systems):
        train, evaluate = selected[train_local], selected[eval_local]
        check_split_boundaries(meta, train, evaluate)
        result.append((train, evaluate))
    return result


def _target_array(y, index: pd.Index) -> np.ndarray:
    if isinstance(y, pd.Series) and not y.index.equals(index):
        raise ValueError("y index must match X exactly")
    result = np.asarray(y, dtype=float)
    if result.ndim != 1 or len(result) != len(index):
        raise ValueError("y must be a one-dimensional aligned target")
    return result


def model_parameters(spec: dict) -> tuple[dict, dict]:
    """Return registered parameters; estimator counts and random seed stay fixed."""
    options = validate_spec(spec)["model_options"]
    hgb = HGB_PARAMS | {
        "loss": options["hgb_loss"], "max_leaf_nodes": options["hgb_max_leaf_nodes"],
        "min_samples_leaf": options["hgb_min_samples_leaf"],
        "l2_regularization": options["hgb_l2_regularization"],
        "learning_rate": options["hgb_learning_rate"],
    }
    et = ET_PARAMS | {"min_samples_leaf": options["et_min_samples_leaf"],
                      "max_features": options["et_max_features"]}
    return hgb, et


def training_sample_weights(meta_train: pd.DataFrame, mode: str) -> tuple[np.ndarray, dict]:
    """Only the current fit's training systems enter its mean-one weights."""
    _meta_frame(meta_train, meta_train.index)
    if mode not in TRAINING_WEIGHTS or not len(meta_train):
        raise ValueError("Nonempty training metadata and a registered weight mode required")
    systems = meta_train.chemical_system.astype(str)
    counts = systems.value_counts()
    weights = (1.0 / systems.map(counts).to_numpy(float) if mode == "chemical_system_balanced"
               else np.ones(len(systems), dtype=float))
    weights /= weights.mean()
    totals = pd.Series(weights, index=meta_train.index).groupby(systems).sum()
    summary = {"mode": mode, "rows": len(weights), "chemical_systems": len(counts),
               "normalization": "mean_one_per_current_training_fit",
               "minimum": float(weights.min()), "maximum": float(weights.max()),
               "mean": float(weights.mean()), "sum": float(weights.sum()),
               "system_total_minimum": float(totals.min()), "system_total_maximum": float(totals.max()),
               "uses_evaluation_rows_or_targets": False}
    return weights, summary


def _component_count(estimator: str) -> int:
    return 2 if estimator == "blend" else 1


def estimate_fit_count(X_train: pd.DataFrame, spec: dict) -> int:
    """Exact number of base learners under the actual minimum-group fallback; no fitting."""
    X_train, spec = _feature_frame(X_train), validate_spec(spec)
    if not len(X_train):
        raise ValueError("Training rows must be nonempty")
    count = _component_count(spec["global_estimator"])
    if spec["routing"] != "global":
        groups = route_labels(X_train, spec["routing"])
        for group in GROUP_LABELS[spec["routing"]]:
            if np.sum(groups == group) >= spec["min_train_per_group"]:
                count += _component_count(spec["expert_estimators"].get(group, spec["global_estimator"]))
    return count


def estimate_learner_fits(X: pd.DataFrame, meta: pd.DataFrame, spec: dict, train_idx,
                          folds=None) -> dict:
    """Exact reservation for historical validation fit plus registered training OOF fits."""
    X = _feature_frame(X)
    _meta_frame(meta, X.index)
    train = _positions(train_idx, len(X))
    folds = make_group_folds(meta, n_splits=2, indices=train) if folds is None else list(folds)
    blocks = [{"role": "validation", "rows": len(train),
               "learner_fits": estimate_fit_count(X.iloc[train], spec)}]
    covered = []
    for number, (a, b) in enumerate(folds):
        check_split_boundaries(meta, a, b)
        a, b = _positions(a, len(X)), _positions(b, len(X))
        if not set(a).issubset(set(train)) or not set(b).issubset(set(train)):
            raise ValueError("OOF reservation must use historical training rows only")
        covered.extend(b.tolist())
        blocks.append({"role": f"OOF_{number}", "rows": len(a),
                       "learner_fits": estimate_fit_count(X.iloc[a], spec)})
    if len(folds) != 2 or len(covered) != len(train) or set(covered) != set(train):
        raise ValueError("Expected two-fold OOF covering each historical training row exactly once")
    return {"total_learner_fits": sum(block["learner_fits"] for block in blocks),
            "blocks": blocks, "fitting_performed": False}


def _fit_models(X: np.ndarray, y: np.ndarray, estimator: str, spec=None,
                sample_weight=None, fit_events=None, role="global") -> dict:
    models = {}
    spec = validate_spec(spec or {"routing": "global", "global_estimator": estimator})
    hgb_params, et_params = model_parameters(spec)
    events = fit_events if fit_events is not None else []
    if spec["training_weight"] == "chemical_system_balanced":
        weights = np.asarray(sample_weight, dtype=float)
        if weights.shape != np.asarray(y).shape or not np.isfinite(weights).all() or np.any(weights <= 0):
            raise ValueError("Balanced learner fit requires aligned positive finite training weights")
    for name, factory, params in (("hgb", HistGradientBoostingRegressor, hgb_params),
                                  ("extra_trees", ExtraTreesRegressor, et_params)):
        if estimator not in (name, "blend"):
            continue
        event = {"event": "base_learner_fit", "role": role, "learner": name,
                 "rows": len(y), "features": X.shape[1], "status": "started"}
        events.append(event)
        try:
            metadata = {"learner": name, "training_rows": len(y), "features": X.shape[1],
                        "role": role, "training_weight": spec["training_weight"]}
            if FIT_EVENT_CALLBACK is not None:
                FIT_EVENT_CALLBACK(metadata | {"phase": "started"})
            # Omitting uniform weights retains the original estimator call semantics.
            kwargs = {} if spec["training_weight"] == "uniform" else {"sample_weight": sample_weight}
            models[name] = factory(**params).fit(X, y, **kwargs)
            event["status"] = "complete"
            if FIT_EVENT_CALLBACK is not None:
                FIT_EVENT_CALLBACK(metadata | {"phase": "completed"})
        except Exception as exc:
            event["status"] = "failed"
            event["error"] = f"{type(exc).__name__}: {exc}"
            exc.fit_events = events
            raise
    return models


def _predict_models(models: dict, X: np.ndarray, weight: float) -> np.ndarray:
    if len(models) == 1:
        return np.asarray(next(iter(models.values())).predict(X), dtype=float)
    return weight * models["hgb"].predict(X) + (1 - weight) * models["extra_trees"].predict(X)


@dataclass
class FittedStrategy:
    spec: dict
    global_models: dict
    expert_models: dict
    group_train_counts: dict
    training_summary: dict

    def predict(self, X_new: pd.DataFrame, meta_new=None, return_routes: bool = False):
        """Predict without target values; meta is only optional output identity."""
        X_new = _feature_frame(X_new)
        if not len(X_new):
            raise ValueError("Cannot predict an empty feature table")
        if meta_new is not None:
            _meta_frame(meta_new, X_new.index)
        values = X_new.loc[:, FEATURE_SETS[self.spec.get("feature_set", "full42")]].to_numpy(float)
        groups = route_labels(X_new, self.spec["routing"])
        with threadpool_limits(limits=1):
            global_prediction = _predict_models(self.global_models, values, self.spec["blend_weight"])
            prediction = global_prediction.copy()
            model_route = np.full(len(X_new), "global", dtype=object)
            fallback = np.zeros(len(X_new), dtype=bool)
            reason = np.full(len(X_new), "", dtype=object)
            if self.spec["routing"] != "global":
                for group in GROUP_LABELS[self.spec["routing"]]:
                    mask = groups == group
                    if not mask.any():
                        continue
                    if group not in self.expert_models:
                        fallback[mask] = True
                        reason[mask] = "train_group_below_minimum"
                        model_route[mask] = "global_fallback"
                    else:
                        expert_prediction = _predict_models(self.expert_models[group], values[mask],
                                                           self.spec["blend_weight"])
                        global_weight = self.spec["shrinkage"]
                        prediction[mask] = ((1 - global_weight) * expert_prediction
                                            + global_weight * global_prediction[mask])
                        backend = self.spec["expert_estimators"].get(group, self.spec["global_estimator"])
                        model_route[mask] = f"expert:{group}:{backend}"
        if not np.isfinite(prediction).all():
            raise ValueError("Nonfinite predictions")
        if not return_routes:
            return prediction
        result = pd.DataFrame({"prediction": prediction, "input_group": groups,
                               "model_route": model_route, "fallback": fallback,
                               "fallback_reason": reason,
                               "expert_train_rows": [self.group_train_counts.get(g, 0) for g in groups]},
                              index=X_new.index)
        result.index.name = "material_id"
        if meta_new is not None:
            result.insert(0, "chemical_system", meta_new.chemical_system.astype(str))
        return result


def fit_strategy(X_train: pd.DataFrame, y_train, meta_train: pd.DataFrame, spec: dict) -> FittedStrategy:
    X_train = _feature_frame(X_train)
    _meta_frame(meta_train, X_train.index)
    y = _target_array(y_train, X_train.index)
    if not len(y) or not np.isfinite(y).all():
        raise ValueError("Training targets must be nonempty and finite")
    spec = validate_spec(spec)
    feature_names = FEATURE_SETS[spec["feature_set"]]
    values = X_train.loc[:, feature_names].to_numpy(float)
    groups = route_labels(X_train, spec["routing"])
    counts = {group: int(np.sum(groups == group)) for group in GROUP_LABELS[spec["routing"]]}
    experts, fit_events, weight_summaries = {}, [], {}
    with threadpool_limits(limits=1):
        weights, weight_summaries["global"] = training_sample_weights(meta_train, spec["training_weight"])
        global_models = _fit_models(values, y, spec["global_estimator"], spec, weights, fit_events, "global")
        if spec["routing"] != "global":
            for group, count in counts.items():
                if count >= spec["min_train_per_group"]:
                    mask = groups == group
                    backend = spec["expert_estimators"].get(group, spec["global_estimator"])
                    weights, weight_summaries[group] = training_sample_weights(meta_train.iloc[np.flatnonzero(mask)], spec["training_weight"])
                    experts[group] = _fit_models(values[mask], y[mask], backend, spec, weights, fit_events, group)
    component_count = len(global_models) + sum(len(models) for models in experts.values())
    summary = {"rows": len(y), "chemical_systems": int(meta_train.chemical_system.nunique()),
               "features": len(feature_names), "feature_columns": feature_names,
               "feature_set": spec["feature_set"], "group_train_counts": counts,
               "fitted_expert_groups": sorted(experts), "fitted_component_models": component_count,
               "fit_count": component_count,
               "fit_events": fit_events, "training_weight": spec["training_weight"],
               "training_weights": weight_summaries,
               "hgb_parameters": model_parameters(spec)[0], "extra_trees_parameters": model_parameters(spec)[1],
               "spec": spec, "preprocessing": "Frozen 42 finite prepared inputs; selected raw30/full42, input-only routing, current-training-only sample weights; no new descriptors."}
    if component_count != estimate_fit_count(X_train, spec) or len(fit_events) != component_count:
        raise RuntimeError("Base learner fit accounting mismatch")
    return FittedStrategy(spec, global_models, experts, counts, summary)


def regression_metrics(truth, prediction) -> dict:
    y, p = np.asarray(truth, dtype=float), np.asarray(prediction, dtype=float)
    if y.ndim != 1 or p.shape != y.shape or not len(y) or not np.isfinite(y).all() or not np.isfinite(p).all():
        raise ValueError("Metrics require aligned, nonempty finite targets and predictions")
    return {"rows": len(y), "MAE_eV_atom": float(np.mean(np.abs(y - p))),
            "RMSE_eV_atom": float(np.sqrt(np.mean((y - p) ** 2)))}


def group_mae_summaries(X_eval: pd.DataFrame, truth, prediction) -> dict:
    y, p = np.asarray(truth, float), np.asarray(prediction, float)
    regression_metrics(y, p)
    if len(X_eval) != len(y):
        raise ValueError("Group summaries require aligned features")
    result = {}
    for routing in ("oxygen_presence", "n_elements", "anion_family"):
        labels = route_labels(X_eval, routing)
        result[routing] = {
            label: regression_metrics(y[labels == label], p[labels == label]) if np.any(labels == label)
            else {"rows": 0, "MAE_eV_atom": None, "RMSE_eV_atom": None}
            for label in GROUP_LABELS[routing]}
    return result


def run_strategy(X, y, meta, spec, train_idx, eval_idx) -> dict[str, Any]:
    X = _feature_frame(X)
    _meta_frame(meta, X.index)
    check_split_boundaries(meta, train_idx, eval_idx)
    train, evaluate = _positions(train_idx, len(X)), _positions(eval_idx, len(X))
    targets = _target_array(y, X.index)
    # Evaluation targets are used only below, after training and prediction.
    fitted = fit_strategy(X.iloc[train], targets[train], meta.iloc[train], spec)
    predicted = fitted.predict(X.iloc[evaluate], meta.iloc[evaluate], return_routes=True)
    predicted.insert(1, "truth", targets[evaluate])
    prediction = predicted.prediction.to_numpy(float)
    return {"model": fitted, "predictions": predicted,
            "metrics": regression_metrics(targets[evaluate], prediction),
            "group_metrics": group_mae_summaries(X.iloc[evaluate], targets[evaluate], prediction),
            "training_summary": fitted.training_summary}


def paired_system_bootstrap(y_true, prediction_a, prediction_b, systems,
                            resamples: int = 2000, seed: int = SEED) -> dict:
    """Paired chemical-system clusters; statistic is row-weighted MAE A-B."""
    y, a, b = (np.asarray(values, dtype=float) for values in (y_true, prediction_a, prediction_b))
    regression_metrics(y, a)
    regression_metrics(y, b)
    if not isinstance(resamples, (int, np.integer)) or resamples < 100:
        raise ValueError("At least 100 bootstrap resamples are required")
    raw_systems = np.asarray(systems, dtype=object)
    if pd.isna(raw_systems).any():
        raise ValueError("Missing chemical systems are forbidden")
    systems = raw_systems.astype(str)
    if systems.shape != y.shape or np.any(systems == ""):
        raise ValueError("Aligned nonempty chemical systems are required")
    unique, inverse = np.unique(systems, return_inverse=True)
    delta = np.abs(y - a) - np.abs(y - b)
    totals, counts = np.bincount(inverse, weights=delta), np.bincount(inverse)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(unique), size=(resamples, len(unique)))
    sampled = totals[draws].sum(axis=1) / counts[draws].sum(axis=1)
    low, high = np.quantile(sampled, [0.025, 0.975])
    return {"rows": len(y), "chemical_systems": len(unique), "MAE_A_minus_B_eV_atom": float(delta.mean()),
            "lower95": float(low), "upper95": float(high), "resamples": int(resamples), "seed": int(seed),
            "scope": "Paired cluster percentile interval conditional on fitted predictions; excludes search/training uncertainty. Development comparisons are not independent confirmation."}


def _csv_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, float_precision="round_trip").set_index("material_id")
    if not frame.index.is_unique:
        raise ValueError(f"Duplicate material IDs in {path.name}")
    frame.index = frame.index.astype(str)
    return frame


def load_development(data_dir, e04_path=None):
    """Explicit observed development inputs only; returns aligned sorted rows."""
    directory = Path(data_dir)
    e04_path = Path(e04_path) if e04_path is not None else directory.parent / "agent_descriptors/E04/development_descriptors.csv.gz"
    features = _csv_frame(directory / "features.csv.gz").sort_index()
    targets = _csv_frame(directory / "targets.csv.gz")
    e04 = _csv_frame(e04_path)
    if set(features.index) != set(targets.index) or set(features.index) != set(e04.index):
        raise ValueError("Prepared raw/E04/targets IDs must match exactly")
    targets, e04 = targets.loc[features.index], e04.loc[features.index]
    for identity in ("chemical_system", "composition_signature"):
        if identity in features and identity in targets and not features[identity].equals(targets[identity]):
            raise ValueError(f"Prepared identity mismatch: {identity}")
    if set(e04.columns) != set(E04_FEATURES):
        raise ValueError("Only frozen historical E04 twelve columns are allowed")
    X = pd.concat([features.loc[:, RAW_FEATURES], e04.loc[:, E04_FEATURES]], axis=1)
    X = _feature_frame(X)
    metadata = features.loc[:, [c for c in ("formula", "chemical_system", "composition_signature") if c in features]].copy()
    metadata.insert(0, "material_id", X.index.to_numpy())
    metadata["split"] = targets["split"]
    _meta_frame(metadata, X.index)
    if not targets["split"].isin(("train", "validation")).all():
        raise ValueError("This evaluator accepts only historical train/validation development rows")
    if len(X) != 2879 or targets["split"].value_counts().to_dict() != {"train": 2164, "validation": 715}:
        raise ValueError("Observed development boundary must be 2164 train + 715 validation")
    return X, targets.loc[:, ["split", *TARGETS]].copy(), metadata


def schema() -> dict:
    return {"features": FEATURES, "target_choices": list(TARGETS), "groups": GROUP_LABELS,
            "spec_fields": {"routing": list(GROUP_LABELS), "global_estimator": ESTIMATORS,
                            "blend_weight": [0.25, 0.5, 0.75], "expert_estimators": "fixed group label -> estimator; missing inherits global",
                            "min_train_per_group": [100, 150], "shrinkage": [0, 0.25, 0.5],
                            "feature_set": list(FEATURE_SETS), "training_weight": list(TRAINING_WEIGHTS),
                            "model_options": MODEL_OPTION_DOMAINS},
            "blend_definition": "weight * HGB + (1-weight) * ExtraTrees, also for a blend expert",
            "shrinkage_definition": "(1-shrinkage) * expert + shrinkage * global; small/unseen groups use global",
            "anion_family_definition": "Frozen raw numeric element-presence aggregates: oxygen > halogen > other chalcogen > other. Includes At/Po as in raw schema; no ionic-state inference.",
            "fixed_catalogue": fixed_catalogue(), "hgb_parameters": HGB_PARAMS,
            "extra_trees_parameters": ET_PARAMS,
            "fold_definition": "GroupKFold with shuffle=False, chemical_system, stable sorted input IDs, historical training rows only for internal folds",
            "candidate_budget": "Enforced by caller using candidate attempts and exact base learner fit reservations. This module never searches or chooses a strategy."}


def _json_write(path: Path, data) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _output_directory(path) -> Path:
    destination = Path(path)
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError("Output directory must be new or empty")
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def _save_result(result: dict, destination: Path, target: str) -> None:
    result["predictions"].to_csv(destination / "predictions.csv", index_label="material_id")
    joblib.dump(result["model"], destination / "model.joblib")
    _json_write(destination / "summary.json", {key: value for key, value in result.items()
                if key not in ("model", "predictions")} | {"target": target})


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("schema")
    for command in ("run", "cv"):
        sub = commands.add_parser(command)
        sub.add_argument("--data-dir", required=True)
        sub.add_argument("--e04-path", required=True)
        sub.add_argument("--spec", required=True)
        sub.add_argument("--output", required=True)
        sub.add_argument("--target", choices=TARGETS, default=TARGETS[0])
        if command == "run":
            sub.add_argument("--train-split", choices=("train",), default="train")
            sub.add_argument("--eval-split", choices=("validation",), default="validation")
        else:
            sub.add_argument("--n-splits", type=int, choices=(2, 3, 5), default=2)
    predict = commands.add_parser("predict")
    predict.add_argument("--model", required=True)
    predict.add_argument("--features", required=True, help="CSV with material_id and frozen 42 features")
    predict.add_argument("--output", required=True)
    bootstrap = commands.add_parser("bootstrap")
    bootstrap.add_argument("--proposed", required=True)
    bootstrap.add_argument("--control", required=True)
    bootstrap.add_argument("--output", required=True)
    bootstrap.add_argument("--resamples", type=int, default=2000)
    args = parser.parse_args(argv)
    if args.command == "schema":
        print(json.dumps(schema(), ensure_ascii=False, indent=2))
        return
    if args.command in ("run", "cv"):
        X, target_table, meta = load_development(args.data_dir, args.e04_path)
        spec = validate_spec(json.loads(Path(args.spec).read_text(encoding="utf-8")))
        target = target_table[args.target]
        destination = _output_directory(args.output)
        train = np.flatnonzero(meta.split.eq("train").to_numpy())
        if args.command == "run":
            evaluate = np.flatnonzero(meta.split.eq("validation").to_numpy())
            result = run_strategy(X, target, meta, spec, train, evaluate)
            _save_result(result, destination, args.target)
            print(json.dumps(result["metrics"]))
        else:
            folds = make_group_folds(meta, n_splits=args.n_splits, indices=train)
            summaries, predictions, fold_ids = [], [], []
            for number, (fold_train, fold_eval) in enumerate(folds):
                result = run_strategy(X, target, meta, spec, fold_train, fold_eval)
                frame = result["predictions"].copy()
                frame["fold"] = number
                predictions.append(frame)
                summaries.append({"fold": number, **{key: result[key] for key in
                                 ("metrics", "group_metrics", "training_summary")}})
                fold_ids.append({"fold": number, "train_ids": X.index[fold_train].tolist(),
                                 "eval_ids": X.index[fold_eval].tolist()})
                del result
            combined = pd.concat(predictions).loc[X.index[train]]
            if not combined.index.is_unique or len(combined) != len(train):
                raise RuntimeError("OOF records are not one prediction per training row")
            combined.to_csv(destination / "oof_predictions.csv", index_label="material_id")
            metrics = regression_metrics(combined.truth, combined.prediction)
            _json_write(destination / "summary.json", {"target": args.target, "metrics": metrics,
                        "group_metrics": group_mae_summaries(X.loc[combined.index], combined.truth, combined.prediction),
                        "folds": summaries, "scope": "Historical training OOF development diagnostics; no independent confirmation."})
            _json_write(destination / "folds.json", fold_ids)
            print(json.dumps(metrics))
        return
    if args.command == "predict":
        # joblib is executable serialization: use only this evaluator's trusted model files.
        model = joblib.load(args.model)
        features = _csv_frame(Path(args.features))
        metadata = features.loc[:, ["chemical_system"]] if "chemical_system" in features else None
        result = model.predict(features.loc[:, FEATURES], metadata, return_routes=True)
        destination = _output_directory(args.output)
        result.to_csv(destination / "predictions.csv", index_label="material_id")
        print(json.dumps({"rows": len(result), "labels_used": False}))
        return
    proposed, control = _csv_frame(Path(args.proposed)).sort_index(), _csv_frame(Path(args.control)).sort_index()
    if not proposed.index.equals(control.index) or not proposed.chemical_system.equals(control.chemical_system):
        raise ValueError("Bootstrap prediction identities/systems must match exactly")
    if not np.array_equal(proposed.truth.to_numpy(float), control.truth.to_numpy(float)):
        raise ValueError("Bootstrap target rows must match exactly")
    result = paired_system_bootstrap(proposed.truth, proposed.prediction, control.prediction,
                                     proposed.chemical_system, args.resamples)
    _json_write(Path(args.output), result)
    print(json.dumps(result))


if __name__ == "__main__":
    # Canonical module name keeps CLI-fitted artifacts loadable by imported runners.
    sys.modules["evaluation"] = sys.modules[__name__]
    FittedStrategy.__module__ = "evaluation"
    main()
