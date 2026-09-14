# PRIS core analyzer validation

[English](core_validation.md) | [简体中文](core_validation_zh.md)

Source: AI4QC/PRIS, commit `34e6c86c083759dc1ee594ae22238ea9b5ebd8f4`.

## Import and test audit

Inspected `tests/test_pris_analyze.py`, `tests/test_regressions.py`, the public
`src/pris_analyze.py` entry point, its direct feature modules, and transitive
imports through `phys_feat.py` / `polymorph_rank2.py`.

- No network calls, subprocess launches, or shell commands are exercised by
  the chosen tests or the selected analyzer feature functions.
- Analyzer input is read from supplied local CIF files. Bond-valence parameters
  are read from committed `data/bvparm2020.cif`; PSS coefficients and feature
  normalization are read from committed
  `agent_loop/frozen/20260814_f3_synth/F3_frozen.json`.
- The chosen tests create temporary CIF files and a temporary CSV directory.
  Importing `fig3_anatomy` imports `paper_figs`, which creates `paper/figs` if
  absent and configures matplotlib. It does not regenerate figures at import.
- No upstream source edits were made by this validation task.

## Independent checks

`scripts/validate_core.py` creates analytical synthetic structures with known
nearest-neighbor distances. These are geometry controls, not independent
experimental data. It compares pymatgen periodic neighbors against explicit
lattice-translation enumeration, including periodic images of the same site.

Checks cover conventional and primitive NaCl, a translated NaCl cell, a NaCl
supercell, conventional MgO, two-site CsCl, and a deliberately tiny one-atom
cubic cell. The one-atom cell is included to demonstrate why setting the entire
distance-matrix diagonal to infinity can miss periodic self-image contacts.

The script also checks translation invariance and compares the same NaCl
geometry under different cell representations. Execution results are recorded
below.

## Regression test results

Executed the six upstream tests in `tests/test_regressions.py` with Python 3.12.14
and the bundled NumPy/Pandas runtime. First run: four passed, two errored. One
error was Windows cp1252 console encoding when printing Chinese text. Running
Python with `-X utf8` resolves that runtime issue without editing source.

UTF-8 rerun: **5 passed, 1 error**. The remaining test,
`SplitDisciplineRegressionTests.test_bond_report_does_not_promote_unsplit_rows`,
reads `src/build_bonds.py`, which is absent from the public checkout and from
`git ls-files`. This is a missing upstream test fixture/source file, not a
failed structure-analysis numerical assertion. The test was not modified or
silently skipped. Logs: `work/upstream_regressions.log` and
`work/upstream_regressions_utf8.log`.

Command (run from `work/PRIS`):

```powershell
& '<bundled-python>/python.exe' -X utf8 -m unittest discover -s tests -p test_regressions.py -v
```

## Full selected upstream pytest results

After installing the scientific dependencies, ran the two selected upstream
test files together:

```powershell
python -X utf8 -m pytest tests/test_pris_analyze.py tests/test_regressions.py -q --tb=short
```

**15 passed, 1 failed, 28 warnings** in 97.84 seconds. All **10 public analyzer
tests passed**, including the manuscript Fig. 3a contact ratios, damage
detection, frozen PSS weights, PSS parent ranking, and malformed-CIF handling.
The sole failure is the same absent `src/build_bonds.py` test fixture documented
above. Warnings are spglib API deprecations and duplicate site labels emitted
when the upstream synthetic spinel is serialized; numerical analyzer checks
still passed. Full output: `upstream_core_pytest.log` in this directory.

## Independent result: input-cell dependence

The seven analytical periodic-distance checks all pass. They use explicit
translations from -2 to +2, which is sufficient for these cubic/fcc controls;
the enumeration is not offered as a general algorithm for arbitrary skew cells.

The checks uncover a substantive limitation of the unmodified public analyzer:
its Law 7 and some PSS descriptors depend on the supplied representation of the
unit cell. These three cells represent exactly the same ideal NaCl crystal with
a conventional lattice parameter of 5.64 Å and minimum contact of 2.82 Å:

| NaCl representation | Sites | Law 7 value | Set 4 verdict | PSS | poly_deg_max | frac_isolated |
|---|---:|---:|---|---:|---:|---:|
| Primitive cell | 2 | 1.000 | implausible | -1.905422 | 0 | 1 |
| Conventional cell | 8 | 0.250 | plausible | -1.787582 | 3 | 0 |
| 2×2×2 primitive supercell | 16 | 0.125 | plausible | -1.663290 | 7 | 0 |

The other seven law quantities agree to a tolerance of 1e-5, and shifting the
whole conventional structure does not change its verdict. Law 7 computes the
number of symmetry-equivalent site orbits divided by the number of sites in the
input cell. Replication increases the denominator while preserving the number
of distinct orbits. The `criteria` function also builds polyhedron connections
using site indices from the finite input cell, which changes `poly_deg_max`
and `frac_isolated` under primitive/conventional/supercell representations.
In the primitive NaCl cell, periodic connectivity is summarized as an isolated
polyhedron even though the physical crystal is a connected periodic network.

This is an input-representation sensitivity, not evidence that primitive NaCl
is physically implausible. It affects the strict Set 4 decision and PSS values.
It does not invalidate the observed execution of the author's Fig. 3a tests,
and it has not been silently patched in this reproduction. A follow-up should
define and freeze a common cell convention, fix periodic graph accounting,
and recalibrate affected thresholds/normalizations on a development split
before making general performance claims.

Additional controls: conventional MgO is plausible, two-site CsCl is rejected
by Law 7, and the single-element one-site cell receives `no verdict` because
formal cation/anion charges are undefined. The tiny one-site cubic control
still has a minimum periodic distance of 0.8 Å; the geometry baseline catches
that self-image distance.

Machine-readable output and all seven generated CIFs are included here.
The portable `scripts/validate_core.py` uses the unchanged vendored analyzer
and recreates the results. To rerun from the reproduction bundle:

```powershell
python -X utf8 scripts/validate_core.py
```

Pytest logs preserve the test output; machine-specific absolute path prefixes
may be redacted for publication. The portable validation JSON stores CIF
filenames without machine-specific paths.

The two selected test files and four helper modules are also bundled unchanged
under `vendor/pris`. A second run using these bundled files passed all **10
analyzer tests** in 6.19 seconds; see `bundled_analyzer_pytest.log`.

```powershell
python -X utf8 -m pytest vendor/pris/tests/test_pris_analyze.py -q
```

The earlier combined log includes the missing-source regression failure and
is preserved. Running the complete bundled two-file suite will show that same
known failure unless the author supplies `src/build_bonds.py`.
