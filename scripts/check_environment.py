"""Check the portable workflow separately from unavailable upstream inputs."""
from pathlib import Path
import argparse
import csv
import hashlib
import importlib.metadata
import json
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_INPUTS = [
    ("src/build_bonds.py", "source", "Historical bond-feature pipeline; absent from the public release."),
    ("outputs/20260815_threshold_transfer/transfer.json", "data", "Exact threshold-transfer measurements required by Fig. 2."),
    ("outputs/20260822_property_design_synthesis_score/inverse_scores.parquet", "data", "Full inverse-design candidate scores, not the selected E4 subset."),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, help="Optional full upstream checkout to inspect.")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    packages = []
    for line in (ROOT / "requirements-lock.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, required = line.split("==", 1)
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            installed = None
        packages.append({"name": name, "required": required, "installed": installed,
                         "matches": installed == required})
    vendor = json.loads((ROOT / "vendor_manifest.json").read_text(encoding="utf-8"))
    source_problems = []
    for entry in vendor["unmodified_files"]:
        path = ROOT / entry["path"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            source_problems.append(entry["path"])
    required_data = ["data/original_e3/manifest.csv", "data/eos/stage_b_collected.json",
                     "data/eos/published_bulk_moduli.json", "data/eos/manifest.json",
                     "data/symmetry/provenance.json", "data/symmetry/reference/published_index.csv"]
    missing_data = [p for p in required_data if not (ROOT / p).is_file()]
    data_checks = []
    def check_data(path, digest):
        relative = path.relative_to(ROOT).as_posix()
        matches = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest
        data_checks.append({"path": relative, "matches": matches})
    if not missing_data:
        with (ROOT / "data/original_e3/manifest.csv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                check_data(ROOT / "data/original_e3" / row["structure_file"], row["structure_sha256"])
        eos = json.loads((ROOT / "data/eos/manifest.json").read_text(encoding="utf-8"))
        for entry in eos["files"]:
            check_data(ROOT / "data/eos" / entry["file"], entry["sha256"])
        symmetry = json.loads((ROOT / "data/symmetry/provenance.json").read_text(encoding="utf-8"))
        for row in symmetry["records"]:
            for state in ("generated", "relaxed"):
                check_data(ROOT / "data/symmetry" / row[state + "_file"], row[state + "_sha256"])
    data_problems = [entry["path"] for entry in data_checks if not entry["matches"]]
    python_ok = sys.version_info[:2] == (3, 12)
    ready = (python_ok and all(p["matches"] for p in packages) and not source_problems
             and not missing_data and not data_problems)
    external = [{"path": path, "kind": kind, "reason": reason,
                 "present": (args.upstream / path).is_file() if args.upstream else None}
                for path, kind, reason in EXTERNAL_INPUTS]
    result = {"python": platform.python_version(), "platform": platform.system(),
              "supported_python": python_ok, "packages": packages,
              "vendor_source_problems": source_problems, "missing_bundled_data": missing_data,
              "input_files_checked": len(data_checks), "input_hash_problems": data_problems,
              "bundled_workflow_ready": ready, "upstream_inputs": external,
              "scope": "The bundled six-step reproduction only. Full original search, feature stores, PU shards, and licensed VASP inputs are not supplied by installing Python packages."}
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
