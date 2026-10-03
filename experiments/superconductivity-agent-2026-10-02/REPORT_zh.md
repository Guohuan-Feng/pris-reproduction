# 超导临界温度：Agent 模型与分组选择第二轮（2026-10-02）

Agent 选择 A05 后，旧验证整体 MAE 与全局基线基本持平：仅下降 0.0037 K（0.045%），尚无稳定额外收益。 本轮完成了真实 GPT 工具闭环、固定模型对照、同尝试次数的自动搜索、方案冻结、一次开发评估以及独立数值复核。

这轮 Agent 在旧验证上有整体 MAE 数值改善，但组差值区间跨零，尚未建立稳定收益。 记录零值 MAE：共享全局 3.0222 → Agent 2.8844 K；正 Tc MAE：共享全局 10.1449 → Agent 10.1957 K；≥40 K MAE：共享全局 37.3135 → Agent 36.4197 K。整体仅降低 0.0037 K（0.045%）。

## 数据集与代码流程

数据是公开 [3DSC-MP 冻结快照](https://huggingface.co/datasets/fgh123654/3dsc-mp-tc-pilot)：共 5,773 条，成分、匹配 MP 晶体结构和 Tc（K）。本轮训练 **3,764 条 / 1,117 个严格连接组**，旧验证 **869 条 / 280 个组**；历史评估 1,140 条的标签不参与本轮。化学体系或 MP 母体关联的记录放在同一连接组，三个训练 OOF 折均检查了化学体系、母体、标准成分及连接组的交叉重叠为零。保留第一轮的成分重复度倒数权重。

![第二轮完整流程](figures/workflow_v2.png)

[矢量流程图](figures/workflow_v2.svg)；[执行协议](PROTOCOL.md)；[准备及分组证据](data/data_audit.json)。

1. 固定输入为 109 个成分特征，或者 109 + 12 个修复后的结构描述符。
2. 在训练集固定的三个严格分组折上计算 pooled OOF 反馈；所有填补、变量筛选、缩放、聚类和模型拟合只使用该折拟合部分。
3. 先计算八个共享全局模型和四个额外参考。GPT 根据 OOF 误差案例选择输入、ExtraTrees / HGB、原值 / log1p 目标和全局 / 成分规则 / KMeans 分组。各组可有独立模型与目标，过小或未配置组回退到全局模型。
4. 自动搜索使用预先冻结的五个种子配置，只执行与 GPT 总尝试次数相同的前缀。失败、重复也消耗次数；次数相同不代表算力、模型拟合数、先验或配置分布相同。
5. 两臂统一使用正 Tc OOF 不退步约束，再最小化整体加权 MAE。基准锚点是整体 OOF 最好的同一个共享全局模型 G01，不是从不同模型挑选最好的子群分数。
6. 记录、配置、代码和两臂选择冻结后，仅用原训练集重拟合。准备阶段已分离旧验证标签；最终评分器保存所有锁定预测后才打开隔离标签文件评分，不按验证结果重新排名或再次搜索。

“成分分组”是 Cu 和 O 同时存在优先，其次 Fe 和 P/As/S/Se/Te 中至少一种，剩余为 other。专家需要至少 80 个拟合样本和 12 个严格组。KMeans=3，10 次初始化，每折独立拟合，按质心 comp_Z_mean 命名；跨折的同名 cluster 不一定对应同一群体。这些规则均不能证明物理材料家族。

HGB 是 `HistGradientBoostingRegressor`（直方图梯度提升树）。它与 ExtraTrees 共同构成固定模型菜单。ExtraTrees 使用 160 棵树、叶子最小样本 2、max_features=1.0（全部特征）；HGB 使用 160 次迭代、15 个最大叶节点、学习率 0.08、最小叶样本 20、L2=1、关闭提前停止。种子均为 20261002，单线程；完整参数见代码，未宣称最优调参。

## 描述符修复

真实正占据权重按其实际和归一化；方向量改为完整张量 `(3 tr(Q²)-1)/2`，消除笛卡尔方向依赖。无有效邻居时的未定义矩改为缺失值。本轮修复包含这一语义变化，不能将差异全部归因于旋转不变性。

共 480 项训练结构表示检查、240 项合成表示检查、96 项原描述符重放检查通过；解析方向例子 isotropic=0、planar=0.25、collinear=1。68 个结构无 3.5 Å 内邻居，四个原零值矩改为缺失，共 272 处预期变化（训练 45、旧验证 16、历史结构 7）；共享特征没有其他变化。第一轮冻结源文件未修改。[完整审计](repair/audit.json)。

## 实际 Agent 运行

请求模型 `gpt-5.6-sol`，推理强度 `medium`，通过现有 Codex 登录执行一个会话。共 **10 次工具调用、5 次配置尝试**，耗时 **469.3 秒**。工具次数：`{"describe_data": 1, "run_strategy": 5, "counterexamples": 1, "compare_strategies": 2, "record_conclusion": 1}`。外部工具调用审计为空。自动臂匹配 5 次尝试；成功候选的 OOF 回归器拟合数 Agent=42、自动=60，共享参考、KMeans 拟合及失败尝试中的部分工作不在该候选合计中；最终回归器重拟合 46 次。

- **A01 chemistry_et_raw_uniform**：Fold-local experts on the fixed mutually exclusive cu_o, fe_anion, and other composition routes will reduce pooled OOF MAE by separating target relationships, while raw-target ExtraTrees will preserve positive-Tc and rare high-Tc predictions.
  检验条件：Falsified if pooled OOF MAE is not below G01's 7.9126834488 K or positive-Tc OOF MAE exceeds G01's 8.8321655079 K; high-Tc MAE and route behavior diagnose whether specialization merely overfits small groups.；修订来源：none；状态：complete。
- **A02 chemistry_cuo_global_et_raw**：A01's largest errors reflect unstable cu_o specialization under group-distribution imbalance; routing cu_o through the global raw ExtraTrees model while retaining fe_anion and other experts will lower overall and recorded-zero error without losing the positive-Tc guard.
  检验条件：Falsified as a revision if OOF MAE is not below A01's 7.8365759376 K, or if positive-Tc MAE exceeds G01's 8.8321655079 K; a rebound in high-Tc MAE would show that the cu_o expert's gains came with the observed zero-Tc tradeoff.；修订来源：A01；状态：complete。
- **A03 chemistry_cuo_hgb_raw**：The cu_o route benefits from specialization for high-Tc cases, but ExtraTrees is unstable across its relatively few connected groups; a raw-target histogram gradient boosting cu_o expert with raw ExtraTrees elsewhere will reduce extreme cu_o misses and improve A01.
  检验条件：Falsified if pooled OOF MAE is not below A01's 7.8365759376 K or positive-Tc MAE exceeds G01's 8.8321655079 K; worse high-Tc MAE would refute the intended regularization benefit for rare high-Tc cases.；修订来源：A01；状态：failed。
- **A04 chemistry_cuo_hgb_raw_retry**：The cu_o route benefits from specialization for high-Tc cases, but ExtraTrees is unstable across its relatively few connected groups; a raw-target histogram gradient boosting cu_o expert with raw ExtraTrees elsewhere will reduce extreme cu_o misses and improve A01.
  检验条件：Falsified if pooled OOF MAE is not below A01's 7.8365759376 K or positive-Tc MAE exceeds G01's 8.8321655079 K; worse high-Tc MAE would refute the intended regularization benefit for rare high-Tc cases.；修订来源：A01；状态：complete。
- **A05 chemistry_fe_global_et_raw**：The 37-group fe_anion specialist contributes avoidable small-route variance, while the cu_o expert supplies the observed high-Tc gain and the large other expert is well supported; falling fe_anion back to global raw ExtraTrees will improve A01 without sacrificing its positive-Tc guard.
  检验条件：Falsified if pooled OOF MAE is not below A01's 7.8365759376 K or positive-Tc MAE exceeds G01's 8.8321655079 K; degradation localized to high-Tc error would indicate useful fe_anion specialization despite its small group count.；修订来源：A01；状态：complete。

[实际工具记录](agent/tool_events.jsonl)、[Agent 结论](agent/conclusion.json)、[调用与使用量](agent/invocation.json)、[自动搜索预承诺](controls/plan.json)、[自动执行](controls/execution.json)。Agent 结论只基于训练 OOF，下面旧验证结果由外层评估器在其结束后计算。

## 选择与结果

G02 是本轮按种子 20261002 重算的“成分＋ExtraTrees＋log1p”参考，用于同队列公平比较；它并非第一轮种子 20261001 的不可修改模型。

共享全局锚点 **G01**；Agent 选 **A05**，自动臂选 **G01**。额外参考也参与比较，OOF 最好的全部全局参考为 **G01**。Agent 训练 OOF MAE=7.7526 K，对照锚点=7.9127 K。[锁定选择](selection.json)。

| 方案 | 输入 / 路由 | 全局模型 / 目标 | OOF MAE (K) | 旧验证 MAE (K) | RMSE (K) | 正 Tc MAE (K) | ≥40 K MAE (K) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| G01 | composition / global | extra_trees / raw | 7.9127 | 8.0885 | 15.5450 | 10.1449 | 37.3135 |
| G02 | composition / global | extra_trees / log1p | 9.0014 | 8.7599 | 17.6386 | 11.8156 | 54.1618 |
| A05 | composition / chemistry | extra_trees / raw | 7.7526 | 8.0849 | 15.5496 | 10.1957 | 36.4197 |
| D01 | diagnostic_repair11 / global | extra_trees / raw | 8.1111 | 7.9427 | 15.1510 | 9.9223 | 40.4597 |


表中的“旧验证”是同一 869 条开发样本。本轮零值 248 条、正 Tc 621 条、≥40 K 35 条；高 Tc 只有 9 个严格组。OOF 和旧验证列对应不同队列，不能横向解释为误差随实验下降。

Agent 减共享全局的旧验证 MAE 差 **-0.0037 K**，配对组 bootstrap 95% 区间 **[-0.1948, +0.1507] K**。Agent 减自动臂差 **-0.0037 K**，区间 **[-0.1948, +0.1507] K**。负差表示 Agent 的误差更小；区间只描述这些固定模型在这一已观察开发队列上的条件差异，未包含训练、搜索、历史观察不确定性。[完整结果](final/results.json)。

所选 Agent 在旧验证上的正 Tc MAE 退步 0.0508 K，这一失败需保留。正 Tc 约束只用于训练 OOF 选择，不能保证旧验证子群不退步；必须保留表中实际正 Tc、高 Tc 与 RMSE 结果。第一轮历史 1,140 条约 4.3 K MAE 属于另一个队列，本轮未重读其目标，不能用来和新 OOF / 869 条验证分数计算改善比例。

### 全部执行方案

| 方案 | 输入 / 路由 | 全局模型 / 目标 | OOF MAE (K) | 旧验证 MAE (K) | RMSE (K) | 正 Tc MAE (K) | ≥40 K MAE (K) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| G01 | composition / global | extra_trees / raw | 7.9127 | 8.0885 | 15.5450 | 10.1449 | 37.3135 |
| G02 | composition / global | extra_trees / log1p | 9.0014 | 8.7599 | 17.6386 | 11.8156 | 54.1618 |
| G03 | composition / global | hist_gradient_boosting / raw | 8.2833 | 8.2716 | 15.5102 | 10.0590 | 33.9725 |
| G04 | composition / global | hist_gradient_boosting / log1p | 9.3140 | 8.2258 | 16.3008 | 10.7315 | 39.7005 |
| G05 | composition_repaired / global | extra_trees / raw | 7.9811 | 8.0320 | 15.4104 | 10.0311 | 41.6926 |
| G06 | composition_repaired / global | extra_trees / log1p | 9.3310 | 8.6168 | 17.5491 | 11.5300 | 57.7505 |
| G07 | composition_repaired / global | hist_gradient_boosting / raw | 8.3461 | 8.0990 | 15.3633 | 9.6878 | 33.3927 |
| G08 | composition_repaired / global | hist_gradient_boosting / log1p | 9.2506 | 8.3637 | 16.8147 | 11.0257 | 50.0121 |
| D01 | diagnostic_repair11 / global | extra_trees / raw | 8.1111 | 7.9427 | 15.1510 | 9.9223 | 40.4597 |
| D02 | diagnostic_repair11 / global | extra_trees / log1p | 9.3601 | 8.6033 | 17.6912 | 11.5371 | 59.4441 |
| R01 | reference_structure28 / global | extra_trees / raw | 8.1162 | 8.1541 | 15.3632 | 10.0304 | 38.7001 |
| R02 | reference_structure28 / global | extra_trees / log1p | 8.9231 | 8.8060 | 18.3851 | 11.7797 | 62.0205 |
| A01 | composition / chemistry | extra_trees / raw | 7.8366 | 8.0930 | 15.5622 | 10.1944 | 36.4197 |
| A02 | composition / chemistry | extra_trees / raw | 7.9112 | 8.1206 | 15.6677 | 10.2447 | 37.3135 |
| A04 | composition / chemistry | extra_trees / raw | 8.0417 | 8.0651 | 15.4921 | 10.0876 | 32.4278 |
| A05 | composition / chemistry | extra_trees / raw | 7.7526 | 8.0849 | 15.5496 | 10.1957 | 36.4197 |
| C01 | composition / chemistry | extra_trees / log1p | 8.1027 | 7.7819 | 15.0134 | 9.6226 | 32.3768 |
| C02 | composition / kmeans3 | hist_gradient_boosting / log1p | 8.6636 | 7.6720 | 14.6575 | 9.5161 | 30.1392 |
| C03 | composition_repaired / chemistry | extra_trees / raw | 9.0494 | 7.7134 | 15.4455 | 9.9204 | 40.6332 |
| C04 | composition_repaired / kmeans3 | extra_trees / raw | 8.2681 | 8.0282 | 15.2229 | 10.0408 | 39.8343 |
| C05 | composition / chemistry | extra_trees / log1p | 8.0417 | 8.0651 | 15.4921 | 10.0876 | 32.4278 |


专家配置、逐折路由及回退在各 `candidates/<ID>/result.json`；原始 OOF 预测和独立复核见 [comparison_table.csv](comparison_table.csv)、[verification.json](verification.json)、[protocol_review.md](protocol_review.md)。额外 11 特征参考只删掉修复块中的方向量；28 特征参考为原常规结构块，均属于菜单外固定诊断。

## 结论的适用范围与下一步

这轮更明确的开发改善来自固定目标选择：纯成分 ExtraTrees 的原值目标（G01）相对 log1p（G02）把同一旧验证 MAE 从 8.7599 降至 8.0885 K（约 7.66%），这是传统回归目标选择，不能记作新增 Agent 收益。Agent 再增加分组选择只得到 0.045% 的整体数值变化且区间跨零，正 Tc 退步；本轮未证明分组 Agent 有稳定额外价值。

预先固定的 11 特征参考 D01 旧验证 MAE=7.9427 K，低于 Agent 的 8.0849 K。它在训练 OOF 上未胜出，因此这里只作固定诊断，不依据验证结果重新选择。

本轮检查的是具体的“模型与路由选择”干预。单次 GPT 会话加单次种子自动搜索不能证明 Agent 普遍优于自动搜索。旧验证和整个公开数据源此前都已观察，因此本轮没有全新独立验证。匹配 MP 结构、人工掺杂、记录的 Tc=0 等代理限制仍然存在；不构成新超导体、标签错误或物理机制证据。

下一步先依据这次冻结结果决定是否值得为路由策略申请真正未观察数据和多个种子复核。若增益不足或子群退步，应另立分类 / 异常识别协议，先定义可核查标签、实际使用场景和独立评估数据，再启动新 Agent 搜索；不把回归残差直接当成错误标签。

## 重现和证据

`prepare_data.py` 产生隔离输入；`pipeline.py` 实现固定 OOF、专家回退和冻结评估；`scientific_server.py` 限制训练反馈；`run_agent.py` 保存真实 GPT 会话；`run_controls_and_finalize.py` 执行预先固定的自动配置；`verify_results.py` 独立重算指标和本地模型预测。

本包含实际数值输入、折分配、修复特征、全部配置 / OOF 预测、最终预测、审计与日志。大型 joblib 模型保留在本地，模型文件哈希在最终结果中；公开包不含模型二进制。公开复核可运行 `python verify_results.py --root <此目录> --skip-models`，会明确跳过本地模型重放。不得在已有搜索目录重启 Agent 或改变冻结配置。首次从原数据计算修复还需 Hugging Face 冻结结构载荷；软件版本见 [environment_versions.json](environment_versions.json)。

数据继承上游 3DSC 的 CC BY 4.0 归属和使用条件，来源在公开数据集卡及第一轮报告中。代码和数值结论为本研究的实际执行记录。本报告不包含会议录音或转录。

[Data provenance and upstream attribution](DATA_PROVENANCE.md) · [Upstream license](UPSTREAM_LICENSE.md).

实际为 5 次尝试、4 个完成方案、1 次拟合前文件写入失败（A03）；失败仍消耗预算，未补开会话。原始状态与工具日志保留，随后仅补全失败事实记录，未改变配置或数值结果。 [Reconciliation record](agent/attempt_record_reconciliation.json).

原值目标相对 log1p 的整体收益伴随零值误差退步：G02 的记录零值 MAE 为 1.2316 K，G01 为 3.0222 K，不能称为所有子群都改善。Agent 的 Cu/O 路由贡献 −0.02754 K，被 other 路由 +0.02388 K 基本抵消。Agent 与自动臂的差值区间和对 G01 的区间相同，因为自动臂保留 G01；它们不是两份独立确认。

[Route and group decomposition](final/route_diagnostics.json) · [Final interpretation audit](final/final_interpretation_audit.md) · [Administrative audit](final/administrative_audit.json) · [Portable public verification](public_verification.json).
