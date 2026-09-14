"""Run the portable, data-complete parts of the PRIS reproduction bundle."""
from pathlib import Path
import argparse
import os
import subprocess
import sys
import time
import json

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["MPLBACKEND"] = "Agg"
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        env.setdefault(variable, "1")
    jobs = [
        ("geometry_and_cell_controls", ["scripts/validate_core.py"]),
        ("original_structure_benchmark", ["scripts/run_structure_benchmark.py", "--workers", str(args.workers)]),
        ("independent_eos_refit", ["scripts/refit_eos.py"]),
        ("paired_symmetry_recompute", ["scripts/recompute_symmetry.py"]),
        ("report_figures", ["scripts/make_report_figures.py"]),
        ("upstream_analyzer_tests", ["-m", "pytest", "-q", "vendor/pris/tests/test_pris_analyze.py"]),
    ]
    results = []
    log_dir = ROOT / "results" / "run_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    for name, arguments in jobs:
        print(f"Running {name}", flush=True)
        started = time.perf_counter()
        with (log_dir / f"{name}.log").open("w", encoding="utf-8") as log:
            result = subprocess.run([sys.executable, *arguments], cwd=ROOT, env=env,
                                    stdout=log, stderr=subprocess.STDOUT)
        entry = {"job": name, "exit_code": result.returncode,
                 "seconds": round(time.perf_counter()-started, 3), "log": f"results/run_logs/{name}.log"}
        results.append(entry)
        print(f"  exit={result.returncode}, {entry['seconds']:.1f}s", flush=True)
        if result.returncode:
            print((log_dir / f"{name}.log").read_text(encoding="utf-8")[-3000:], flush=True)
    (log_dir / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0 if all(r["exit_code"] == 0 for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
