"""Bounded, input-only execution of Agent-authored structural representations.

The contract fixes 4..32 finite, intensive, invariant outputs but no formulas,
bins, element channels, or feature names. Geometry and resource primitives are
imported from a byte-frozen earlier runtime. The expanded numerical AST checker
is local to this new stage. This is not a general OS sandbox.
No target, real row identifier, training code, or dataset path enters the worker.
"""
from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

import numpy as np

RUNTIME_ROOT = Path(__file__).resolve().parent
FROZEN_GEOMETRY_PATH = RUNTIME_ROOT.parent / "materials_structure_agent_2026-10-05_pilot" / "descriptor_runtime.py"
FROZEN_GEOMETRY_SHA256 = "c1d99ab97cce8adea015d41a88a9f98d9501aec4aaa6a735c1bcada81162fd06"
MIN_FEATURES, MAX_FEATURES = 4, 32
DEFAULT_TIMEOUT_S = 20.0
DEFAULT_MEMORY_MB = 768
TRANSFORMATIONS = ("rotation", "translation_wrap", "atom_and_edge_permutation", "equivalent_basis", "supercell_2x1x1")
INVARIANCE_RTOL, INVARIANCE_ATOL = 1e-8, 1e-9


def _load_frozen_geometry():
    source_bytes = FROZEN_GEOMETRY_PATH.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != FROZEN_GEOMETRY_SHA256:
        raise RuntimeError("frozen geometry source has changed; execution refused")
    spec = importlib.util.spec_from_file_location("_frozen_representation_geometry", FROZEN_GEOMETRY_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    # Compile the verified bytes directly; do not create a cache in the old root
    # even when the trusted caller forgot Python's -B option.
    exec(compile(source_bytes, str(FROZEN_GEOMETRY_PATH), "exec"), module.__dict__)
    return module


_geometry = _load_frozen_geometry()
ProposalRejected = _geometry.ProposalRejected
RuntimeRejected = _geometry.RuntimeRejected
STRUCTURE_FIELDS = _geometry.STRUCTURE_FIELDS
HELPER_RULE = _geometry.HELPER_RULE
transform_structure = _geometry.transform_structure
NP_NAMES = _geometry.NP_NAMES | frozenset({"log", "log1p", "expm1", "tanh", "quantile", "percentile", "cov", "corrcoef", "trace"})
NP_LINALG_NAMES = _geometry.NP_LINALG_NAMES | frozenset({"eigh", "slogdet", "solve", "inv"})
MATH_NAMES = _geometry.MATH_NAMES
SAFE_BUILTINS = _geometry.SAFE_BUILTINS
ARRAY_ATTRIBUTES = _geometry.ARRAY_ATTRIBUTES
ALLOWED_NODE_TYPES = frozenset(_geometry.ALLOWED_NODE_TYPES)
MAX_CODE_BYTES = _geometry.MAX_CODE_BYTES
MAX_AST_NODES = _geometry.MAX_AST_NODES


@dataclass
class ValidationResult:
    accepted: bool
    status: str
    code_sha256: str
    feature_names: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    receipt_path: str | None = None


def _code_hash(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _runtime_hash():
    if hashlib.sha256(FROZEN_GEOMETRY_PATH.read_bytes()).hexdigest() != FROZEN_GEOMETRY_SHA256:
        raise RuntimeRejected("frozen geometry source has changed")
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def validate_feature_names(feature_names):
    if not isinstance(feature_names, (list, tuple)) or not (MIN_FEATURES <= len(feature_names) <= MAX_FEATURES):
        raise ProposalRejected("declare 4..32 feature_names before any compute or model fit")
    names = list(feature_names)
    if any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name) or "__" in name for name in names):
        raise ProposalRejected("feature_names must be identifiers of 1..64 characters without dunders")
    if len(set(names)) != len(names):
        raise ProposalRejected("feature_names must be unique and ordered")
    return names


def _attribute_path(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return [node.id, *reversed(parts)] if isinstance(node, ast.Name) else None


def check_ast(code: str) -> dict:
    """Local expanded numerical allowlist; frozen geometry globals stay intact.

    Matrix size, memory, and runtime remain constrained by the worker process.
    This extends numerical expressiveness only, never imports or external I/O.
    """
    if not isinstance(code,str) or len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise ProposalRejected("code must be UTF-8 text of at most 32768 bytes")
    try:
        tree = ast.parse(code,mode="exec")
    except SyntaxError as exc:
        raise ProposalRejected(f"invalid Python syntax at line {exc.lineno}") from None
    nodes = list(ast.walk(tree))
    if any(not isinstance(item,(ast.Import,ast.ImportFrom,ast.FunctionDef)) for item in tree.body):
        raise ProposalRejected("module may contain only numeric imports and function definitions; move constants and state inside compute or pure helper functions")
    if len(nodes) > MAX_AST_NODES:
        raise ProposalRejected("AST node limit exceeded")
    functions = {node.name for node in nodes if isinstance(node,ast.FunctionDef)}
    computes = [node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="compute"]
    if len(computes)!=1 or len(computes[0].args.args)!=1 or computes[0].args.args[0].arg!="structure" or computes[0].args.defaults or computes[0].args.kwonlyargs or computes[0].args.vararg or computes[0].args.kwarg:
        raise ProposalRejected("compute must be a single top-level function with exactly argument structure")
    imported = {alias.name for item in nodes if isinstance(item,ast.ImportFrom) for alias in item.names}
    trusted_names = {"np","math","closest_neighbors"}
    forbidden_names = {"eval","exec","open","compile","getattr","setattr","delattr","globals","locals","vars","dir","type","object","input","print","help","breakpoint","memoryview","bytes","bytearray","super"}
    for node in nodes:
        if type(node) not in ALLOWED_NODE_TYPES:
            raise ProposalRejected(f"AST construct {type(node).__name__} is not allowed")
        if isinstance(node,(ast.Name,ast.arg)):
            name = node.id if isinstance(node,ast.Name) else node.arg
            if "__" in name or name in forbidden_names:
                raise ProposalRejected(f"name {name!r} is not allowed")
            if isinstance(node,ast.Name) and isinstance(node.ctx,ast.Store) and name in trusted_names:
                raise ProposalRejected("trusted names cannot be rebound")
        if isinstance(node,ast.Constant) and isinstance(node.value,str):
            if "__" in node.value:
                raise ProposalRejected("dunder strings are not allowed")
            if node.value=="material_id":
                raise ProposalRejected("material_id is alignment metadata and cannot be a descriptor input")
        if isinstance(node,ast.FunctionDef):
            if "__" in node.name or node.name in SAFE_BUILTINS or node.name in trusted_names or node.decorator_list:
                raise ProposalRejected("invalid function name or decorator")
            if node.returns is not None:
                raise ProposalRejected("function annotations are not allowed")
        if isinstance(node,ast.arg) and node.annotation is not None:
            raise ProposalRejected("function annotations are not allowed")
        if isinstance(node,ast.arguments):
            if node.defaults or node.kwonlyargs or node.kw_defaults or node.posonlyargs or node.vararg or node.kwarg:
                raise ProposalRejected("function arguments cannot have defaults, keyword-only, positional-only, or variadic parameters; construct local state per call")
        if isinstance(node,ast.Import):
            for alias in node.names:
                if (alias.name,alias.asname) not in {("numpy","np"),("math",None),("math","math")}:
                    raise ProposalRejected("imports are limited to import numpy as np and import math")
        if isinstance(node,ast.ImportFrom):
            permitted = NP_NAMES if node.module=="numpy" else MATH_NAMES if node.module=="math" else frozenset()
            if node.level or not permitted or any(alias.name not in permitted or alias.asname not in {None,alias.name} for alias in node.names):
                raise ProposalRejected("from-import is outside the numpy/math allowlist")
        if isinstance(node,ast.Attribute):
            if "__" in node.attr:
                raise ProposalRejected("dunder attributes are not allowed")
            path = _attribute_path(node)
            if path and path[0]=="np":
                if not (len(path)==2 and path[1] in NP_NAMES | {"linalg"}) and not (len(path)==3 and path[1]=="linalg" and path[2] in NP_LINALG_NAMES):
                    raise ProposalRejected("numpy attribute is outside allowlist")
            elif path and path[0]=="math":
                if len(path)!=2 or path[1] not in MATH_NAMES:
                    raise ProposalRejected("math attribute is outside allowlist")
            elif node.attr not in ARRAY_ATTRIBUTES:
                raise ProposalRejected(f"attribute {node.attr!r} is outside array allowlist")
        if isinstance(node,ast.Call):
            if isinstance(node.func,ast.Name):
                if node.func.id not in set(SAFE_BUILTINS) | functions | imported | {"closest_neighbors"}:
                    raise ProposalRejected(f"call {node.func.id!r} is not allowed; callable aliases are prohibited")
            elif not isinstance(node.func,ast.Attribute):
                raise ProposalRejected("indirect callable expressions are not allowed")
            if any(keyword.arg is None for keyword in node.keywords):
                raise ProposalRejected("expanded call keywords are not allowed")
        if isinstance(node,ast.comprehension) and node.is_async:
            raise ProposalRejected("async comprehensions are not allowed")
        if isinstance(node,(ast.Assign,ast.AnnAssign,ast.AugAssign)):
            targets = node.targets if isinstance(node,ast.Assign) else [node.target]
            for target in targets:
                if any(isinstance(part,ast.Attribute) for part in ast.walk(target)):
                    raise ProposalRejected("attribute assignment is not allowed")
    return {"ast_nodes":len(nodes),"code_bytes":len(code.encode("utf-8")),"functions":sorted(functions),"ast_allowlist_stage":"evolving_representation_v2"}


def validate_structure(record):
    _geometry.validate_structure(record)
    n = int(record["n_sites"])
    for name in ("atomic_numbers", "covalent_radii", "electronegativities"):
        values = np.asarray(record[name], dtype=float)
        if values.shape != (n,) or not np.isfinite(values).all():
            raise RuntimeRejected(f"{name} must contain finite site inputs")
    zs = np.asarray(record["atomic_numbers"], dtype=float)
    if np.any(zs < 1) or np.any(zs > 118) or not np.array_equal(zs, zs.astype(int)):
        raise RuntimeRejected("atomic_numbers must be integers in 1..118")
    if np.any(np.asarray(record["covalent_radii"], dtype=float) <= 0):
        raise RuntimeRejected("covalent_radii must be positive")
    if any(not isinstance(symbol, str) or not re.fullmatch(r"[A-Z][a-z]?", symbol) for symbol in record["symbols"]):
        raise RuntimeRejected("symbols must be chemical element symbols")
    distances = np.asarray(record["distance_matrix"], dtype=float)
    # Historical input matrices store a positive nearest periodic self-image
    # distance on the diagonal. Generated geometric fixtures may use zero.
    # Neither convention invalidates the separately verified periodic edges.
    if not np.isfinite(distances).all() or np.any(distances < 0) or not np.allclose(distances, distances.T, rtol=0, atol=1e-8):
        raise RuntimeRejected("distance_matrix must be finite, symmetric and nonnegative")


def closest_neighbors(structure):
    """Current trusted helper: nearest 12 within 6 A, retaining all boundary ties.

    Submitted code can instead read the full periodic neighbor arrays for other
    radial/interaction constructions. No angular or aggregation formula is fixed.
    """
    validate_structure(structure)
    return _geometry.closest_neighbors(structure)


def _worker_main():
    request = json.load(sys.stdin)
    code, names = request["code"], validate_feature_names(request["feature_names"])
    check_ast(code)
    namespace = {"__builtins__": {**SAFE_BUILTINS, "__import__": _geometry._safe_import}, "np": np, "math": math, "closest_neighbors": closest_neighbors}
    exec(compile(code, "<agent-representation>", "exec"), namespace, namespace)
    outputs = []
    start = time.perf_counter()
    for record in request["records"]:
        validate_structure(record)
        closest_neighbors(record)  # Always check the resource/tie rule, including unused helper.
        input_record = {**record, "material_id": "redacted-input-id"}
        result = np.asarray(namespace["compute"](_geometry._freeze(input_record)))
        if result.shape != (len(names),) or result.dtype.kind not in "iuf" or not np.isfinite(result).all():
            raise RuntimeRejected(f"compute must return {len(names)} finite real numeric scalars, shape ({len(names)},)")
        outputs.append(result.astype(float).tolist())
    return {"status": "ok", "values": outputs, "feature_names": names, "worker_compute_seconds": time.perf_counter()-start, "records": len(outputs)}


def run_isolated(code, records, *, feature_names, timeout_s=DEFAULT_TIMEOUT_S, memory_mb=DEFAULT_MEMORY_MB):
    """Return a matrix and resource receipt. No model fit; stdin is input-only."""
    runtime_hash = _runtime_hash()
    names, ast_info = validate_feature_names(feature_names), check_ast(code)
    if not (0.1 <= timeout_s <= 300) or not (128 <= memory_mb <= 2048):
        raise RuntimeRejected("runtime resource configuration outside bounds")
    records = list(records)
    if not records or len(records) > 128:
        raise RuntimeRejected("isolation batch must contain 1..128 input records")
    for record in records:
        validate_structure(record)
    # Real IDs are stripped before serialization as well as before compute.
    worker_records = [{**record, "material_id": "redacted-input-id"} for record in records]
    payload = json.dumps({"code": code, "feature_names": names, "records": worker_records}, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(payload) > 64*1024**2:
        raise RuntimeRejected("input payload exceeds 64 MiB per isolated batch")
    env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "TEMP", "TMP", "PATH") if name in os.environ}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
    kwargs = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "cwd": str(RUNTIME_ROOT), "env": env}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        kwargs["preexec_fn"] = _geometry._posix_preexec(memory_mb, timeout_s)
    runtime_file = str(Path(__file__).resolve())
    trusted_site = str(Path(np.__file__).resolve().parent.parent)
    bootstrap = f"import sys,runpy;sys.path.insert(0,{trusted_site!r});sys.argv=[{runtime_file!r},'--worker'];runpy.run_path({runtime_file!r},run_name='__main__')"
    interpreter = getattr(sys, "_base_executable", None) or sys.executable
    started = time.perf_counter()
    process = subprocess.Popen([interpreter, "-I", "-B", "-X", "utf8", "-c", bootstrap], **kwargs)
    job = None
    try:
        if os.name == "nt":
            job = _geometry._WindowsJob(process, memory_mb, timeout_s)
        try:
            stdout, stderr = process.communicate(payload, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            if job:
                job.close()
            process.kill()
            process.communicate()
            raise RuntimeRejected("representation subprocess wall timeout exceeded") from None
        if len(stdout) > 512*1024 or len(stderr) > 64*1024:
            raise RuntimeRejected("representation worker output exceeds cap")
        if process.returncode:
            raise RuntimeRejected(f"representation worker failed or resource limit exceeded (exit {process.returncode})")
        try:
            response = json.loads(stdout.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise RuntimeRejected("invalid representation worker response") from None
        if response.get("status") != "ok":
            raise RuntimeRejected(response.get("reason", "worker rejected")[:2000])
        values = np.asarray(response["values"], dtype=float)
        if response.get("feature_names") != names or values.shape != (len(records), len(names)) or not np.isfinite(values).all():
            raise RuntimeRejected("worker matrix format or ordered feature_names is invalid")
        metrics = {"wall_seconds": time.perf_counter()-started, "worker_compute_seconds": response["worker_compute_seconds"], "records": len(records), "columns": len(names), "timeout_s": timeout_s, "memory_limit_MB": memory_mb, "memory_enforcement": "Windows JobObject" if os.name == "nt" else "POSIX RLIMIT_AS", "hidden_process": os.name == "nt", "thread_limit": 1, "runtime_sha256": runtime_hash, "frozen_geometry_sha256": FROZEN_GEOMETRY_SHA256, "numeric_target_access": False, "real_material_ids_sent_to_worker": False, **ast_info}
        return values, metrics
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        if job:
            job.close()


def _make_geometry(symbols, zs, frac, lattice, electronegativities, radii):
    """Synthetic periodic input generation, solely for engineering validation."""
    frac, lattice = np.asarray(frac, dtype=float), np.asarray(lattice, dtype=float)
    n = len(symbols)
    shifts = np.array([(x,y,z) for x in range(-3,4) for y in range(-3,4) for z in range(-3,4)], dtype=int)
    nc, nj, ni, nd = [], [], [], []
    matrix = np.zeros((n,n))
    for i in range(n):
        for j in range(n):
            vectors = (frac[j] + shifts - frac[i]) @ lattice
            distances = np.linalg.norm(vectors, axis=1)
            matrix[i,j] = np.min(distances)
            for index in np.flatnonzero((distances > 1e-10) & (distances <= 6.0+1e-8)):
                nc.append(i); nj.append(j); ni.append(shifts[index].tolist()); nd.append(float(distances[index]))
    return {"material_id": "synthetic-input", "n_sites": n, "symbols": list(symbols), "atomic_numbers": list(zs), "electronegativities": list(electronegativities), "covalent_radii": list(radii), "frac_coords": frac.tolist(), "lattice": lattice.tolist(), "distance_matrix": matrix.tolist(), "neighbor_center": nc, "neighbor_index": nj, "neighbor_image": ni, "neighbor_distance": nd, "volume": float(abs(np.linalg.det(lattice)))}


def geometry_fixtures():
    """Five diverse geometries; no prescribed descriptor or target answers."""
    rows = [
        _make_geometry(["C"], [6], [[0,0,0]], np.diag([4.,4.,4.]), [2.55], [.76]),
        _make_geometry(["Si","O","O"], [14,8,8], [[.1,.1,.1],[.35,.25,.2],[.7,.65,.6]], np.diag([5.2,6.1,7.]), [1.90,3.44,3.44], [1.11,.66,.66]),
        _make_geometry(["Fe","O","N"], [26,8,7], [[.05,.15,.25],[.42,.52,.32],[.78,.64,.71]], [[4.3,.4,.1],[.8,5.1,.3],[.2,.6,5.8]], [1.83,3.44,3.04], [1.32,.66,.71]),
        _make_geometry(["C","O","N","H"], [6,8,7,1], [[.1,.2,.3],[.3,.3,.3],[.45,.45,.45],[.56,.5,.43]], np.diag([8.,8.4,9.2]), [2.55,3.44,3.04,2.20], [.76,.66,.71,.31]),
        _make_geometry(["H"], [1], [[.123,.345,.567]], np.diag([15.,15.,15.]), [2.20], [.31]),
    ]
    for index, row in enumerate(rows):
        row["material_id"] = f"synthetic-geometry-{index}"
        validate_structure(row)
    return rows


def _geometry_invariants(record):
    """Trusted transform checks, independent of submitted descriptor semantics."""
    n = int(record["n_sites"])
    distances = np.asarray(record["neighbor_distance"], dtype=float)
    zs = np.asarray(record["atomic_numbers"], dtype=float)
    return np.array([float(record["volume"])/n, np.mean(zs), np.var(zs), len(distances)/n, np.sum(distances)/n, np.sum(distances**2)/n], dtype=float)


def _write_receipt(result, receipt_path):
    if receipt_path is None:
        return
    path = Path(receipt_path).resolve()
    allowed = (RUNTIME_ROOT / "runtime_receipts").resolve()
    if not path.is_relative_to(allowed) or path.suffix != ".json":
        raise RuntimeRejected("receipts may only be written as JSON under runtime_receipts")
    if path.exists():
        raise RuntimeRejected("existing runtime receipt must not be overwritten")
    path.parent.mkdir(parents=True, exist_ok=True)
    result.receipt_path = str(path)
    with path.open("x", encoding="utf-8") as stream:
        json.dump({"schema_version": 2, "engineering_only_no_fit": True, "runtime_sha256": _runtime_hash(), "frozen_geometry_sha256": FROZEN_GEOMETRY_SHA256, "optional_closest_neighbors_rule": HELPER_RULE, **asdict(result)}, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def validate_proposal(code, feature_names, *, invariant_records=None, timeout_s=DEFAULT_TIMEOUT_S, memory_mb=DEFAULT_MEMORY_MB, receipt_path=None):
    """AST + general geometry invariance. Arbitrary formulas; no model fit."""
    started = time.perf_counter()
    result = ValidationResult(False, "rejected", _code_hash(code))
    try:
        names = validate_feature_names(feature_names)
        result.feature_names = names
        ast_info = check_ast(code)
        real_records = list(invariant_records) if invariant_records is not None else []
        if len(real_records) > 8:
            raise RuntimeRejected("invariance input allows at most 8 extra input-only records")
        fixtures = geometry_fixtures()
        base_records = fixtures + real_records
        transformed, checks, base_positions = [], [], []
        geometry_checks = 0
        for index, record in enumerate(base_records):
            validate_structure(record)
            base_positions.append(len(transformed))
            transformed.append(record)
            checks.append((index, "base"))
            for kind in TRANSFORMATIONS:
                altered = transform_structure(record, kind)
                validate_structure(altered)
                if not np.allclose(_geometry_invariants(altered), _geometry_invariants(record), rtol=1e-10, atol=1e-8):
                    raise RuntimeRejected(f"trusted geometry transform {kind} failed input-only sanity check")
                geometry_checks += 1
                transformed.append(altered)
                checks.append((index, kind))
        outputs, worker_metrics = run_isolated(code, transformed, feature_names=names, timeout_s=timeout_s, memory_mb=memory_mb)
        max_residual, max_scaled_residual = 0.0, 0.0
        for pos, (source_index, kind) in enumerate(checks):
            reference = outputs[base_positions[source_index]]
            delta = np.abs(outputs[pos]-reference)
            residual = float(np.max(delta))
            scaled = delta/(INVARIANCE_ATOL + INVARIANCE_RTOL*np.abs(reference))
            max_residual = max(max_residual, residual)
            max_scaled_residual = max(max_scaled_residual, float(np.max(scaled)))
            if not np.allclose(outputs[pos], reference, rtol=INVARIANCE_RTOL, atol=INVARIANCE_ATOL):
                failed = [names[column] for column in np.flatnonzero(scaled > 1)]
                advice = "aggregate site statistics per atom; raw n_sites, cell volume, or all-atom sums change under cell replication" if kind == "supercell_2x1x1" else "use periodic Cartesian relative vectors and permutation-invariant aggregations rather than cell axes, absolute coordinates, or site order"
                raise RuntimeRejected(f"{kind} invariance failed on input {source_index}; columns={failed}; max_absolute_difference={residual:.8g}; {advice}")
        # A valid representation is a function of one structure, never of the
        # preceding structure, process lifetime, batch partition, or row order.
        # Same exact input must repeat bit-for-bit; invariance tolerances apply
        # only to the deliberately transformed coordinates above.
        reference_rows = outputs[np.asarray(base_positions,dtype=int)]
        subprocess_metrics = [worker_metrics]
        repeated_checks = 0
        probe_groups = [
            ("forward_reverse", base_records + list(reversed(base_records)), np.concatenate([reference_rows,reference_rows[::-1]],axis=0)),
            ("first_partition",base_records[:len(base_records)//2],reference_rows[:len(base_records)//2]),
            ("second_partition",base_records[len(base_records)//2:],reference_rows[len(base_records)//2:]),
        ]
        probe_groups.extend((f"singleton_{index}",[record],reference_rows[index:index+1]) for index,record in enumerate(base_records))
        for probe_name, probe_records, expected in probe_groups:
            repeated, probe_metrics = run_isolated(code,probe_records,feature_names=names,timeout_s=timeout_s,memory_mb=memory_mb)
            subprocess_metrics.append({"probe_kind":probe_name,**probe_metrics})
            if not np.array_equal(repeated,expected):
                failed = [names[column] for column in np.flatnonzero(np.any(repeated!=expected,axis=0))]
                raise RuntimeRejected(f"batch independence failed for {probe_name}; columns={failed}; compute must depend only on its supplied structure, with no mutable shared state or uninitialized arrays")
            repeated_checks += len(probe_records)
        result.accepted, result.status = True, "proposal_validated_no_fit"
        result.metrics = {**ast_info, "runtime_sha256": _runtime_hash(), "frozen_geometry_sha256": FROZEN_GEOMETRY_SHA256, "geometry_fixtures": len(fixtures), "prescribed_descriptor_answers": False, "invariant_real_records": len(real_records), "invariant_base_records": len(base_records), "invariant_variants": len(transformed), "trusted_geometry_checks": geometry_checks, "transformations": list(TRANSFORMATIONS), "invariance_rtol": INVARIANCE_RTOL, "invariance_atol": INVARIANCE_ATOL, "max_invariance_absolute_residual": max_residual, "max_invariance_scaled_residual": max_scaled_residual, "batch_independence_verified": True, "batch_independence_exact_row_checks": repeated_checks, "batch_independence_subprocesses": len(probe_groups), "batch_independence_probe_kinds": [item[0] for item in probe_groups], "subprocesses": subprocess_metrics, "model_fits": 0}
    except (ProposalRejected, RuntimeRejected, ValueError, TypeError, KeyError) as exc:
        result.reasons.append(str(exc)[:2000])
    result.metrics["validation_wall_seconds"] = time.perf_counter()-started
    _write_receipt(result, receipt_path)
    return result


def compute_validated(code, structures, *, feature_names, original_feature_rows, validation=None, batch_size=64, timeout_s=DEFAULT_TIMEOUT_S, memory_mb=DEFAULT_MEMORY_MB, whole_compute_deadline_s=300., receipt_path=None):
    """Compute aligned 4..32 new features and reject uninformative columns.

    old42 rows are trusted-parent checks only; they never enter the worker.
    Caller must save the submitted source and names before invoking this API.
    """
    started = time.perf_counter()
    names = validate_feature_names(feature_names)
    if not (1 <= whole_compute_deadline_s <= 1800):
        raise RuntimeRejected("whole_compute_deadline_s outside 1..1800")
    if validation is None:
        validation = validate_proposal(code, names, timeout_s=timeout_s, memory_mb=memory_mb)
    if not validation.accepted or validation.code_sha256 != _code_hash(code) or validation.feature_names != names:
        raise RuntimeRejected("code and ordered feature_names have no matching accepted proposal validation")
    runtime_hash = _runtime_hash()
    if validation.metrics.get("runtime_sha256") != runtime_hash or validation.metrics.get("frozen_geometry_sha256") != FROZEN_GEOMETRY_SHA256:
        raise RuntimeRejected("runtime or frozen geometry changed after validation")
    if validation.metrics.get("batch_independence_verified") is not True:
        raise RuntimeRejected("proposal has no verified batch independence probes")
    records = list(structures)
    if not records or len(records) > 2879 or len({record["material_id"] for record in records}) != len(records):
        raise RuntimeRejected("development records must have unique IDs, at most 2879")
    old = np.asarray(original_feature_rows, dtype=float)
    if old.shape != (len(records), 42) or not np.isfinite(old).all():
        raise RuntimeRejected("old feature check requires aligned finite original42 only")
    if not (1 <= batch_size <= 128):
        raise RuntimeRejected("batch_size outside 1..128")
    matrices, timings = [], []
    for offset in range(0, len(records), batch_size):
        remaining = whole_compute_deadline_s-(time.perf_counter()-started)
        if remaining < .1:
            raise RuntimeRejected("whole compute deadline exceeded")
        values, metrics = run_isolated(code, records[offset:offset+batch_size], feature_names=names, timeout_s=min(timeout_s,remaining), memory_mb=memory_mb)
        matrices.append(values); timings.append(metrics)
        if time.perf_counter()-started > whole_compute_deadline_s:
            raise RuntimeRejected("whole compute deadline exceeded")
    matrix = np.concatenate(matrices, axis=0)
    constants = [names[column] for column in range(len(names)) if np.max(matrix[:,column]) == np.min(matrix[:,column])]
    duplicates = [{"new_column": names[column], "old_column_index": old_col} for column in range(len(names)) for old_col in range(42) if np.array_equal(matrix[:,column], old[:,old_col])]
    internal = [{"left": names[left], "right": names[right]} for left in range(len(names)) for right in range(left+1,len(names)) if np.array_equal(matrix[:,left], matrix[:,right])]
    if constants or duplicates or internal:
        raise RuntimeRejected(f"uninformative columns: constants={constants}, exact_old42_duplicates={duplicates}, internal_duplicates={internal}; replace or remove each named column while keeping 4..32 total")
    id_hash = hashlib.sha256(json.dumps([record["material_id"] for record in records], ensure_ascii=False, separators=(",",":")).encode("utf-8")).hexdigest()
    result = ValidationResult(True, "development_matrix_validated_no_fit", _code_hash(code), names, metrics={"rows": len(records), "columns": len(names), "runtime_sha256": runtime_hash, "frozen_geometry_sha256": FROZEN_GEOMETRY_SHA256, "ordered_material_ids_sha256": id_hash, "matrix_float64_le_sha256": hashlib.sha256(matrix.astype("<f8",copy=False).tobytes(order="C")).hexdigest(), "subprocesses": timings, "total_wall_seconds": time.perf_counter()-started, "whole_compute_deadline_s": whole_compute_deadline_s, "constant_columns": constants, "exact_old42_duplicates": duplicates, "internal_duplicates": internal, "numeric_target_access": False, "real_material_ids_sent_to_worker": False, "model_fits": 0})
    _write_receipt(result, receipt_path)
    return matrix, result


if __name__ == "__main__":
    if sys.argv[1:] != ["--worker"]:
        raise SystemExit("Library API only; trusted parent uses --worker.")
    try:
        response = _worker_main()
    except Exception as exc:
        response = {"status": "error", "reason": f"{type(exc).__name__}: {str(exc)[:1800]}"}
    sys.stdout.write(json.dumps(response, allow_nan=False, separators=(",",":")))
