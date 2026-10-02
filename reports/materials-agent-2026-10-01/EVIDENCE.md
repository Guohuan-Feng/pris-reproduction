# Methods and evidence / 方法与证据

This page accompanies the faculty progress report. It publishes selected complete numerical comparison tables and source-check summaries. The 2,879 prepared inputs are publicly available on [Hugging Face](https://huggingface.co/datasets/fgh123654/materials-energy-stability-agent-dev); the full analysis source and complete replay archive are not included here. The two revised explanations failed their defined exploratory tests; passing a numerical audit is not independent scientific confirmation.

本页是导师汇报的证据索引，提供完整组表及源核查摘要。本轮 2,879 条准备后的输入已在 [Hugging Face](https://huggingface.co/datasets/fgh123654/materials-energy-stability-agent-dev) 公开；完整分析源码及全部重放包仍未完整公开。数值复核通过不等于独立科学确认。

| File | Contents / 内容 |
|---|---|
| [progress_summary.json](evidence/progress_summary.json) | Data boundary, initial/revised outcomes, case numbers, audit status, original input hashes / 数据范围、结果、核查状态 |
| [H01_pairs.csv](evidence/H01_pairs.csv) | All 39 composition groups, highest/lowest energy members, fixed-q short contacts / 39 组全量对照 |
| [H01b_group_scores.csv](evidence/H01b_group_scores.csv) | All 39 signed relative-compression scores / 修订后的完整方向结果 |
| [matched_pairs_stage1.csv](evidence/matched_pairs_stage1.csv) | All 21 matched pairs with environment distances / 筛选后的全部 21 对 |
| [matched_pairs_stage2.csv](evidence/matched_pairs_stage2.csv) | All 21 matched pairs at 3 fixed cutoffs (63 rows) / 第二轮全部阈值结果 |
| [composition_groups.csv](evidence/composition_groups.csv) | Group minima, native hull labels and exact composition checks / 组内最低能仍可能不稳定 |
| [composition_pairs.csv](evidence/composition_pairs.csv) | All 43 formation-vs-hull difference identity checks / 两种差值不构成独立证据 |
| [source_quality_report.json](evidence/source_quality_report.json) | Eight selected source cases and the correction-hypothesis revision / 八例源兼容核查与修订 |
| [pair_comparisons.json](evidence/pair_comparisons.json) | Five same-composition source pairs, raw/corrected energy differences and declared matcher settings / 五对源条目分解 |

## Definitions and interpretation

- Composition is atomic fractions, not equal cell size. Exact rational fractions were checked for repeated groups.
- q = distance / sum of the two covalent radii. Contacts are positive-distance directed periodic edges within 6 Å, retaining image multiplicity and nonzero self images. Contact counts and smooth weights are geometric descriptors, not physical bond counts.
- H01 fixes q < 0.8; high-minus-low differences use equal group weight. H01b averages signed log(q_low/q_high) over common element pairs. The lowest-energy reference is selected with observed labels and is retrospective. Pair types present in only one member are excluded by the predefined intersection, limiting physical interpretation.
- H02 matching is energy-blind: symmetric relative per-atom-volume difference ≤5% and absolute qmin difference ≤0.03. Smooth weights are exp(-(q/1.2)^6); species-resolved empirical distributions use Wasserstein-1, contact matrices and EN loads. The combined distance is the mean of available fixed components, with no fitted coefficients.
- H02R1 uses hard q ≤ 1.1,1.2,1.3 contacts; each Mg–Mg decrease and Mg–Zn increase must persist at all three cutoffs. Only 1.2 supports both. Local mixing tensors do not encode full network topology.
- H01/H01b registration and result chronology have executed-code snapshots and a hash chain in the retained local archive. H02 preserves original hypothesis/revision bytes, logs, final code and supplemental file times; the successful stage-1 source was not independently snapshotted. No backdated registration is claimed.
- Independent numerical implementations reproduce the contact/thermodynamic checks and all environment comparisons to floating-point precision. Final-code replay reproduced both environment summaries. These audits test numerical execution, not causality or unseen-data performance.
- The source audit verifies eight selected prepared records against released computed entries/elemental references, plus periodic geometry. This does not prove DFT convergence, true magnetic/charge state or absence of upstream association errors. Compatibility corrections are shipped snapshot values; the full historical generation environment is unavailable.

## Provenance and publication boundary

The original input filenames and SHA256 are in progress_summary.json. Prepared development inputs were derived from the earlier [scientific-agent experiment](../../experiments/scientific-agent-2026-09-30/README.md). Source release: Materials Project / Matbench Discovery Figshare article 22715158 version 38. Raw filenames inspected were 2023-02-07-mp-computed-structure-entries.json.gz, 2023-02-07-mp-elemental-reference-entries.json.gz and 2025-02-01-mp-energies.csv.gz. Snapshot attribution/license details are preserved in the earlier [data license](../../experiments/scientific-agent-2026-09-30/DATA_LICENSE.md) (CC BY 4.0).

Public data repository: [fgh123654/materials-energy-stability-agent-dev](https://huggingface.co/datasets/fgh123654/materials-energy-stability-agent-dev). It contains the same 2,879 already observed development records: 2,164 historical train-role and 715 adaptive-validation-role records. The [online material table](https://huggingface.co/datasets/fgh123654/materials-energy-stability-agent-dev/viewer/default/development) is available with HF viewer config `default` and one `development` split. The retained `split` column records the historical roles and does not create a new held-out test. The [complete prepared structures](https://huggingface.co/datasets/fgh123654/materials-energy-stability-agent-dev/resolve/main/structures.jsonl.gz?download=true), `features.csv.gz` and `targets.csv.gz` are at the [repository root](https://huggingface.co/datasets/fgh123654/materials-energy-stability-agent-dev/tree/main). These three gzip inputs retain their original SHA256 values recorded in [progress_summary.json](evidence/progress_summary.json); [materials.csv](https://huggingface.co/datasets/fgh123654/materials-energy-stability-agent-dev/blob/main/materials.csv) is a merged derivative. Materials Project / Matbench Discovery source attribution and CC BY 4.0 remain applicable. This is data publication, not new original experimental data or a new model training run.

The selected CSV/JSON evidence copies are byte-identical to their completed local result files. progress_summary.json is a derived publication summary; it excludes local machine paths and does not replace historical registration records. Figures are copies of the reviewed findings plot and newly drawn workflow diagrams; drawing a workflow is not an additional experiment. PUBLICATION_MANIFEST.json inventories only this report's publication files. The full local scientific archive remains unchanged.

中文要点：保持原有科学证据不变；上传的是导师报告与选定完整表格。汇总 JSON 为发布时整理的派生摘要，不冒充原始登记文件。所有研究仍限于已观察开发数据；本轮没有拟合预测器、运行新 DFT 或使用此前最终/确认数据。当前 Agent 调查不能冒充 2026-09-30 另一轮 GPT CLI 实验。

The [dataset publication receipt](evidence/dataset_publication.json) pins HF revision `11d4111608864bb8ecc4a8a8f50360097deb82a7`, records an anonymous byte-for-byte download check of all 11 release files, and confirms the fully indexed 2,879-row, 40-column viewer. / [数据发布校验记录](evidence/dataset_publication.json)固定 HF 版本并记录公开下载一致性与完整在线表格检查。
