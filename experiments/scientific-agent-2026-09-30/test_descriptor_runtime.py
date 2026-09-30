"""Synthetic, label-free checks of the descriptor interface, not a security proof."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from pymatgen.core import Lattice, Structure

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("runtime_under_test", ROOT / "descriptor_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def record(structure, mid):
    centers, indices, images, distances = structure.get_neighbor_list(6.0)
    matrix = structure.distance_matrix.copy()
    np.fill_diagonal(matrix, min(np.linalg.norm(structure.lattice.matrix, axis=1)))
    return {
        "material_id": mid,
        "symbols": [site.specie.symbol for site in structure],
        "atomic_numbers": [site.specie.Z for site in structure],
        "electronegativities": [float(site.specie.X) for site in structure],
        "covalent_radii": [1.0 for site in structure],
        "n_sites": len(structure), "volume": float(structure.volume),
        "lattice": structure.lattice.matrix.tolist(),
        "frac_coords": structure.frac_coords.tolist(),
        "distance_matrix": matrix.tolist(),
        "neighbor_center": centers.tolist(), "neighbor_index": indices.tolist(),
        "neighbor_image": images.tolist(), "neighbor_distance": distances.tolist(),
        # Deliberately supplied canaries: compute must exclude both from featurize(s).
        "formation_energy_per_atom": 123456.0, "split": "sealed-canary",
    }


def main():
    checks = []

    def check(name, fn):
        started = time.monotonic()
        try:
            detail = fn()
            checks.append({"name": name, "passed": True, "detail": detail,
                           "seconds": time.monotonic() - started})
        except Exception as exc:
            checks.append({"name": name, "passed": False,
                           "detail": f"{type(exc).__name__}: {exc}",
                           "seconds": time.monotonic() - started})

    base = Structure(Lattice.cubic(5.64), ["Na", "Cl"], [[0, 0, 0], [.5, .5, .5]])
    base_record = record(base, "synthetic-base")
    invariant_code = '''def featurize(s):
    z = np.array(s["atomic_numbers"], dtype=float)
    d = np.array(s["neighbor_distance"], dtype=float)
    centers = np.array(s["neighbor_center"], dtype=int)
    cn = np.bincount(centers, weights=np.array(d < 5.0, dtype=float), minlength=len(z))
    return {"mean_z": np.mean(z), "mean_cn": np.mean(cn), "neighbor_mean": np.mean(d), "volume_per_site": s["volume"] / len(z)}
'''

    def invariant(kind):
        if kind == "site_permutation":
            alternate = Structure.from_sites([base[1], base[0]])
        elif kind == "fractional_translation":
            alternate = base.copy()
            alternate.translate_sites(range(len(alternate)), [.137, .239, .347], frac_coords=True, to_unit_cell=True)
        elif kind == "cell_replication":
            alternate = base.copy()
            alternate.make_supercell([2, 1, 1])
        elif kind == "rigid_rotation":
            rotation = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
            alternate = Structure(Lattice(base.lattice.matrix @ rotation), base.species, base.frac_coords)
        result = runtime.compute(invariant_code, [base_record, record(alternate, "synthetic-variant")])
        left, right = result["rows"]
        for name in result["descriptor_names"]:
            assert np.isclose(left[name], right[name], atol=1e-9, rtol=1e-9), (name, left[name], right[name])
        return "Known invariant descriptor agrees within atol=rtol=1e-9."

    for kind in ["site_permutation", "fractional_translation", "cell_replication", "rigid_rotation"]:
        check(kind, lambda kind=kind: invariant(kind))

    def reject(code):
        try:
            runtime.compute(code, [base_record])
        except (ValueError, TypeError, KeyError, NameError):
            return "Rejected."
        raise AssertionError("Expected rejection, but code executed successfully")

    bad = {
        "import": 'def featurize(s):\n    import os\n    return {"x": 1}',
        "file_open": 'def featurize(s):\n    return {"x": open("missing.txt")}',
        "numpy_file_function": 'def featurize(s):\n    return {"x": np.load("missing.npy")}',
        "private_reflection": 'def featurize(s):\n    return {"x": s.__class__}',
        "indirect_call": 'def featurize(s):\n    return {"x": s["callable"]()}',
        "while_loop": 'def featurize(s):\n    while True:\n        pass\n    return {"x": 1}',
        "nested_function": 'def featurize(s):\n    def nested():\n        return 1\n    return {"x": 1}',
        "too_many_outputs": 'def featurize(s):\n    return {str(i): i for i in range(13)}',
        "array_output": 'def featurize(s):\n    return {"x": [1, 2]}',
        "infinite_output": 'def featurize(s):\n    return {"x": np.inf}',
        "identity_collision": 'def featurize(s):\n    return {"material_id": 1}',
        "numeric_namespace_mutation": 'def featurize(s):\n    np.pi = np.pi + 1\n    return {"x": np.pi}',
    }
    # Avoid relying on an unavailable str builtin for the width test.
    bad["too_many_outputs"] = 'def featurize(s):\n    return {' + ','.join(f'"f{i}": {i}' for i in range(13)) + '}'
    for name, code in bad.items():
        check(name, lambda code=code: reject(code))

    def label_canary():
        output = runtime.compute('def featurize(s):\n    return {"label": s.get("formation_energy_per_atom", -1), "role": s.get("split", -2), "identity": s.get("material_id", -3)}', [base_record])["rows"][0]
        assert output == {"material_id": "synthetic-base", "label": -1., "role": -2., "identity": -3.}, output
        return "Target, split and material ID are absent from the function argument."
    check("input_target_and_identity_stripping", label_canary)

    def nan_output():
        result = runtime.compute('def featurize(s):\n    return {"missing": np.nan}', [base_record])
        assert result["rows"][0]["missing"] is None
        json.dumps(result, allow_nan=False)
        return "NaN becomes JSON null; this check does not test evaluator imputation."
    check("missing_output_serialization", nan_output)

    def timeout():
        code = 'def featurize(s):\n    x = 0\n    for i in range(1000000000000):\n        x += i\n    return {"x": x}'
        try:
            subprocess.run([sys.executable, str(ROOT / "descriptor_runtime.py")],
                           input=json.dumps({"code": code, "records": [base_record]}),
                           text=True, capture_output=True, timeout=2, check=False)
        except subprocess.TimeoutExpired:
            return "Synthetic CPU loop terminated by subprocess timeout=2s."
        raise AssertionError("Loop unexpectedly completed before timeout")
    check("bounded_worker_timeout", timeout)

    report = {
        "scope": "Synthetic runtime checks only; no dataset, labels, MCP server or model calls loaded.",
        "runtime_sha256": hashlib.sha256((ROOT / "descriptor_runtime.py").read_bytes()).hexdigest(),
        "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "passed": sum(c["passed"] for c in checks), "total": len(checks), "checks": checks,
        "limitations": ["Not a hostile-code security audit or OS sandbox proof.",
                        "Invariance of one known descriptor does not establish invariance of arbitrary generated code.",
                        "Server budgeting, actual tool exposure and evaluator leakage require separate checks."],
    }
    path = ROOT / "descriptor_runtime_checks.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "total": report["total"],
                      "failed": [c for c in checks if not c["passed"]]}))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
