"""Recompute frozen PRIS rules on the 180 published E3 experimental inputs.

This is a discovery-split functional reproduction, NOT the paper's held-out
benchmark. No thresholds are fitted and no structures are silently removed.
Run: python scripts/run_structure_benchmark.py --workers 4
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import warnings

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "vendor" / "pris" / "src"
sys.path.insert(0, str(SOURCE))
for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(name, "1")
os.environ.setdefault("MPLBACKEND", "Agg")
warnings.filterwarnings("ignore")

KINDS = ("P0", "S1", "S2", "S3", "S4", "S5")
METHODS = ("Distance 0.5 A", "Distance 0.7 A", "Set 1", "Set 1'", "Set 2", "Set 3", "Set 4")


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def minimum_periodic_distance(structure):
    """Minimum interatomic distance, including nonzero periodic self-images.

    The off-diagonal distance matrix also catches distinct coincident sites.
    Searching to the shortest basis-vector length necessarily finds at least
    one periodic self-image, including for one-site primitive structures.
    """
    import numpy as np
    matrix = np.asarray(structure.distance_matrix, dtype=float).copy()
    np.fill_diagonal(matrix, np.inf)
    nearest_distinct = float(matrix.min())
    radius = min(structure.lattice.abc) + 1e-7
    *_, distances = structure.get_neighbor_list(radius)
    positive = distances[distances > 1e-8]
    nearest_image = float(positive.min()) if len(positive) else math.inf
    return min(nearest_distinct, nearest_image)


def evaluate(job):
    import numpy as np
    from pymatgen.core import Structure
    import pris_analyze as pa
    row, data_root = job
    started = time.perf_counter()
    path = Path(data_root) / row["structure_file"]
    result = {"task": row["task"], "parent_id": row["parent_id"],
              "cod_id": row["cod_id"], "variant": row["variant"],
              "label": row["label"], "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    try:
        structure = Structure.from_file(str(path))
        distance = minimum_periodic_distance(structure)
        analysis = pa.analyse(str(path))
        analysis["file"] = row["structure_file"]
        result.update(formula=structure.composition.reduced_formula,
                      composition=structure.composition.as_dict(), n_sites=len(structure),
                      volume_a3=float(structure.volume), density_g_cm3=float(structure.density),
                      minimum_distance_a=distance, analysis=analysis)
        verdicts = {f"Distance {cutoff} A": "plausible" if distance >= cutoff else "implausible"
                    for cutoff in (0.5, 0.7)}
        for method in pa.SET_ORDER:
            verdicts[method] = analysis.get("sets", {}).get(method, {}).get("verdict", "no verdict")
        result["verdicts"] = verdicts
        # Check the archived damage labels against the parent, rather than
        # treating TASK.json's generic kind='experimental' as a class label.
        if row["variant"] != "P0":
            parent_path = path.parent.parent / f"E3-{row['parent_id']}-P0" / "POSCAR.init"
            parent = Structure.from_file(str(parent_path))
            result["preserves_composition"] = structure.composition == parent.composition
            result["preserves_n_sites"] = len(structure) == len(parent)
            result["preserves_lattice"] = bool(np.allclose(structure.lattice.matrix, parent.lattice.matrix))
        else:
            result["preserves_composition"] = True
            result["preserves_n_sites"] = True
        result["status"] = "processed"
    except Exception as exc:
        result.update(status="error", error=f"{type(exc).__name__}: {exc}",
                      verdicts={m: "no verdict" for m in METHODS})
    result["seconds"] = time.perf_counter() - started
    return clean(result)


def write_csv(path, rows, fields=None):
    if not rows:
        return
    fields = fields or list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def summarize(records, elapsed):
    tables = []
    for method in METHODS:
        for cohort in (*KINDS, "damaged_all"):
            selected = [r for r in records if (r["variant"] != "P0" if cohort == "damaged_all"
                                                else r["variant"] == cohort)]
            counts = {v: sum(r["verdicts"].get(method, "no verdict") == v for r in selected)
                      for v in ("plausible", "implausible", "no verdict")}
            n = len(selected)
            tables.append({"method": method, "cohort": cohort, "n": n,
                           "plausible": counts["plausible"], "implausible": counts["implausible"],
                           "no_verdict": counts["no verdict"],
                           "pass_fraction_all": counts["plausible"] / n if n else None,
                           "rejection_fraction_all": counts["implausible"] / n if n else None,
                           "coverage_fraction": 1 - counts["no verdict"] / n if n else None})
    summary = {"scope": "Published E3 discovery-split functional reproduction; not held-out validation",
               "source_commit": "34e6c86c083759dc1ee594ae22238ea9b5ebd8f4",
               "n_structures": len(records), "n_parents": sum(r["variant"] == "P0" for r in records),
               "n_errors": sum(r["status"] == "error" for r in records),
               "wall_seconds": elapsed,
               "selection_warning": "E3 selects first 30 eligible discovery parents; every variant has d_min >= 0.9 A by construction. Thus 0.5/0.7 A rejection is structurally zero, not an independent performance win.",
               "missing_measurement_policy": "Upstream deployment: no verdict is separate, never counted as pass; any observed rule failure rejects a set.",
               "cell_policy": "Preserve author POSCAR.init exactly; do not silently standardize cells.",
               "composition_checks_passed": all(r.get("preserves_composition", False) and r.get("preserves_n_sites", False) for r in records),
               "metrics": tables}
    return summary, tables


def plot_metrics(tables, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    values = {(r["method"], r["cohort"]): r for r in tables}
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    x = np.arange(len(METHODS))
    colors = ["#aeb8bf", "#8c9ca8", "#8fc2c7", "#5ba7b0", "#328d98", "#176d7e", "#123f58"]
    for ax, cohort, key, title in ((axes[0], "P0", "pass_fraction_all", "Experimental parents retained (n=30)"),
                                   (axes[1], "damaged_all", "rejection_fraction_all", "Damaged inputs rejected (n=150)")):
        ys = [100 * values[(m, cohort)][key] for m in METHODS]
        ax.bar(x, ys, color=colors)
        for xi, y in zip(x, ys):
            ax.text(xi, y + 2, f"{y:.1f}%", ha="center", fontsize=9)
        ax.set_xticks(x, ["d >= 0.5 A", "d >= 0.7 A", "Set 1", "Set 1'", "Set 2", "Set 3", "Set 4"], rotation=40, ha="right")
        ax.set_ylim(0, 112)
        ax.set_yticks(range(0, 101, 20))
        ax.set_ylabel("Percent of all inputs")
        ax.set_title(title, loc="left", fontweight="bold")
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("PRIS recomputed from 180 published E3 structure files", fontweight="bold")
    fig.supxlabel("Selected discovery inputs, not held-out validation. All distances >= 0.9 A by dataset construction.\nNo-verdict inputs stay in the denominator; they are not counted as passing or rejected.", fontsize=9)
    fig.savefig(destination / "structure_benchmark.png", dpi=180)
    plt.close(fig)
    # No imputation: no-verdict cases remain visibly distinct from passes.
    methods = METHODS[2:]
    z = np.array([[100 * values[(m, c)]["rejection_fraction_all"] for c in KINDS[1:]] for m in methods])
    fig, ax = plt.subplots(figsize=(8, 4.4), constrained_layout=True)
    im = ax.imshow(z, vmin=0, vmax=100, cmap="Blues")
    ax.set_xticks(range(5), ["S1\nCompression", "S2\nCation swap", "S3\nDisplacement", "S4\nExpansion", "S5\nCation-anion swap"])
    ax.set_yticks(range(len(methods)), methods)
    for i in range(len(methods)):
        for j in range(5):
            ax.text(j, i, f"{z[i,j]:.1f}%", ha="center", va="center", color="white" if z[i,j] > 55 else "#132c3d")
    ax.set_title("Damage detection by class (30 inputs per class)", loc="left", fontweight="bold")
    fig.colorbar(im, ax=ax, label="Rejected / all inputs (%)", shrink=0.85)
    fig.supxlabel("Published E3 discovery subset; fixed rules, original cells, no refitting. No verdict is not a pass.", fontsize=9)
    fig.savefig(destination / "damage_classes.png", dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "original_e3")
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "structure_benchmark")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="Debug subset; omitted for the full reproduction")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.data / "manifest.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows = sorted(rows, key=lambda r: r["task"])
    if args.limit:
        rows = rows[:args.limit]
    started = time.perf_counter()
    records = []
    with (args.out / "records.jsonl").open("w", encoding="utf-8") as handle:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            jobs = [pool.submit(evaluate, (row, str(args.data.resolve()))) for row in rows]
            for future in as_completed(jobs):
                record = future.result()
                records.append(record)
                handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                handle.flush()
                if len(records) % 10 == 0 or len(records) == len(rows):
                    print(f"Processed {len(records)}/{len(rows)} structures ({time.perf_counter()-started:.1f}s)", flush=True)
    records.sort(key=lambda r: r["task"])
    (args.out / "records.json").write_text(json.dumps(records, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    summary, tables = summarize(records, time.perf_counter() - started)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    write_csv(args.out / "metrics.csv", tables)
    flat = []
    law_rows = []
    for r in records:
        a = r.get("analysis", {})
        flat.append({k: r.get(k) for k in ("task", "parent_id", "variant", "label", "formula", "n_sites", "minimum_distance_a", "seconds", "status")} |
                    {"pss": a.get("pss"), **r["verdicts"]})
        for law, info in a.get("laws", {}).items():
            law_rows.append({"task": r["task"], "variant": r["variant"], "law": law,
                             **{k: info.get(k) for k in ("quantity", "value", "threshold", "state", "mechanism")}})
    write_csv(args.out / "structure_results.csv", flat)
    write_csv(args.out / "law_results.csv", law_rows)
    if not args.limit:
        plot_metrics(tables, args.out)
    print(json.dumps({k: summary[k] for k in ("n_structures", "n_parents", "n_errors", "wall_seconds", "composition_checks_passed")}, indent=2))
    return 0 if summary["n_errors"] == 0 and summary["composition_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
