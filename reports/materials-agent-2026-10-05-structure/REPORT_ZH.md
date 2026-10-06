# 材料形成能Agent：定向试验与同读入对照

**目前完成6个模型比较，共74次学习器fit：原定4项36 fit＋必需的M0同读入对照15 fit＋P5严格内折残差干预23 fit。共7个Agent会话；描述符构建cycle不算模型实验，旧E011缓存参照为0新增fit。**

**结果：** 本轮5个方向干预方案没有降低缓存E011的综合误差。本轮没有方案同时通过综合分、验证MAE和OOF MAE的联合晋级。仍保留旧E011：综合分0.227966611，验证MAE 0.215235468、OOF MAE 0.240697754 eV/atom。

Agent在第7会话依据训练证据接受并执行一次P5残差干预。

**完成方式：** 7次真实Agent会话中，6次正常保存决策；P5科学结果完整，但最后决策工具因状态枚举被拒。原失败保留，另行只把completed_no_promotion规范化为unsupported，并逐字保留Agent的反思、科学结论、停止行动和证据ID。恢复为0新fit、0新LLM会话；不是原工具自动成功。

MAE表示平均每个材料的形成能预测与真实值相差多少，单位eV/atom。综合分为715条验证MAE与2164条训练OOF MAE的平均，越低越好。

独立质量审查：原四项已完成，状态pass；M0扩展已完成，状态pass；P5接受或放弃阶段已完成，状态pass。不能把父阶段通过解释为扩展自动通过。报告器数值与证据检查：838项，失败0项。

本轮Agent亲自在隔离会话中提交compute(structure)函数，调用数值工具实际训练，读取结果后保存反思并选择下一候选。16列的物理方向、定义和四项比较框架来自此前训练OOF诊断及预定约束；这不等于Agent完全自主发明了描述符。

## 数据与代码流程

沿用2879条已观察开发数据：2164训练、715验证。训练OOF沿用E011保存的两折化学体系ID，每条训练材料由未训练其所在体系的模型预测；没有重新划分、没有读取旧1000确认集。

旧42列已经包含组成、几何和邻域汇总。G8新增每个原子中心两邻居之间的周期键角四箱均值与站点间总体方差各4列；NO8新增N中心、O中心四箱均值各4列。这里是中心键角关联，区别于旧晶胞角、配位或径向方差。

先在6Å周期邻居中保留最近12个及距离容差内全部并列邻居，再构造无序邻居对的角度余弦四箱；无有效角度或不存在对应元素时使用冻结零向量规则。安全数值接口、对称合成例、旋转/周期平移/原子重排和整开发矩阵检查通过后冻结源码与输出SHA；首次fit之后不回改特征。

P1/P2复用完整E011：全局ExtraTrees（极端随机树），含氧/不含氧两组专家各混合50% HGB（直方图梯度提升树）与50% ExtraTrees，最终全局与组内预测各50%；HGB学习率0.1、L2为0。P3/P4为全局RBF核岭回归KRR，alpha固定1；每个实际训练块单独StandardScaler、y均值居中与距离中位数带宽，没有参数网格。

## 为什么补做M0

独立数值审计发现，本批CSV默认读取与历史round_trip读取在旧42列有24426个末位差，最大绝对差2.27374e-13；目标值最大差0。这些微小差异确实改变了HGB分箱与部分样本分组，不能因差值很小就宣称模型完全相同。

因此在原四项全部结束后，另行登记并冻结M0：使用本批相同默认读取的旧42列和完整E011模型，新增15 fit。父阶段源码、四项结果与原门槛均不改，旧B0仍是原缓存E011。M0是排除数值读入因素的对照，不是新增角度特征或新增物理信息。

P1/P2的角度贡献应相对M0解释；P1→P2和P3→P4原本就是同读取方式内部比较。B0→P1/P2同时含读取方式与新增特征变化，不能单独归因于角度。

实测M0与B0预测的最大绝对差：715条验证0.0589297049，2164条OOF 0.0812081613 eV/atom。

![Agent与工具的实际循环流程](workflow.png)

## 结果

| 方案 | 验证MAE | 训练OOF MAE | 综合分 | 误差降低% | 联合晋级 | 新增fit |
|---|---:|---:|---:|---:|---|---:|
| 缓存E011：旧42列＋树路由 | 0.215235468 | 0.240697754 | 0.227966611 | 0.000 | 缓存参照 | 0 |
| M0：同读入旧42列树对照 | 0.216219324 | 0.240650270 | 0.228434797 | -0.205 | 读入对照 | 15 |
| P1：旧42列＋G8＋树路由 | 0.217982698 | 0.243774322 | 0.230878510 | -1.277 | 未通过 | 15 |
| P2：旧42列＋G8＋NO8＋树路由 | 0.217990114 | 0.243238493 | 0.230614304 | -1.161 | 未通过 | 15 |
| P3：旧42列＋KRR | 0.247600103 | 0.282607105 | 0.265103604 | -16.291 | 未通过 | 3 |
| P4：旧42列＋G8＋NO8＋KRR | 0.257333325 | 0.288144240 | 0.272738782 | -19.640 | 未通过 | 3 |
| P5：严格内折OOF残差纠偏 | 0.217465954 | 0.241035940 | 0.229250947 | -0.563 | 未通过 | 23 |

误差降低%的负数表示比缓存E011更差。低于基线的最低观察值与联合晋级分别报告，不用一项指标改善掩盖另一项恶化。

原四项联合晋级要求综合分≤0.22682677761911027、验证MAE≤0.21523546763324838、OOF MAE≤0.24069775371169688。0.5%是预定决策门槛，不是统计显著性证明。

![结构试验、同读入对照与残差纠偏结果](results.png)

## 单因素与2×2消融

同读入M0、P2、P3、P4形成旧/新结构块×E011/KRR的2×2；P1拆开全局角度和N/O条件角度的贡献。所有预测器获得相同新增信息的机会。这是完整预测方案比较，不把路由效果单独归因于某个学习器。

| 比较 | 验证MAE差 | OOF MAE差 | 综合分差 |
|---|---:|---:|---:|
| 读入方式：M0−B0 | +0.000983856 | -0.000047483 | +0.000468187 |
| 全局角度：P1−M0 | +0.001763374 | +0.003124052 | +0.002443713 |
| N/O条件角度：P2−P1 | +0.000007416 | -0.000535829 | -0.000264207 |
| 树方案的新块：P2−M0 | +0.001770790 | +0.002588222 | +0.002179506 |
| KRR的新块：P4−P3 | +0.009733221 | +0.005537135 | +0.007635178 |
| 旧42列换预测方案：P3−M0 | +0.031380779 | +0.041956835 | +0.036668807 |
| 新58列换预测方案：P4−P2 | +0.039343210 | +0.044905747 | +0.042124479 |
| 严格内折残差：P5−M0 | +0.001246630 | +0.000385670 | +0.000816150 |
| 严格内折残差：P5−B0 | +0.002230487 | +0.000338187 | +0.001284337 |

差值小于0表示误差降低；这些差值描述本数据上的响应，不证明物理因果或独立泛化。

## 训练OOF重点组诊断

| 方案 | N条数 | N MAE | N预测减真值偏差 | O条数 | O MAE | 全体p99绝对误差 |
|---|---:|---:|---:|---:|---:|---:|
| B0 | 169 | 0.366267 | -0.130404 | 837 | 0.278874 | 1.239100 |
| M0 | 169 | 0.367763 | -0.125903 | 837 | 0.279089 | 1.234562 |
| P1 | 169 | 0.381760 | -0.130727 | 837 | 0.280966 | 1.251602 |
| P2 | 169 | 0.379885 | -0.084333 | 837 | 0.280639 | 1.209913 |
| P3 | 169 | 0.367926 | -0.118280 | 837 | 0.318742 | 1.430532 |
| P4 | 169 | 0.393299 | -0.060493 | 837 | 0.327477 | 1.523568 |
| P5 | 169 | 0.365881 | +0.002360 | 837 | 0.279586 | 1.207389 |

负偏差表示预测偏低。重点组的改善不能代替整体两项MAE和联合门槛；含N每外训练折样本较少，本轮没有另建独立N专家。

## Agent每轮的实际证据与反思

通过的描述符提交为S001，compute源码SHA256为 `ece7dc8bb57faaed59c511f4ebd3f2cf0746089d5dcff99581e23fe2c6a9f123`；矩阵形状为[2879, 16]。几何验证与整矩阵检查详情在descriptor/APPROVAL.json及注册引用中，拒绝的提交也保留。

### cycle 0：描述符构建与登记（0新增模型fit）

引用真实工具证据：T0001, T0002, T0003；科学状态：pending。

Agent反思：T0001 provides training-only E011 OOF diagnosis: overall MAE 0.24069775371169688, oxygen MAE 0.2788736838333377 on 837 rows versus no-oxygen 0.21661843682261372 on 1327, and nitrogen underprediction in both folds. These patterns motivate tests but cannot identify a mechanism or establish descriptor utility. T0002 approved my exact preregistered 16-feature compute function on submission 1, with 8 semantic fixtures, 96 invariant variants over 16 base records, maximum invariance residual 1.3877787807814457e-16, and a finite 2879-by-16 development matrix; this is implementation evidence only. T0003 froze all four substantive hypotheses and joint falsification before any predictor fit. Choose P1 first because E011 is held fixed, allowing the registered new50 representation contrast to be evaluated directly before interpreting the larger representation or estimator comparisons. No candidate performance evidence yet exists, so no promotion claim is justified.

Agent科学结论：The preregistered angular descriptor is implemented, approved, and frozen; all four comparisons are registered. Its predictive utility and all candidate promotion hypotheses remain untested in this cycle. The next candidate is P1. Subsequent results are empirical adaptive-development evidence, not fresh test confirmation or physical-mechanism evidence.

下一问题：Does frozen E011/new50 pass the current joint promotion criterion relative to E011/old42, and do foldwise oxygen/no-oxygen errors indicate broadly useful empirical information rather than offsetting group regressions?

下一工具计划：In the next actual isolated session, inspect research_context and available cached baseline evidence, then evaluate_pilot exactly once for P1 using its registered hypothesis and falsification. Inspect the resulting metrics and fold/group diagnostics, reflect against all three joint thresholds and the registered secondary claims, and save a new evidence-based record_cycle_decision selecting a remaining unrun candidate. Do not fit any model in this descriptor cycle, revise the approved descriptor, tune settings, access confirmation data, or refit a failed/unknown experiment.

保存动作：continue；下一候选：P1。

### cycle 1：模型实验P1

引用真实工具证据：T0005, T0006, T0007；科学状态：unsupported。

登记假设：With the frozen E011 estimator, old42 input-only oxygen routing, fixed folds and all hyperparameters unchanged, new50 (old42 plus eight global angular histogram mean/variance features) supplies empirically useful predictive information relative to cached E011/old42. The primary hypothesis is joint promotion: selection score <=0.22682677761911027, validation MAE <=0.21523546763324838, and OOF MAE <=0.24069775371169688. Secondary diagnostic expectation is oxygen MAE improvement in both outer folds without offsetting no-oxygen regressions; inspect nitrogen MAE and signed bias in both folds given prior underprediction. These are predictions about adaptive observed-development performance, not claims of a physical mechanism or fresh confirmation.

证伪条件：Reject P1's promotion hypothesis if any current joint threshold fails. Failure of oxygen MAE to improve in both folds, or group regressions offsetting gains, undermines broad empirical usefulness even if an aggregate improves. Lack of consistent nitrogen improvement does not support a claim of resolving nitrogen underprediction. Report actual OOF, fold, N/O and validation metrics without tuning descriptor, estimator, routing or folds, without confirmation-set access and without rerunning failures. Regardless of P1 outcome, schedule all remaining preregistered P2/P3/P4 comparisons; P5/P6 are not enabled.

Agent反思：T0007 completed the single P1 evaluation with 15 learner fits. All three joint conditions failed: score 0.23087851022847566 exceeds 0.22682677761911027; validation MAE 0.2179826983825324 on 715 rows exceeds baseline/limit 0.21523546763324838; OOF MAE 0.24377432207441896 on 2164 rows exceeds baseline/limit 0.24069775371169688. Relative to T0006 baseline, validation MAE rose by 0.00274723074928402 and OOF MAE by 0.00307656836272208 eV/atom. Validation RMSE rose from 0.3296357940176692 to 0.33488650379083845, and OOF RMSE from 0.373659510864794 to 0.37550725897183834. P1 fold 0/1 overall MAEs are 0.25233686229208374/0.2352117818567542 (1082 evaluation rows each); no baseline overall fold MAEs were returned here, so these alone do not establish foldwise overall changes. Oxygen pooled MAE rose from 0.2788736838333377 to 0.2809656014883979 (837 rows). Oxygen fold 0 rose from 0.27904399219665116 to 0.2793392655813579 (434 rows), and fold 1 from 0.2786902748266925 to 0.28271704015751786 (403 rows), contradicting the consistent oxygen-improvement expectation. No-oxygen pooled MAE rose from 0.21661843682261372 to 0.22031606972362747 (1327 rows); P1 fold MAEs are 0.2342519193483415/0.20701646654716993 (648/679 rows), without returned baseline fold comparators. Nitrogen pooled MAE rose from 0.3662665887230086 to 0.38176021994670617 (169 rows), with fold 0 rising from 0.42025043557377156 to 0.4451507034333969 (81 rows) and fold 1 from 0.31657691150810174 to 0.32341216128282047 (88 rows). Nitrogen pooled mean prediction-minus-truth remained negative, -0.13040409590594138 to -0.1307266885734753; fold 0 bias became less negative (-0.15098861127288624 to -0.1442121615113179), but fold 1 became more negative (-0.11145698517045802 to -0.11831392371023383). Thus one bias movement is not a consistent accuracy gain. These empirical results do not support P1 promotion or broad N/O improvement and identify no physical mechanism. Select unrun P2 next because its eight additional N/O-centered features directly test whether that frozen representation contributes useful information beyond P1's global angular summaries while E011 remains fixed. P1's result cannot prejudge P2, P3 or P4; all must still run.

Agent科学结论：P1 (frozen E011/new50) is unsupported for promotion: score, validation MAE and OOF MAE all worsen relative to cached E011/old42, with oxygen and nitrogen MAE regressions in both folds and pooled no-oxygen regression. This is adaptive observed-development evidence, not fresh independent test confirmation, a significance claim, or physical-mechanism evidence. P2 is next; P3 and P4 remain mandatory and their hypotheses pending. After all four comparisons stop. If later separately authorized, a preregistered training-only shared nitrogen correction or genuinely independent confirmation could address remaining questions; neither was executed, and optional P5/P6 are not enabled.

下一问题：Does frozen E011/new58 pass the joint promotion criterion relative to cached E011/old42, and does adding the eight N/O-centered angular features improve on P1/new50 in overall, foldwise oxygen and nitrogen errors without offsetting no-oxygen regressions?

下一工具计划：In the next actual isolated experiment session inspect research_context/compare_results as needed, formulate the frozen registered P2 hypothesis and falsification, and call evaluate_pilot(candidate_id='P2') exactly once. Compare actual score, validation and OOF metrics against all three current joint thresholds; compare P2 with cached E011 and completed P1, including foldwise N/O MAE and nitrogen signed bias. Save an evidence-based record_cycle_decision selecting an unrun P3 or P4. All four required comparisons must run regardless of negative results; after the fourth stop. Keep descriptor, hyperparameters, preprocessing boundaries, routes and folds frozen; no confirmation-set access, failed/unknown refits, or P5/P6 execution.

保存动作：continue；下一候选：P2。

### cycle 2：模型实验P2

引用真实工具证据：T0010, T0011, T0012；科学状态：unsupported。

登记假设：With the approved descriptor, E011 estimator, input-only oxygen routes, hyperparameters and chemical-system folds frozen, P2/new58 tests whether the eight N/O-centered angular summaries add useful empirical predictive information beyond P1/new50 and cached E011/old42. Predict lower overall OOF and validation MAE, consistent oxygen MAE reductions in both folds, and improved nitrogen MAE/signed underprediction without offsetting no-oxygen regressions. This is an empirical adaptive-development hypothesis, not a physical mechanism claim.

证伪条件：The promotion hypothesis fails unless all current joint conditions pass: selection_score <= 0.22682677761911027, validation MAE <= 0.21523546763324838, and OOF MAE <= 0.24069775371169688. The secondary broad-information hypothesis is not supported if overall OOF does not improve, oxygen MAE does not decrease consistently across both folds, or other large-group regressions offset gains; compare N/O fold errors and nitrogen signed bias with E011 and P1, and distinguish any partial improvement from promotion. No tuning, descriptor changes, rerouting, fold changes, confirmation-set access or independent-confirmation claim.

Agent反思：T0012 completed the single P2 evaluation with 15 learner fits. All three joint promotion conditions failed: selection score 0.230614303606053 > 0.22682677761911027; validation MAE 0.217990114310013 on 715 rows > 0.21523546763324838; OOF MAE 0.24323849290209304 on 2164 rows > 0.24069775371169688. T0010 cached E011 score is 0.22796661067247265. P2 validation RMSE 0.33636173621892484 worsened from E011 0.3296357940176692 and P1 0.33488650379083845; OOF RMSE 0.3734853355342942 was slightly lower than E011 0.373659510864794 and P1 0.37550725897183834, a partial secondary gain insufficient for promotion. Relative to P1, OOF MAE improved from 0.24377432207441896 but validation MAE was slightly worse than 0.2179826983825324. P2 overall fold 0/1 MAEs 0.25155729258647186/0.23491969321771422 (1082 rows each) improved on P1 0.25233686229208374/0.2352117818567542; cached E011 overall fold MAEs were not returned, so no overall fold comparison to baseline is asserted. Oxygen pooled MAE 0.2806393763857908 (837 rows) is below P1 0.2809656014883979 but above baseline 0.2788736838333377. Oxygen fold MAEs 0.2813446665788906/0.2798798331009141 (434/403 rows) both exceed baseline 0.27904399219665116/0.2786902748266925; relative to P1 0.2793392655813579/0.28271704015751786, fold 0 worsened and fold 1 improved. No-oxygen pooled MAE 0.21964803361358134 (1327 rows) improved on P1 0.22031606972362747 but remained above baseline 0.21661843682261372. No-oxygen fold MAEs 0.2316071069187099/0.20823495629145572 (648/679 rows) improved/worsened respectively versus P1 0.2342519193483415/0.20701646654716993; no baseline fold no-oxygen comparator was returned. Nitrogen pooled MAE 0.37988522434762134 (169 rows) improved on P1 0.38176021994670617 but remained above baseline 0.3662665887230086. Nitrogen fold MAEs 0.4359786715008924/0.3282537559451785 (81/88 rows) both exceeded baseline 0.42025043557377156/0.31657691150810174; versus P1 0.4451507034333969/0.32341216128282047, fold 0 improved but fold 1 worsened. Nitrogen mean prediction-minus-truth became less negative: pooled -0.08433274103970209 versus baseline -0.13040409590594138 and P1 -0.1307266885734753; fold 0/1 -0.07138446892764329/-0.09625103696102898 versus baseline -0.15098861127288624/-0.11145698517045802 and P1 -0.1442121615113179/-0.11831392371023383. Thus reduced nitrogen signed bias does not imply improved absolute accuracy against baseline. N and O groups overlap and their error shares must not be added. P2 shows partial empirical improvements over P1, but neither tree augmentation supports promotion or consistent N/O accuracy improvement over baseline. Select unrun P3 next: with both frozen tree augmentations failing, the preregistered estimator-only KRR/old42 comparison directly tests the remaining alternative and provides a clean same-estimator comparator for P4/new58. This is a scheduling rationale, not evidence that KRR will win. P3 and P4 remain mandatory.

Agent科学结论：P2/E011/new58 is unsupported for promotion: score, validation MAE and OOF MAE all fail the current joint criterion. Small OOF improvements over P1 and reduced nitrogen underprediction coexist with worse N/O MAE than E011 in both folds; they do not establish broad descriptor utility. These are previously observed adaptive-development comparisons, not fresh test confirmation, statistical significance, or physical mechanisms. P3 is next and P4 must follow irrespective of outcome; stop after all four comparisons. Useful future work, only under a separate authorization and preregistration, could test a constrained shared nitrogen correction trained on inner-fold residuals and seek genuinely independent confirmation. Neither was executed; optional P5/P6 are disabled.

下一问题：Does frozen KRR/old42 (P3) improve empirical prediction relative to cached E011/old42 under the joint promotion criterion and foldwise N/O diagnostics, providing the estimator-only comparator for mandatory P4/KRR/new58?

下一工具计划：In the next actual isolated experiment session inspect research_context/compare_results as needed, formulate the frozen P3 hypothesis and falsification, then evaluate_pilot(candidate_id='P3') exactly once. Assess the actual joint score, validation and OOF criteria and foldwise N/O errors and nitrogen signed bias relative to cached E011 and completed tree candidates. Save record_cycle_decision selecting remaining P4; P4 must run regardless of P3 outcome, and after the fourth comparison stop. Keep descriptor, hyperparameters, training-only preprocessing, routes and folds frozen. No confirmation-set access, failed/unknown refits, or optional P5/P6 execution.

保存动作：continue；下一候选：P3。

### cycle 3：模型实验P3

引用真实工具证据：T0015, T0016, T0017；科学状态：unsupported。

登记假设：Frozen P3 KRR/old42 tests the estimator-only empirical alternative to cached E011/old42 after P1 and P2 tree augmentations failed joint promotion. Predict that the frozen RBF KRR (alpha=1, training-block-only StandardScaler and target centering, registered median-distance gamma, unchanged folds and routes) will jointly attain score<=0.22682677761911027, validation MAE<=0.21523546763324838 and OOF MAE<=0.24069775371169688. Secondary expectation is lower pooled and both-fold O/N MAE relative to E011 without offsetting no-oxygen deterioration, and reduced absolute nitrogen signed bias. These are empirical predictions on previously observed adaptive development, not physical mechanisms or independent confirmation. P3 also establishes the same-estimator comparator for mandatory P4.

证伪条件：Promotion hypothesis is unsupported if any of the three joint thresholds fails; 0.5 percent is a scheduling threshold, not significance. Consistent N/O improvement is contradicted if either fold fails to improve the relevant group's MAE versus E011, or no-oxygen deterioration offsets gains. Bias reduction alone cannot establish MAE improvement. Reflect actual OOF, validation, RMSE, fold and N/O results, including mixed outcomes, without tuning descriptors, hyperparameters, preprocessing boundaries, routes or folds. P4 must still run next regardless of P3 outcome; no confirmation-set access or P5/P6.

Agent反思：T0017 completed the single P3 evaluation, frozen KRR/old42, with 3 learner fits. All three joint promotion conditions failed: score 0.26510360424205 > 0.22682677761911027; validation MAE 0.24760010324872053 on 715 rows > 0.21523546763324838; OOF MAE 0.28260710523537946 on 2164 rows > 0.24069775371169688. T0015 baseline score is 0.22796661067247265. Validation RMSE increased from baseline 0.3296357940176692 to 0.3663675386238301, and OOF RMSE from 0.373659510864794 to 0.42611959384795034. Overall validation/OOF MAE and RMSE are also worse than both P1 and P2. P3 fold 0/1 MAEs are 0.2941770463938534/0.2710371640769057 (1082 evaluation rows each), worse than P1 0.25233686229208374/0.2352117818567542 and P2 0.25155729258647186/0.23491969321771422. P3 fold RMSEs are 0.4629086401556939/0.3858385768575903. Baseline overall fold MAEs were not returned; no direct overall fold comparison with baseline is asserted. Oxygen pooled MAE increased from baseline 0.2788736838333377 to 0.3187417271747018 (837 rows); fold 0 increased from 0.27904399219665116 to 0.31582792432325424 (434 rows), and fold 1 from 0.2786902748266925 to 0.3218796687070299 (403 rows). These also exceed P1 and P2 oxygen MAEs in both folds. No-oxygen pooled MAE increased from baseline 0.21661843682261372 to 0.2598153354062817 (1327 rows); fold MAEs 0.27967630407693983/0.24086112671911467 (648/679 rows) exceed both P1 and P2. No baseline no-oxygen fold comparator was returned. Nitrogen pooled MAE 0.36792602362311233 (169 rows) is slightly worse than baseline 0.3662665887230086, though lower than P1 0.38176021994670617 and P2 0.37988522434762134. Nitrogen fold 0 improves versus baseline, 0.42025043557377156 to 0.41498092412952453 (81 rows), while fold 1 worsens, 0.31657691150810174 to 0.32461412656607397 (88 rows). P3 N fold 0 improves over both tree augmentations; fold 1 improves over P2 0.3282537559451785 but worsens versus P1 0.32341216128282047. Nitrogen pooled mean prediction-minus-truth is less negative than baseline (-0.13040409590594138 to -0.11828000692242986), but fold 0 becomes more negative (-0.15098861127288624 to -0.16775769576514118) while fold 1 becomes less negative (-0.11145698517045802 to -0.07273804332857056). Thus nitrogen gains are mixed, do not consistently reduce bias or absolute error against baseline, and cannot rescue the failed joint criterion. N and O overlap; their error shares are not additive. This falsifies promotion and consistent N/O improvement for the specific frozen P3, not all possible KRR settings or a physical mechanism. Select P4, the sole remaining mandatory candidate: P1/P2 tree augmentations and P3 estimator-only change failed, but the frozen combined KRR/new58 comparison remains unresolved. P3 now supplies its same-estimator old42 comparator, and P2 its same-feature new58 comparator. P4 must run despite the negative results; no tuning is justified by these observed-development outcomes.

Agent科学结论：P3/KRR/old42 is unsupported for promotion: all three joint conditions fail, overall MAE/RMSE regress versus E011 and both tree candidates, oxygen MAE worsens in both folds, and nitrogen improvements are inconsistent across folds relative to E011. This is previously observed adaptive-development evidence, not fresh independent test confirmation, statistical significance, or a physical mechanism. P4/KRR/new58 remains pending and is the final required comparison; stop after it. Future separately authorized, preregistered work could examine a constrained shared nitrogen correction trained on inner-fold residuals and obtain genuinely independent confirmation. Neither is executed here; P5/P6 are disabled.

下一问题：Does frozen KRR/new58 (P4) pass the joint promotion criterion against cached E011/old42, and does adding the frozen angular block improve empirical overall and foldwise N/O accuracy over P3/KRR/old42? Compare P4 with P2/E011/new58 to complete the registered estimator/representation comparisons.

下一工具计划：In the next actual isolated experiment session inspect research_context/compare_results as needed, formulate P4 hypothesis and falsification, and evaluate_pilot(candidate_id='P4') exactly once. Compare real selection score, validation and OOF MAE/RMSE with all three frozen joint thresholds, E011 and P3; inspect both folds, pooled O/no-O/N diagnostics and nitrogen signed bias, and compare P2 at fixed new58. Save final record_cycle_decision and stop after this fourth required comparison regardless of outcome. Keep descriptors, hyperparameters, training-only preprocessing, routes and folds frozen. No confirmation-set access, failed/unknown refits or optional P5/P6 execution.

保存动作：continue；下一候选：P4。

### cycle 4：模型实验P4

引用真实工具证据：T0021, T0022, T0023；科学状态：unsupported。

登记假设：Test frozen P4 KRR/new58 exactly once as the final mandatory comparison. The empirical hypothesis is that adding the approved 16 angular features to old42 improves validation and OOF accuracy relative to P3 KRR/old42, with lower O and N MAE in both fixed outer folds, and yields promotion against cached E011/old42: score <= 0.22682677761911027, validation MAE <= 0.21523546763324838, OOF MAE <= 0.24069775371169688 jointly. P2 E011/new58 supplies the fixed-feature estimator comparator. Prior P1/P2/P3 promotion failures lower expectations but do not resolve the combined P4 comparison. These are empirical predictive hypotheses on previously observed adaptive development, not physical mechanisms or fresh confirmation. Keep descriptor, hyperparameters, routes, folds and training-only preprocessing frozen.

证伪条件：Any failed joint threshold falsifies P4 promotion under the current rule; secondary gains cannot override that failure. Failure to reduce both validation and OOF MAE versus P3 rejects the proposed overall benefit of angular augmentation for this frozen KRR. Failure to lower O and N MAE in each outer fold rejects consistent subgroup benefit; inspect pooled O/no-O/N errors, fold MAE/RMSE and nitrogen mean prediction-minus-truth so reduced signed bias is not mistaken for improved absolute accuracy. Compare P2 at fixed new58 and cached E011, without asserting unavailable baseline fold metrics. N/O groups overlap. No significance or independent-test claim, tuning, confirmation-set access, refits, or optional P5/P6. Save final decision and stop after P4 regardless of outcome.

Agent反思：T0023 completed the sole P4 evaluation (frozen KRR/new58), with 3 learner fits. All three joint promotion conditions failed: selection score 0.27273878231572585 > 0.22682677761911027; validation MAE 0.2573333245662145 on 715 rows > 0.21523546763324838; OOF MAE 0.2881442400652372 on 2164 rows > 0.24069775371169688. T0022 cached E011 score is 0.22796661067247265. Validation RMSE 0.3821941805867099 and OOF RMSE 0.43619299249357757 exceed E011 0.3296357940176692/0.373659510864794 and P3 0.3663675386238301/0.42611959384795034. At fixed KRR, adding the frozen angular block worsens validation MAE from P3 0.24760010324872053 and OOF MAE from 0.28260710523537946. At fixed new58, P4 also worsens validation/OOF MAE and RMSE versus P2 (MAE 0.217990114310013/0.24323849290209304; RMSE 0.33636173621892484/0.3734853355342942). All four overall metrics are worse than P1 as well. P4 overall fold 0/1 MAEs 0.29992672112209057/0.2763617590083838 (1082 evaluation rows each) exceed P3 0.2941770463938534/0.2710371640769057 and P2 0.25155729258647186/0.23491969321771422; fold RMSEs 0.4774101030573629/0.3906510551627406 exceed P3 0.4629086401556939/0.3858385768575903. Baseline overall fold metrics were not returned, so no direct comparison is asserted. Oxygen pooled MAE 0.327477255358784 (837 rows) exceeds E011 0.2788736838333377, P3 0.3187417271747018 and P2 0.2806393763857908. Oxygen fold MAEs 0.3262474293223739/0.3288016833979949 (434/403 rows) exceed E011 0.27904399219665116/0.2786902748266925, P3 0.31582792432325424/0.3218796687070299 and P2 0.2813446665788906/0.2798798331009141. No-oxygen pooled MAE 0.26333509628174157 (1327 rows) exceeds E011 0.21661843682261372, P3 0.2598153354062817 and P2 0.21964803361358134. No-oxygen fold MAEs 0.28229834556819705/0.24523762126315074 (648/679 rows) exceed P3 0.27967630407693983/0.24086112671911467 and P2 0.2316071069187099/0.20823495629145572; no baseline no-oxygen fold comparison was returned. Nitrogen pooled MAE 0.393298765925442 (169 rows) exceeds E011 0.3662665887230086, P3 0.36792602362311233, P2 0.37988522434762134 and P1 0.38176021994670617. Nitrogen fold MAEs 0.43944937740133716/0.35081922581694774 (81/88 rows) both exceed E011 0.42025043557377156/0.31657691150810174, P3 0.41498092412952453/0.32461412656607397 and P2 0.4359786715008924/0.3282537559451785. Relative to P1, nitrogen fold 0 improves from 0.4451507034333969 but fold 1 worsens from 0.32341216128282047. Nitrogen pooled mean prediction-minus-truth is less negative at -0.06049291814609601 versus E011 -0.13040409590594138, P3 -0.11828000692242986 and P2 -0.08433274103970209. Fold 0/1 nitrogen bias is -0.04335352381493743/-0.07626895156454881: both closer to zero than E011 -0.15098861127288624/-0.11145698517045802 and P2 -0.07138446892764329/-0.09625103696102898, but versus P3 -0.16775769576514118/-0.07273804332857056 only fold 0 improves. Reduced signed bias therefore does not establish better absolute accuracy. Pooled nitrogen p90 absolute error falls versus P3 (0.9547095711301361 to 0.8372534201645022) while its RMSE rises (0.5235033322134471 to 0.5361743110610103) and p99 rises (1.6387674660794587 to 1.6457470708332558); this partial secondary gain does not rescue promotion. N and O groups overlap, so their error shares are not additive. The hypotheses of promotion, overall angular benefit for frozen KRR, and consistent foldwise N/O improvement versus P3 are rejected by these observed-development results. All P1-P4 now completed: scores P1 0.23087851022847566, P2 0.230614303606053, P3 0.26510360424205, P4 0.27273878231572585; none passes the joint rule. P2 has the lowest pilot score but remains worse than cached E011 and is not promoted. No unrun required candidate remains; stop now.

Agent科学结论：P4/KRR/new58 is unsupported for promotion: all three joint thresholds fail, validation and OOF MAE/RMSE worsen versus P3 and E011, and N/O MAE worsens in both folds versus P3, P2 and E011. Less negative pooled nitrogen signed bias coexists with worse nitrogen MAE/RMSE. Across all four preregistered comparisons, none qualifies for promotion; retain cached E011 as the reference, with no claim of universal model superiority. These are previously observed adaptive-development comparisons, not fresh independent test confirmation, significance evidence, or physical mechanisms. Descriptor validity and geometric invariance do not establish predictive utility. Stop after the fourth comparison; no next candidate is enabled. Useful future work, not executed here, could separately preregister a constrained shared nitrogen correction trained only on inner-fold residuals, requiring foldwise N accuracy gains without overall regression, and seek genuinely independent confirmation in a separately authorized study. Optional P5/P6 remain disabled.

下一问题：None within this completed registered pilot. All four required candidates P1-P4 have run; optional P5/P6 are disabled.

下一工具计划：Stop after saving this final decision. No further experiments, tuning, descriptor changes, refits or confirmation-set access. Future work described in the conclusion is unexecuted and requires a separate authorized preregistered study.

保存动作：stop；下一候选：无，结束本轮。

### cycle 5：另登记的M0匹配读入对照

登记假设：M0 with the exact same default-reader old42 inputs and immutable E011 models provides the valid comparator for P1/P2 feature effects. No assumption the reader difference improves or worsens performance.

证伪条件：B0 and M0 predictions equal within1e-12 would show no realized prediction effect for this configuration; otherwise report the effect. Compare P1/P2 against M0 and retain B0 original metrics; never assign reader effects to angles.

Agent反思：C0002 completed the sole M0 evaluation: 15 learner fits; validation 715 rows, OOF 2164. M0 validation/OOF MAE = 0.2162193240197367/0.24065027042997694, RMSE = 0.330625907580303/0.3737226193346646, score = 0.22843479722485682. Preserve original B0 (C0001): MAE = 0.21523546763324838/0.24069775371169688, RMSE = 0.3296357940176692/0.373659510864794, score = 0.22796661067247265. M0 minus B0 MAE = +0.0009838563864883/-0.00004748328171994; RMSE = +0.0009901135626338/+0.00006310846987062. These MAE differences rule out all predictions agreeing within 1e-12 under the fixed evaluation, although the receipt supplies no direct prediction-difference statistic. Reader effects have mixed direction and are not angular effects. Against matched-reader M0, P1 validation/OOF MAE worsens by +0.0017633743627957/+0.0031240516444420 and P2 by +0.0017707902902763/+0.0025882224721161. P1 RMSE worsens on both partitions; P2 validation RMSE worsens by 0.0057358286386218 but OOF RMSE improves by 0.0002372838003704. Both scores worsen versus M0. P1/P2 pooled and both-fold nitrogen/oxygen MAEs exceed M0. Retain all original P1-P4 metrics, diagnostics and negative promotion decisions: scores 0.23087851022847566, 0.230614303606053, 0.26510360424205, 0.27273878231572585; all fail the original joint rule. M0 corrects attribution, without replacing historical B0 or retroactively changing thresholds.

Agent科学结论：C0001 and C0002 support a realized parser effect and the need for M0 as the matched-reader old42 E011 comparator; P1/P2 do not improve validation and OOF MAE over M0. Same-reader P1→P2 (new50→new58, fixed E011) slightly worsens validation MAE by 0.0000074159274806 and RMSE by 0.0014752324280864, while improving OOF MAE by 0.0005358291723259, RMSE by 0.0020219234375441 and score by 0.0002642066224227. This incremental feature contrast is mixed, not a parser effect or consistent angular benefit; nitrogen and oxygen foldwise MAE changes are mixed despite pooled MAE gains. Same-reader P3→P4 (old42→new58, fixed KRR) worsens validation MAE 0.24760010324872053→0.2573333245662145 and OOF MAE 0.28260710523537946→0.2881442400652372; validation/OOF RMSE rise 0.3663675386238301→0.3821941805867099 and 0.42611959384795034→0.43619299249357757. Overall and nitrogen/oxygen MAEs worsen in both folds. Less negative pooled nitrogen bias and lower p90 error do not rescue worse MAE/RMSE. This tests the full added feature block under frozen KRR, not the isolated incremental P1→P2 block. All four original promotion failures remain; no candidate is promoted. These are observed-development comparisons, not independent confirmation, significance evidence, universal model rankings or physical mechanisms.

下一科学行动：Stop after saving this decision. No residual study, other followups, additional evaluations, tuning, refits, descriptor changes or confirmation-data access. Preserve historical B0 and all original negative results together with the separately preregistered M0 control.

引用实际M0工具证据：C0001, C0002；保存stop。

### cycle 6：独立冻结的P5接受或放弃决策

Agent在第7会话依据训练证据接受并执行一次P5残差干预。

此前阶段的stop在其已完成范围内有效；本阶段独立冻结后由真实Agent决定接受或放弃，不改此前停止决策、代码和结果。固定纠偏方法与严格预算事先登记，不声称Agent完全自主发明算法。

原C0004决策保存失败：Agent提交scientific_status=completed_no_promotion，冻结后端只接受supported/unsupported/mixed/pending，包装器把失败标记为不可重试，因此原controller_failure与transport completed=false保留。此处展示recovery/canonical_decision.json；它仅规范化状态枚举，不是Agent重新运行或原MCP工具保存成功。

恢复receipt SHA256：`bc3ed802fc4d9a6ddd10d4fea9d2d6afe67652a3fc7f6252514007754b2b60fb`。原始CLI参数、失败账本、研究状态、全部预测与源码SHA均绑定并保留，0模型训练、0新Agent会话。

Agent登记假设：The fixed alpha10 Ridge correction using hasN/hasO and an intercept may reduce formation-energy MAE sufficiently to pass the frozen joint promotion rule. OuterOOF corrections must learn exclusively from fresh nested cross-fitted residuals within each outertraining context; only the disjoint validation correction may use verified fulltrain M0 OOF residuals.

证伪条件：Evaluate exactly once. Reject scheduling promotion unless score <0.22682677761911027, validation MAE <0.21523546763324838, and OOF MAE <0.24065027042997694, thereby beating historical B0 and matched-reader M0 jointly. Examine returned fold/group MAE and signed bias: reduced bias without absolute-error improvement does not establish benefit. No samefold observed-error calibration, tuning, clipping, descriptor changes, confirmation access or followup fits. Stop after the single trial regardless of outcome. Results concern observed development only, with no mechanism, significance or independent-confirmation claim.

接受试验的训练证据理由：Current C0001 training evidence justifies one trial, mainly through nitrogen: prediction-minus-truth means are -0.149599 and -0.104093 eV/atom in folds 0/1, versus MAEs 0.420668 and 0.319067 (81/88 rows). Signed bias is consistently negative and about 36%/33% of MAE, unlike merely elevated absolute error. Historical nitrogen medians are also negative in both folds, but are not independent evidence. Oxygen has MAE near 0.279 in both folds yet means -0.013380/+0.006248, weak and sign-inconsistent; oxygen error alone does not justify correction. Groups overlap, and mean-residual fitting need not improve MAE. The nitrogen signal supports testing the already frozen joint N/O method without changing its descriptors, base, parser, folds, preprocessing or cache.

Agent反思：C0003 completed the single preregistered P5 trial with 23 learner fits. Validation/OOF MAE = 0.217465954441/0.241035940251 eV/atom; score = 0.229250947346. Relative to M0, MAEs worsen by 0.001246630421/0.000385669821; relative to B0, by 0.002230486807/0.000338186539. All three frozen promotion thresholds fail. Validation/OOF RMSE = 0.328983786528/0.372541526084, improving over both comparators, but not rescuing MAE failure. Against M0, fold0 MAE improves 0.247634070796 to 0.246495715988; fold1 worsens 0.233666470064 to 0.235576164514. Pooled nitrogen bias changes -0.125903342530 to +0.002359849887 and MAE improves slightly 0.367763395630 to 0.365880695815. Oxygen MAE worsens 0.279088757965 to 0.279585633542 and bias changes -0.003929829967 to +0.008596689122. Global bias approaches zero, yet global MAE worsens. Returned fold summaries contain no corrected subgroup diagnostics; no foldwise subgroup benefit is inferred.

Agent科学结论：The training-only nitrogen signed bias justified the fixed honest-nested test, but the observed trial fails joint scheduling promotion against historical B0 and reader-matched M0. Bias reduction and RMSE improvement do not establish MAE improvement; pooled nitrogen gains are small and overall fold effects are mixed. Do not promote P5. This is an observed-development negative promotion result, not evidence of mechanism, significance, independent confirmation or universal failure of residual correction. Preserve all previous completed-scope stop decisions and original negative results.

下一科学行动（尚未执行）：Stop this separately frozen optional stage now. No further evaluations, refits, tuning, descriptor changes, calibration or confirmation-data access. Further plans remain unexecuted.

保存动作stop；科学状态unsupported；实际工具证据：C0001, C0002, C0003。

P5预定联合门槛同时要求超过历史B0和同读入M0：综合分≤0.22682677761911027、验证MAE≤0.21523546763324838、OOF MAE≤0.24065027042997694。

P5沿用默认CSV读取和旧42列完整E011基模型。每个外层OOF训练块内部重新按化学体系生成两折inner OOF，Ridge(alpha=10，带截距)只用是否含N/是否含O学习训练残差，随后校正该外层未参与训练的材料。验证715条的纠偏训练仅使用全训练2164条的已核验M0 OOF；这些残差不会用来训练外层OOF纠偏器。没有从全体外OOF偏差直接加常数、没有同折误差训练与评价。

实际新增20次inner基模型fit＋3次Ridge fit。M0已有15次独有基模型训练被核验复用；其中全训练验证支路的10次inner fit与这15次重叠，均为0新增，不能相加成25次。外层已保存预测也为0新增fit。

这是依据训练N/O偏差提出的预测残差校准实验，未增加新的结构描述符，也不能据此宣称发现物理机制。

P5的N组平均有符号偏差接近零，部分RMSE下降，但整体两项MAE均恶化；不能把偏差或RMSE改善改称本任务的MAE晋级。每折总体收益有分歧，不据汇总N偏差推断各折N子组均改善。

## 成本、停止与结论边界

实际6个模型比较，预留74、started 74、completed 74次学习器fit；沿用原fit上限96。原四项36 fit与M0 15 fit分开登记，P5新增23 fit。描述符提交1次，描述符cycle不计模型实验。

原阶段控制器墙钟658.6秒；从原启动到扩展终态的墙钟2262.0秒（含审查等待）。合计未缓存输入Token 201694/300000，输出Token 16297/20000，实际工具调用31/80。Token额度是资源计数，不是货币账单。

原父controller_outcome的tool_calls记录为0，属于陈旧元数据；原件保留。本报告按父server_state实际24加M0 server_state实际3加P5阶段server_state实际4合计，未把0解释为没有调用工具。

P5接受或放弃阶段已按真实记录披露；P6种子复验未启用，没有为凑轮次追加拟合。

本轮有一次真实决策schema失败及独立元数据恢复；没有追加科学训练或LLM会话。后续工程改进应让工具schema明确枚举值，并允许只纠正元数据格式的重试，同时禁止重跑科学拟合；本轮冻结源码不回改。

本次是已观察开发数据上的形成能实验，没有新的独立确认、没有Ehull稳定性专门评价；未用本轮固定比较证明Agent选实验策略优于随机搜索，也没有证明预测误差来自某种物理机制。给定既有计算结构的预测收益不能直接解释为省去DFT或发现新稳定材料。

审计源：原protocol/registration/outcome、extensions/parser_control的独立登记/adapter provenance/结果、各阶段cycle证据与质量审查、extensions/nested_residual的protocol/接受或放弃决策/缓存与结果证据。父质量SHA256：f27ac8d34aaa5e944882c917910d89c4eadb52003e8133c2c027728db304d981；M0质量SHA256：33f225b69bc64288a41463157b107cb100f3c423e35bdde8c05c4538198a13fb；P5阶段质量SHA256：0b591ef4730f5c0923fea814c08da1a593cb44695f7d4a4c5e693decc096d9cd
