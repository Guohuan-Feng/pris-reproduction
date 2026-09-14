"""Independent local checks for the unmodified public PRIS analyzer.

Analytical cells below are synthetic geometry controls, not experimental data.
Their known nearest-neighbor distances test periodic-distance handling.  Cell
representation comparisons document behavior; they do not redefine PRIS laws.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    bundle = Path(__file__).resolve().parents[1]
    parser.add_argument("--repo", type=Path, default=bundle / "vendor" / "pris")
    parser.add_argument("--out", type=Path, default=bundle / "results" / "core_validation")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.repo / "src"))
    import numpy as np
    from pymatgen.core import Lattice, Structure
    import pris_analyze as pa

    def brute_periodic_minimum(st):
        """Independent finite enumeration sufficient for these cubic/fcc cells."""
        lattice = st.lattice.matrix
        xyz = st.cart_coords
        best = float("inf")
        for image in itertools.product(range(-2, 3), repeat=3):
            distances = np.linalg.norm(xyz[:, None, :] - xyz[None, :, :] + np.array(image) @ lattice, axis=-1)
            if image == (0, 0, 0):
                np.fill_diagonal(distances, np.inf)
            best = min(best, float(distances.min()))
        return best

    def neighbor_periodic_minimum(st):
        # Includes periodic self images (i == j, nonzero lattice translation).
        radius = min(st.lattice.abc) * 1.01
        neighbors = st.get_all_neighbors(radius)
        return min(float(nb.nn_distance) for site_neighbors in neighbors for nb in site_neighbors)

    a = 5.64
    conv_nacl = Structure.from_spacegroup("Fm-3m", Lattice.cubic(a), ["Na", "Cl"], [[0, 0, 0], [0.5, 0, 0]])
    primitive_nacl = Structure(Lattice([[0, a / 2, a / 2], [a / 2, 0, a / 2], [a / 2, a / 2, 0]]), ["Na", "Cl"], [[0, 0, 0], [0.5, 0.5, 0.5]])
    mg_o = Structure.from_spacegroup("Fm-3m", Lattice.cubic(4.212), ["Mg", "O"], [[0, 0, 0], [0.5, 0, 0]])
    cscl = Structure(Lattice.cubic(4.123), ["Cs", "Cl"], [[0, 0, 0], [0.5, 0.5, 0.5]])
    one_atom = Structure(Lattice.cubic(0.8), ["Na"], [[0, 0, 0]])
    translated = conv_nacl.copy()
    translated.translate_sites(list(range(len(translated))), [0.23, -0.42, 1.13], frac_coords=True)
    replicated = primitive_nacl.copy()
    replicated.make_supercell([2, 2, 2])
    cases = [
        ("NaCl_conventional", conv_nacl, a / 2),
        ("NaCl_primitive", primitive_nacl, a / 2),
        ("NaCl_conventional_shifted", translated, a / 2),
        ("NaCl_primitive_2x2x2", replicated, a / 2),
        ("MgO_conventional", mg_o, 4.212 / 2),
        ("CsCl_two_site", cscl, 4.123 * np.sqrt(3) / 2),
        ("one_atom_tiny_cubic_control", one_atom, 0.8),
    ]

    results = []
    for name, st, expected in cases:
        t0 = time.perf_counter()
        brute = brute_periodic_minimum(st)
        pmg = neighbor_periodic_minimum(st)
        assert np.isclose(brute, expected, atol=1e-10), (name, brute, expected)
        assert np.isclose(pmg, expected, atol=1e-10), (name, pmg, expected)
        path = args.out / (name + ".cif")
        st.to(filename=str(path))
        analysis = pa.analyse(str(path))
        analysis["file"] = path.name
        row = {"name": name, "synthetic_control": True,
               "expected_min_distance_A": float(expected),
               "brute_force_min_distance_A": brute,
               "neighbor_min_distance_A": pmg,
               "elapsed_seconds": time.perf_counter() - t0,
               "analysis": analysis}
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    lookup = {r["name"]: r["analysis"] for r in results}
    conv, prim, shifted, sup = [lookup[k] for k in ["NaCl_conventional", "NaCl_primitive", "NaCl_conventional_shifted", "NaCl_primitive_2x2x2"]]
    assert conv["verdict"] == shifted["verdict"], "translation changes verdict"
    for law in (1, 2, 3, 4, 5, 6, 8):
        # Cell representations have the same intensive law quantities.
        vals = [x["laws"][law]["value"] for x in (conv, prim, sup)]
        assert all(np.isclose(vals[0], value, atol=1e-5) for value in vals[1:]), (law, vals)
    assert lookup["one_atom_tiny_cubic_control"]["verdict"] == "no verdict"

    summary = {"periodic_geometry_cases_passed": len(results),
               "upstream_source_modified": False,
               "source_commit": "34e6c86c083759dc1ee594ae22238ea9b5ebd8f4",
               "same_NaCl_geometry": {key: {"verdict": val["verdict"], "law7": val["laws"][7], "pss": val["pss"]} for key, val in [("conventional", conv), ("primitive", prim), ("primitive_2x2x2", sup)]},
               "results": results}
    (args.out / "results.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
