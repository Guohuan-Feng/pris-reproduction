# Independent E4 equation-of-state reanalysis

[English](README.md) | [简体中文](README_zh.md)

**All 260 published bulk-modulus fits were recomputed from the released collected energy-volume values.** No VASP calculation was run. The independent optimizer agrees with the published bulk moduli to a maximum absolute difference of **0.00023253 GPa**; the median difference is **0.0000000509 GPa**. Maximum relative difference is **0.00009615%**.

The 1,300 input stage-B records contain 1,296 complete, one unconverged, and three failed tasks. The same eligibility convention as the source leaves 1,297 E(V) points, yielding 257 five-point fits and three four-point fits. No published candidate is missing from the reanalysis.

| Quantity | Recomputed result |
|---|---:|
| Fitted candidates | 260 |
| Priority / retained-control / screened | 140 / 60 / 60 |
| Median bulk modulus | 374.47091 GPa |
| Largest bulk modulus | 418.54561 GPa |
| UMA-versus-DFT Pearson correlation | 0.769259 |
| UMA-versus-DFT Spearman correlation | 0.710143 |
| Median DFT/UMA modulus ratio | 0.93954685 |
| Corresponding mapped DFT threshold | 375.81874 GPa |
| Above mapped threshold: retained / screened | 123 / 1 |
| Retention above mapped threshold | 99.19355% |
| Priority-versus-screened pairwise ranking accuracy | 0.966190 |

The original 400 GPa threshold has **two** qualifying candidates in the published row-level data, and the independent fits preserve both:

| Candidate | Formula | Role | Refit bulk modulus |
|---|---|---|---:|
| candidate_0017 | Os | priority | 400.38451 GPa |
| candidate_0980 | Re2IrOs6 | screened | 418.54561 GPa |

Thus the released numerical data support one **priority** candidate above 400 GPa, not one candidate across the entire selected set. The highest-modulus candidate was screened out. This is consistent with the repository's `dft/RESULTS.md` showing one above-threshold priority candidate and one above-threshold screened candidate; the main manuscript's phrase about one candidate above 400 GPa should not be copied as a total-set count.

The mapped threshold is calculated after comparing DFT and UMA scales; it is distinct from the original 400 GPa design target. Also, these 260 candidates deliberately oversample high UMA predictions. Their retention fractions do not independently establish a 67.3% reduction over the full 1,081-candidate generation pool.

`per_candidate.csv` contains every refit, the published reference, absolute/relative errors, EOS residuals, and roles. `energy_volume_points.csv` contains the exact eligible numerical inputs. `summary.json` records all counts, excluded tasks, dependencies, and SHA256 hashes. Re-run `python scripts/refit_eos.py` from the bundle root; dependencies used here were Python 3.12.14, NumPy 2.5.3, SciPy 1.18.1.
