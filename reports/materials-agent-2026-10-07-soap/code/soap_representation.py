"""Fixed, targetless periodic SOAP representation for the structure experiment.

The proposed contract is DScribe 2.1.2: GTO, r_cut=5 Angstrom, n_max=4,
l_max=3, sigma=0.5 Angstrom, outer averaging, mu1nu1 compression, and a
global species vocabulary Z=1..94. Each 6016-dimensional float64 vector is
L2-normalized independently. This module does no file I/O, fitting, PCA,
standardization, label access, installation, or dependency-path mutation.

The caller must register this source/configuration and verify the isolated
dependency lock before generating a real matrix. It supplies pure geometry
records and persists returned arrays/receipts in the new external stage.
The later learned adapter must fit StandardScaler and PCA(24) on each
training fold only, then append those 24 columns to the existing 66 columns.
Raw SOAP must never be passed directly to the 160-column learner kernel.

API: specification(), create_descriptor(), compute_one(record, descriptor),
and compute_matrix(records, expected_ids=..., descriptor=...). A descriptor
can be reused to avoid constructing the fixed basis for every material.

Official API: https://singroup.github.io/dscribe/latest/tutorials/descriptors/soap.html
Dimension: https://singroup.github.io/dscribe/latest/_modules/dscribe/descriptors/soap.html
"""

from __future__ import annotations

import hashlib
import json
from importlib import metadata
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np


DSCRIBE_VERSION = "2.1.2"
SPECIES = tuple(range(1, 95))
RAW_FEATURES = len(SPECIES) * 4 ** 2 * (3 + 1)
FEATURE_NAMES = tuple(f"SOAP_MU1NU1_{i:04d}" for i in range(RAW_FEATURES))
PURE_RECORD_KEYS = frozenset({
    "material_id", "n_sites", "volume", "symbols", "frac_coords", "lattice",
    "distance_matrix", "atomic_numbers", "electronegativities",
    "covalent_radii", "neighbor_center", "neighbor_index", "neighbor_distance",
    "neighbor_image",
})
REQUIRED_RECORD_KEYS = frozenset({
    "material_id", "atomic_numbers", "frac_coords", "lattice",
})


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def specification() -> dict[str, Any]:
    """Return an independent copy of the sole proposed descriptor contract."""
    return {
        "descriptor": "SOAP", "implementation": "dscribe",
        "implementation_version": DSCRIBE_VERSION,
        "periodic": True, "rbf": "gto", "r_cut": 5.0,
        "n_max": 4, "l_max": 3, "sigma": 0.5, "average": "outer",
        "compression": {"mode": "mu1nu1", "species_weighting": None},
        "species": list(SPECIES), "sparse": False, "dtype": "float64",
        "n_jobs": 1, "normalization": "l2_per_structure",
        "fractional_coordinate_handling": "wrap_modulo_1_before_periodic_SOAP",
        "raw_features": RAW_FEATURES, "learned_preprocessing": None,
    }


def _validate_descriptor(descriptor: Any) -> None:
    """Check the registered DScribe 2.1.2 object's actual configuration."""
    expected = {
        "_r_cut": 5.0, "_n_max": 4, "_l_max": 3, "_sigma": 0.5,
        "_rbf": "gto", "average": "outer", "periodic": True,
        "sparse": False, "dtype": "float64", "_eta": 2.0,
    }
    for key, value in expected.items():
        actual = getattr(descriptor, key, None)
        if type(actual) is not type(value) or actual != value:
            raise ValueError(f"SOAP configuration mismatch: {key}")
    species = np.asarray(descriptor.species)
    if species.shape != (94,) or not np.array_equal(species, SPECIES):
        raise ValueError("SOAP global species vocabulary must be Z=1..94")
    compression = descriptor.compression
    if compression != {"mode": "mu1nu1", "species_weighting": None}:
        raise ValueError("SOAP compression must be mu1nu1")
    if getattr(descriptor, "_weighting", None) != {}:
        raise ValueError("SOAP radial weighting must be the unweighted default")
    weights = getattr(descriptor, "_species_weights", None)
    if weights is None or not np.array_equal(np.asarray(weights), np.ones(94)):
        raise ValueError("SOAP species weighting must be uniform")
    if descriptor.get_number_of_features() != RAW_FEATURES:
        raise ValueError("SOAP output dimension is not 6016")


def create_descriptor() -> Any:
    """Construct the one fixed descriptor; dependencies must already be locked."""
    if metadata.version("dscribe") != DSCRIBE_VERSION:
        raise RuntimeError("The registered DScribe version must be 2.1.2")
    from dscribe.descriptors import SOAP

    descriptor = SOAP(
        species=list(SPECIES), periodic=True, rbf="gto", r_cut=5.0,
        n_max=4, l_max=3, sigma=0.5, average="outer",
        compression={"mode": "mu1nu1", "species_weighting": None},
        sparse=False, dtype="float64",
    )
    _validate_descriptor(descriptor)
    return descriptor


def _geometry(record: Mapping[str, Any]) -> tuple[str, np.ndarray, np.ndarray, np.ndarray]:
    if not isinstance(record, Mapping):
        raise TypeError("A pure structure record must be a mapping")
    if set(record) - PURE_RECORD_KEYS:
        raise ValueError("Structure contains an unregistered field; labels are forbidden")
    if not REQUIRED_RECORD_KEYS.issubset(record):
        raise ValueError("Structure is missing an ID or required geometry")
    material_id = record["material_id"]
    if not isinstance(material_id, str) or not material_id:
        raise ValueError("material_id must be a nonempty string")
    number_input = record["atomic_numbers"]
    if not isinstance(number_input, (list, tuple, np.ndarray)):
        raise ValueError("atomic_numbers must be an integer sequence")
    if any(isinstance(x, (bool, np.bool_)) for x in number_input):
        raise ValueError("Boolean atomic numbers are forbidden")
    raw_numbers = np.asarray(number_input)
    if (raw_numbers.ndim != 1 or raw_numbers.size == 0
            or raw_numbers.dtype.kind not in "iu"):
        raise ValueError("atomic_numbers must be a nonempty integer vector")
    numbers = np.asarray(raw_numbers, dtype=np.int64)
    if np.any(numbers < 1) or np.any(numbers > 94):
        raise ValueError("Structure has an element outside the registered Z=1..94")
    if "n_sites" in record:
        if type(record["n_sites"]) is not int or record["n_sites"] != numbers.size:
            raise ValueError("n_sites does not match atomic_numbers")
    fractional = np.asarray(record["frac_coords"], dtype=np.float64)
    lattice = np.asarray(record["lattice"], dtype=np.float64)
    if fractional.shape != (numbers.size, 3) or lattice.shape != (3, 3):
        raise ValueError("Invalid fractional-coordinate or lattice shape")
    if not np.isfinite(fractional).all() or not np.isfinite(lattice).all():
        raise ValueError("Geometry must be finite")
    determinant = float(np.linalg.det(lattice))
    if not np.isfinite(determinant) or abs(determinant) <= 1e-12:
        raise ValueError("Periodic SOAP requires a full-rank cell")
    return material_id, numbers, fractional, lattice


def compute_one(record: Mapping[str, Any], descriptor: Any | None = None) -> tuple[np.ndarray, dict[str, Any]]:
    """Return one normalized 6016-vector and pure numeric geometry metadata."""
    material_id, numbers, fractional, lattice = _geometry(record)
    if descriptor is None:
        descriptor = create_descriptor()
    _validate_descriptor(descriptor)
    from ase import Atoms

    # No calculator, target, velocity, momentum, or arbitrary record extras enter ASE.
    atoms = Atoms(numbers=numbers, scaled_positions=np.remainder(fractional, 1.0),
                  cell=lattice, pbc=(True, True, True))
    raw = np.asarray(descriptor.create(atoms, n_jobs=1), dtype=np.float64)
    if raw.shape != (RAW_FEATURES,) or not np.isfinite(raw).all():
        raise ValueError("SOAP returned a nonfinite vector or wrong shape")
    scale = float(np.max(np.abs(raw)))
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("SOAP returned a zero or invalid vector")
    scaled = raw / scale
    scaled_norm = float(np.linalg.norm(scaled))
    raw_norm = scale * scaled_norm
    if not np.isfinite(raw_norm) or raw_norm <= 0:
        raise ValueError("SOAP vector has an invalid L2 norm")
    result = np.ascontiguousarray(scaled / scaled_norm, dtype=np.float64)
    normalized_norm = float(np.linalg.norm(result))
    if not np.isfinite(result).all() or abs(normalized_norm - 1.0) > 1e-12:
        raise ValueError("SOAP L2 normalization failed")
    receipt = {
        "material_id": material_id, "n_sites": int(numbers.size),
        "raw_features": RAW_FEATURES, "raw_l2_norm": raw_norm,
        "normalized_l2_norm": normalized_norm,
        "geometry_sha256": _canonical_hash({
            "atomic_numbers": numbers.tolist(),
            "frac_coords": fractional.tolist(), "lattice": lattice.tolist(),
        }),
    }
    return result, receipt


def compute_matrix(
    records: Iterable[Mapping[str, Any]], *, expected_ids: Sequence[str],
    descriptor: Any | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Generate rows in an explicitly registered ID order; perform no I/O.

    The caller authorizes real input generation separately. No ID sorting,
    dropping, fallback, parallel worker, learned reduction, or retry occurs.
    """
    ids = list(expected_ids)
    if (not ids or any(not isinstance(x, str) or not x for x in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("expected_ids must be a nonempty unique string sequence")
    if descriptor is None:
        descriptor = create_descriptor()
    _validate_descriptor(descriptor)
    matrix = np.empty((len(ids), RAW_FEATURES), dtype=np.float64)
    row_receipts = []
    count = 0
    for count, record in enumerate(records, start=1):
        if count > len(ids):
            raise ValueError("Structure count exceeds the registered ID sequence")
        if record.get("material_id") != ids[count - 1]:
            raise ValueError("Structure order differs from registered expected_ids")
        vector, receipt = compute_one(record, descriptor)
        matrix[count - 1] = vector
        row_receipts.append(receipt)
        if progress_callback is not None and (count % 64 == 0 or count == len(ids)):
            progress_callback(count, len(ids))
    if count != len(ids):
        raise ValueError("Structure count is below the registered ID sequence")
    numeric = np.ascontiguousarray(matrix, dtype="<f8")
    norms = np.linalg.norm(matrix, axis=1)
    matrix_hash = hashlib.sha256(numeric.tobytes()).hexdigest()
    receipt = {
        "status": "PASS", "target_values_accessed": False,
        "parameters": specification(),
        "ordered_train_ids_sha256": _canonical_hash(ids),
        "matrix_numeric_sha256": matrix_hash,
        "descriptor_specification": specification(),
        "descriptor_specification_sha256": _canonical_hash(specification()),
        "shape": list(matrix.shape), "dtype": "float64",
        "ordered_IDs_sha256": _canonical_hash(ids),
        "feature_names_sha256": _canonical_hash(list(FEATURE_NAMES)),
        "matrix_float64_LE_sha256": matrix_hash,
        "finite": bool(np.isfinite(matrix).all()),
        "normalized_l2_norm_min": float(norms.min()),
        "normalized_l2_norm_max": float(norms.max()),
        "row_receipts": row_receipts,
        "scientific_learner_fits_performed": 0,
        "learned_preprocessing_fits_performed": 0,
        "target_fields_accepted": False,
    }
    return matrix, receipt
