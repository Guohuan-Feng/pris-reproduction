"""M0: current-parser old42/E011 numerical matching control.

No data read or fitting occurs on import. Parent source, input parsing, model
parameters, saved folds and existing results are never changed here. Only the
explicit evaluate entry point fits; it is owned by the separately registered
M0 Agent cycle and requires two immutable receipts.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

EXTENSION_ROOT = Path(__file__).resolve().parent
PARENT_ROOT = EXTENSION_ROOT.parents[1]
CANDIDATE_ID = "M0"
SPEC = {"estimator": "e011_tree", "feature_set": "old42"}
EXPECTED_FITS = 15
PARENT_SOURCES = ("backend.py", "science_server.py", "run_session.py", "controller.py", "descriptor_runtime.py", "pilot_evaluation.py")
PARENT_FITS = {"P1": 15, "P2": 15, "P3": 3, "P4": 3}
STANDARD_OUTPUTS = ("result.json", "validation_predictions.csv.gz", "internal_oof_predictions.csv.gz", "folds.json", "base_fit_events.jsonl")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda: stream.read(1024*1024), b""):
            h.update(part)
    return h.hexdigest()


def json_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _array_sha(values):
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes(order="C")).hexdigest()


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _relative(root, path):
    path = Path(path).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("artifact escapes its registered parent boundary")
    return path.relative_to(root.resolve()).as_posix()


def collect_parent_provenance(parent_root, expected_protocol_sha256, *, require_four_complete=True):
    """Hash parent artifacts only, with protocol binding; never instantiate Context."""
    root = Path(parent_root).resolve()
    protocol_path = root / "protocol.json"
    if sha(protocol_path) != expected_protocol_sha256:
        raise ValueError("parent protocol changed")
    protocol = _read(protocol_path)
    if set(protocol["source_hashes"]) != set(PARENT_SOURCES):
        raise ValueError("parent six-source freeze set differs")
    source_hashes = {name: sha(root/name) for name in PARENT_SOURCES}
    if source_hashes != protocol["source_hashes"]:
        raise ValueError("parent scientific source changed")
    input_hashes = []
    for name, expected in protocol["input_hashes"].items():
        path = Path(name).resolve()
        # Original input manifest is SHA-bound; still refuse out-of-work paths.
        relative = _relative(root.parent, path)
        actual = sha(path)
        if actual != expected:
            raise ValueError("parent input changed")
        input_hashes.append({"work_relative_path": relative, "sha256": actual})
    state = _read(root/"state/research_state.json")
    if state["protocol_sha256"] != expected_protocol_sha256:
        raise ValueError("parent state protocol binding differs")
    if state.get("active_operation"):
        raise ValueError("parent scientific operation is active")
    registration = root / "registration.json"
    if sha(registration) != state["registered_plan"]["sha256"]:
        raise ValueError("parent registration changed")
    descriptor = {}
    for name, expected in state["descriptor"]["frozen_files"].items():
        path = (root/name).resolve()
        relative = _relative(root,path)
        if sha(path) != expected:
            raise ValueError("parent approved descriptor artifact changed")
        descriptor[relative] = expected
    results = {}
    for candidate, expected_fits in PARENT_FITS.items():
        item = state.get("experiments",{}).get(candidate)
        if not item or item.get("status") != "complete":
            if require_four_complete:
                raise ValueError("M0 requires all original four experiments complete")
            continue
        directory = root/"experiments"/candidate
        result = _read(directory/"result.json")
        if result["id"] != candidate or result["learner_fits"] != expected_fits or result["fit_started"] != expected_fits or result["fit_completed"] != expected_fits:
            raise ValueError("parent completed experiment fit count is inconsistent")
        files = {name: sha(directory/name) for name in STANDARD_OUTPUTS}
        for name, actual in files.items():
            if item["files"][name]["sha256"] != actual:
                raise ValueError("parent result artifact changed")
        results[candidate] = {"spec": result["spec"], "learner_fits": expected_fits, "files": files}
    counters = state["counters"]
    if require_four_complete and (set(results) != set(PARENT_FITS) or any(counters[name] != 36 for name in ("base_fits_reserved","fit_started","fit_completed")) or counters["experiments"] != 4):
        raise ValueError("original four-stage learner ledger is not exactly36 complete")
    receipt = {
        "schema_version": 1,
        "parent_protocol_sha256": expected_protocol_sha256,
        "parent_source_hashes": source_hashes,
        "parent_registration_sha256": sha(registration),
        "parent_descriptor_artifact_hashes": descriptor,
        "parent_input_hashes": sorted(input_hashes,key=lambda item:item["work_relative_path"]),
        "parent_results": results,
        "parent_learner_counts": {name: counters[name] for name in ("base_fits_reserved","fit_started","fit_completed","experiments")},
        "require_four_complete": require_four_complete,
        "current_csv_semantics": "Unmodified backend.Context pandas.read_csv default for original30/E04/targets and augmented descriptor; no round_trip override",
        "scope": "Existing development only; numerical matching control, not a new feature or residual correction",
    }
    receipt["receipt_sha256"] = json_sha(receipt)
    return receipt


def _checked_frame(ctx):
    """Use precisely the parent Context/augmented flow, then select old42 in evaluator."""
    frame = ctx.augmented()
    if len(ctx.ev.old_columns) != 42 or (len(ctx.X),len(ctx.train),len(ctx.val)) != (2879,2164,715):
        raise ValueError("M0 requires the fixed2879 development row boundary and old42")
    if not frame.index.equals(ctx.X.index) or not frame.loc[:,ctx.ev.old_columns].equals(ctx.X.loc[:,ctx.ev.old_columns]):
        raise ValueError("augmented frame changes old42 values/order or dtype")
    if not np.isfinite(frame.loc[:,ctx.ev.old_columns].to_numpy(float)).all():
        raise ValueError("M0 old42 contains nonfinite values")
    if not ctx.y.index.equals(ctx.X.index) or not ctx.meta.index.equals(ctx.X.index):
        raise ValueError("M0 target/metadata ID order differs")
    return frame


def preflight(ctx):
    """No fit; receipt is stable and must be frozen before evaluate is enabled."""
    frame = _checked_frame(ctx)
    spec = ctx.ev.validate_spec(deepcopy(SPEC))
    reservation = ctx.ev.estimate_learner_fits(frame,ctx.meta,spec,ctx.train,ctx.val,ctx.folds)
    if reservation["total_learner_fits"] != EXPECTED_FITS or reservation.get("fitting_performed") is not False:
        raise ValueError("M0 no-fit reservation differs from15")
    ids = ctx.X.index.astype(str).tolist()
    train_ids = ctx.X.index[ctx.train]
    folds = [[str(mid),int(fold)] for mid,fold in ctx.folds.loc[train_ids].items()]
    receipt = {
        "schema_version": 1,
        "id": CANDIDATE_ID,
        "spec": spec,
        "new_descriptor": False,
        "P5_residual_adjustment": False,
        "fitting_performed": False,
        "adapter_source_sha256": sha(__file__),
        "rows": {"train":2164,"validation":715,"total":2879},
        "expected_new_learner_fits": EXPECTED_FITS,
        "fit_reservation": reservation,
        "ordered_material_ids_sha256": json_sha(ids),
        "old42_columns": list(ctx.ev.old_columns),
        "old42_float64_le_sha256": _array_sha(ctx.X.loc[:,ctx.ev.old_columns].to_numpy(float)),
        "targets_float64_le_sha256": _array_sha(ctx.y.to_numpy(float)),
        "metadata_sha256": json_sha(ctx.meta.astype(str).to_dict(orient="split")),
        "fixed_outer_fold_id_sha256": json_sha(folds),
        "e011_tree_spec_sha256": json_sha(ctx.ev.e011_spec),
        "legacy_evaluation_sha256": ctx.ev.legacy_sha256,
        "read_semantics": "Same parent Context defaultCSV including target parsing; no parser substitution, new random seed or fold generation",
        "scope": "M0 numerical matching control for existing development, not independent confirmation",
    }
    receipt["receipt_sha256"] = json_sha(receipt)
    return receipt


def _receipt_valid(receipt):
    copy = deepcopy(receipt)
    value = copy.pop("receipt_sha256",None)
    return value is not None and value == json_sha(copy)


def evaluate(ctx, *, expected_preflight, parent_provenance, event_callback=None):
    """Explicit science entry point; root's independently registered Agent owns it."""
    if not _receipt_valid(expected_preflight) or not _receipt_valid(parent_provenance) or not parent_provenance["require_four_complete"]:
        raise ValueError("M0 requires complete immutable preflight/parent receipts")
    current = preflight(ctx)
    if current != expected_preflight:
        raise ValueError("M0 context/source changed since pre-fit registration")
    actual_parent = collect_parent_provenance(PARENT_ROOT,parent_provenance["parent_protocol_sha256"],require_four_complete=True)
    if actual_parent != parent_provenance:
        raise ValueError("M0 parent provenance changed since registration")
    frame = _checked_frame(ctx)
    forwarded = []
    def relay(event):
        forwarded.append(deepcopy(event))
        if event_callback is not None:
            event_callback(event)
    bundle = ctx.ev.evaluate(frame,ctx.y,ctx.meta,deepcopy(SPEC),ctx.train,ctx.val,ctx.folds,relay)
    result = bundle["result"]
    if result["spec"] != SPEC or any(result[name] != EXPECTED_FITS for name in ("learner_fits","fit_started","fit_completed")):
        raise RuntimeError("M0 result differs from fixed spec or15 actual fits")
    if sum(event["phase"]=="started" for event in forwarded) != EXPECTED_FITS or sum(event["phase"]=="completed" for event in forwarded) != EXPECTED_FITS:
        raise RuntimeError("M0 component fit events are not15/15")
    if result["fixed_fold_id_sha256"] != current["fixed_outer_fold_id_sha256"]:
        # Both modules use the same canonical sorted-key JSON encoding.
        raise RuntimeError("M0 evaluation folds differ from preflight")
    result.update(id=CANDIDATE_ID,experiment_kind="current_parser_numerical_matching_control",new_descriptor=False,P5_residual_adjustment=False,scope="Previously observed development; old42/E011 under current parent defaultCSV, not independent confirmation",adapter_source_sha256=current["adapter_source_sha256"],M0_preflight_sha256=current["receipt_sha256"],parent_provenance_sha256=parent_provenance["receipt_sha256"])
    bundle["adapter_provenance"] = {"schema_version":1,"candidate_id":CANDIDATE_ID,"preflight":current,"parent_provenance":parent_provenance,"interpretation":"Compare P1/P2 against M0 to isolate added angular features; M0/P2 × P3/P4 forms matched-parser model×old42/new58. Cached historical E011 has different parsing semantics; do not attribute its change to new features."}
    return bundle


def _parent_saver():
    """Load exactly the frozen parent's artifact writer; no Context/data/fits."""
    path = PARENT_ROOT/"pilot_evaluation.py"
    name = "_m0_frozen_parent_pilot_evaluation"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name,path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name].save_evaluation


def save(bundle, output_dir, *, saver=None):
    """Save standard result bundle + receipts only under this extension, no overwrite."""
    directory = Path(output_dir).resolve()
    if not directory.is_relative_to(EXTENSION_ROOT.resolve()) or directory == EXTENSION_ROOT.resolve():
        raise ValueError("M0 output must stay within an extension subdirectory")
    provenance_file = directory/"adapter_provenance.json"
    if provenance_file.exists() or any((directory/name).exists() for name in STANDARD_OUTPUTS):
        raise FileExistsError("M0 saved artifacts already exist; no overwrite")
    if bundle["result"].get("id") != CANDIDATE_ID or "adapter_provenance" not in bundle:
        raise ValueError("M0 bundle missing fixed id/provenance")
    directory.mkdir(parents=True,exist_ok=True)
    with provenance_file.open("x",encoding="utf-8") as stream:
        json.dump(bundle["adapter_provenance"],stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write("\n")
    files = (saver if saver is not None else _parent_saver())(bundle,directory)
    files["adapter_provenance.json"] = {"path":str(provenance_file),"sha256":sha(provenance_file)}
    return files
