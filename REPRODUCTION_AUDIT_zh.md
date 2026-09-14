# PRIS 复现审计（2026-09-14）

[English](REPRODUCTION_AUDIT.md) | 中文

来源：[AI4QC/PRIS](https://github.com/AI4QC/PRIS)，固定提交 `34e6c86c083759dc1ee594ae22238ea9b5ebd8f4`。
本审计只读检查上游源码；`work/PRIS` 下没有发现 AGENTS.md。审计人员没有执行上游分析或集群脚本。后文单独记录使用独立脚本完成的数值复算。

## 可以据实复算的内容

1. 对给定原子结构运行完整 PRIS 分析器，包括公开的 MgAl2O4 示例。
2. **E3 公开结构子集：**30 个 COD 实验母体和 150 个固定受损变体，每类 S1–S5 各 30 个。原始 POSCAR 已提交，可重新测量。这是从 discovery split 选出的诊断子集，不是独立留出基准，也不是论文 5,297/3,612 主结果的直接复现。
3. **E4 数值再分析：**从 1,300 条 stage-B DFT 记录独立拟合 260 条 Birch–Murnaghan 状态方程，并与公开体模量比较。这是从已发布数值输出重新推导物理量，没有重新运行 VASP。
4. **E4 对称性检查：**260 个公开 DFT 弛豫后 CIF 可用 spglib/pymatgen 独立测量，对应生成态 POSCAR 位于 `dft/E4_design/tasks`。公开补充数据的 `SUMMARY.json` 采用 `src/dft_supplementary_data.py` 的**输入晶胞口径**，`symprec=0.01 Å`：生成态 Law 7 通过 61 个，弛豫后通过 113 个，新增通过 52 个、失去通过 0 个。这些计数及逐结构空间群编号、位点比例和判定均已独立复算一致。另一个函数 `dft/analyze.py:spacegroup_and_economy` 使用标准原胞；对应敏感性分析得到 66→110 个通过，新增 44 个、失去 0 个。标准化可能在容差内理想化坐标，不能把全部判定变化归因于晶胞重复。完整分析器无法判定许多富金属 E4 结构，但单独的 Law 7 不需要电荷。
5. 多张图可根据公开汇总数据重绘。汇总图重绘是数值一致性检查，不等于从原始结构独立重算基准。

## E3 的准确来源与筛选条件

文件：`work/PRIS/dft/E3_crosscheck/tasks/E3-cod-<id>-<variant>/POSCAR.init`；同目录 `TASK.json` 记录元数据；`dft/E3_crosscheck/selection.json` 记录筛选；`MANIFEST.json` 记录哈希。

- 30 个 `P0` 母体，`S1`、`S2`、`S3`、`S4`、`S5` 各 30 个；另外 20 个未扰动的 GNoME 晶胞不能并入实验正例组。
- `dft/build_tasks.py:load_provenance` 先限制为 `in_analysis_set`：阴离子仅取 O/S/Se/Te/N/P/F/Cl/Br/I 中一种，不含 H 或 C；这是上游 provenance 规则。
- `build_e3` 选择 discovery split，要求 `n_sites <=16`、`n_elements >=2`，按 `source_id` 排序，取最先符合条件的 30 个母体。
- 必须能解析、实际含 2–16 个位点、结构有序、母体最短接触距离 ≥1.0 Å，并成功进行**整数**价态分配 `discriminate.guess_oxi`。
- 五类扰动均须可构造；在 `StructureMatcher(primitive_cell=False, attempt_supercell=False, scale=False, ltol=0.01, stol=0.02, angle_tol=0.5)` 下，S2 或 S5 不能与母体相同。
- 六个晶胞中的每一个都必须具有 ≥0.9 Å 的最小接触距离，否则剔除整个母体。较早预注册写的是 0.6 Å，但 Amendment 2 明确提高至 0.9 Å；现有源码和 `selection.json` 均采用 0.9 Å。
- 随机数使用由 `E3|<source_id>` 的 SHA256 导出的稳定种子；直接使用已提交的变体可避免重新生成时的歧义。
- **筛选母体没有要求 DFT 计算成功。**公开 E3 表分析全部 200 个任务，包括完成但未收敛的任务。固定晶胞计算收敛 189/200，全晶胞计算收敛 195/200。PRIS 预筛选应使用输入 POSCAR，不应按之后的 DFT 结果删除结构。
- S1：单个晶格轴压缩 15–30%。S2：交换不同元素且形式电荷差 ≥1 的两个阳离子。S3：向各位点加入各向同性高斯随机笛卡尔位移，幅度在 0.3–0.8 Å 抽样。S4：晶格整体膨胀 20–40%。S5：交换一个阳离子和一个阴离子。来源为 `src/make_negatives.py:perturb`。
- S2/S5 在坐标不变时交换元素，保持组成不变；推断电荷须随元素移动。重新读取 POSCAR 并按组成推断电荷即可实现，不应在交换后仍应用原来按位点索引排列的价态向量。

## E3 特征流程与指标定义

`src/pris_analyze.py:measure` 使用公开维护的科学函数：`guess_oxi/frac_oxi`、`phys_law.phys_feats`、`elec_feat.elec_feats`、`discriminate.criteria`、`f3_features._feats` 和仅依赖组成的离子性。完整 440 母体部署脚本使用同一组核心 `phys_feats/elec_feats/criteria`，并以 0.01 Å 容差直接运行 spglib 对称性分析。E3 原本检验的是 DFT 与 MatterSim 弛豫能量的关系；未找到专门报告这 30 个 E3 COD 母体的 PRIS 通过率/检出率的冻结表。因此，新增 E3 PRIS 测量没有可以直接对齐的论文百分比。

对每个规则集和样本组，保留全部输入行，记 P=合理、I=不合理、U=无法判定、N=P+I+U：

- 可判定覆盖率：`(P+I)/N`。
- 全输入实验通过率：`P/N`；明确拒绝率：`I/N`；无法判定率：`U/N`。
- 已判定样本中的实验通过率：`P/(P+I)`，仅在分母大于 0 时报告。
- 全输入扰动检出率：`I/N`；另行标明已判定样本中的检出率 `I/(P+I)`。
- 如需比较论文口径，可为正例另报**论文式未拒绝率** `(P+U)/N`，因为相应基准把不可用特征视为满足条件。不能把它称为部署通过率，也不能悄悄把 U 转成合理。
- 分别报告 S1–S5 和合并扰动组。由于每类均为 30 个，不加权的宏平均与微平均检出率相同。
- 配对比较应在同一批 150 个受损输入上统计“基线漏检而 PRIS 检出”和“基线检出而 PRIS 漏检”。如给出不确定度，应按母体进行聚类 bootstrap，因为同一母体的五个变体相互依赖。
- 距离基线的通过条件是最小距离 >0.5 Å 或 >0.7 Å。匹配上游实现时，最小值取自周期距离矩阵的非对角元素和最短晶格向量长度。E3 全部变体按 ≥0.9 Å 选入，因此这些基线必然零检出。这是选择效应，必须说明；不能据 E3 对这些阈值作无偏的定量优越性判断。

## 冻结规则细节与常见误读

- 公开分析器常数：Set 1/Set 1′ 的 ρ≥0.735，Set 2–4 的 ρ≥0.804；Law 2 为离子性 >0.50 时要求 ρ≤1.05；Law 3 为平均阴离子 CN≤3.333 时要求平均约化接触距离 ≤1.081；Law 4 要求 Madelung/价态范围 ≤31.45 eV；Law 5 要求最大位点 Madelung 能量 ≤15.17 eV；Law 6 为离子性 >0.55 时要求同号电荷键比例 ≤1e-4；Law 7 要求不同对称位点数/位点总数 ≤2/3；Law 8 要求平均相对键价偏差 ≤0.7143。
- **Set 4 由七条规则组成：1、3、4、5、6、7、8。Law 2 只属于 Set 1′。**不能把八条全部取交集后称为 Set 4。
- 公开分析器将四舍五入后的规则阈值写成常数，尽管其开头注释声称全部阈值来自冻结文件。实际只有 PSS 系数从 `F3_frozen.json` 加载。归档 L4/validity 代码的 BV 阈值是 0.7143040821865658，公开 CLI 用 0.7143。应记录版本及舍入差异，不应静默改源码。
- 公开 CLI 在电荷推断失败时返回无法判定；若一条可测规则失败，即使另一条缺失，仍可返回不合理。已知触发条件为假的条件规则视为满足；触发条件缺失则无法判定。
- Shannon 半径有最近配位数和代表半径回退；原始半径缺失不必然导致无法判定。应冻结依赖版本，因为元素表、邻居选取和对称性求解均可能改变测量。
- 历史名称 D1–D8 表示单条规则；L1–L4 表示规则集。部分绘图文件名仍保留旧图号。
- `src/make_negatives.py:one` 仍使用 Python 加盐哈希且只有 S1–S4；不能调用它并声称确定性地复现最终五类基准。当前物理流程使用 CRC32 种子，而 E3 单独使用 SHA256 种子。

## 已发表指标与缺失数据

留出集目标为 5,297 个实验结构＋3,612 个受损结构，仅凭已公开汇总表不能重算。Set 1 的通过率/检出率为 0.991882/0.2890；Set 1′ 为 0.989428/0.3837；Set 2 为 0.957901/0.6121；Set 3 为 0.917123/0.7004；Set 4 为 0.8180101944496885/0.9111295681063123。Set 4 分类别检出率为 0.7338308458/0.9090909091/1.0/0.9287749288/0.9850931677。来源：`agent_loop/frozen/20260814_l4_plausibility/calib_result.json` 和 `experiments/pris_composition_holdout_20260829/results/metrics.csv`。

另一个部署基准含 440 个实验结构＋2,024 个受损结构，Set 4 通过率 0.8295454545454546、检出率 0.8789525691699605。0.5 Å 距离基线检出率 0.01581027668，0.7 Å 为 0.03211462451。来源表：`paper/data/fig6_validity.csv`。脚本 docstring 留有旧计数 1,964；现有表和论文使用 2,024。

`src/validity_rulesets.py` 需要未提供的 `PRIS_FEATURES/provenance.parquet` 和 `PRIS_MATDATA_BLOB` 中的 `structures.blob`；它按 `n=900/random_state=5` 抽样，要求 ≤50 个原子、整数电荷分配成功，取前 440 个通过筛选的结构。完整 discovery/held-out 特征也没有分发。ICSD 结构受原许可证限制不能再分发；COD 使用 CC0。不能声称新抽取的小规模 COD 样本重建了相同原始划分。

PSS 的系数、均值、标准差和缺失值填充中位数位于 `agent_loop/frozen/20260814_f3_synth/F3_frozen.json`。完整同组成训练对和留出对的特征库缺失；计算部分 PSS 分数不等于复现其 68.1%/94.4% 排序结果。报告为 48 GB 的 PU 模型分数分片和全部 8,125,976 个未标注结构没有分发，仅凭本地公开仓库不能独立重算完整 Fig. 4/S17/S19/S22。

仓库没有提供 VASP POTCAR；任务包只有赝势规格和哈希引用。重新运行 DFT 需要有许可的 VASP/赝势及足够算力。已收集的公开输出可以直接用于透明的数值再分析。

## E4 数值复算协议

输入：`dft/E4_design/stage_b/collected.json`（1,300 条任务记录）和 `dft/E4_design/bulk_moduli.json`（260 条拟合结果）。

- 匹配 `dft/analyze.py:usable`：保留 `complete` 和 `unconverged`，排除失败或未完成记录。
- 按 `parent_task` 分组。提取 **`stage_results.static.energy_last_ev`**；体积来自 `static.final_cell`，缺失时回退至 `relax_ions.final_cell`。不用 `relax_ions` 能量、TOTEN 或四舍五入后的 `volume_last_a3`。
- 每个候选至少四个有效 E(V) 点，按体积排序。拟合三阶 Birch–Murnaghan，要求 V0/B0 为正且 V0 位于采样体积范围内。换算关系为 1 eV/Å³ =160.21766208 GPa。
- 独立脚本对能量中心化，使用代数等价 BM3 和 SciPy `least_squares`，不导入上游分析代码。比较 B0 绝对误差、相对误差和残差，不使用公开拟合参数强行对齐结果。
- 公开 E4 样本有意超额抽取高 UMA 体模量候选；不能把 260 个候选的比例外推到全部 1,081 个候选，也不能由此重建全队列削减率。
- 上游 `RESULTS.md` 记录 260 个拟合（60 screened、140 priority、60 control），排除三条 stage-B 记录；DFT/UMA 比值中位数约 0.940，Pearson 约 0.769，Spearman 约 0.710。在 `400×median(DFT/UMA)≈376 GPa` 的阈值下，保留组 123 个、筛除组 1 个达标，得到 `123/124≈99.2%` 的保留率。原始 400 GPa 阈值与事后映射阈值必须分开报告。
- `RESULTS.md` 记录 **1 个 priority 和 1 个 screened** 的 DFT 体模量 ≥400 GPa，而正文写作“one candidate remained above 400 GPa”。应先检查逐行拟合结果，不能直接照搬该叙述。

交付脚本：[scripts/refit_eos.py](scripts/refit_eos.py)；可移植输入副本位于 `data/eos`，数值结果位于 `results/eos`。

### 已完成的 E4 结果

1,300 条记录→1,297 个有效点→260/260 个成功拟合。B0 最大绝对误差 0.0002325267482 GPa，中位绝对误差 5.089376×10⁻⁸ GPa，最大相对误差 9.614573×10⁻⁷。独立 SciPy `least_squares` 与上游 `curve_fit` 的差异远低于 0.001 GPa；257 个为五点拟合，3 个为四点拟合。

确认有两个候选达到原始 400 GPa：`candidate_0017`（Os，priority，400.384513 GPa）和 `candidate_0980`（Re2IrOs6，screened，418.545609 GPa）。映射阈值 375.818741 GPa 下，保留组 123 个、筛除组 1 个达标，故保留率 `123/124=99.19355%`。priority 与 screened 的成对排序准确率为 0.9661905。具体解释见 [EOS 说明](results/eos/README.md)。
