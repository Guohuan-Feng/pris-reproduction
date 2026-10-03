# Superconductivity Agent pipeline-selection pilot — 2026-10-02

One real GPT session completed 5 attempted pipelines in 10 tool calls (469.3 s). The Agent selected **A05**, the seeded automated arm selected **G01**, and the shared-global anchor was **G01**. Selection was frozen using training OOF before the final development diagnosis.

![Executed workflow](figures/workflow_v2.png)

The public [3DSC-MP snapshot](https://huggingface.co/datasets/fgh123654/3dsc-mp-tc-pilot) has 5,773 records. This round uses 3,764 original training rows / 1,117 chemical-system-or-MP-parent connected groups for three fixed group folds. The original 869 validation rows / 280 groups are held aside this round, but were inspected historically: this is a development comparison, not independent validation. The 1,140 retrospective targets are not accessed this round. Original inverse-composition-multiplicity weights are retained.

Inputs are 109 composition features or 109 plus 12 fixed repaired descriptors. Choices are ExtraTrees / HistGradientBoosting, raw / log1p Tc, global / composition-template / fold-fitted KMeans-3 routing, with separate specialist estimator and target choices. Unspecified routes or those with fewer than 80 fitting rows or 12 groups fall back to the global. Chemistry presence templates and ordinal cluster labels are not proven physical families. Preprocessing, clusters and models fit only fold-training rows. HistGradientBoosting disables early stopping; seed=20261002 and one numerical thread. Full parameters are in [PROTOCOL.md](PROTOCOL.md).

Eight global references are shared before search; four extra references (11 repaired or 28 conventional structure features, ExtraTrees raw/log) are outside the search menu. Both arms select minimum weighted pooled OOF MAE subject to positive-Tc OOF MAE not exceeding that of the SAME overall-best shared global. Fixed automated configurations were precommitted; only the prefix matching all Agent attempts, including failures/duplicates, was executed. Equal attempts do not imply equal fit cost, runtime, priors or sampling distributions. Successful-candidate CV regressor fits (excluding shared references, KMeans fitting and any partial failed-attempt work): Agent=42, automated=60. This one session and one seed do not establish a general Agent advantage.

Repair uses actual positive occupancy-weight sums and the invariant full-direction tensor `(3 tr(Q²)-1)/2`. Undefined short-neighborhood moments become missing: 272 planned shared-value changes on 68 structures, including 45 training and 16 old-validation rows. Performance differences cannot be attributed solely to anisotropy/normalization. Representation checks: 480 training + 240 synthetic, plus 96 original-descriptor replay checks, all pass. Original frozen first-round sources are unchanged. See [repair/audit.json](repair/audit.json).

## Frozen development results

The Agent has a numerical overall-MAE improvement on old validation, but the paired-group interval crosses zero, so a stable benefit is not established.

G02 is the V2 seed-20261002 recomputation of composition + ExtraTrees + log1p, not the immutable seed-20261001 first-round model.

| Pipeline | Input / routing | Global model / target | OOF MAE (K) | Validation MAE (K) | Validation RMSE (K) | Validation positive-Tc MAE (K) | Validation high-Tc MAE (K) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| G01 | composition / global | extra_trees / raw | 7.9127 | 8.0885 | 15.5450 | 10.1449 | 37.3135 |
| G02 | composition / global | extra_trees / log1p | 9.0014 | 8.7599 | 17.6386 | 11.8156 | 54.1618 |
| A05 | composition / chemistry | extra_trees / raw | 7.7526 | 8.0849 | 15.5496 | 10.1957 | 36.4197 |
| D01 | diagnostic_repair11 / global | extra_trees / raw | 8.1111 | 7.9427 | 15.1510 | 9.9223 | 40.4597 |


Column labels are MAE/RMSE in kelvin; OOF uses training rows and the later columns use the old 869-row validation. That validation has 248 recorded-zero, 621 positive and 35 high-Tc rows (9 high-Tc groups). Positive/high-Tc and RMSE tradeoffs must be retained. The positive guard is an OOF selection criterion, not a guarantee of validation non-regression.

Agent minus shared-global validation MAE: **-0.0037 K**, paired group-bootstrap 95% interval **[-0.1948, +0.1507]**. Agent minus automated arm: **-0.0037 K**, interval **[-0.1948, +0.1507]**. Negative means lower Agent error. These are conditional intervals on historically observed development rows; they exclude training/search/prior-inspection uncertainty. The best global across shared and extra references by OOF was G01; do not conflate it with the shared anchor. Original-round retrospective MAE around 4.3 K is a separate cohort, not a denominator for this round's improvement.

All selections, specifications, code/data hashes and actual search records were frozen, then all models refit on original training. Preparation separated the old validation labels. The final scorer persisted all frozen predictions before opening that isolated label file for scoring; scientific tools never exposed those labels. No validation refit, post-evaluation reranking or second search occurred. [Selection](selection.json), [access journal](final/access_journal.json), [all metrics](final/results.json), [complete comparison table](comparison_table.csv), [independent verification](verification.json).

Actual Agent hypotheses and revisions appear in [tool events](agent/tool_events.jsonl) and [its OOF-only conclusion](agent/conclusion.json). The report's subsequent validation outcomes were unavailable to that scientific session. Full advisor report: [中文](REPORT_zh.md).

Next: use the frozen overall/subgroup tradeoffs to decide whether routing warrants genuinely unobserved data and multiple-seed evaluation. If regression gains are inadequate, design a separate classification/anomaly task with verifiable labels and an independent evaluation before another search. Regression residuals alone do not prove label errors, physical mechanisms or new superconductors. MP-matched geometries and artificial doping remain proxies; recorded zero is not universal nonsuperconductivity evidence.

This public package includes isolated inputs, folds, repaired features, code, all OOF/final predictions and complete search evidence. Large local joblib binaries are omitted; their hashes remain in results. `python verify_results.py --root <package> --skip-models` checks public numeric/selection evidence and explicitly omits local model replay. Do not rerun the bounded Agent in the frozen directory. [Environment versions](environment_versions.json), [protocol audit](protocol_review.md), [package manifest](PACKAGE_MANIFEST.json). Upstream 3DSC data attribution remains CC BY 4.0 as documented by the linked dataset card. No private meeting recording or transcript is published.

The clearer development improvement is conventional target choice: composition ExtraTrees raw Tc has validation MAE 8.0885 versus log1p 8.7599 K (approximately 7.66% lower). This must not be credited as the new Agent intervention. Added Agent routing changes overall MAE by only 0.0037 K (0.045%), with an interval crossing zero and slightly worse positive-Tc MAE. Predeclared diagnostic D01 has lower validation MAE (7.9427 K) than the Agent; it did not win OOF selection, and no post-validation reselection occurs.

[Data provenance and upstream attribution](DATA_PROVENANCE.md) · [Upstream license](UPSTREAM_LICENSE.md).

Actual accounting: five attempts, four completed pipelines, one pre-fit file-persistence failure (A03), which consumed an attempt. Original state and tool logs are preserved; an explicitly documented administrative reconstruction completed the failure inventory without changing specifications, results or budget. [Reconciliation record](agent/attempt_record_reconciliation.json).

The conventional raw-target gain worsens recorded-zero MAE from 1.2316 (G02) to 3.0222 K (G01). The added Agent Cu/O contribution of −0.02754 K is almost canceled by other-route +0.02388 K. Agent-versus-control and Agent-versus-G01 intervals are the same comparison because the control retained G01, not two independent confirmations.

[Route and group decomposition](final/route_diagnostics.json) · [Final interpretation audit](final/final_interpretation_audit.md) · [Administrative audit](final/administrative_audit.json) · [Portable public verification](public_verification.json).
