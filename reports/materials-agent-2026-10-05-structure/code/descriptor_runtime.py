"""Controlled, label-free execution of Agent-submitted structural descriptors.

The trusted helper only selects periodic neighbor vectors. It does not compute
the final 16 angular columns. The Agent must submit compute(structure) itself.
This is an allowlisted execution boundary, not a general Python sandbox.
"""
from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from types import MappingProxyType
from typing import Any

import numpy as np

FEATURE_NAMES = tuple([f"angular_G{i:02d}" for i in range(1, 9)] + [f"angular_N{i:02d}" for i in range(1, 5)] + [f"angular_O{i:02d}" for i in range(1, 5)])
STRUCTURE_FIELDS = frozenset({"atomic_numbers", "covalent_radii", "distance_matrix", "electronegativities", "frac_coords", "lattice", "material_id", "n_sites", "neighbor_center", "neighbor_distance", "neighbor_image", "neighbor_index", "symbols", "volume"})
HELPER_RULE = {"k": 12, "radius_A": 6.0, "distance_tie_tolerance_A": 1e-8, "zero_distance_threshold_A": 1e-10, "max_selected_neighbors_per_site": 256, "max_unordered_pairs_per_site": 32640}
RUNTIME_ROOT = Path(__file__).resolve().parent
MAX_CODE_BYTES = 32768
MAX_AST_NODES = 5000
DEFAULT_TIMEOUT_S = 20.0
DEFAULT_MEMORY_MB = 768

SAFE_BUILTINS = {"abs": abs, "all": all, "any": any, "bool": bool, "dict": dict, "enumerate": enumerate, "float": float, "int": int, "len": len, "list": list, "max": max, "min": min, "range": range, "reversed": reversed, "round": round, "set": set, "sorted": sorted, "sum": sum, "tuple": tuple, "zip": zip, "ValueError": ValueError}
NP_NAMES = frozenset("abs absolute all allclose amax amin any arange argmax argmin argsort array asarray bincount ceil clip column_stack concatenate cos count_nonzero cross cumsum diag dot einsum empty equal exp eye finfo float32 float64 floor full histogram hstack inner int32 int64 isclose isfinite isin isnan linspace logical_and logical_not logical_or matmul max maximum mean median min minimum nan_to_num nanmean nanstd nansum nanvar newaxis ones outer pi power prod ravel rint round searchsorted sign sin sort sqrt stack std sum take transpose triu_indices unique var vstack where zeros".split())
NP_LINALG_NAMES = frozenset({"det", "eigvalsh", "norm", "svd"})
MATH_NAMES = frozenset("acos asin atan atan2 ceil cos exp fabs floor fsum isfinite log log1p pi pow sin sqrt tan tau".split())
ARRAY_ATTRIBUTES = frozenset("T astype copy dtype item max mean min ndim ravel reshape shape size squeeze std sum tolist transpose var eps tiny".split())
ALLOWED_NODE_TYPES = {
    ast.Module, ast.Import, ast.ImportFrom, ast.alias, ast.FunctionDef, ast.arguments, ast.arg,
    ast.Return, ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Expr, ast.If, ast.For, ast.Pass,
    ast.Break, ast.Continue, ast.Raise, ast.Assert, ast.Name, ast.Constant, ast.List, ast.Tuple,
    ast.Dict, ast.Set, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.comprehension,
    ast.Subscript, ast.Slice, ast.Call, ast.Attribute, ast.keyword, ast.BinOp, ast.UnaryOp,
    ast.BoolOp, ast.Compare, ast.IfExp, ast.Lambda, ast.Load, ast.Store,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.MatMult,
    ast.UAdd, ast.USub, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt, ast.LtE,
    ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot, ast.BitAnd, ast.BitOr,
}


class ProposalRejected(ValueError):
    pass


class RuntimeRejected(RuntimeError):
    pass


@dataclass
class ValidationResult:
    accepted: bool
    status: str
    code_sha256: str
    feature_names: list[str] = field(default_factory=lambda: list(FEATURE_NAMES))
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    receipt_path: str | None = None


def _code_hash(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _attribute_path(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return [node.id, *reversed(parts)]
    return None


def check_ast(code: str) -> dict:
    """Reject filesystem, network, process, reflection and executable indirection."""
    if not isinstance(code, str) or len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise ProposalRejected("code must be UTF-8 text of at most 32768 bytes")
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise ProposalRejected(f"invalid Python syntax at line {exc.lineno}") from None
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_AST_NODES:
        raise ProposalRejected("AST node limit exceeded")
    functions = {node.name for node in nodes if isinstance(node, ast.FunctionDef)}
    if "compute" not in functions:
        raise ProposalRejected("submit def compute(structure)")
    computes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "compute"]
    if len(computes) != 1 or len(computes[0].args.args) != 1 or computes[0].args.args[0].arg != "structure" or computes[0].args.defaults or computes[0].args.kwonlyargs or computes[0].args.vararg or computes[0].args.kwarg:
        raise ProposalRejected("compute must be a single top-level function with exactly argument structure")
    for node in nodes:
        if type(node) not in ALLOWED_NODE_TYPES:
            raise ProposalRejected(f"AST construct {type(node).__name__} is not allowed")
        if isinstance(node, (ast.Name, ast.arg)):
            name = node.id if isinstance(node, ast.Name) else node.arg
            if "__" in name or name in {"eval", "exec", "open", "compile", "getattr", "setattr", "delattr", "globals", "locals", "vars", "dir", "type", "object", "input", "print", "help", "breakpoint", "memoryview", "bytes", "bytearray", "super"}:
                raise ProposalRejected(f"name {name!r} is not allowed")
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and name in {"np", "math", "closest_neighbors"}:
                raise ProposalRejected("trusted names cannot be rebound")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "__" in node.value:
            raise ProposalRejected("dunder strings are not allowed")
        if isinstance(node, ast.Constant) and node.value == "material_id":
            raise ProposalRejected("material_id is alignment metadata and cannot be a descriptor input")
        if isinstance(node, ast.FunctionDef):
            if "__" in node.name or node.name in SAFE_BUILTINS or node.name in {"np", "math", "closest_neighbors"} or node.decorator_list:
                raise ProposalRejected("invalid function name or decorator")
            if node.args.vararg or node.args.kwarg:
                raise ProposalRejected("variadic functions are not allowed")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if (alias.name, alias.asname) not in {("numpy", "np"), ("math", None), ("math", "math")}:
                    raise ProposalRejected("imports are limited to import numpy as np and import math")
        if isinstance(node, ast.ImportFrom):
            permitted = NP_NAMES if node.module == "numpy" else MATH_NAMES if node.module == "math" else frozenset()
            if node.level or not permitted or any(alias.name not in permitted or alias.asname not in {None, alias.name} for alias in node.names):
                raise ProposalRejected("from-import is outside the numpy/math allowlist")
        if isinstance(node, ast.Attribute):
            if "__" in node.attr:
                raise ProposalRejected("dunder attributes are not allowed")
            path = _attribute_path(node)
            if path and path[0] == "np":
                if path not in [["np", name] for name in NP_NAMES] + [["np", "linalg"]] + [["np", "linalg", name] for name in NP_LINALG_NAMES]:
                    raise ProposalRejected("numpy attribute is outside allowlist")
            elif path and path[0] == "math":
                if len(path) != 2 or path[1] not in MATH_NAMES:
                    raise ProposalRejected("math attribute is outside allowlist")
            elif node.attr not in ARRAY_ATTRIBUTES:
                raise ProposalRejected(f"attribute {node.attr!r} is outside array allowlist")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                imported = {alias.name for item in nodes if isinstance(item, ast.ImportFrom) for alias in item.names}
                if node.func.id not in set(SAFE_BUILTINS) | functions | imported | {"closest_neighbors"}:
                    raise ProposalRejected(f"call {node.func.id!r} is not allowed; callable aliases are prohibited")
            elif not isinstance(node.func, ast.Attribute):
                raise ProposalRejected("indirect callable expressions are not allowed")
            if any(keyword.arg is None for keyword in node.keywords):
                raise ProposalRejected("expanded call keywords are not allowed")
        if isinstance(node, ast.comprehension) and node.is_async:
            raise ProposalRejected("async comprehensions are not allowed")
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if any(isinstance(part, ast.Attribute) for part in ast.walk(target)):
                    raise ProposalRejected("attribute assignment is not allowed")
    return {"ast_nodes": len(nodes), "code_bytes": len(code.encode("utf-8")), "functions": sorted(functions)}


def validate_structure(record):
    """Require exactly the 14 input fields; never tolerate extra label fields."""
    if set(record) != STRUCTURE_FIELDS:
        raise RuntimeRejected("structure must contain exactly the 14 input-only fields")
    n = record["n_sites"]
    if isinstance(n, bool) or int(n) != n or n < 1:
        raise RuntimeRejected("invalid n_sites")
    n = int(n)
    frac = np.asarray(record["frac_coords"], dtype=float)
    lattice = np.asarray(record["lattice"], dtype=float)
    if frac.shape != (n, 3) or lattice.shape != (3, 3) or not np.isfinite(frac).all() or not np.isfinite(lattice).all():
        raise RuntimeRejected("invalid coordinates or lattice")
    if not np.isfinite(float(record["volume"])) or float(record["volume"]) <= 0 or not np.isclose(abs(np.linalg.det(lattice)), record["volume"], rtol=1e-10, atol=1e-8):
        raise RuntimeRejected("volume and lattice disagree")
    for name in ("atomic_numbers", "covalent_radii", "electronegativities", "symbols"):
        if len(record[name]) != n:
            raise RuntimeRejected("site array length mismatch")
    if np.asarray(record["distance_matrix"]).shape != (n, n):
        raise RuntimeRejected("distance_matrix shape mismatch")
    raw_c = np.asarray(record["neighbor_center"])
    raw_j = np.asarray(record["neighbor_index"])
    raw_im = np.asarray(record["neighbor_image"], dtype=float).reshape(-1, 3)
    c, j, im = raw_c.astype(int), raw_j.astype(int), raw_im.astype(int)
    d = np.asarray(record["neighbor_distance"], dtype=float)
    if c.ndim != 1 or j.ndim != 1 or d.ndim != 1 or not (len(c) == len(j) == len(im) == len(d)):
        raise RuntimeRejected("neighbor arrays disagree")
    if not np.array_equal(raw_c, c) or not np.array_equal(raw_j, j) or not np.array_equal(raw_im, im):
        raise RuntimeRejected("neighbor indices/images must be integers")
    if np.any((c < 0) | (c >= n)) or np.any((j < 0) | (j >= n)) or not np.isfinite(d).all() or np.any(d < 0):
        raise RuntimeRejected("invalid neighbor indices or distances")
    rebuilt = np.linalg.norm((frac[j] + im - frac[c]) @ lattice, axis=1)
    if not np.allclose(rebuilt, d, rtol=1e-10, atol=1e-8):
        raise RuntimeRejected("periodic neighbor image/distance mismatch")


def closest_neighbors(structure):
    """Return vectors by center, within 6A and 12-nearest including all ties.

    Zero-distance edges are excluded. Nonzero self-images remain valid. This
    does not compute angles, angular bins, N/O statistics or final features.
    """
    validate_structure(structure)
    frac = np.asarray(structure["frac_coords"], dtype=float)
    lattice = np.asarray(structure["lattice"], dtype=float)
    c = np.asarray(structure["neighbor_center"], dtype=int)
    j = np.asarray(structure["neighbor_index"], dtype=int)
    images = np.asarray(structure["neighbor_image"], dtype=int).reshape(-1, 3)
    d = np.asarray(structure["neighbor_distance"], dtype=float)
    vectors = (frac[j] + images - frac[c]) @ lattice
    output = []
    for center in range(int(structure["n_sites"])):
        selected = np.flatnonzero((c == center) & (d > 1e-10) & (d <= 6.0 + 1e-8))
        if len(selected) > 12:
            boundary = float(np.partition(d[selected], 11)[11])
            selected = selected[d[selected] <= boundary + 1e-8]
        if len(selected) > 256:
            raise RuntimeRejected("neighbor resource cap exceeded: no silent truncation")
        # Stable order aids audit; all tied edges are preserved, not tie-broken.
        selected = selected[np.argsort(d[selected], kind="stable")]
        output.append(tuple(tuple(float(value) for value in vectors[index]) for index in selected))
    return tuple(output)


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name not in {"numpy", "math"}:
        raise ProposalRejected("runtime import rejected")
    return np if name == "numpy" else math


def _worker_main():
    # This trusted loader reads only the input payload supplied by the parent.
    request = json.load(sys.stdin)
    code = request["code"]
    check_ast(code)
    builtins = {**SAFE_BUILTINS, "__import__": _safe_import}
    namespace = {"__builtins__": builtins, "np": np, "math": math, "closest_neighbors": closest_neighbors}
    exec(compile(code, "<agent-descriptor>", "exec"), namespace, namespace)
    outputs = []
    helper_calls = 0
    start = time.perf_counter()
    for record in request["records"]:
        validate_structure(record)
        # Ensure every record's fixed neighbor rule/cap is validated, whether or
        # not submitted compute calls the helper itself.
        closest_neighbors(record)
        helper_calls += 1
        # Real IDs are kept by the trusted parent for row alignment only. The
        # proposal never receives them, even through constructed string keys.
        input_record = {**record, "material_id": "redacted-input-id"}
        result = np.asarray(namespace["compute"](_freeze(input_record)))
        if result.shape != (16,) or result.dtype.kind not in "iuf" or not np.isfinite(result).all():
            raise RuntimeRejected("compute must return a finite numeric vector of shape (16,)")
        outputs.append(result.astype(float).tolist())
    return {"status": "ok", "values": outputs, "worker_compute_seconds": time.perf_counter() - start, "records": len(outputs), "trusted_prechecks": helper_calls}


class _WindowsJob:
    """Kill-on-close + process memory/CPU/child-count limit on Windows."""
    def __init__(self, process, memory_mb, timeout_s):
        import ctypes
        from ctypes import wintypes
        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
        class EXTENDED(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.SetInformationJobObject.restype = wintypes.BOOL
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise RuntimeRejected("cannot create Windows isolation JobObject")
        config = EXTENDED()
        config.BasicLimitInformation.LimitFlags = 0x0002 | 0x0008 | 0x0100 | 0x2000
        config.BasicLimitInformation.PerProcessUserTimeLimit = int(math.ceil(timeout_s + 2) * 10_000_000)
        config.BasicLimitInformation.ActiveProcessLimit = 1
        config.ProcessMemoryLimit = int(memory_mb * 1024**2)
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(config), ctypes.sizeof(config)):
            self.close()
            raise RuntimeRejected("cannot set Windows process resource limits")
        process_handle = self.kernel.OpenProcess(0x0100 | 0x0001, False, process.pid)
        assigned = process_handle and self.kernel.AssignProcessToJobObject(self.handle, process_handle)
        if process_handle:
            self.kernel.CloseHandle(process_handle)
        if not assigned:
            self.close()
            raise RuntimeRejected("cannot attach descriptor process to resource JobObject")

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def _posix_preexec(memory_mb, timeout_s):
    def limits():
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (int(memory_mb * 1024**2), int(memory_mb * 1024**2)))
        resource.setrlimit(resource.RLIMIT_CPU, (int(math.ceil(timeout_s + 2)), int(math.ceil(timeout_s + 2))))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    return limits


def run_isolated(code, records, *, timeout_s=DEFAULT_TIMEOUT_S, memory_mb=DEFAULT_MEMORY_MB):
    """No fit. Worker can only receive explicit label-free structures in stdin."""
    ast_info = check_ast(code)
    if not (0.1 <= timeout_s <= 300) or not (128 <= memory_mb <= 2048):
        raise RuntimeRejected("runtime resource configuration outside bounds")
    records = list(records)
    if not records or len(records) > 128:
        raise RuntimeRejected("isolation batch must contain 1..128 input records")
    for record in records:
        validate_structure(record)
    payload = json.dumps({"code": code, "records": records}, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(payload) > 64 * 1024**2:
        raise RuntimeRejected("input payload exceeds 64 MiB per isolated batch")
    # Do not inherit auth or arbitrary user environment into the descriptor worker.
    env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "TEMP", "TMP", "PATH") if name in os.environ}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
    kwargs = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "cwd": str(RUNTIME_ROOT), "env": env}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        kwargs["preexec_fn"] = _posix_preexec(memory_mb, timeout_s)
    started = time.perf_counter()
    # Windows virtualenv executables may be redirectors which launch another
    # process. Launch the real interpreter directly so a one-process JobObject
    # encloses all execution; add only this trusted NumPy installation path.
    runtime_file = str(Path(__file__).resolve())
    trusted_site = str(Path(np.__file__).resolve().parent.parent)
    bootstrap = f"import sys,runpy;sys.path.insert(0,{trusted_site!r});sys.argv=[{runtime_file!r},'--worker'];runpy.run_path({runtime_file!r},run_name='__main__')"
    interpreter = getattr(sys, "_base_executable", None) or sys.executable
    process = subprocess.Popen([interpreter, "-I", "-B", "-X", "utf8", "-c", bootstrap], **kwargs)
    job = None
    try:
        # Child waits for stdin. No submitted code is sent until JobObject limits attach.
        if os.name == "nt":
            job = _WindowsJob(process, memory_mb, timeout_s)
        try:
            stdout, stderr = process.communicate(payload, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            if job:
                job.close()
            process.kill()
            process.communicate()
            raise RuntimeRejected("descriptor subprocess wall timeout exceeded") from None
        if len(stdout) > 512 * 1024 or len(stderr) > 64 * 1024:
            raise RuntimeRejected("descriptor worker output exceeds cap")
        if process.returncode:
            raise RuntimeRejected(f"descriptor worker failed or resource limit exceeded (exit {process.returncode})")
        try:
            response = json.loads(stdout.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise RuntimeRejected("invalid descriptor worker response") from None
        if response.get("status") != "ok":
            raise RuntimeRejected(response.get("reason", "worker rejected")[:2000])
        values = np.asarray(response["values"], dtype=float)
        if values.shape != (len(records), 16) or not np.isfinite(values).all():
            raise RuntimeRejected("worker matrix format is invalid")
        metrics = {"wall_seconds": time.perf_counter() - started, "worker_compute_seconds": response["worker_compute_seconds"], "records": len(records), "timeout_s": timeout_s, "memory_limit_MB": memory_mb, "memory_enforcement": "Windows JobObject" if os.name == "nt" else "POSIX RLIMIT_AS", "hidden_process": os.name == "nt", "thread_limit": 1, **ast_info}
        return values, metrics
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        if job:
            job.close()


def _clone(record):
    return json.loads(json.dumps(record))


def transform_structure(record, kind):
    """Label-blind invariance transformations preserving physical environments."""
    out = _clone(record)
    n = int(out["n_sites"])
    frac = np.asarray(out["frac_coords"], dtype=float)
    lattice = np.asarray(out["lattice"], dtype=float)
    c = np.asarray(out["neighbor_center"], dtype=int)
    j = np.asarray(out["neighbor_index"], dtype=int)
    images = np.asarray(out["neighbor_image"], dtype=int).reshape(-1, 3)
    if kind == "rotation":
        a, b = 0.713, 0.391
        rz = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
        ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
        out["lattice"] = (lattice @ (rz @ ry).T).tolist()
    elif kind == "translation_wrap":
        shifted = frac + np.array([0.713, -0.337, 1.291])
        wraps = np.floor(shifted).astype(int)
        out["frac_coords"] = (shifted - wraps).tolist()
        out["neighbor_image"] = (images + wraps[j] - wraps[c]).tolist()
    elif kind == "atom_and_edge_permutation":
        perm = np.arange(n)[::-1]
        inv = np.argsort(perm)
        for name in ("frac_coords", "atomic_numbers", "symbols", "covalent_radii", "electronegativities"):
            out[name] = [out[name][int(index)] for index in perm]
        out["distance_matrix"] = np.asarray(out["distance_matrix"])[np.ix_(perm, perm)].tolist()
        out["neighbor_center"] = inv[c][::-1].tolist()
        out["neighbor_index"] = inv[j][::-1].tolist()
        out["neighbor_image"] = images[::-1].tolist()
        out["neighbor_distance"] = out["neighbor_distance"][::-1]
    elif kind == "equivalent_basis":
        basis = np.array([[1, 1, 0], [0, 1, 0], [0, 0, 1]], dtype=int)
        inverse = np.array([[1, -1, 0], [0, 1, 0], [0, 0, 1]], dtype=int)
        raw_frac = frac @ inverse
        wraps = np.floor(raw_frac).astype(int)
        out["frac_coords"] = (raw_frac - wraps).tolist()
        out["lattice"] = (basis @ lattice).tolist()
        out["neighbor_image"] = (images @ inverse + wraps[j] - wraps[c]).tolist()
    elif kind == "supercell_2x1x1":
        scale = np.array([2, 1, 1], dtype=int)
        cells = [np.array([0, 0, 0]), np.array([1, 0, 0])]
        out["n_sites"] = 2 * n
        out["volume"] *= 2
        out["lattice"] = (np.diag(scale) @ lattice).tolist()
        out["frac_coords"] = np.concatenate([(frac + cell) / scale for cell in cells]).tolist()
        for name in ("atomic_numbers", "symbols", "covalent_radii", "electronegativities"):
            out[name] = out[name] * 2
        nc, nj, ni, nd = [], [], [], []
        for cell_index, cell in enumerate(cells):
            neighbor_cell_raw = cell + images
            neighbor_cell = np.mod(neighbor_cell_raw, scale)
            new_images = np.floor_divide(neighbor_cell_raw, scale)
            nc.extend((cell_index * n + c).tolist())
            nj.extend((neighbor_cell[:, 0] * n + j).tolist())
            ni.extend(new_images.tolist())
            nd.extend(out["neighbor_distance"])
        out["neighbor_center"], out["neighbor_index"], out["neighbor_image"], out["neighbor_distance"] = nc, nj, ni, nd
        # Input distance matrix remains geometric. For this fixed doubled cell,
        # reconstruct minimum images using a sufficient inverse-lattice bound.
        new_frac = np.asarray(out["frac_coords"])
        new_lattice = np.asarray(out["lattice"])
        matrix = np.empty((2*n, 2*n))
        for i in range(2*n):
            for k in range(2*n):
                delta = new_frac[k] - new_frac[i]
                nearest = np.rint(delta)
                # Minimum in a skew cell may extend beyond +/-1; bound from
                # initial distance and reciprocal row lengths, rather than guess.
                bound = np.linalg.norm((delta-nearest) @ new_lattice)
                recip = np.linalg.norm(np.linalg.inv(new_lattice), axis=0)
                lo = np.ceil(-delta - bound*recip - 1e-10).astype(int)
                hi = np.floor(-delta + bound*recip + 1e-10).astype(int)
                ranges = [range(lo[t], hi[t]+1) for t in range(3)]
                if math.prod(len(item) for item in ranges) > 100000:
                    raise RuntimeRejected("supercell validation lattice bound exceeds resource cap")
                candidates = np.array([(x,y,z) for x in ranges[0] for y in ranges[1] for z in ranges[2]], dtype=float)
                matrix[i,k] = np.min(np.linalg.norm((delta + candidates) @ new_lattice, axis=1))
        out["distance_matrix"] = matrix.tolist()
    else:
        raise ValueError("unknown transformation")
    validate_structure(out)
    return out


def semantic_fixtures():
    """Fixed geometry/expected answers, not a general descriptor implementation."""
    def make(symbols, zs, per_site_images):
        n = len(symbols)
        frac = [[0.25*i, 0.25*i, 0.25*i] for i in range(n)]
        c, j, images, d = [], [], [], []
        for site, site_images in enumerate(per_site_images):
            for image in site_images:
                c.append(site); j.append(site); images.append(image)
                d.append(float(np.linalg.norm(np.asarray(image)*2)))
        matrix = np.linalg.norm((np.asarray(frac)[:,None,:]-np.asarray(frac)[None,:,:])*2, axis=-1).tolist()
        return {"atomic_numbers": zs, "covalent_radii": [1.0]*n, "distance_matrix": matrix, "electronegativities": [3.0]*n, "frac_coords": frac, "lattice": [[2.,0.,0.],[0.,2.,0.],[0.,0.,2.]], "material_id": "synthetic", "n_sites": n, "neighbor_center": c, "neighbor_distance": d, "neighbor_image": images, "neighbor_index": j, "symbols": symbols, "volume": 8.0}
    axes = [[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]]
    rows = [make(["N"],[7],[axes]), make(["O"],[8],[axes]), make(["H"],[1],[[]]), make(["N","O"],[7,8],[[[1,0,0],[-1,0,0]],[[1,0,0],[0,1,0]]])]
    expected = np.array([
        [.2,0,.8,0, 0,0,0,0, .2,0,.8,0, 0,0,0,0],
        [.2,0,.8,0, 0,0,0,0, 0,0,0,0, .2,0,.8,0],
        [0]*16,
        [.5,0,.5,0, .25,0,.25,0, 1,0,0,0, 0,0,1,0],
    ], dtype=float)
    # Exact angular bin boundaries: -0.5 belongs to bin2, +0.5 to bin4.
    for cosine, column in [(-.5, 1), (.5, 3)]:
        record = make(["N"], [7], [[[1,0,0], [0,1,0]]])
        record["lattice"] = [[2.,0.,0.], [2*cosine, math.sqrt(3), 0.], [0.,0.,2.]]
        record["volume"] = 4*math.sqrt(3)
        row = np.zeros(16); row[column] = 1.; row[8+column] = 1.
        rows.append(record); expected = np.vstack([expected, row])
    # Unequal pair counts: aggregate site histograms equally, not pooled pairs.
    record = make(["N", "O"], [7,8], [axes, [[1,0,0],[-1,0,0]]])
    rows.append(record)
    expected = np.vstack([expected, [.6,0,.4,0, .16,0,.16,0, .2,0,.8,0, 1,0,0,0]])
    # The 12th neighbor lies in a 12-fold sqrt(2) shell after 6 axial neighbors.
    # All 18 must remain. Analytically its 153 pairs have bins 33,24,48,48.
    shell = [list(image) for image in ((x,y,z) for x in (-1,0,1) for y in (-1,0,1) for z in (-1,0,1)) if sum(value*value for value in image) in (1,2)]
    record = make(["N"], [7], [shell])
    # Lattice length2: sqrt(2) shell remains within6A, third shell excluded by k12.
    rows.append(record)
    tie_hist = np.array([33.,24.,48.,48.]) / 153.
    expected = np.vstack([expected, np.concatenate([tie_hist, np.zeros(4), tie_hist, np.zeros(4)])])
    return rows, expected


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
    payload = {"schema_version": 1, "engineering_only_no_fit": True, "runtime_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "helper_rule": HELPER_RULE, **asdict(result)}
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def validate_proposal(code, *, invariant_records=None, timeout_s=DEFAULT_TIMEOUT_S, memory_mb=DEFAULT_MEMORY_MB, receipt_path=None):
    """AST + fixed semantic fixtures + geometric invariance; never fits a model."""
    started = time.perf_counter()
    result = ValidationResult(False, "rejected", _code_hash(code))
    try:
        ast_info = check_ast(code)
        fixtures, expected = semantic_fixtures()
        real_records = list(invariant_records) if invariant_records is not None else []
        if len(real_records) > 8:
            raise RuntimeRejected("invariance input allows at most8 extra label-free records")
        # Goldens always receive all transformations, even at the real backend
        # entry point. Supplying real records must not replace boundary/tie cases.
        base_records = fixtures + real_records
        transformed = []
        checks = []
        for index, record in enumerate(base_records):
            validate_structure(record)
            transformed.append(record)
            checks.append((index, "base"))
            for kind in ("rotation", "translation_wrap", "atom_and_edge_permutation", "equivalent_basis", "supercell_2x1x1"):
                transformed.append(transform_structure(record, kind))
                checks.append((index, kind))
        rows, fixture_metrics = run_isolated(code, fixtures, timeout_s=timeout_s, memory_mb=memory_mb)
        if not np.allclose(rows, expected, rtol=0, atol=1e-10):
            raise RuntimeRejected("fixed angular semantic fixtures disagree (bins/zero/N/O/ddof0)")
        outputs, invariant_metrics = run_isolated(code, transformed, timeout_s=timeout_s, memory_mb=memory_mb)
        max_residual = 0.0
        for pos, (source_index, kind) in enumerate(checks):
            residual = float(np.max(np.abs(outputs[pos] - outputs[6*source_index])))
            max_residual = max(max_residual, residual)
            if not np.allclose(outputs[pos], outputs[6*source_index], rtol=0, atol=1e-9):
                raise RuntimeRejected(f"descriptor failed {kind} invariance")
        result.accepted, result.status = True, "proposal_validated_no_fit"
        result.metrics = {**ast_info, "runtime_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "semantic_fixtures": len(fixtures), "invariant_real_records": len(real_records), "invariant_base_records": len(base_records), "invariant_variants": len(transformed), "max_invariance_absolute_residual": max_residual, "subprocesses": [fixture_metrics, invariant_metrics]}
    except (ProposalRejected, RuntimeRejected, ValueError, TypeError, KeyError) as exc:
        result.reasons.append(str(exc)[:2000])
    result.metrics["validation_wall_seconds"] = time.perf_counter() - started
    _write_receipt(result, receipt_path)
    return result


def compute_validated(code, structures, *, original_feature_rows, validation=None, batch_size=64, timeout_s=DEFAULT_TIMEOUT_S, memory_mb=DEFAULT_MEMORY_MB, whole_compute_deadline_s=300., receipt_path=None):
    """Return (matrix, receipt); require the passed proposal and old42 check.

    Caller owns the exact development ID order. original_feature_rows must be
    a label-free numeric (rows,42) array in exactly that order. Nothing is fit.
    """
    started = time.perf_counter()
    if not (1 <= whole_compute_deadline_s <= 1800):
        raise RuntimeRejected("whole_compute_deadline_s outside1..1800")
    if validation is None:
        validation = validate_proposal(code, timeout_s=timeout_s, memory_mb=memory_mb)
    if not validation.accepted or validation.code_sha256 != _code_hash(code):
        raise RuntimeRejected("code has no matching accepted proposal validation")
    runtime_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if validation.metrics.get("runtime_sha256") != runtime_hash:
        raise RuntimeRejected("runtime changed after proposal validation")
    records = list(structures)
    if not records or len(records) > 2879 or len({record["material_id"] for record in records}) != len(records):
        raise RuntimeRejected("development records must have unique IDs, at most2879")
    old = np.asarray(original_feature_rows, dtype=float)
    if old.shape != (len(records), 42) or not np.isfinite(old).all():
        raise RuntimeRejected("old feature check requires aligned finite original42 only")
    if not (1 <= batch_size <= 128):
        raise RuntimeRejected("batch_size outside 1..128")
    matrices, timings = [], []
    for offset in range(0, len(records), batch_size):
        remaining = whole_compute_deadline_s - (time.perf_counter()-started)
        if remaining < .1:
            raise RuntimeRejected("whole compute deadline exceeded")
        values, metrics = run_isolated(code, records[offset:offset+batch_size], timeout_s=min(timeout_s, remaining), memory_mb=memory_mb)
        matrices.append(values); timings.append(metrics)
        if time.perf_counter()-started > whole_compute_deadline_s:
            raise RuntimeRejected("whole compute deadline exceeded")
    matrix = np.concatenate(matrices, axis=0)
    constants = [FEATURE_NAMES[col] for col in range(16) if np.max(matrix[:,col]) == np.min(matrix[:,col])]
    duplicates = [{"new_column": FEATURE_NAMES[col], "old_column_index": old_col} for col in range(16) for old_col in range(42) if np.array_equal(matrix[:,col], old[:,old_col])]
    internal_duplicates = [{"left": FEATURE_NAMES[left], "right": FEATURE_NAMES[right]} for left in range(16) for right in range(left+1,16) if np.array_equal(matrix[:,left], matrix[:,right])]
    if constants or duplicates or internal_duplicates:
        raise RuntimeRejected(f"uninformative columns: constants={constants}, exact_old42_duplicates={duplicates}, internal_duplicates={internal_duplicates}")
    id_order_hash = hashlib.sha256(json.dumps([record["material_id"] for record in records], ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    result = ValidationResult(True, "development_matrix_validated_no_fit", _code_hash(code), metrics={"rows": len(records), "columns": 16, "runtime_sha256": runtime_hash, "ordered_material_ids_sha256": id_order_hash, "matrix_float64_le_sha256": hashlib.sha256(matrix.astype("<f8", copy=False).tobytes(order="C")).hexdigest(), "subprocesses": timings, "total_wall_seconds": time.perf_counter()-started, "whole_compute_deadline_s": whole_compute_deadline_s, "constant_columns": constants, "exact_old42_duplicates": duplicates, "internal_duplicates": internal_duplicates, "numeric_target_access": False, "real_material_ids_exposed_to_compute": False, "model_fits": 0})
    _write_receipt(result, receipt_path)
    return matrix, result


if __name__ == "__main__":
    if sys.argv[1:] != ["--worker"]:
        raise SystemExit("Library API only; trusted parent uses --worker.")
    try:
        response = _worker_main()
    except Exception as exc:
        response = {"status": "error", "reason": f"{type(exc).__name__}: {str(exc)[:1800]}"}
    sys.stdout.write(json.dumps(response, allow_nan=False, separators=(",", ":")))
