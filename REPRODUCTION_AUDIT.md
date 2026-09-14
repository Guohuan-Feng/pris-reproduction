# PRIS reproduction audit (2026-09-14)

English | [中文](REPRODUCTION_AUDIT_zh.md)

Source: https://github.com/AI4QC/PRIS, commit `34e6c86c083759dc1ee594ae22238ea9b5ebd8f4`.
Read-only source inspection; no AGENTS.md found beneath work/PRIS. No upstream analysis/cluster scripts executed by this auditor.

## What can be recomputed honestly

1. Full PRIS analyzer readings on supplied atomic structures, including the published MgAl2O4 example.
2. **E3 public structure subset:** 30 COD experimental parents and 150 fixed damaged variants (30 for each S1–S5). These original POSCARs are committed and can be remeasured. This is a selected discovery-split diagnostic, not an independent held-out benchmark or a reproduction of the headline 5,297/3,612 result.
3. **E4 numerical reanalysis:** independently refit 260 Birch–Murnaghan equations of state from the 1,300 collected stage-B DFT records; compare with published fitted moduli. This recomputes derived physics quantities from published numerical outputs; it does not re-run VASP.
4. **E4 symmetry check:** 260 released DFT-relaxed CIFs can be independently measured using spglib/pymatgen. The generated counterpart POSCARs exist in dft/E4_design/tasks. The released supplementary SUMMARY.json uses the **input-cell convention** in `src/dft_supplementary_data.py`, with symprec=0.01 Å: 61 pass Law 7 as generated, 113 after DFT relaxation, 52 gains and 0 losses. These counts and all per-structure space-group numbers, site fractions, and verdicts were independently reproduced. The separate `dft/analyze.py:spacegroup_and_economy` function uses standard primitive cells; the corresponding sensitivity analysis gives 66→110 passes, 44 gains and 0 losses. Standardization may idealize coordinates within tolerance, so its verdict changes cannot all be attributed to cell repetition alone. The full analyzer cannot judge many metal-rich E4 structures; Law 7 alone does not need charges.
5. Many figures can be redrawn from published aggregates. Redrawing an aggregate is a consistency check, not independent benchmark recomputation.

## Exact E3 source and selection

Files: `work/PRIS/dft/E3_crosscheck/tasks/E3-cod-<id>-<variant>/POSCAR.init`; metadata beside each file in TASK.json; `dft/E3_crosscheck/selection.json`; hashes in MANIFEST.json.

- 30 `P0` parents, 30 each of `S1`, `S2`, `S3`, `S4`, `S5`; a separate 20 unmodified GNoME cells must not be merged into the experimental-positive cohort.
- `dft/build_tasks.py:load_provenance` restricts to `in_analysis_set` before selecting: one anion among O/S/Se/Te/N/P/F/Cl/Br/I, no H or C (documented upstream provenance rule).
- `build_e3` selects discovery split, n_sites <=16 and n_elements >=2, sorts by source_id, and takes the first 30 qualifying parents.
- Parse success; 2–16 actual sites; ordered structure; parent shortest contact >=1.0 Å; successful **integer** `discriminate.guess_oxi`.
- All five perturbations must be constructible; S2 or S5 cannot be identical to parent under StructureMatcher(primitive_cell=False, attempt_supercell=False, scale=False, ltol=0.01, stol=0.02, angle_tol=0.5).
- Every one of the six cells must have minimum contact >=0.9 Å; otherwise drop the whole parent. The older pre-registration says 0.6 Å, but Amendment 2 explicitly raises it to 0.9 Å; current code and selection.json agree on 0.9.
- RNG uses stable SHA256-derived seed of `E3|<source_id>`; use committed variants directly to avoid regeneration ambiguity.
- **No DFT success condition selected these parents.** The published E3 table analyzes all 200 tasks, including unconverged but completed tasks. Published fixed-cell convergence is 189/200; full-cell convergence is 195/200. A PRIS pre-screen test should use the input POSCARs and not remove structures based on later DFT outcomes.
- S1: one lattice axis compressed 15–30%. S2: different-element cations with formal-charge difference >=1 swapped. S3: isotropic random Gaussian Cartesian site shifts, with amplitude sampled 0.3–0.8 Å. S4: lattice expanded 20–40%. S5: a cation and an anion swapped. Source `src/make_negatives.py:perturb`.
- S2/S5 are species swaps at fixed coordinates and preserve composition; inferred charges must move with species. Re-reading POSCAR and inferring charges by composition does this; never reapply the original indexed valence vector after a swap.

## E3 feature path and report definitions

`src/pris_analyze.py:measure` uses the public maintained scientific functions: guess_oxi/frac_oxi, phys_law.phys_feats, elec_feat.elec_feats, discriminate.criteria, f3_features._feats and composition-only ionicity. The full 440-parent deployment script uses the same core phys_feats/elec_feats/criteria, with direct spglib symmetry at 0.01 Å. E3 itself originally tests DFT vs MatterSim relaxation energies; I found no frozen table reporting PRIS satisfaction/detection specifically on the 30 E3 COD parents. Therefore new E3 PRIS measurements have no exact paper percentage to match.

For each law set on each cohort, preserve all input rows and report counts P=plausible, I=implausible, U=no verdict, N=P+I+U:

- Coverage: (P+I)/N.
- Experimental acceptance on all inputs: P/N; explicit experimental rejection: I/N; no-verdict: U/N.
- Experimental satisfaction among evaluated: P/(P+I), if denominator >0.
- Damage detection on all attempted inputs: I/N; evaluated-only detection I/(P+I), separately labelled.
- If needed to compare convention with paper, report **paper-style non-rejection** (P+U)/N for positives, since the benchmark counts unavailable feature values as satisfying. Do not call this deployment acceptance or silently turn U into plausible.
- Report detection for every S1–S5 class and pooled damage; because this subset has 30 in each class, unweighted macro and micro damage detection agree.
- Paired comparison: on the same 150 damaged inputs, count baseline miss + PRIS detect, and baseline detect + PRIS miss. Use a parent-cluster bootstrap if giving uncertainty: the five variants of a parent are dependent.
- Baseline validity is minimum distance >0.5 Å or >0.7 Å. Matching source implementation uses minimum off-diagonal periodic distance plus the shortest lattice-vector length. All E3 variants were selected to have minimum contact >=0.9 Å, so these baselines are guaranteed to detect zero on E3. This is a selection artifact and must be called out; E3 cannot provide an unbiased quantitative superiority estimate over those cutoffs.

## Frozen rule details and pitfalls

- Public analyzer constants: rho >=0.735 for Set 1/Set 1-prime, >=0.804 for Sets 2–4; Law2 ionicity >0.50 => rho<=1.05; Law3 mean anion CN<=3.333 => mean reduced contact<=1.081; Law4 Madelung/valence range<=31.45 eV; Law5 max site Madelung energy<=15.17 eV; Law6 ionicity>0.55 => like-charge-bond fraction<=1e-4; Law7 distinct sites/site count<=2/3; Law8 mean relative BV deviation<=0.7143.
- **Set 4 contains seven laws: 1,3,4,5,6,7,8. Law2 only belongs to Set 1-prime.** Do not conjunct all eight and call it Set4.
- Public analyzer hardcodes the reported rounded law thresholds, despite its introductory comment saying every threshold is read from frozen files. Only PSS coefficients are loaded from F3_frozen.json. Archived L4/validity code uses BV threshold 0.7143040821865658; public CLI uses 0.7143. Report version/rounding, do not silently rewrite source.
- The public CLI returns no verdict when charge inference fails; it can return an implausible verdict when one evaluable law fails even if another is missing. Conditional laws with a known false trigger are satisfied; missing trigger is no verdict.
- Shannon radii use nearest-CN and representative-radius fallbacks; missing raw radius does not always produce a no-verdict outcome. Freeze dependency versions since element tables, neighbour selection, and symmetry can affect readings.
- Historical names D1–D8 are individual laws; L1–L4 are sets, not individual laws. Some plotting filenames retain earlier figure numbering.
- `src/make_negatives.py:one` still uses Python salted hash and only S1–S4; do not invoke it to claim deterministic reproduction of the final five-class benchmark. The current physics pipeline uses CRC32 seed; E3 uses its separate SHA256 seed.

## Published metric targets and absent data

Held-out targets (not computable from the released aggregate tables alone): 5,297 experimental +3,612 damaged. Set1 satisfaction/detection 0.991882/0.2890; Set1-prime 0.989428/0.3837; Set2 0.957901/0.6121; Set3 0.917123/0.7004; Set4 0.8180101944496885/0.9111295681063123. Set4 per-class 0.7338308458/0.9090909091/1.0/0.9287749288/0.9850931677. Files: agent_loop/frozen/20260814_l4_plausibility/calib_result.json and experiments/pris_composition_holdout_20260829/results/metrics.csv.

The different deployment benchmark is 440 experimental +2,024 damaged, with Set4 acceptance 0.8295454545454546 and detection 0.8789525691699605. Fixed-distance detections 0.01581027668 at 0.5 Å and 0.03211462451 at 0.7 Å. Source table paper/data/fig6_validity.csv. Its script docstring retains an old 1,964 count: current reported table/paper use 2,024.

`src/validity_rulesets.py` needs absent `PRIS_FEATURES/provenance.parquet` and `PRIS_MATDATA_BLOB` structures.blob, sampling n=900/random_state=5, <=50 atoms, integer-charge success, first440 accepted. The overall discovery/held-out features also are not distributed. ICSD structures are not redistributable under source licence; COD is CC0. Do not imply new small-COD sample re-creates these exact original splits.

PSS coefficients, means, standard deviations and imputation medians are in agent_loop/frozen/20260814_f3_synth/F3_frozen.json. The complete same-composition training and held-out pair feature stores are absent; computing some PSS scores is not reproducing its fitted 68.1%/94.4% ranking results. PU model score shards (reported 48 GB) and all 8,125,976 unlabelled structures are not distributed. Full Fig4/S17/S19/S22 cannot be independently recomputed from checkout alone.

No VASP POTCAR is shipped; task packages contain only potential specifications/hash references. Re-running DFT requires licensed VASP/potentials and adequate compute. Collected outputs permit transparent numerical reanalysis immediately.

## E4 numerical replay protocol

Source: dft/E4_design/stage_b/collected.json (1300 task records) and dft/E4_design/bulk_moduli.json (260 fitted rows).

- Match source `dft/analyze.py:usable`: statuses complete or unconverged; failed/incomplete excluded.
- Group by parent_task. Extract **stage_results.static.energy_last_ev**; volume from static.final_cell, falling back to relax_ions.final_cell. Do not use relax_ions energy, TOTEN, or rounded volume_last_a3.
- At least four valid E(V) points per candidate, sorted by volume. Fit third-order Birch–Murnaghan; require positive V0/B0 and V0 inside the sampled volume interval. Conversion 1eV/Å^3 =160.21766208 GPa.
- Independent script uses energy centering and scipy least_squares with an algebraically equivalent BM3, no upstream analysis imports. Comparisons include absolute and relative B0 errors and residuals, without forcing agreement by using published fit parameters.
- Published E4 figures deliberately oversample large UMA moduli; cannot extrapolate the 260-candidate proportions to all1081 candidates or reproduce full-queue reduction from this subset.
- Source RESULTS.md expects 260 fits (60 screened,140 priority,60 control), excluded3 stageB records; median DFT/UMA ratio0.940, Pearson0.769, Spearman0.710. At 400*median(DFT/UMA)≈376GPa, 123 retained and1 screened meet threshold, yielding123/124≈99.2% retention. Original400GPa and posthoc rescaled threshold must be reported separately.
- RESULTS.md says **1 priority and1 screened** at or above400GPa, despite main text saying 'one candidate remained above400GPa'. Inspect row-level refit before copying the prose.

Deliverable script: outputs/pris_reproduction/scripts/refit_eos.py; portable source copies under outputs/pris_reproduction/data/eos; numerical results under outputs/pris_reproduction/results/eos.

### Completed E4 result

1300 collected records =>1297 eligible points=>260/260 fits. Maximum absolute B0 error0.0002325267482GPa; median5.089376e-8GPa; max relative9.614573e-7. Independent scipy least_squares agrees with reference curve_fit values to substantially better than0.001GPa. 257 five-point and3 four-point fits. Original400GPa count confirmed2: candidate_0017 (Os,priority,400.384513GPa) and candidate_0980 (Re2IrOs6,screened,418.545609GPa). Mapped threshold375.818741GPa gives123 retained+1 screened, hence123/124=99.19355%. Priority-vs-screened ranking0.9661905. See outputs/pris_reproduction/results/eos/README.md for interpretation.
