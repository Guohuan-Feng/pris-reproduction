# PRIS reproduction report

English | [中文](REPORT_zh.md)

Date: September 14, 2026. Paper: [Autonomous discovery of new structure-plausibility laws for explainable and rapid crystal diagnosis and screening](https://arxiv.org/abs/2609.01209). Upstream code: [AI4QC/PRIS](https://github.com/AI4QC/PRIS), pinned to commit `34e6c86c083759dc1ee594ae22238ea9b5ebd8f4`.

## Results and scope

This reproduction runs the released PRIS analyzer on published crystal structures, independently refits published energy–volume data, and preserves the inputs, per-structure results, figures, and rerun scripts. **It reproduces the portions supported by complete public inputs; it is not an end-to-end reproduction of every experiment in the paper.**

| Component | Work completed and result | What it establishes |
|---|---|---|
| PRIS structure analysis | All 180 structures processed: 30 COD experimental parents and 150 fixed damaged variants | Functional and mechanism checks on the public E3 subset |
| Fig. 3 numerical example | Spinel and five perturbations recomputed; all 10 upstream analyzer tests passed | The key example and selected rule implementations can be rerun |
| E4 bulk moduli | 1,297 eligible E(V) points extracted from 1,300 records; 260/260 candidates independently fitted | The derivation of bulk moduli from published DFT numbers can be reproduced; no new DFT calculations were run |
| E4 symmetry from atomic coordinates | 260 pairs, or 520 structures, recomputed; Law 7 pass counts reproduced as 61→113, with no per-structure discrepancies | Direct reproduction of the published symmetry results from released coordinates |
| Equivalent crystal representations | All seven periodic-geometry controls passed; NaCl cell representation changed Set 4 and PSS outputs | The public deployment interface has input-representation sensitivity |
| Upstream figures | Figs. 1, 3, and 5 regenerated; Fig. 2 lacked a required input | Figure regeneration is recorded separately from structure-level recomputation |

Rule thresholds and PSS coefficients were left at the upstream values; they were not retuned to match results. The main scientific runs used Python 3.12.14. Exact dependency versions are recorded in [requirements-lock.txt](requirements-lock.txt).

## 1. Recomputing the original crystal structures

Inputs come directly from the upstream `dft/E3_crosscheck/tasks/` directory. The original bytes of each `POSCAR.init` are preserved. The [data manifest](data/original_e3/manifest.csv) records source paths, COD IDs, labels, perturbation types, and SHA256 hashes. Damaged variants are explicitly labeled as synthetic damage; the upstream metadata field `kind=experimental` was not interpreted as making every variant an experimental positive.

| Rule set | Experimental pass / 30 | Experimental reject / no verdict | Damage detected / 150 | Damage pass / no verdict |
|---|---:|---:|---:|---:|
| Set 1 | 30 (100%) | 0 / 0 | 41 (27.33%) | 101 / 8 |
| Set 1′ | 30 (100%) | 0 / 0 | 58 (38.67%) | 84 / 8 |
| Set 2 | 30 (100%) | 0 / 0 | 86 (57.33%) | 56 / 8 |
| Set 3 | 30 (100%) | 0 / 0 | 105 (70.00%) | 37 / 8 |
| Set 4 | 27 (90.00%) | 2 / 1 | 119 (79.33%) | 20 / 11 |

**No-verdict cases remain in the total denominator and count as neither passes nor detections.** A 90% experimental pass rate for Set 4 therefore does not mean that the other 10% were all rejected. Some upstream benchmark code treats unavailable features as satisfying conditions. This reproduction uses the public analyzer's deployment semantics; the two conventions must not be combined.

![E3 structure recomputation results](results/structure_benchmark/structure_benchmark.png)

Set 4 detects 18/30 uniaxial compressions, 26/30 cation swaps, 30/30 random displacements, 21/30 uniform expansions, and 24/30 cation–anion swaps. See the [per-structure results](results/structure_benchmark/structure_results.csv), [per-law results](results/structure_benchmark/law_results.csv), and [complete records](results/structure_benchmark/records.json).

![Detection by perturbation class](results/structure_benchmark/damage_classes.png)

### Selection limits

E3 is drawn from the **discovery split**. The upstream procedure sorts by `source_id` and selects the first 30 eligible parents. Each must be ordered, contain 2–16 sites, permit integer oxidation-state assignment and all five perturbations, and produce non-equivalent swap variants. **Every variant must have a minimum contact distance of at least 0.9 Å.** This is not a random independent test set.

The 0.5 Å and 0.7 Å distance baselines consequently detect 0% of these variants by construction. Their difference from PRIS on this subset cannot establish a general performance improvement. Likewise, the 79.33% detection rate here is not a direct success or failure to reproduce the paper's 87.9% or 91.1% rates: the datasets, selection procedures, and missing-value conventions differ.

The two experimental parents rejected by Set 4 are AgAsSe2 (COD 1509200) and CrAgSe2 (COD 1509271); both fail Law 7. Cr2AgTe4 (COD 1509274) receives no verdict because its Law 8 measurement is missing. CrAgSe2 also lacks a Law 8 measurement, but its observed Law 7 failure is sufficient for rejection. Keeping individual failure reasons is therefore necessary to interpret the overall verdict.

## 2. Independently refitting 260 bulk moduli

The fit inputs are the released task-level DFT numbers, rather than copied final bulk moduli. An independently implemented third-order Birch–Murnaghan equation of state is fitted with SciPy `least_squares` to each candidate's volumes and static energies. The resulting moduli are then compared with the published fits.

- The 1,300 task records comprise 1,296 `complete`, one `unconverged`, and three `failed` records. The first two statuses are retained under the upstream analysis convention.
- The fits use 1,297 E(V) points: 257 candidates have five points and three candidates have four.
- All 260 candidates fit successfully.
- The maximum absolute difference from the published bulk modulus is **0.000232527 GPa**; the median absolute difference is approximately **5.09×10⁻⁸ GPa**.
- The maximum relative difference is approximately **0.00009615%**.

This validates the numerical processing from the released energy–volume data to bulk moduli. It does not validate the underlying DFT inputs, pseudopotentials, electronic convergence, or machine-learning potential. The unconverged record is retained and disclosed rather than silently excluded.

![Refitted bulk moduli and screening thresholds](results/eos/eos_reproduction.png)

### The threshold behind “99.2% retained”

Reanalysis of the 260 publicly released, selected candidates gives:

| DFT threshold | Candidates above threshold | Retained | Screened out |
|---|---:|---:|---:|
| Upstream UMA-to-DFT mapped threshold, 375.81874 GPa | 124 | 123 (99.19355%) | 1 |
| Original absolute target, 400 GPa | 2 | 1 | 1 |

The two candidates whose refitted DFT bulk moduli exceed 400 GPa are `candidate_0017` (Os, priority group, approximately 400.38451 GPa) and `candidate_0980` (Re2IrOs6, screened group, approximately 418.54561 GPa). The latter has the highest modulus among these 260 candidates and belongs to the screened-out group. These are observations within a deliberately selected sample; they cannot be extrapolated to the success rate of the full generation space.

The [per-candidate fits](results/eos/per_candidate.csv), [E(V) points](results/eos/energy_volume_points.csv), and [EOS method notes](results/eos/README.md) provide the full record.

## 3. Recomputing symmetry for 260 structure pairs

The 260 generated POSCARs and their corresponding 260 DFT-relaxed CIFs are independently read and analyzed at `symprec=0.01 Å`. Space groups and fractions of symmetry-distinct sites are computed using the **input-cell convention** of the upstream supplementary-data export. Every row agrees with the published index:

- Generated structures passing Law 7: **61/260**.
- Relaxed structures passing Law 7: **113/260**.
- Newly passing after relaxation: **52**; newly failing: **0**.
- Rows with a discrepancy in space-group number, site fraction, or verdict: **0**.

This calculation starts from atomic coordinates, including the published relaxed coordinates. The DFT calculations that produced those coordinates were not rerun. The original E4 selection contains 261 candidates, but `candidate_0248` has no corresponding released relaxed CIF. This analysis uses the same fixed 260 pairs as the public supplementary dataset.

A separate sensitivity analysis first converts structures to standard primitive cells. Its pass counts are **66→110**, with 44 gains and no losses. Nine generated-state verdicts and three relaxed-state verdicts differ from the input-cell convention. Standardization may idealize coordinates within the symmetry tolerance, so these changes cannot all be attributed solely to repeating a unit cell. See the [symmetry method notes](results/symmetry/README.md) and [per-structure comparison](results/symmetry/recomputed_symmetry.csv).

## 4. Input-representation sensitivity

Three representations of the same ideal infinite periodic NaCl crystal produce different results from the unchanged public analyzer:

| Representation | Sites | Law 7 value | Set 4 verdict |
|---|---:|---:|---|
| Primitive cell | 2 | 1.000 | Implausible |
| Conventional cell | 8 | 0.250 | Plausible |
| 2×2×2 primitive supercell | 16 | 0.125 | Plausible |

The other seven individual-law verdicts agree. Law 7 uses the number of symmetry-distinct site orbits divided by the number of sites in the input cell, and the deployment entry point does not standardize the cell. PSS also changes because its site-complexity and some polyhedral-graph descriptors depend on the representation. **The reproduction neither patches the upstream code nor chooses a favorable representation to force a pass.**

![Different verdicts for equivalent NaCl representations](results/core_validation/cell_representation.png)

This finding motivates an explicit cell convention and a review of periodic-neighbor accounting. Converting all inputs to primitive cells alone does not establish the scientific validity of the rule: primitive NaCl still fails the current Law 7 threshold. The applicability of the empirical criterion therefore also needs evaluation.

The [core validation notes](results/core_validation/core_validation.md) document the controls and tests. All 10 upstream analyzer tests pass. Of six additional historical regression tests, five pass and one fails because the release lacks `src/build_bonds.py`; the error log is preserved. This is not a claim that the entire upstream test suite passes.

## 5. Figures and remaining gaps

- **Fig. 1:** regenerated from committed aggregate data. The agent's discovery search was not rerun.
- **Fig. 3:** the illustrative MgAl2O4 parent and five perturbations were recomputed. The parent has ρ=0.986487, the compressed structure ρ=0.756613, and the expanded structure ρ=1.282433, matching the rounded values in the text. The S2 cation swap does not trigger a rule in this example; that result is preserved. Other panels use published aggregates or DFT numbers.
- **Fig. 5:** regenerated from published aggregates and DFT outputs. Its files retain the upstream historical name `fig6_deployment`.
- **Fig. 2:** a regeneration attempt confirmed that `outputs/20260815_threshold_transfer/transfer.json` is missing, preventing complete regeneration.
- **Fig. 4:** complete regeneration requires unpublished positive–unlabelled (PU) score shards and the full inverse-design dataset.

The [figure rerun inventory](results/author_figures/README.md) records successful outputs, logs, and the computational scope of each figure.

The complete 5,297/3,612 held-out benchmark, the 440-parent deployment benchmark, several gigabytes of feature tables, some structure blobs, and the full set of 1,081 inverse-design candidates are not included in the public release. The E3 subset and available aggregate curves cannot substitute for these original inputs. The original search involving more than two million candidate evaluations and new VASP calculations were not executed.

Two published screening policies must also be distinguished. The upstream [STATUS.json](https://github.com/AI4QC/PRIS/blob/34e6c86c083759dc1ee594ae22238ea9b5ebd8f4/outputs/20260823_fig45_merged_nature_inverse_f_v1/STATUS.json) reports that Set 4 removes 728/1,081 candidates (67.345%) while retaining 45/140 candidates with UMA bulk-modulus proxy ≥400 GPa. PSS at the selected cutoff removes 61/1,081 candidates (5.643%) and retains 140/140. **These are published aggregate counts, not independently recomputed full-pool results. The reduction from one policy must not be combined with the retention from the other.**

## 6. Research follow-up

A useful follow-up is to evaluate whether explicit cell conventions and consistent periodic-graph accounting improve the reliability of PRIS diagnostics. This should begin by reconciling the input-cell and primitive-cell conventions used in different upstream analyses, obtaining the missing original benchmark inputs, and retaining all no-verdict outcomes in reported denominators.

Any revised representation procedure or affected descriptor should be developed and, where necessary, recalibrated on a development split before evaluation on a fixed held-out set. The comparison should report experimental acceptance, damage detection, no-verdict coverage, and sensitivity to equivalent cell representations. It should preserve the unchanged analyzer as the baseline and keep absolute property targets separate from thresholds mapped between UMA and DFT. This provides a concrete extension of the present reproducibility findings without treating the selected E3 diagnostic as independent evidence of general performance.

Rerun commands and dependency installation are documented in the [README](README.md).
