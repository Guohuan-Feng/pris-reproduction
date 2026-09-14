"""Recompute E4 Law 7 from public as-generated and relaxed atomic structures.

This performs no DFT calculation. The relaxed structures are author-supplied
DFT outputs. No precomputed symmetry feature is used for feature computation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import statistics
import time
import warnings

from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

SYMPREC = 0.01
LAW7_BOUND = 2.0 / 3.0


def describe(st: Structure, primitive: bool) -> dict:
    if primitive:
        st = SpacegroupAnalyzer(st, symprec=SYMPREC).get_primitive_standard_structure()
    analyzer = SpacegroupAnalyzer(st, symprec=SYMPREC)
    dataset = analyzer.get_symmetry_dataset()
    if dataset is None:
        raise ValueError("spglib returned no symmetry dataset")
    distinct = len(set(dataset.equivalent_atoms))
    fraction = distinct / len(st)
    return {"n_atoms": len(st), "spacegroup_symbol": analyzer.get_space_group_symbol(),
            "spacegroup_number": int(dataset.number), "n_inequivalent": distinct,
            "site_fraction": fraction, "law7": fraction <= LAW7_BOUND}


def get_summary(rows: list[dict], convention: str) -> dict:
    gen = f"generated_{convention}_"
    rel = f"relaxed_{convention}_"
    roles = sorted({r["role"] for r in rows})
    return {
        "n_structures": len(rows),
        "law7_satisfied_generated": sum(r[gen + "law7"] for r in rows),
        "law7_satisfied_dft_relaxed": sum(r[rel + "law7"] for r in rows),
        "gained_law7_on_relaxation": sum(not r[gen + "law7"] and r[rel + "law7"] for r in rows),
        "lost_law7_on_relaxation": sum(r[gen + "law7"] and not r[rel + "law7"] for r in rows),
        "median_site_fraction_generated": statistics.median(r[gen + "site_fraction"] for r in rows),
        "median_site_fraction_dft_relaxed": statistics.median(r[rel + "site_fraction"] for r in rows),
        "law7_after_relaxation_by_role": {
            role: round(statistics.mean(int(r[rel + "law7"]) for r in rows if r["role"] == role), 4)
            for role in roles},
        "spacegroups_dft_relaxed": dict(sorted(Counter(r[rel + "spacegroup_symbol"] for r in rows).items())),
    }


def main() -> int:
    bundle = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=bundle / "data" / "symmetry")
    ap.add_argument("--out", type=Path, default=bundle / "results" / "symmetry")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    provenance = json.loads((args.data / "provenance.json").read_text(encoding="utf-8"))
    rows, errors = [], []
    for i, record in enumerate(provenance["records"], start=1):
        row = {"candidate_id": record["candidate_id"], "role": record["role"]}
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                warnings.simplefilter("ignore", UserWarning)
                for state, fmt in (("generated", "poscar"), ("relaxed", "cif")):
                    path = args.data / record[state + "_file"]
                    raw = path.read_bytes()
                    if hashlib.sha256(raw).hexdigest() != record[state + "_sha256"]:
                        raise ValueError("Input SHA256 mismatch: " + str(path))
                    st = Structure.from_str(raw.decode("utf-8"), fmt=fmt)
                    for convention in ("input", "primitive"):
                        features = describe(st, primitive=convention == "primitive")
                        row.update({f"{state}_{convention}_{key}": value for key, value in features.items()})
            rows.append(row)
        except Exception as exc:
            errors.append({"candidate_id": record["candidate_id"], "error": repr(exc)})
        if i % 50 == 0 or i == len(provenance["records"]):
            print(f"Analyzed {i}/{len(provenance['records'])} pairs; {len(errors)} errors", flush=True)
    if errors:
        (args.out / "errors.json").write_text(json.dumps(errors, indent=2), encoding="utf-8")
        raise RuntimeError(f"{len(errors)} structure pairs failed; results not silently filtered")
    assert len(rows) == provenance["n_pairs"]
    with (args.out / "recomputed_symmetry.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    # References are consulted only after independent feature computation.
    reference = json.loads((args.data / "reference" / "published_summary.json").read_text(encoding="utf-8"))
    with (args.data / "reference" / "published_index.csv").open(encoding="utf-8") as handle:
        index = {r["candidate_id"]: r for r in csv.DictReader(handle)}
    row_mismatches = []
    for row in rows:
        expected = index[row["candidate_id"]]
        for state, published in (("generated", "generated"), ("relaxed", "dft_relaxed")):
            for col in ("spacegroup_number", "site_fraction"):
                value, want = row[f"{state}_input_{col}"], float(expected[f"{col}_{published}"])
                if abs(value - want) > 1e-10:
                    row_mismatches.append({"candidate_id": row["candidate_id"], "quantity": f"{state}_{col}", "recomputed": value, "published": want})
    input_summary, primitive_summary = get_summary(rows, "input"), get_summary(rows, "primitive")
    comparison = {key: {"recomputed": value, "published": reference.get(key), "matches": value == reference.get(key)}
                  for key, value in input_summary.items()}
    convention_changed = {state: [r["candidate_id"] for r in rows if r[f"{state}_input_law7"] != r[f"{state}_primitive_law7"]]
                          for state in ("generated", "relaxed")}
    convention_rows = []
    for row in rows:
        for state in ("generated", "relaxed"):
            if row["candidate_id"] in convention_changed[state]:
                details = {"candidate_id": row["candidate_id"], "stage": state}
                details.update({key.removeprefix(state + "_"): value for key, value in row.items() if key.startswith(state + "_")})
                convention_rows.append(details)
    if convention_rows:
        with (args.out / "standardization_verdict_changes.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(convention_rows[0]))
            writer.writeheader()
            writer.writerows(convention_rows)
    result = {"source_commit": provenance["source_commit"], "symprec_A": SYMPREC,
              "law7_threshold": LAW7_BOUND, "angle_tolerance_degrees": 5,
              "scope": "Reanalysis of public atomic structures, not a new DFT run.",
              "standardization_note": "The primitive-standard procedure may idealize coordinates within the symmetry tolerance; it is reported as a sensitivity analysis, not substituted for the input-cell publication protocol.",
              "input_cell_summary": input_summary, "primitive_standard_summary": primitive_summary,
              "published_summary_comparison": comparison,
              "all_compared_published_summary_values_match": all(v["matches"] for v in comparison.values()),
              "n_per_structure_mismatches": len(row_mismatches), "per_structure_mismatches": row_mismatches,
              "verdict_changes_from_cell_convention": convention_changed,
              "n_errors": len(errors), "elapsed_seconds": time.perf_counter() - start,
              "package_versions": {name: importlib.metadata.version(name) for name in ("pymatgen", "spglib", "numpy")}}
    (args.out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
