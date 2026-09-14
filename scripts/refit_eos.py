#!/usr/bin/env python3
"""Independently refit PRIS E4 equations of state from published collected energies.

This reanalysis does not run VASP or reproduce the underlying DFT calculations.
Dependencies: Python 3.10+, numpy, scipy. See ../data/eos/README.md.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import least_squares
from scipy.stats import pearsonr, spearmanr

GPA_PER_EV_A3 = 160.21766208


def bm3(volume, offset_energy, equilibrium_volume, modulus_ev_a3, derivative):
    """Third-order Birch--Murnaghan E(V), algebraically equal to source equation."""
    strain = (equilibrium_volume / volume) ** (2.0 / 3.0) - 1.0
    return offset_energy + 9.0 * equilibrium_volume * modulus_ev_a3 / 16.0 * (
        2.0 * strain**2 + (derivative - 4.0) * strain**3
    )


def fit_eos(volumes, energies):
    volumes = np.asarray(volumes, dtype=float)
    energies = np.asarray(energies, dtype=float)
    # Subtracting a constant preserves B0 and improves numerical conditioning.
    reference_energy = float(energies.min())
    shifted = energies - reference_energy
    quadratic = np.polyfit(volumes, shifted, 2)
    initial_v0 = -quadratic[1] / (2.0 * quadratic[0])
    initial = [
        np.polyval(quadratic, initial_v0),
        initial_v0,
        2.0 * quadratic[0] * initial_v0,
        4.0,
    ]
    # Independent optimizer/parameter arithmetic; do not import upstream analyze.py.
    result = least_squares(
        lambda parameters: bm3(volumes, *parameters) - shifted,
        initial,
        jac="3-point",
        x_scale="jac",
        max_nfev=20000,
        ftol=1e-12,
        xtol=1e-12,
        gtol=1e-12,
    )
    e0, v0, b0, bp = map(float, result.x)
    if not result.success or not (v0 > 0 and b0 > 0 and volumes.min() < v0 < volumes.max()):
        raise ValueError(f"unusable fit: {result.message}; parameters={result.x}")
    return {
        "refit_b0_gpa": b0 * GPA_PER_EV_A3,
        "refit_v0_a3": v0,
        "refit_bp": bp,
        "refit_e0_ev": e0 + reference_energy,
        "refit_rms_ev": float(np.sqrt(np.mean(result.fun**2))),
        "optimizer_nfev": result.nfev,
    }


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=root / "data" / "eos")
    parser.add_argument("--output-dir", type=Path, default=root / "results" / "eos")
    arguments = parser.parse_args()
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    collected_path = arguments.input_dir / "stage_b_collected.json"
    published_path = arguments.input_dir / "published_bulk_moduli.json"
    collected = read_json(collected_path)
    published = {row["parent_task"]: row for row in read_json(published_path)}
    candidates = defaultdict(list)
    excluded = []
    point_rows = []
    for record in collected["records"]:
        if record["status"] not in ("complete", "unconverged"):
            excluded.append({"task": record["task"], "reason": record.get("status_reason", record["status"])})
            continue
        candidates[record["parent_task"]].append(record)

    results = []
    for parent, records in sorted(candidates.items()):
        points = []
        for record in records:
            stages = record["stage_results"]
            static = stages.get("static", {})
            cell = static.get("final_cell") or stages.get("relax_ions", {}).get("final_cell")
            # Match the paper's final *static* energy, not relaxation energy or TOTEN.
            if static.get("energy_last_ev") is None or not cell:
                excluded.append({"task": record["task"], "reason": "missing final static energy or cell"})
                continue
            volume, energy = float(cell["volume_a3"]), float(static["energy_last_ev"])
            points.append((volume, energy))
            point_rows.append({"parent_task": parent, "candidate_id": record["candidate_id"],
                               "task": record["task"], "status": record["status"],
                               "volume_a3": volume, "static_energy_ev": energy})
        if len(points) < 4:
            excluded.append({"task": parent, "reason": f"only {len(points)} usable volume points"})
            continue
        points.sort()
        try:
            fitted = fit_eos(*zip(*points))
        except ValueError as error:
            excluded.append({"task": parent, "reason": str(error)})
            continue
        reference = published[parent]
        error = fitted["refit_b0_gpa"] - float(reference["dft_bulk_modulus_gpa"])
        results.append({"parent_task": parent, "candidate_id": records[0]["candidate_id"],
                        "formula": records[0]["formula"], "role": records[0]["role"],
                        "n_points": len(points), **fitted,
                        "published_b0_gpa": float(reference["dft_bulk_modulus_gpa"]),
                        "signed_error_gpa": error, "absolute_error_gpa": abs(error),
                        "relative_error": abs(error) / abs(float(reference["dft_bulk_modulus_gpa"])),
                        "published_v0_a3": float(reference["v0_a3"]),
                        "published_bp": float(reference["bp"]),
                        "published_rms_ev": float(reference["fit_rms_ev"]),
                        "uma_bulk_modulus_gpa": float(records[0]["uma_bulk_modulus_gpa"]),
                        "pss": float(records[0]["pss"])})
    if not results:
        raise RuntimeError("No successful fits")

    modulus = np.array([row["refit_b0_gpa"] for row in results])
    proxy = np.array([row["uma_bulk_modulus_gpa"] for row in results])
    absolute = np.array([row["absolute_error_gpa"] for row in results])
    relative = np.array([row["relative_error"] for row in results])
    bias = float(np.median(modulus / proxy))
    mapped_threshold = 400.0 * bias
    priority = [row for row in results if row["role"] == "priority"]
    screened = [row for row in results if row["role"] == "screened"]
    retained = [row for row in results if row["role"] != "screened"]
    retained_high = sum(row["refit_b0_gpa"] >= mapped_threshold for row in retained)
    screened_high = sum(row["refit_b0_gpa"] >= mapped_threshold for row in screened)
    ranking_accuracy = float(np.mean([
        (a["refit_b0_gpa"] > b["refit_b0_gpa"]) + 0.5 * (a["refit_b0_gpa"] == b["refit_b0_gpa"])
        for a in priority for b in screened
    ]))
    summary = {
        "scope": "Independent numerical reanalysis of published collected DFT energies; no new VASP/DFT calculations.",
        "source_url": "https://github.com/AI4QC/PRIS",
        "source_commit": "34e6c86c083759dc1ee594ae22238ea9b5ebd8f4",
        "selection": "Retain complete and unconverged records; final static energy; static final_cell or relaxation final_cell; >=4 volume points; positive modulus and fitted V0 inside sampled interval.",
        "optimizer": "scipy.optimize.least_squares, independent algebraically equivalent BM3, centered energy, 3-point numerical Jacobian, tolerances 1e-12",
        "input_records": len(collected["records"]),
        "input_status_counts": dict(Counter(row["status"] for row in collected["records"])),
        "used_volume_points": len(point_rows),
        "fitted_candidates": len(results),
        "published_candidates": len(published),
        "published_candidates_missing_from_refit": sorted(set(published) - {row["parent_task"] for row in results}),
        "fit_point_count_distribution": dict(Counter(row["n_points"] for row in results)),
        "role_counts": dict(Counter(row["role"] for row in results)),
        "b0_absolute_error_gpa_median": float(np.median(absolute)),
        "b0_absolute_error_gpa_max": float(absolute.max()),
        "b0_relative_error_median": float(np.median(relative)),
        "b0_relative_error_max": float(relative.max()),
        "largest_discrepancy_candidate": results[int(np.argmax(absolute))]["candidate_id"],
        "all_b0_within_0_01_gpa": bool(np.all(absolute <= 0.01)),
        "max_refit_rms_ev": max(row["refit_rms_ev"] for row in results),
        "refit_b0_median_gpa": float(np.median(modulus)),
        "refit_b0_max_gpa": float(modulus.max()),
        "proxy_dft_pearson": float(pearsonr(proxy, modulus).statistic),
        "proxy_dft_spearman": float(spearmanr(proxy, modulus).statistic),
        "median_dft_to_uma_ratio": bias,
        "mapped_dft_threshold_gpa": mapped_threshold,
        "at_or_above_original_400_gpa": {role: sum(row["refit_b0_gpa"] >= 400 for row in results if row["role"] == role) for role in ("priority", "screened", "control")},
        "at_or_above_mapped_threshold": {"retained": retained_high, "screened": screened_high,
                                         "retention_fraction": retained_high / (retained_high + screened_high)},
        "priority_vs_screened_pairwise_ranking_accuracy": ranking_accuracy,
        "sampling_limit": "E4 deliberately oversamples high UMA bulk moduli. These 260-candidate proportions cannot be extrapolated to the full 1081-candidate generation pool.",
        "excluded_records": excluded,
        "software": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "input_sha256": {collected_path.name: sha256(collected_path), published_path.name: sha256(published_path)},
        "script_sha256": sha256(Path(__file__)),
    }
    write_csv(arguments.output_dir / "per_candidate.csv", results)
    write_csv(arguments.output_dir / "energy_volume_points.csv", point_rows)
    (arguments.output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in (
        "input_records", "used_volume_points", "fitted_candidates", "b0_absolute_error_gpa_max",
        "b0_absolute_error_gpa_median", "b0_relative_error_max", "all_b0_within_0_01_gpa",
        "proxy_dft_pearson", "median_dft_to_uma_ratio", "at_or_above_original_400_gpa",
        "at_or_above_mapped_threshold")}, indent=2))


if __name__ == "__main__":
    main()
