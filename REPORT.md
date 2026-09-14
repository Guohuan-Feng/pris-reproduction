# Technical Report: Reproduction and Numerical Verification of PRIS

English | [中文](REPORT_zh.md)

Date: September 14, 2026. Paper: [Autonomous discovery of new structure-plausibility laws for explainable and rapid crystal diagnosis and screening](https://arxiv.org/abs/2609.01209). Source repository: [AI4QC/PRIS](https://github.com/AI4QC/PRIS), fixed at commit `34e6c86c083759dc1ee594ae22238ea9b5ebd8f4`.

## 1. Objective and scope

This study assessed the reproducibility of PRIS components for which sufficient public inputs were available. The analysis comprised execution of the released crystal-structure classifier, independent refitting of published energy–volume data, recomputation of crystallographic symmetry from atomic coordinates, assessment of equivalent cell representations, and selected figure regeneration.

The objective was to establish agreement between reproducible computations and published outputs while identifying methodological and data-access limitations. The study did not reproduce the complete autonomous discovery process or every experiment in the paper. Inputs, per-structure outputs, figures, and executable analysis scripts were retained as supporting records.

## 2. Methods

### 2.1 Software and parameter control

The released analyzer was evaluated without modifications to its rule thresholds or PSS coefficients. No parameters were retuned to reproduce the reported results. The main scientific computations used Python 3.12.14; exact package versions are recorded in [requirements-lock.txt](requirements-lock.txt).

A fresh isolated Python 3.12.14 environment was prepared, and verification and reproduction were executed through `bootstrap.py`. All 48 locked distributions installed successfully, and `pip check` reported no broken requirements. Environment validation verified the hashes of 20 vendored source files and 703 archived input files. Installation and validation are documented in [Dependencies](DEPENDENCIES.md).

### 2.2 E3 structure cohort and outcome definitions

The E3 inputs were obtained from the upstream `dft/E3_crosscheck/tasks/` directory. The cohort contained 30 COD experimental-source parent structures and their 150 fixed damaged variants, yielding 180 structures. Each `POSCAR.init` was archived from the pinned local checkout with SHA256 verification. These hashes identify the preserved checkout bytes, which may differ in line endings from Git blob bytes. Source paths, COD identifiers, labels, perturbation types, and hashes are recorded in the [data manifest](data/original_e3/manifest.csv).

Damaged variants were labeled as synthetic damage. The upstream metadata field `kind=experimental` was interpreted as parent provenance rather than as evidence that every variant was an experimental positive.

The upstream selection procedure used the **discovery split**, sorted eligible structures by `source_id`, and selected the first 30 parents. Eligibility required ordered structures containing 2–16 sites, integer oxidation-state assignment, applicability of all five perturbations, and non-equivalent swap variants. Every variant was required to have a minimum contact distance of at least 0.9 Å.

The public analyzer's deployment semantics were retained: no-verdict outcomes remained in the total denominator and were counted as neither passes nor detections. An observed rule failure was sufficient to reject a rule set even when another required measurement was unavailable. This convention differs from upstream benchmark procedures that treat some unavailable features as satisfying conditions.

### 2.3 Independent equation-of-state fitting

Bulk moduli were recalculated from released task-level volumes and static energies using an independently implemented third-order Birch–Murnaghan equation of state and SciPy `least_squares`. Published final moduli were used for comparison after fitting.

The 1,300 task records comprised 1,296 `complete`, one `unconverged`, and three `failed` records. The first two categories were retained in accordance with the upstream analysis convention, producing 1,297 E(V) points. Of the 260 candidates, 257 had five usable points and three had four. No new DFT calculations were performed.

### 2.4 Symmetry recomputation

The symmetry analysis used 260 generated-state POSCARs and their corresponding 260 DFT-relaxed CIFs, comprising 520 structures. Space-group numbers and fractions of symmetry-distinct sites were recomputed at `symprec=0.01 Å` using the input-cell convention of the upstream supplementary-data export.

The original E4 selection contained 261 candidates. Because `candidate_0248` lacked a corresponding released relaxed CIF, the analyzed cohort comprised the same fixed 260 pairs as the public supplementary dataset. A separate sensitivity analysis applied standard primitive-cell conversion before symmetry evaluation. The published relaxed coordinates were analyzed without rerunning the DFT calculations that produced them.

The 260 relaxed CIFs, index, and summary in the arXiv source matched the corresponding GitHub materials after CRLF/LF normalization. This comparison establishes text agreement across the two releases; archive hashes identify the preserved local files.

### 2.5 Geometric controls, tests, and figures

Seven analytical periodic-geometry controls were evaluated, including three equivalent representations of an ideal infinite periodic NaCl crystal. The checks assessed periodic distances and the dependence of analyzer outputs on cell representation.

The illustrative MgAl2O4 structure and five perturbations associated with Fig. 3 were recomputed. Selected upstream analyzer and historical regression tests were also executed. Figure regeneration from aggregate data was recorded separately from structure-level recomputation and from analysis of previously calculated DFT outputs.

## 3. Results

### 3.1 Summary of completed computations

| Component | Result | Evidential scope |
|---|---|---|
| PRIS structure analysis | All 180 structures processed: 30 COD experimental parents and 150 fixed damaged variants | Functional and mechanism checks on the public E3 subset |
| Fig. 3 numerical example | Spinel and five perturbations recomputed; all 10 upstream analyzer tests passed | Reproduction of the selected numerical example and analyzer checks |
| E4 bulk moduli | 1,297 eligible E(V) points extracted from 1,300 records; 260/260 candidates independently fitted | Verification of the numerical derivation of bulk moduli from published DFT values |
| E4 symmetry | 260 pairs, or 520 structures, recomputed; Law 7 pass counts reproduced as 61→113 with no per-structure discrepancies | Verification of published symmetry results from released coordinates |
| Equivalent crystal representations | All seven periodic-geometry controls passed; NaCl representation changed Set 4 and PSS outputs | Evidence of input-representation sensitivity in the public deployment interface |
| Upstream figures | Figs. 1, 3, and 5 regenerated; Fig. 2 lacked a required input | Regeneration of available figure components, with separate computational provenance |

### 3.2 E3 classification outcomes

| Rule set | Experimental pass / 30 | Experimental reject / no verdict | Damage detected / 150 | Damage pass / no verdict |
|---|---:|---:|---:|---:|
| Set 1 | 30 (100%) | 0 / 0 | 41 (27.33%) | 101 / 8 |
| Set 1′ | 30 (100%) | 0 / 0 | 58 (38.67%) | 84 / 8 |
| Set 2 | 30 (100%) | 0 / 0 | 86 (57.33%) | 56 / 8 |
| Set 3 | 30 (100%) | 0 / 0 | 105 (70.00%) | 37 / 8 |
| Set 4 | 27 (90.00%) | 2 / 1 | 119 (79.33%) | 20 / 11 |

Set 4 accepted 27/30 experimental-source parents, rejected two, and returned no verdict for one. Its 90.00% pass rate therefore does not imply a 10% rejection rate. Among the damaged structures, 119/150 were detected, 20 passed, and 11 received no verdict.

![E3 structure recomputation results](results/structure_benchmark/structure_benchmark.png)

The Set 4 detections by perturbation class were 18/30 for uniaxial compression, 26/30 for cation exchange, 30/30 for random displacement, 21/30 for uniform expansion, and 24/30 for cation–anion exchange. The [per-structure results](results/structure_benchmark/structure_results.csv), [per-law results](results/structure_benchmark/law_results.csv), and [complete records](results/structure_benchmark/records.json) provide the corresponding measurements and decisions.

![Detection by perturbation class](results/structure_benchmark/damage_classes.png)

The rejected experimental-source parents were AgAsSe2 (COD 1509200) and CrAgSe2 (COD 1509271), both of which failed Law 7. Cr2AgTe4 (COD 1509274) received no verdict because its Law 8 measurement was unavailable. CrAgSe2 also lacked a Law 8 measurement; its observed Law 7 failure nevertheless determined the overall rejection under the specified deployment semantics.

### 3.3 Equation-of-state agreement and threshold-dependent retention

All 260 candidates were fitted successfully. The maximum absolute difference from the published bulk modulus was **0.000232527 GPa**, and the median absolute difference was approximately **5.09×10⁻⁸ GPa**. The maximum relative difference was approximately **0.00009615%**.

![Refitted bulk moduli and screening thresholds](results/eos/eos_reproduction.png)

Retention estimates depended on the property threshold applied to the 260 selected candidates:

| DFT threshold | Candidates above threshold | Retained | Screened out |
|---|---:|---:|---:|
| Upstream UMA-to-DFT mapped threshold, 375.81874 GPa | 124 | 123 (99.19355%) | 1 |
| Original absolute target, 400 GPa | 2 | 1 | 1 |

The approximately 99.2% retention statement corresponds to the mapped threshold. The two candidates with refitted DFT bulk moduli exceeding 400 GPa were `candidate_0017` (Os, priority group, approximately 400.38451 GPa) and `candidate_0980` (Re2IrOs6, screened group, approximately 418.54561 GPa). The latter had the highest modulus in the 260-candidate cohort and belonged to the screened-out group.

The [per-candidate fits](results/eos/per_candidate.csv), [E(V) points](results/eos/energy_volume_points.csv), and [EOS method notes](results/eos/README.md) document the numerical analysis.

### 3.4 Symmetry agreement and standardization sensitivity

Under the input-cell convention, **61/260** generated structures and **113/260** relaxed structures passed Law 7. Relaxation produced **52** newly passing structures and **0** newly failing structures. There were **0** per-structure discrepancies in space-group number, site fraction, or verdict relative to the published index.

The separate standard primitive-cell analysis produced pass counts of **66→110**, with **44** gains and **0** losses after relaxation. Compared with the input-cell convention, nine generated-state verdicts and three relaxed-state verdicts differed. Standardization may idealize coordinates within the symmetry tolerance; consequently, these changes are not attributable exclusively to repetition of a unit cell. The [symmetry method notes](results/symmetry/README.md) and [per-structure comparison](results/symmetry/recomputed_symmetry.csv) record both analyses.

### 3.5 Equivalent NaCl cell representations

The unchanged public analyzer produced the following outputs for three representations of the same ideal periodic NaCl crystal:

| Representation | Sites | Law 7 value | Set 4 verdict |
|---|---:|---:|---|
| Primitive cell | 2 | 1.000 | Implausible |
| Conventional cell | 8 | 0.250 | Plausible |
| 2×2×2 primitive supercell | 16 | 0.125 | Plausible |

The other seven individual-law verdicts agreed. Law 7 evaluates the number of symmetry-distinct site orbits divided by the number of input sites, and the deployment entry point does not standardize the cell. PSS also varied because its site-complexity and some polyhedral-graph descriptors depend on the input representation. The upstream implementation and the complete set of evaluated representations were retained without modification or outcome-based selection.

![Different verdicts for equivalent NaCl representations](results/core_validation/cell_representation.png)

### 3.6 Tests and figure regeneration

All six tasks in the clean-environment rerun completed with exit code 0: geometric controls, the E3 structure benchmark, independent EOS fitting, paired symmetry recomputation, report-figure generation, and the selected upstream analyzer tests. This rerun did not include the six additional historical regression tests discussed below.

All 10 selected upstream analyzer tests passed. Of six additional historical regression tests, five passed and one failed because the release lacked `src/build_bonds.py`. The preserved logs in the [core validation notes](results/core_validation/core_validation.md) distinguish these results from a claim that the complete upstream test suite passed.

Figure-level outcomes were as follows:

- **Fig. 1:** regenerated from committed aggregate data; the autonomous discovery search was not rerun.
- **Fig. 3:** the illustrative MgAl2O4 parent and five perturbations were recomputed. The parent yielded ρ=0.986487, the compressed structure ρ=0.756613, and the expanded structure ρ=1.282433, consistent with the rounded values in the text. The S2 cation exchange did not trigger a rule in this example. Other panels used published aggregates or DFT values.
- **Fig. 5:** regenerated from published aggregates and DFT outputs; the files retain the upstream historical name `fig6_deployment`.
- **Fig. 2:** complete regeneration was prevented by the missing input `outputs/20260815_threshold_transfer/transfer.json`.
- **Fig. 4:** complete regeneration requires unpublished positive–unlabelled (PU) score shards and the full inverse-design dataset.

The [figure rerun inventory](results/author_figures/README.md) records outputs, logs, and the computational scope of each figure.

## 4. Limitations

### 4.1 Sampling and outcome conventions

The E3 cohort is a selected discovery-split subset rather than a random independent test set. Its minimum-distance requirement of 0.9 Å causes the 0.5 Å and 0.7 Å distance baselines to detect 0% of its damaged variants by construction. Differences from PRIS on this cohort therefore do not establish general performance improvements.

The E3 detection rate of 79.33% is not directly comparable with the paper's 87.9% or 91.1% rates because the datasets, selection procedures, and missing-value conventions differ. No-verdict cases remain explicit in the present denominators; deployment and benchmark conventions are not combined.

The E4 candidates were deliberately selected. Retention and threshold-specific results from this 260-candidate cohort cannot be extrapolated to the success rate of the full generation space.

### 4.2 Numerical reanalysis versus first-principles validation

Agreement of the independent EOS fits verifies numerical processing from published energy–volume values to bulk moduli. It does not validate the underlying DFT inputs, pseudopotentials, electronic convergence, or machine-learning potential. The single `unconverged` record was retained and reported under the upstream protocol. Similarly, symmetry agreement verifies analysis of released coordinates rather than the calculations that generated the relaxed structures.

### 4.3 Incomplete public inputs

The complete 5,297/3,612 held-out benchmark, the 440-parent deployment benchmark, several gigabytes of feature tables, some structure blobs, and the full set of 1,081 inverse-design candidates were not included in the public release. The available E3 subset and aggregate curves do not replace those inputs. The search involving more than two million candidate evaluations and new VASP calculations were not executed. Missing figure inputs and the historical source-file omission are identified in Section 3.6.

### 4.4 Distinct screening policies

The upstream [STATUS.json](https://github.com/AI4QC/PRIS/blob/34e6c86c083759dc1ee594ae22238ea9b5ebd8f4/outputs/20260823_fig45_merged_nature_inverse_f_v1/STATUS.json) reports that Set 4 removes 728/1,081 candidates (67.345%) while retaining 45/140 candidates with UMA bulk-modulus proxy ≥400 GPa. PSS at the selected cutoff removes 61/1,081 candidates (5.643%) and retains 140/140. These are published aggregate counts, not independently recomputed full-pool results. They describe distinct screening policies and cannot be combined into a single reduction-and-retention estimate.

### 4.5 Representation-dependent criteria

The NaCl controls establish a dependence of some deployment outputs on equivalent cell representation. Standardizing all structures to primitive cells would not by itself establish the scientific validity of Law 7, because primitive NaCl still fails the current threshold. Both representation conventions and the applicability of the empirical criterion require evaluation.

## 5. Conclusions

The released materials support reproducible execution of the PRIS analyzer on the selected E3 cohort, numerical verification of all 260 published EOS fits, and exact recovery of the evaluated symmetry results for 260 structure pairs. The selected analyzer tests and numerical Fig. 3 example also reproduced successfully.

The results additionally identify input-representation sensitivity in Law 7 and PSS, threshold-dependent interpretation of property retention, and limitations arising from sample selection and unavailable inputs. These findings support a bounded computational reproduction; they do not establish an end-to-end reproduction of autonomous discovery or independent confirmation of the paper's full-population performance claims.

## 6. Future work

Further evaluation requires reconciliation of the input-cell and primitive-cell conventions used across upstream analyses, examination of periodic-graph accounting, and access to the missing original benchmark inputs. Any revised representation procedure or affected descriptor would require development and, where necessary, recalibration on a development split before evaluation on a fixed held-out set.

A subsequent comparison would retain the unchanged analyzer as the baseline and report experimental acceptance, damage detection, no-verdict coverage, and sensitivity to equivalent cell representations. Absolute property targets and thresholds mapped between UMA and DFT would remain separate. Such an evaluation would assess potential methodological changes without interpreting the selected E3 diagnostic cohort as independent evidence of general performance.

Execution commands and dependency installation are documented in the [README](README.md).
