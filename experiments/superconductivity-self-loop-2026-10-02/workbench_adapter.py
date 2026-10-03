"""Training-only adapter over the frozen Tc V2 evaluator.

Only an explicit source-file allowlist is copied.  Historical validation data,
post-freeze results, reports, and selection records are never read.  Cached OOF
evidence is useful development memory, not independent generalization evidence.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import sys
import threading
from datetime import datetime, timezone

_DATA = ("train.csv.gz", "schema.json", "fold_assignments.csv", "data_audit.json")
_CODE = ("pipeline.py", "prepare_data.py")
_EVIDENCE = ("specification.json", "result.json", "oof_predictions.csv.gz")
_ID = re.compile(r"[A-Z][A-Z0-9_-]{0,31}\Z")
_PRIOR_ID = re.compile(r"[GDRAC][0-9]+\Z")
_IMPORT_LOCK = threading.Lock()
_SCOPE = "Original training fixed-group OOF only; adaptive development feedback"


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(path)


def _canonical(spec):
    return json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def fingerprint(spec):
    """Canonical specification hash, independent of mapping insertion order."""
    return hashlib.sha256(_canonical(spec).encode("utf-8")).hexdigest()


def _check_id(cid):
    if not isinstance(cid, str) or not _ID.fullmatch(cid):
        raise ValueError("Invalid candidate ID")


def _safe_file(path, parent):
    path, parent = Path(path), Path(parent).resolve()
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(parent):
        raise ValueError("Missing or unsafe allowlisted file: " + str(path))


def _check_manifest(run_dir, source_dir, manifest):
    if manifest.get("format") != "tc-self-loop-train-only-v1":
        raise ValueError("Unknown adapter manifest")
    if manifest["source_dir"] != str(source_dir):
        raise ValueError("Cannot resume with a different frozen source")
    root = run_dir / "workbench"
    for relative, record in manifest["files"].items():
        original, copied = source_dir / relative, root / relative
        _safe_file(original, source_dir)
        _safe_file(copied, root)
        if _sha(original) != record["sha256"] or _sha(copied) != record["sha256"]:
            raise ValueError("Frozen training evidence changed: " + relative)
    forbidden = [root / "final", root / "selection.json"]
    forbidden += [p for p in (root / "data").glob("*") if p.name not in _DATA]
    if any(p.exists() for p in forbidden):
        raise ValueError("Unexpected non-training artifact in isolated workbench")


def prepare_run(run_dir: Path, source_dir: Path) -> dict:
    """Copy and hash allowlisted training evidence; never prepare or evaluate data."""
    run_dir, source_dir = Path(run_dir).resolve(), Path(source_dir).resolve()
    if run_dir.is_relative_to(source_dir) or source_dir.is_relative_to(run_dir):
        raise ValueError("Run and frozen-source directories must be disjoint")
    manifest_path = run_dir / "workbench_manifest.json"
    if manifest_path.exists():
        manifest = _load(manifest_path)
        _check_manifest(run_dir, source_dir, manifest)
        return manifest
    root = run_dir / "workbench"
    if root.exists() and any(root.iterdir()):
        raise ValueError("Unmanifested workbench already exists; use a clean run directory")
    names = list(_CODE) + ["data/" + name for name in _DATA]
    prior_ids, skipped = [], []
    for directory in sorted((source_dir / "candidates").iterdir()):
        if not directory.is_dir() or not _PRIOR_ID.fullmatch(directory.name):
            continue
        if not all((directory / name).is_file() for name in _EVIDENCE):
            skipped.append(directory.name)
            continue
        result = _load(directory / "result.json")
        if result.get("candidate_id") != directory.name or not isinstance(result.get("metrics"), dict):
            raise ValueError("Invalid prior candidate: " + directory.name)
        if "training" not in result.get("feedback_scope", "").lower() or "oof" not in result.get("feedback_scope", "").lower():
            raise ValueError("Prior candidate lacks a training-OOF scope: " + directory.name)
        if not math.isfinite(result["metrics"].get("MAE_K", float("nan"))):
            raise ValueError("Prior candidate has no finite completed result: " + directory.name)
        prior_ids.append(directory.name)
        names += ["candidates/" + directory.name + "/" + name for name in _EVIDENCE]
    if "G01" not in prior_ids:
        raise ValueError("Frozen training baseline G01 is required")
    files = {}
    for relative in names:
        original, copied = source_dir / relative, root / relative
        _safe_file(original, source_dir)
        before = _sha(original)
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, copied)
        if _sha(original) != before or _sha(copied) != before:
            raise ValueError("Source changed during copy: " + relative)
        files[relative] = {"sha256": before, "bytes": copied.stat().st_size}
    manifest = {"format": "tc-self-loop-train-only-v1", "source_dir": str(source_dir),
                "created_utc": datetime.now(timezone.utc).isoformat(), "scope": _SCOPE,
                "prior_candidate_ids": prior_ids, "skipped_incomplete_ids": skipped,
                "files": files, "copy_policy": "Explicit code/training-file/candidate-OOF allowlist only"}
    _check_manifest(run_dir, source_dir, manifest)
    _save(manifest_path, manifest)
    return manifest


def _vendor(root):
    """Import copied source with its absolute prepare_data import isolated."""
    identity = hashlib.sha256(str(root).encode()).hexdigest()[:20]
    module_name = "_tc_train_vendor_" + identity
    with _IMPORT_LOCK:
        if module_name in sys.modules:
            return sys.modules[module_name]
        previous = sys.modules.get("prepare_data")
        try:
            prep_spec = importlib.util.spec_from_file_location("prepare_data", root / "prepare_data.py")
            prep = importlib.util.module_from_spec(prep_spec)
            sys.modules["prepare_data"] = prep
            prep_spec.loader.exec_module(prep)
            pipe_spec = importlib.util.spec_from_file_location(module_name, root / "pipeline.py")
            pipe = importlib.util.module_from_spec(pipe_spec)
            sys.modules[module_name] = pipe
            pipe_spec.loader.exec_module(pipe)
        except BaseException:
            sys.modules.pop(module_name, None)
            raise
        finally:
            if previous is None:
                sys.modules.pop("prepare_data", None)
            else:
                sys.modules["prepare_data"] = previous
    return pipe


def _compact_metrics(value):
    keys = ("rows", "groups", "weight_sum", "MAE_K", "RMSE_K", "bias_K")
    result = {key: value[key] for key in keys if key in value}
    result["subgroups"] = {name: {key: item[key] for key in keys if key in item}
                           for name, item in value.get("subgroups", {}).items()
                           if name in ("reported_zero", "positive_tc", "high_tc_ge40K")}
    return result


class Adapter:
    def __init__(self, run_dir: Path, source_dir: Path):
        self.run_dir, self.source_dir = Path(run_dir).resolve(), Path(source_dir).resolve()
        self.manifest = prepare_run(self.run_dir, self.source_dir)
        self.root = self.run_dir / "workbench"
        self._pipeline = _vendor(self.root)
        self._bench = self._pipeline.Workbench(self.root)
        self._bench._training()
        self._check_training()
        self.index_path = self.run_dir / "adapter_index.json"
        self._index = _load(self.index_path) if self.index_path.exists() else {"version": 1, "evidence": {}}
        self._index.setdefault("pending", {})
        self._check_index()
        for cid in self.manifest["prior_candidate_ids"]:
            self._verify_candidate(cid)
        self._recover_pending()

    fingerprint = staticmethod(fingerprint)

    def _check_training(self):
        np, frame, schema = self._pipeline.np, self._bench.train, self._bench.schema
        if not frame.material_id.is_unique or frame.material_id.isna().any() or frame.group.isna().any():
            raise ValueError("Training IDs/groups must be present and unique per record")
        if "split" in frame and set(frame.split) != {"train"}:
            raise ValueError("Non-training row in isolated feedback")
        for identity in ("chemical_system", "parent_id", "canonical_composition"):
            if identity in frame and frame.groupby(identity, dropna=False).group.nunique().max() != 1:
                raise ValueError("Strict linked-identity grouping broken: " + identity)
        forbidden = set(schema.get("excluded_predictor_metadata", [])) | {"tc", "weight", "group", "material_id", "formula", "split"}
        for names in schema["inputs"].values():
            if forbidden & set(names) or any(name not in frame for name in names):
                raise ValueError("Predictor schema leaks metadata or references missing columns")
        if not np.isfinite(frame[["tc", "weight"]].to_numpy()).all() or (frame.tc < 0).any() or (frame.weight <= 0).any():
            raise ValueError("Invalid training labels/weights")

    def _check_index(self):
        # The parent controller and evaluator worker keep separate Adapter
        # instances.  Always observe the worker's atomic journal commit before
        # checking or presenting evidence; an in-memory index is not current.
        if self.index_path.exists():
            self._index = _load(self.index_path)
            self._index.setdefault("pending", {})
        for relative, digest in self._index["evidence"].items():
            path = self.root / relative
            _safe_file(path, self.root)
            if _sha(path) != digest:
                raise ValueError("Recorded new candidate evidence changed: " + relative)

    def _commit_evidence(self, cid):
        for name in _EVIDENCE:
            relative = "candidates/" + cid + "/" + name
            self._index["evidence"][relative] = _sha(self.root / relative)
        self._index["pending"].pop(cid, None)
        _save(self.index_path, self._index)

    def _recover_pending(self):
        """Recover a complete, journaled result after interruption without refit."""
        for cid, pending in list(self._index["pending"].items()):
            _check_id(cid)
            expected = self._pipeline.validate_spec(pending["spec"])
            if fingerprint(expected) != pending["fingerprint"]:
                raise ValueError("Pending specification fingerprint mismatch")
            folder = self.root / "candidates" / cid
            if not (folder / "result.json").exists():
                continue
            result = self._verify_candidate(cid)
            if fingerprint(result["specification"]) != pending["fingerprint"]:
                raise ValueError("Completed result disagrees with pending evaluation")
            # A crash can occur between the frozen evaluator's result write
            # and the adapter's metadata write.  Preserve actual prior fit cost
            # and distinguish recovery from a duplicate proposal.
            if "adapter_reused" not in result:
                result.update(adapter_reused=False, reused_from=None,
                              actual_new_regressor_fits=result["actual_model_fits"],
                              candidate_total_regressor_fits=result["actual_model_fits"])
                _save(folder / "result.json", result)
            self._commit_evidence(cid)

    def _verify_candidate(self, cid):
        _check_id(cid)
        folder = self.root / "candidates" / cid
        result, spec = _load(folder / "result.json"), _load(folder / "specification.json")
        self._pipeline.validate_spec(spec, allow_reference=True)
        if result.get("candidate_id") != cid or _canonical(result.get("specification")) != _canonical(spec):
            raise ValueError("Candidate specification/ID disagreement: " + cid)
        for name, key in (("specification.json", "specification_sha256"), ("oof_predictions.csv.gz", "oof_predictions_sha256")):
            if key in result and _sha(folder / name) != result[key]:
                raise ValueError("Candidate evidence digest mismatch: " + cid)
        pd, np, train = self._pipeline.pd, self._pipeline.np, self._bench.train
        table = pd.read_csv(folder / "oof_predictions.csv.gz", float_precision="round_trip")
        for key in ("material_id", "group", "formula", "chemical_system"):
            if table[key].tolist() != train[key].tolist():
                raise ValueError("Candidate OOF alignment mismatch: " + cid + "/" + key)
        for key in ("tc", "weight"):
            if not np.array_equal(table[key].to_numpy(), train[key].to_numpy()):
                raise ValueError("Candidate OOF target/weight mismatch: " + cid)
        if not np.array_equal(table.fold.to_numpy(), self._bench.folds):
            raise ValueError("Candidate OOF fold mismatch: " + cid)
        recomputed = self._pipeline.metrics(table.tc, table.prediction, table.weight, table.group)
        def compare(actual, expected):
            if isinstance(expected, dict):
                for key, value in expected.items():
                    if key not in actual:
                        raise ValueError("Incomplete candidate metrics: " + cid)
                    compare(actual[key], value)
            elif expected is None:
                if actual is not None:
                    raise ValueError("Candidate metrics mismatch: " + cid)
            elif not math.isclose(float(actual), float(expected), rel_tol=1e-10, abs_tol=1e-10):
                raise ValueError("Candidate metrics mismatch: " + cid)
        compare(result["metrics"], recomputed)
        return result

    def _guard(self):
        shared = [(cid, self._bench._result(cid)) for cid in self.manifest["prior_candidate_ids"] if re.fullmatch(r"G\d+", cid)]
        cid, result = min(shared, key=lambda pair: (pair[1]["metrics"]["MAE_K"], pair[1]["actual_model_fits"], pair[0]))
        return {"candidate_id": cid, "MAE_K": result["metrics"]["MAE_K"],
                "positive_tc_MAE_K": result["metrics"]["subgroups"]["positive_tc"]["MAE_K"],
                "rule": "Positive-Tc OOF MAE must not exceed this same best-overall shared global anchor"}

    def known_specifications(self):
        _check_manifest(self.run_dir, self.source_dir, self.manifest)
        self._check_index()
        self._recover_pending()
        result = []
        for path in sorted((self.root / "candidates").glob("*/result.json")):
            cid = path.parent.name
            if cid not in self.manifest["prior_candidate_ids"] and "candidates/" + cid + "/result.json" not in self._index["evidence"]:
                raise ValueError("Unrecorded candidate result: " + cid)
            item = _load(path)
            result.append({"id": cid, "spec": item["specification"], "fingerprint": fingerprint(item["specification"]),
                           "metrics": _compact_metrics(item["metrics"])})
        return result

    def context(self):
        self._check_index()
        df, pipe = self._bench.train, self._pipeline
        routes = pipe.chemistry_routes(df)
        return {"feedback_scope": _SCOPE, "rows": len(df), "groups": int(df.group.nunique()),
                "reported_zero_rows": int((df.tc == 0).sum()), "positive_rows": int((df.tc > 0).sum()),
                "high_tc_ge40_rows": int((df.tc >= 40).sum()), "folds": 3,
                "composition_route_counts": {r: {"rows": int((routes == r).sum()), "groups": int(df.group[routes == r].nunique())} for r in pipe.ROUTES["chemistry"]},
                "menu": {"inputs": list(pipe.INPUTS), "routing": ["global", "chemistry", "kmeans3"], "models": list(pipe.MODELS),
                         "targets": list(pipe.TARGETS), "route_keys": pipe.ROUTES, "minimum_expert_rows": 80, "minimum_expert_groups": 12},
                "guard": self._guard(), "baseline_G01": self._compact(self._bench._result("G01"), reused=True, reused_from="G01", actual_new=0),
                "known_specifications": self.known_specifications(),
                "interpretation": "All metrics are adaptively reused training OOF. Improvements here need a separately designed future evaluation.",
                "routing_caveat": "Composition partitions are operational rules, not verified physical families. KMeans centroid-ordered cluster identities may shift between folds."}

    def _compact(self, result, *, reused=None, reused_from=None, actual_new=None):
        guard = self._guard()
        if reused is None:
            reused = bool(result.get("adapter_reused", False))
        if actual_new is None:
            actual_new = int(result.get("actual_new_regressor_fits", result["actual_model_fits"]))
        return {"candidate_id": result["candidate_id"], "spec": result["specification"], "fingerprint": fingerprint(result["specification"]),
                "feedback_scope": _SCOPE, "metrics": _compact_metrics(result["metrics"]), "reused": reused,
                "reused_from": reused_from if reused_from is not None else result.get("reused_from"),
                "proposal_was_duplicate": bool(result.get("adapter_reused", False)),
                "candidate_total_regressor_fits": int(result.get("candidate_total_regressor_fits", result["actual_model_fits"])),
                "actual_new_regressor_fits": actual_new, "elapsed_seconds": result["elapsed_seconds"],
                "positive_guard_pass": result["metrics"]["subgroups"]["positive_tc"]["MAE_K"] <= guard["positive_tc_MAE_K"] + 1e-12,
                "positive_guard_anchor": guard["candidate_id"], "evidence_directory": "workbench/candidates/" + result["candidate_id"]}

    def evaluate(self, candidate_id, spec):
        _check_id(candidate_id)
        if re.fullmatch(r"[GDR]\d+", candidate_id):
            raise ValueError("Benchmark IDs are reserved")
        spec = self._pipeline.validate_spec(spec)
        _check_manifest(self.run_dir, self.source_dir, self.manifest)
        self._check_index()
        pending = self._index["pending"].get(candidate_id)
        if pending is not None and pending["fingerprint"] != fingerprint(spec):
            raise ValueError("Candidate ID has another pending specification")
        known = self.known_specifications()
        existing = next((item for item in known if item["id"] == candidate_id), None)
        if existing is not None:
            if existing["fingerprint"] != fingerprint(spec):
                raise ValueError("Candidate ID already used for another specification")
            result = self._verify_candidate(candidate_id)
            return self._compact(result, reused=True, reused_from=candidate_id, actual_new=0)
        match = next((item for item in known if item["fingerprint"] == fingerprint(spec)), None)
        folder = self.root / "candidates" / candidate_id
        self._index["pending"][candidate_id] = {"spec": spec, "fingerprint": fingerprint(spec),
                                                "started_utc": datetime.now(timezone.utc).isoformat()}
        _save(self.index_path, self._index)
        if match is not None:
            original = self._verify_candidate(match["id"])
            folder.mkdir(parents=True, exist_ok=True)
            for name in ("specification.json", "oof_predictions.csv.gz"):
                shutil.copyfile(self.root / "candidates" / match["id"] / name, folder / name)
            result = dict(original)
            result.update(candidate_id=candidate_id, adapter_reused=True, reused_from=match["id"],
                          original_regressor_fits=original["actual_model_fits"], actual_model_fits=0,
                          actual_new_regressor_fits=0, candidate_total_regressor_fits=0,
                          elapsed_seconds=0., completed_utc=datetime.now(timezone.utc).isoformat())
            _save(folder / "result.json", result)
        else:
            result = self._bench.run_strategy(candidate_id, spec)
            result.update(adapter_reused=False, reused_from=None, actual_new_regressor_fits=result["actual_model_fits"],
                          candidate_total_regressor_fits=result["actual_model_fits"])
            _save(folder / "result.json", result)
        self._verify_candidate(candidate_id)
        self._commit_evidence(candidate_id)
        return self._compact(result)

    def counterexamples(self, cid, k=3):
        _check_id(cid)
        if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= 10:
            raise ValueError("k must be an integer from 1 to 10")
        known_ids = {item["id"] for item in self.known_specifications()}
        if cid not in known_ids:
            raise ValueError("Unknown completed candidate")
        self._verify_candidate(cid)
        result = self._bench.counterexamples(cid, k)
        keys = ("material_id", "formula", "chemical_system", "tc", "prediction", "absolute_error_K", "signed_error_K", "route", "used_model", "fold")
        return {"scope": _SCOPE, "candidate_id": cid,
                "examples": {name: [{key: row[key] for key in keys if key in row} for row in rows] for name, rows in result["examples"].items()},
                "route_metrics": {name: _compact_metrics(item) for name, item in result["route_metrics"].items()}}
