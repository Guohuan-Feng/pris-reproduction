"""Post hoc representation checks on five deterministic TRAIN structures only.

This is independent of model fitting and selection. It must run after the
discovery invocation has completed and the final selection is frozen.
"""
from __future__ import annotations

import ast
import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import numpy as np
from pymatgen.analysis.molecule_structure_comparator import CovalentRadius
from pymatgen.core import Lattice, Structure

ROOT = Path(__file__).resolve().parent
SEED = "representation-audit-20260930-v1"
TOLERANCE = 1e-8


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_structure_helper():
    """Compile only the pure existing helper, without its module-level reads."""
    path = ROOT / "data_prepare.py"
    source = path.read_text(encoding="utf-8")
    node = next(n for n in ast.parse(source).body
                if isinstance(n, ast.FunctionDef) and n.name == "structural_record")
    namespace = {"np": np, "CovalentRadius": CovalentRadius}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    text = ast.get_source_segment(source, node)
    return namespace["structural_record"], hashlib.sha256(text.encode()).hexdigest()


def variants(original):
    s = Structure(Lattice(original["lattice"]), original["symbols"], original["frac_coords"])
    yield "regenerated_original", s.copy(), {"purpose": "Original-input reconstruction control"}
    yield "site_permutation", Structure.from_sites(list(reversed(s.sites))), {"permutation": list(reversed(range(len(s))))}
    translated = s.copy()
    shift = [.137, .271, .419]
    translated.translate_sites(range(len(s)), shift, frac_coords=True, to_unit_cell=True)
    yield "fractional_origin_translation", translated, {"fractional_shift": shift, "wrap_to_unit_cell": True}
    axis = np.array([1., 2., 3.]); axis /= np.linalg.norm(axis)
    angle = .713
    cross = np.array([[0., -axis[2], axis[1]], [axis[2], 0., -axis[0]], [-axis[1], axis[0], 0.]])
    rotation = np.eye(3) * np.cos(angle) + (1-np.cos(angle))*np.outer(axis, axis) + np.sin(angle)*cross
    assert np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-14)
    rotated = Structure(Lattice(s.lattice.matrix @ rotation.T), s.species, s.frac_coords)
    yield "cartesian_rigid_rotation", rotated, {"rotation_matrix": rotation.tolist(), "row_vector_map": "cartesian @ rotation.T"}
    replicated = s.copy(); replicated.make_supercell([2, 1, 1])
    yield "twofold_supercell", replicated, {"supercell_matrix": [[2, 0, 0], [0, 1, 0], [0, 0, 1]]}


def main():
    invocation = ROOT / "agent/recovered/invocation.json"
    selection = ROOT / "evaluation/selection.json"
    if not load(invocation).get("completed"):
        raise RuntimeError("Wait until discovery is complete; no live-agent feedback is permitted")
    if not selection.exists():
        raise RuntimeError("Wait until selection is frozen before this post hoc audit")
    # Read identities and roles only; no energy/target or test-structure file is read.
    split_file = ROOT / "data/split_assignments.csv"
    with split_file.open(newline="", encoding="utf-8") as stream:
        train = [row["material_id"] for row in csv.DictReader(stream) if row["split"] == "train"]
    selected_ids = sorted(train, key=lambda mid: (hashlib.sha256((SEED + mid).encode()).hexdigest(), mid))[:5]
    assert len(selected_ids) == 5 and len(set(selected_ids)) == 5
    selected_set = set(selected_ids)
    source_records = {}
    descriptor_source = ROOT / "data/descriptor_development.jsonl.gz"
    with gzip.open(descriptor_source, "rt", encoding="utf-8") as stream:
        for line in stream:
            r = json.loads(line)
            if r["material_id"] in selected_set:
                assert r["material_id"] not in source_records
                source_records[r["material_id"]] = r
    assert set(source_records) == selected_set

    helper, helper_sha = load_structure_helper()
    spec = importlib.util.spec_from_file_location("frozen_runtime", ROOT / "descriptor_runtime.py")
    runtime = importlib.util.module_from_spec(spec); spec.loader.exec_module(runtime)
    inputs = {}; transformation_metadata = []
    for mid in selected_ids:
        original = source_records[mid]
        inputs[mid] = {"original": original}
        for name, structure, details in variants(original):
            transformed, _, _ = helper(mid, structure)
            inputs[mid][name] = transformed
            transformation_metadata.append({
                "material_id": mid, "transformation": name,
                "original_sites": original["n_sites"], "transformed_sites": transformed["n_sites"],
                "original_volume_A3": original["volume"], "transformed_volume_A3": transformed["volume"],
                "original_neighbor_edges": len(original["neighbor_distance"]),
                "transformed_neighbor_edges": len(transformed["neighbor_distance"]), **details,
            })

    comparisons = []; experiments = []; errors = []
    for folder in sorted((ROOT / "experiments").iterdir()):
        specification = folder / "specification.json"
        if not folder.is_dir() or not specification.exists():
            continue
        info = load(specification)
        if info.get("status") != "complete":
            continue
        code_path = folder / "descriptor.py"
        assert sha(code_path) == info["code_sha"], "Frozen descriptor source hash mismatch"
        code = code_path.read_text(encoding="utf-8")
        experiments.append({"id": info["id"], "name": info["name"], "code_sha256": sha(code_path),
                            "descriptor_names": info["descriptor_names"]})
        for mid in selected_ids:
            values = {}
            for transform, r in inputs[mid].items():
                try:
                    result = runtime.compute(code, [r])
                    assert result["descriptor_names"] == info["descriptor_names"]
                    values[transform] = result["rows"][0]
                except Exception as exc:
                    errors.append({"experiment": info["id"], "material_id": mid,
                                   "transformation": transform, "error": f"{type(exc).__name__}: {exc}"})
            if "original" not in values:
                continue
            for transform, transformed in values.items():
                if transform == "original":
                    continue
                for descriptor in info["descriptor_names"]:
                    baseline = values["original"][descriptor]
                    altered = transformed[descriptor]
                    both_missing = baseline is None and altered is None
                    finite_pair = baseline is not None and altered is not None
                    agrees = bool(np.isclose(altered, baseline, atol=TOLERANCE, rtol=TOLERANCE)) if finite_pair else None
                    comparisons.append({"experiment": info["id"], "material_id": mid,
                                        "transformation": transform, "descriptor": descriptor,
                                        "original_value": baseline, "transformed_value": altered,
                                        "finite_pair": finite_pair, "both_missing": both_missing,
                                        "agrees_at_tolerance": agrees,
                                        "missingness_changed": not finite_pair and not both_missing,
                                        "absolute_difference": abs(altered-baseline) if finite_pair else None,
                                        "allowed_difference": TOLERANCE + TOLERANCE*abs(baseline) if finite_pair else None})
    assert experiments, "No completed descriptor experiments found"
    failures = [r for r in comparisons if r["agrees_at_tolerance"] is False or r["missingness_changed"]]
    grouped = []
    for experiment in experiments:
        for descriptor in experiment["descriptor_names"]:
            rows = [r for r in comparisons if r["experiment"] == experiment["id"] and r["descriptor"] == descriptor]
            bad = [r for r in rows if r["agrees_at_tolerance"] is False or r["missingness_changed"]]
            grouped.append({"experiment": experiment["id"], "descriptor": descriptor,
                            "finite_comparisons": sum(r["finite_pair"] for r in rows),
                            "both_missing_comparisons": sum(r["both_missing"] for r in rows),
                            "failed_comparisons": len(bad),
                            "failed_transformations": sorted({r["transformation"] for r in bad}),
                            "largest_absolute_difference": max((r["absolute_difference"] for r in rows if r["absolute_difference"] is not None), default=None)})
    result = {
        "scope": "Post hoc five-TRAIN-structure representation audit; not fed to discovery or selection.",
        "selection_seed": SEED, "selection_rule": "First five TRAIN IDs by SHA256(seed + material_id), then ID.",
        "material_ids": selected_ids, "atol": TOLERANCE, "rtol": TOLERANCE,
        "neighbor_cutoff_A": 6.0, "neighbor_numerical_tolerance_A": 1e-8,
        "helper_policy": "Exact structural_record AST from frozen data_prepare.py; module top-level code was not executed.",
        "helper_function_sha256": helper_sha,
        "source_hashes": {str(p.relative_to(ROOT)): sha(p) for p in [split_file, descriptor_source, invocation, selection, ROOT/"data_prepare.py", ROOT/"descriptor_runtime.py", Path(__file__)]},
        "experiments": experiments, "transformations": transformation_metadata,
        "summary": {"completed_experiments": len(experiments), "descriptor_columns": len(grouped),
                    "comparisons": len(comparisons), "finite_comparisons": sum(r["finite_pair"] for r in comparisons),
                    "failed_comparisons": len(failures), "execution_errors": len(errors)},
        "per_descriptor": grouped, "failures": failures, "execution_errors": errors,
        "interpretation": [
            "Five examples and four transformations do not prove universal invariance.",
            "The regenerated-original control checks input reconstruction, not a distinct invariance.",
            "Cell-vector length anisotropy is expected to change when one lattice vector is doubled, despite equivalent infinite crystal geometry.",
            "Cell angles can pass these tests while remaining sensitive to a general change of lattice basis, which is not tested here.",
            "Near-zero variance summaries can differ because of cancellation and rounding; inspect magnitudes before attributing a physical change.",
            "A fixed 6 A neighbor cutoff can produce numerical edge-membership changes at its boundary.",
            "This audit does not read target values or establish predictive, causal or mechanistic benefit.",
        ],
    }
    output = ROOT / "check_representation_results.json"
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with (ROOT / "check_representation_comparisons.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(comparisons[0])); writer.writeheader(); writer.writerows(comparisons)
    print(json.dumps({"summary": result["summary"], "nonagreeing_descriptors": [r for r in grouped if r["failed_comparisons"]]}, indent=2))


if __name__ == "__main__":
    main()
