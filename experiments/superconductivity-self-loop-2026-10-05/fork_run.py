"""Fork a stopped Tc self-loop run into an authorized continuation.

The parent is locked and opened read-only. Only training workbench artifacts
and the run's own provenance are copied. This command never launches a model
or a controller, and never changes the parent's state or budgets.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

from runtime import Store, exclusive, read_json, write_json, utc

DEFAULT_PARENT = Path("C:/Users/28908/Documents/Codex/2026-10-02/tc-self-loop/runs/demo-20261002-verified")
DEFAULT_RUN = Path("C:/Users/28908/Documents/Codex/2026-10-05/tc-self-loop/runs/continuation-20")
UPDATES = {"min_completed_experiments": 22, "max_experiments": 42,
           "max_llm_calls": 105, "max_seconds": 14400., "max_call_seconds": 360.,
           "max_fit_seconds": 900., "patience": 4}
TRAIN_DATA = {"train.csv.gz", "schema.json", "fold_assignments.csv", "data_audit.json"}
EVIDENCE = {"specification.json", "result.json", "oof_predictions.csv.gz"}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                                     allow_nan=False).encode("utf-8")).hexdigest()


def tree_hashes(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlink in parent evidence tree: " + str(path))
        if path.is_file():
            # Windows mandatory byte-range locks prevent a second file handle
            # from hashing the locks currently held by this process. They are
            # ownership sentinels, not scientific or database evidence.
            if path.parent == root and path.name in {"controller.lock", "child.lock"}:
                continue
            if not path.resolve().is_relative_to(root):
                raise ValueError("Evidence escapes parent run")
            result[path.relative_to(root).as_posix()] = sha(path)
    return result


def completed_unique_experiments(state):
    seen = set()
    for cycle in state.get("completed_cycles", []):
        evidence = cycle.get("evaluation", {})
        if not isinstance(evidence.get("metrics"), dict) or evidence.get("proposal_was_duplicate", evidence.get("reused", False)):
            continue
        spec = cycle.get("specification")
        if not isinstance(spec, dict):
            raise ValueError("Successful inherited cycle has no specification")
        key = evidence.get("fingerprint") or canonical_sha(spec)
        seen.add(key)
    return len(seen)


def _allowed_workbench_path(relative):
    parts = Path(relative).parts
    return (len(parts) == 1 and parts[0] in {"pipeline.py", "prepare_data.py"}
            or len(parts) == 2 and parts[0] == "data" and parts[1] in TRAIN_DATA
            or len(parts) == 3 and parts[0] == "candidates" and parts[2] in EVIDENCE)


def fork_run(parent: Path, destination: Path, *, verify_adapter=True):
    parent, destination = Path(parent).resolve(), Path(destination).resolve()
    if not parent.is_dir() or parent == destination or parent.is_relative_to(destination) or destination.is_relative_to(parent):
        raise ValueError("Parent and continuation must be existing-parent/disjoint directories")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Continuation destination must be absent or empty")
    # Requiring pre-existing locks avoids even creating lock artifacts in the
    # frozen parent. Holding both prevents active/orphaned controller work.
    for name in ("controller.lock", "child.lock"):
        if not (parent / name).is_file() or (parent / name).stat().st_size < 1:
            raise ValueError("Stopped parent must already have a nonempty " + name)
    with exclusive(parent / "controller.lock"), exclusive(parent / "child.lock"):
        before = tree_hashes(parent)
        source_db = sqlite3.connect((parent / "memory.sqlite").as_uri() + "?mode=ro", uri=True)
        try:
            if source_db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Parent SQLite integrity check failed")
            row = source_db.execute("SELECT payload FROM state WHERE id=1").fetchone()
            if not row:
                raise ValueError("Parent has no durable state")
            old = json.loads(row[0])
            if old.get("status") != "stopped" or old.get("phase") != "propose":
                raise ValueError("Parent must be stopped at a proposal boundary")
            if any(old.get(name) is not None for name in ("pending_call", "pending_plan", "pending_result")):
                raise ValueError("Parent has unresolved work")
            if read_json(parent / "status.json") != old:
                raise ValueError("Parent status export does not match authoritative SQLite state")
            if old.get("attempts") != 2 or old.get("llm_calls") != 5 or len(old.get("completed_cycles", [])) != 2:
                raise ValueError("Expected the verified two-cycle, five-call parent run")
            inherited_completed = completed_unique_experiments(old)
            if inherited_completed != 2:
                raise ValueError("Expected two unique successful inherited experiments")
            manifest = read_json(parent / "workbench_manifest.json")
            index = read_json(parent / "adapter_index.json")
            if index.get("pending"):
                raise ValueError("Parent workbench contains pending evaluations")
            source_dir = Path(manifest["source_dir"]).resolve()
            permitted = {name: item["sha256"] for name, item in manifest["files"].items()}
            for name, digest in index["evidence"].items():
                if name in permitted and permitted[name] != digest:
                    raise ValueError("Conflicting workbench evidence hashes")
                permitted[name] = digest
            if not permitted or any(not _allowed_workbench_path(name) for name in permitted):
                raise ValueError("Workbench manifest contains a non-training artifact")
            for name, expected in permitted.items():
                source = parent / "workbench" / name
                if not source.resolve().is_relative_to(parent / "workbench") or sha(source) != expected:
                    raise ValueError("Parent workbench integrity failure: " + name)
            destination.mkdir(parents=True, exist_ok=True)
            copied = {}
            def copy_file(relative, target_relative=None):
                source = parent / relative
                target_relative = target_relative or relative
                target = destination / target_relative
                if not source.resolve().is_relative_to(parent) or not target.resolve().is_relative_to(destination):
                    raise ValueError("Copy path escapes the selected run")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                if sha(target) != before[Path(relative).as_posix()]:
                    raise ValueError("Copy digest changed: " + str(relative))
                copied[Path(target_relative).as_posix()] = {"parent_relative_path": Path(relative).as_posix(), "sha256": sha(target)}
            for relative in permitted:
                copy_file("workbench/" + relative)
            for name in ("adapter_index.json", "workbench_manifest.json"):
                copy_file(name)
            for folder in ("calls", "cycles"):
                for file in sorted((parent / folder).rglob("*")):
                    if file.is_file():
                        if file.suffix.lower() in {".joblib", ".pkl", ".pickle", ".pt", ".bin"}:
                            raise ValueError("Unexpected model binary in run provenance")
                        copy_file(file.relative_to(parent))
            for name in ("status.json", "memory_export.json"):
                copy_file(name, "lineage/parent/" + name)
            if (parent / "startup_repair.json").exists():
                copy_file("startup_repair.json", "lineage/parent/startup_repair.json")
            target_db = sqlite3.connect(destination / "memory.sqlite")
            try:
                source_db.backup(target_db)
            finally:
                target_db.close()
            # This immutable backup captures the parent's logical SQLite state;
            # the live continuation database then receives its own event.
            snapshot_db = destination / "lineage/parent/memory.sqlite"
            shutil.copyfile(destination / "memory.sqlite", snapshot_db)
            state = copy.deepcopy(old)
            old_config = copy.deepcopy(state["config"])
            state["config"].update(UPDATES)
            state.update(status="running", stop_reason=None, phase="propose",
                         pending_call=None, pending_plan=None, pending_result=None)
            policy = {"authorization": "User requested at least 20 additional autonomous experiment rounds",
                      "inherited_completed_unique_experiments": inherited_completed,
                      "required_additional_completed_unique_experiments": 20,
                      "required_total_completed_unique_experiments": 22,
                      "counting_rule": "Successful unique evaluated-and-reflected configurations; failed or duplicate proposals do not count",
                      "prior_stop_reflection": "Retained verbatim as history; new completion-floor policy supersedes its exhausted-budget stop decision"}
            state["continuation"] = {"parent_run": str(parent), "parent_state_sha256": canonical_sha(old), **policy}
            after = tree_hashes(parent)
            if after != before:
                raise ValueError("Parent run changed while locked; continuation is not ready")
            lineage = {"format": "tc-self-loop-continuation-v1", "created_utc": utc(), "parent_run": str(parent),
                       "continuation_run": str(destination), "parent_state_sha256": canonical_sha(old),
                       "parent_tree_sha256": canonical_sha(before), "parent_file_sha256": before,
                       "hash_exclusions": ["controller.lock", "child.lock"],
                       "immutable_source_dir": str(source_dir), "initial_incumbent": copy.deepcopy(old["best"]),
                       "inherited_counters": {key: old[key] for key in ("attempts", "llm_calls", "elapsed_seconds", "stagnation")},
                       "old_config": old_config, "new_config": state["config"], "policy": policy,
                       "copied_artifacts": copied, "parent_sqlite_backup_sha256": sha(snapshot_db),
                       "parent_unchanged_verified": True, "controller_launched": False}
            write_json(destination / "lineage.json", lineage)
            store = Store(destination)
            try:
                if store.state() != old:
                    raise ValueError("SQLite backup does not reproduce the parent state")
                store.save(state, "run.continuation_authorized", {
                    "old_config": old_config, "new_config": state["config"], "policy": policy,
                    "parent_run": str(parent), "parent_state_sha256": canonical_sha(old),
                    "parent_tree_sha256": canonical_sha(before), "source_hashes": before,
                    "lineage_sha256": sha(destination / "lineage.json")})
                store.export()
            finally:
                store.close()
            if verify_adapter:
                from workbench_adapter import Adapter
                adapter = Adapter(destination, source_dir)
                context = adapter.context()
                lineage["no_fit_smoke_check"] = {"rows": context["rows"], "groups": context["groups"],
                                                 "known_candidates": len(context["known_specifications"]),
                                                 "guard": context["guard"], "new_model_fits": 0}
                # Keep the event's lineage hash stable by storing smoke evidence
                # separately after the immutable lineage document is committed.
                write_json(destination / "fork_smoke_check.json", lineage.pop("no_fit_smoke_check"))
            if tree_hashes(parent) != before:
                raise ValueError("Parent changed during continuation verification")
            return {"run_dir": str(destination), "source_dir": str(source_dir), "status": "running",
                    "controller_launched": False, "inherited_completed_unique_experiments": inherited_completed,
                    "required_additional_completed_unique_experiments": 20, "config": state["config"],
                    "initial_incumbent": state["best"], "parent_unchanged": True,
                    "lineage_sha256": sha(destination / "lineage.json")}
        finally:
            source_db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, default=DEFAULT_PARENT)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    args = parser.parse_args()
    print(json.dumps(fork_run(args.parent, args.run_dir), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
