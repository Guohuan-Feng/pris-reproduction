"""Package public research evidence and render reports from frozen results."""
from pathlib import Path
import json
import shutil
import hashlib
import importlib.metadata as metadata
import pandas as pd

ROOT=Path(__file__).resolve().parent
OUT=Path('C:/Users/28908/Documents/Codex/2026-10-02/chao-dao-hui-yi/outputs/superconductivity_agent_v2_2026-10-02')
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def fmt(x):return '—' if x is None else f'{x:.4f}'
def write(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8')
def save(p,o):write(p,json.dumps(o,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def main():
    result=load(ROOT/'final/results.json');selection=result['selection']
    invocation_path=ROOT/'agent/invocation.json'
    if (ROOT/'agent/recovered/invocation.json').exists():invocation_path=ROOT/'agent/recovered/invocation.json'
    inv=load(invocation_path);state=load(ROOT/'agent/state.json');repair=load(ROOT/'repair/audit.json')
    if not inv['completed']:raise RuntimeError('No completed scientific run')
    if not (ROOT/'final/verification.json').exists() or not load(ROOT/'final/verification.json')['passed']:raise RuntimeError('Independent verification required before report')
    OUT.mkdir(parents=True,exist_ok=True)
    files=list(ROOT.glob('*.py'))+[ROOT/'PROTOCOL.md',ROOT/'protocol_review.md',ROOT/'benchmark_results.json',ROOT/'selection.json']
    files+=list((ROOT/'data').glob('*'))+list((ROOT/'controls').glob('*.json'))
    files+=list((ROOT/'repair').glob('*.py'))+[ROOT/'repair/audit.json',ROOT/'repair/features12.csv.gz',ROOT/'repair/features11.csv.gz']
    files+=list((ROOT/'figures').glob('*'))
    files+=[p for p in (ROOT/'candidates').rglob('*') if p.is_file()]
    files+=[p for p in (ROOT/'agent').rglob('*') if p.is_file() and p.name not in ('stderr.log',)]
    files+=[p for p in (ROOT/'final').glob('*') if p.is_file()]
    for p in files:
        dest=OUT/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    shutil.copy2(ROOT/'final/verification.json',OUT/'verification.json')
    versions={name:metadata.version(name) for name in ['numpy','pandas','scikit-learn','joblib','matplotlib','pymatgen']}
    save(OUT/'environment_versions.json',versions)
    metrics=result['metrics'];anchor=selection['best_shared_global'];agent=selection['agent']['selected'];control=selection['automated_control']['selected'];strong=selection['best_all_global_reference']
    comparison=result['paired_group_bootstrap']
    ids=selection['shared_global_ids']+selection['outside_menu_reference_ids']+selection['agent_ids']+selection['control_ids']
    rows=[]
    for cid in ids:
        cv=load(ROOT/f'candidates/{cid}/result.json');spec=cv['specification'];m=metrics[cid]
        rows.append({'id':cid,'input':spec['input'],'routing':spec['routing'],'global_model':spec['global']['model'],'target':spec['global']['target'],'OOF_MAE_K':cv['metrics']['MAE_K'],'OOF_positive_MAE_K':cv['metrics']['subgroups']['positive_tc']['MAE_K'],'OOF_fits':cv['actual_model_fits'],'OOF_seconds':cv['elapsed_seconds'],'validation_MAE_K':m['MAE_K'],'validation_RMSE_K':m['RMSE_K'],'validation_zero_MAE_K':m['subgroups']['reported_zero']['MAE_K'],'validation_positive_MAE_K':m['subgroups']['positive_tc']['MAE_K'],'validation_high_MAE_K':m['subgroups']['high_tc_ge40K']['MAE_K']})
    pd.DataFrame(rows).to_csv(OUT/'comparison_table.csv',index=False)
    def table(cids):
        text='| 方案 | 输入 / 路由 | 全局模型 / 目标 | OOF MAE (K) | 旧验证 MAE (K) | RMSE (K) | 正 Tc MAE (K) | ≥40 K MAE (K) |\n| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |\n'
        for r in rows:
            if r['id'] in cids:text+=f"| {r['id']} | {r['input']} / {r['routing']} | {r['global_model']} / {r['target']} | {fmt(r['OOF_MAE_K'])} | {fmt(r['validation_MAE_K'])} | {fmt(r['validation_RMSE_K'])} | {fmt(r['validation_positive_MAE_K'])} | {fmt(r['validation_high_MAE_K'])} |\n"
        return text
    delta=comparison['agent_minus_shared_global'];ci=delta['conditional_95_percent_interval_K'];dcontrol=comparison['agent_minus_automated_control'];dc=dcontrol['conditional_95_percent_interval_K']
    pct=(metrics[anchor]['MAE_K']-metrics[agent]['MAE_K'])/metrics[anchor]['MAE_K']*100
    no_gain=selection['agent']['global_fallback_selected']
    headline=('Agent 最终保留共享全局基线，本轮没有展示额外收益。' if no_gain else f"Agent 在训练 OOF 上选择 {agent}；旧验证 MAE 相对共享全局模型变化 {pct:.2f}%（正值为降低）。")
    actions=[]
    for x in state['strategies']:
        md=load(ROOT/f"agent/{x['id']}_scientific_metadata.json")
        actions.append(f"- **{x['id']} {md['name']}**：{md['hypothesis']}\n  检验条件：{md['falsification']}；修订来源：{md['revision_of']}；状态：{x['status']}。")
    calls=[loadline for line in (ROOT/'agent/tool_events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip() for loadline in [json.loads(line)]]
    types={name:sum(x['tool']==name for x in calls) for name in ['describe_data','run_strategy','counterexamples','compare_strategies','record_conclusion']}
    counts=metrics[anchor]['subgroups']
    audit=repair['summary']
    cv_agent=load(ROOT/f'candidates/{agent}/result.json')['metrics'];cv_anchor=load(ROOT/f'candidates/{anchor}/result.json')['metrics']
    afits=sum(load(ROOT/f"candidates/{x}/result.json")['actual_model_fits'] for x in selection['agent_ids'])
    cfits=sum(load(ROOT/f"candidates/{x}/result.json")['actual_model_fits'] for x in selection['control_ids'])
    usage=inv.get('usage_events',[])
    zh=f'''# 超导临界温度：Agent 模型与分组选择第二轮（2026-10-02）

{headline} 本轮完成了真实 GPT 工具闭环、固定模型对照、同尝试次数的自动搜索、方案冻结、一次开发评估以及独立数值复核。

## 数据集与代码流程

数据是公开 [3DSC-MP 冻结快照](https://huggingface.co/datasets/fgh123654/3dsc-mp-tc-pilot)：共 5,773 条，成分、匹配 MP 晶体结构和 Tc（K）。本轮训练 **3,764 条 / 1,117 个严格连接组**，旧验证 **869 条 / 280 个组**；历史评估 1,140 条的标签不参与本轮。化学体系或 MP 母体关联的记录放在同一连接组，三个训练 OOF 折均检查了化学体系、母体、标准成分及连接组的交叉重叠为零。保留第一轮的成分重复度倒数权重。

![第二轮完整流程](figures/workflow_v2.png)

[矢量流程图](figures/workflow_v2.svg)；[执行协议](PROTOCOL.md)；[准备及分组证据](data/data_audit.json)。

1. 固定输入为 109 个成分特征，或者 109 + 12 个修复后的结构描述符。
2. 在训练集固定的三个严格分组折上计算 pooled OOF 反馈；所有填补、变量筛选、缩放、聚类和模型拟合只使用该折拟合部分。
3. 先计算八个共享全局模型和四个额外参考。GPT 根据 OOF 误差案例选择输入、ExtraTrees / HGB、原值 / log1p 目标和全局 / 成分规则 / KMeans 分组。各组可有独立模型与目标，过小或未配置组回退到全局模型。
4. 自动搜索使用预先冻结的五个种子配置，只执行与 GPT 总尝试次数相同的前缀。失败、重复也消耗次数；次数相同不代表算力、模型拟合数、先验或配置分布相同。
5. 两臂统一使用正 Tc OOF 不退步约束，再最小化整体加权 MAE。基准锚点是整体 OOF 最好的同一个共享全局模型 {anchor}，不是从不同模型挑选最好的子群分数。
6. 记录、配置、代码和两臂选择冻结后，仅用原训练集重拟合。保存所有旧验证预测后才读取旧验证目标，不按验证结果重新排名或再次搜索。

“成分分组”是 Cu 和 O 同时存在优先，其次 Fe 和 P/As/S/Se/Te 中至少一种，剩余为 other。专家需要至少 80 个拟合样本和 12 个严格组。KMeans=3，10 次初始化，每折独立拟合，按质心 comp_Z_mean 命名；跨折的同名 cluster 不一定对应同一群体。这些规则均不能证明物理材料家族。

HGB 是 `HistGradientBoostingRegressor`（直方图梯度提升树）。它与 ExtraTrees 共同构成固定模型菜单。ExtraTrees 使用 160 棵树、叶子最小样本 2、max_features=1.0（全部特征）；HGB 使用 160 次迭代、15 个最大叶节点、学习率 0.08、最小叶样本 20、L2=1、关闭提前停止。种子均为 20261002，单线程；完整参数见代码，未宣称最优调参。

## 描述符修复

真实正占据权重按其实际和归一化；方向量改为完整张量 `(3 tr(Q²)-1)/2`，消除笛卡尔方向依赖。无有效邻居时的未定义矩改为缺失值。本轮修复包含这一语义变化，不能将差异全部归因于旋转不变性。

共 480 项训练结构表示检查、240 项合成表示检查、96 项原描述符重放检查通过；解析方向例子 isotropic=0、planar=0.25、collinear=1。68 个结构无 3.5 Å 内邻居，四个原零值矩改为缺失，共 272 处预期变化（训练 45、旧验证 16、历史结构 7）；共享特征没有其他变化。第一轮冻结源文件未修改。[完整审计](repair/audit.json)。

## 实际 Agent 运行

请求模型 `{inv['requested_model']}`，推理强度 `{inv['reasoning_effort']}`，通过现有 Codex 登录执行一个会话。共 **{state['tool_calls']} 次工具调用、{state['strategy_attempts']} 次配置尝试**，耗时 **{inv['elapsed_seconds']:.1f} 秒**。工具次数：`{json.dumps(types,ensure_ascii=False)}`。外部工具调用审计为空。自动臂匹配 {state['strategy_attempts']} 次尝试；OOF 实际拟合数 Agent={afits}、自动={cfits}，共享参考另外计入，最终重拟合 {result['actual_final_model_fits']} 次。

{chr(10).join(actions)}

[实际工具记录](agent/tool_events.jsonl)、[Agent 结论](agent/conclusion.json)、[调用与使用量](agent/{invocation_path.relative_to(ROOT/'agent').as_posix()})、[自动搜索预承诺](controls/plan.json)、[自动执行](controls/execution.json)。Agent 结论只基于训练 OOF，下面旧验证结果由外层评估器在其结束后计算。

## 选择与结果

共享全局锚点 **{anchor}**；Agent 选 **{agent}**，自动臂选 **{control}**。额外参考也参与比较，OOF 最好的全部全局参考为 **{strong}**。Agent 训练 OOF MAE={fmt(cv_agent['MAE_K'])} K，对照锚点={fmt(cv_anchor['MAE_K'])} K。[锁定选择](selection.json)。

{table(set(['G02',anchor,agent,control,strong]))}

表中的“旧验证”是同一 869 条开发样本。本轮零值 {counts['reported_zero']['rows']} 条、正 Tc {counts['positive_tc']['rows']} 条、≥40 K {counts['high_tc_ge40K']['rows']} 条；高 Tc 只有 {counts['high_tc_ge40K']['groups']} 个严格组。OOF 和旧验证列对应不同队列，不能横向解释为误差随实验下降。

Agent 减共享全局的旧验证 MAE 差 **{delta['MAE_difference_K']:+.4f} K**，配对组 bootstrap 95% 区间 **[{ci[0]:+.4f}, {ci[1]:+.4f}] K**。Agent 减自动臂差 **{dcontrol['MAE_difference_K']:+.4f} K**，区间 **[{dc[0]:+.4f}, {dc[1]:+.4f}] K**。负差表示 Agent 的误差更小；区间只描述这些固定模型在这一已观察开发队列上的条件差异，未包含训练、搜索、历史观察不确定性。[完整结果](final/results.json)。

正 Tc 约束只用于训练 OOF 选择，不能保证旧验证子群不退步；必须保留表中实际正 Tc、高 Tc 与 RMSE 结果。第一轮历史 1,140 条约 4.3 K MAE 属于另一个队列，本轮未重读其目标，不能用来和新 OOF / 869 条验证分数计算改善比例。

### 全部执行方案

{table(set(ids))}

专家配置、逐折路由及回退在各 `candidates/<ID>/result.json`；原始 OOF 预测和独立复核见 [comparison_table.csv](comparison_table.csv)、[verification.json](verification.json)、[protocol_review.md](protocol_review.md)。额外 11 特征参考只删掉修复块中的方向量；28 特征参考为原常规结构块，均属于菜单外固定诊断。

## 结论的适用范围与下一步

本轮检查的是具体的“模型与路由选择”干预。单次 GPT 会话加单次种子自动搜索不能证明 Agent 普遍优于自动搜索。旧验证和整个公开数据源此前都已观察，因此本轮没有全新独立验证。匹配 MP 结构、人工掺杂、记录的 Tc=0 等代理限制仍然存在；不构成新超导体、标签错误或物理机制证据。

下一步先依据这次冻结结果决定是否值得为路由策略申请真正未观察数据和多个种子复核。若增益不足或子群退步，应另立分类 / 异常识别协议，先定义可核查标签、实际使用场景和独立评估数据，再启动新 Agent 搜索；不把回归残差直接当成错误标签。

## 重现和证据

`prepare_data.py` 产生隔离输入；`pipeline.py` 实现固定 OOF、专家回退和冻结评估；`scientific_server.py` 限制训练反馈；`run_agent.py` 保存真实 GPT 会话；`run_controls_and_finalize.py` 执行预先固定的自动配置；`verify_results.py` 独立重算指标和本地模型预测。

本包含实际数值输入、折分配、修复特征、全部配置 / OOF 预测、最终预测、审计与日志。大型 joblib 模型保留在本地，模型文件哈希在最终结果中；公开包不含模型二进制。公开复核可运行 `python verify_results.py --root <此目录> --skip-models`，会明确跳过本地模型重放。不得在已有搜索目录重启 Agent 或改变冻结配置。首次从原数据计算修复还需 Hugging Face 冻结结构载荷；软件版本见 [environment_versions.json](environment_versions.json)。

数据继承上游 3DSC 的 CC BY 4.0 归属和使用条件，来源在公开数据集卡及第一轮报告中。代码和数值结论为本研究的实际执行记录。本报告不包含会议录音或转录。
'''
    write(OUT/'REPORT_zh.md',zh)
    en=f'''# Superconductivity Agent pipeline-selection pilot — 2026-10-02

One real GPT session completed {state['strategy_attempts']} attempted pipelines in {state['tool_calls']} tool calls ({inv['elapsed_seconds']:.1f} s). The Agent selected **{agent}**, the seeded automated arm selected **{control}**, and the shared-global anchor was **{anchor}**. {'The Agent retained a configuration equivalent to the shared global and demonstrated no additional contribution.' if no_gain else 'Selection was frozen using training OOF before the final development diagnosis.'}

![Executed workflow](figures/workflow_v2.png)

The public [3DSC-MP snapshot](https://huggingface.co/datasets/fgh123654/3dsc-mp-tc-pilot) has 5,773 records. This round uses 3,764 original training rows / 1,117 chemical-system-or-MP-parent connected groups for three fixed group folds. The original 869 validation rows / 280 groups are held aside this round, but were inspected historically: this is a development comparison, not independent validation. The 1,140 retrospective targets are not accessed this round. Original inverse-composition-multiplicity weights are retained.

Inputs are 109 composition features or 109 plus 12 fixed repaired descriptors. Choices are ExtraTrees / HistGradientBoosting, raw / log1p Tc, global / composition-template / fold-fitted KMeans-3 routing, with separate specialist estimator and target choices. Unspecified routes or those with fewer than 80 fitting rows or 12 groups fall back to the global. Chemistry presence templates and ordinal cluster labels are not proven physical families. Preprocessing, clusters and models fit only fold-training rows. HistGradientBoosting disables early stopping; seed=20261002 and one numerical thread. Full parameters are in [PROTOCOL.md](PROTOCOL.md).

Eight global references are shared before search; four extra references (11 repaired or 28 conventional structure features, ExtraTrees raw/log) are outside the search menu. Both arms select minimum weighted pooled OOF MAE subject to positive-Tc OOF MAE not exceeding that of the SAME overall-best shared global. Fixed automated configurations were precommitted; only the prefix matching all Agent attempts, including failures/duplicates, was executed. Equal attempts do not imply equal fit cost, runtime, priors or sampling distributions. Search CV fits: Agent={afits}, automated={cfits}. This one session and one seed do not establish a general Agent advantage.

Repair uses actual positive occupancy-weight sums and the invariant full-direction tensor `(3 tr(Q²)-1)/2`. Undefined short-neighborhood moments become missing: 272 planned shared-value changes on 68 structures, including 45 training and 16 old-validation rows. Performance differences cannot be attributed solely to anisotropy/normalization. Representation checks: 480 training + 240 synthetic, plus 96 original-descriptor replay checks, all pass. Original frozen first-round sources are unchanged. See [repair/audit.json](repair/audit.json).

## Frozen development results

{table(set(['G02',anchor,agent,control,strong]))}

Column labels are MAE/RMSE in kelvin; OOF uses training rows and the later columns use the old 869-row validation. That validation has {counts['reported_zero']['rows']} recorded-zero, {counts['positive_tc']['rows']} positive and {counts['high_tc_ge40K']['rows']} high-Tc rows ({counts['high_tc_ge40K']['groups']} high-Tc groups). Positive/high-Tc and RMSE tradeoffs must be retained. The positive guard is an OOF selection criterion, not a guarantee of validation non-regression.

Agent minus shared-global validation MAE: **{delta['MAE_difference_K']:+.4f} K**, paired group-bootstrap 95% interval **[{ci[0]:+.4f}, {ci[1]:+.4f}]**. Agent minus automated arm: **{dcontrol['MAE_difference_K']:+.4f} K**, interval **[{dc[0]:+.4f}, {dc[1]:+.4f}]**. Negative means lower Agent error. These are conditional intervals on historically observed development rows; they exclude training/search/prior-inspection uncertainty. The best global across shared and extra references by OOF was {strong}; do not conflate it with the shared anchor. Original-round retrospective MAE around 4.3 K is a separate cohort, not a denominator for this round's improvement.

All selections, specifications, code/data hashes and actual search records were frozen, then all models refit on original training. All validation predictions were persisted before opening isolated validation targets. No validation refit, post-evaluation reranking or second search occurred. [Selection](selection.json), [access journal](final/access_journal.json), [all metrics](final/results.json), [complete comparison table](comparison_table.csv), [independent verification](verification.json).

Actual Agent hypotheses and revisions appear in [tool events](agent/tool_events.jsonl) and [its OOF-only conclusion](agent/conclusion.json). The report's subsequent validation outcomes were unavailable to that scientific session. Full advisor report: [中文](REPORT_zh.md).

Next: use the frozen overall/subgroup tradeoffs to decide whether routing warrants genuinely unobserved data and multiple-seed evaluation. If regression gains are inadequate, design a separate classification/anomaly task with verifiable labels and an independent evaluation before another search. Regression residuals alone do not prove label errors, physical mechanisms or new superconductors. MP-matched geometries and artificial doping remain proxies; recorded zero is not universal nonsuperconductivity evidence.

This public package includes isolated inputs, folds, repaired features, code, all OOF/final predictions and complete search evidence. Large local joblib binaries are omitted; their hashes remain in results. `python verify_results.py --root <package> --skip-models` checks public numeric/selection evidence and explicitly omits local model replay. Do not rerun the bounded Agent in the frozen directory. [Environment versions](environment_versions.json), [protocol audit](protocol_review.md), [package manifest](PACKAGE_MANIFEST.json). Upstream 3DSC data attribution remains CC BY 4.0 as documented by the linked dataset card. No private meeting recording or transcript is published.
'''
    write(OUT/'REPORT.md',en)
    write(OUT/'README.md',f'''# 超导方向第二轮进展（2026-10-02）

真实 GPT 已完成 {state['strategy_attempts']} 次模型 / 分组方案尝试、{state['tool_calls']} 次科学工具调用。采用训练集严格分组 OOF 决策，冻结方案后在旧 869 条验证数据上比较。

{headline}

| 固定选择 | 旧验证加权 MAE (K) |
| --- | ---: |
| 共享全局 {anchor} | {fmt(metrics[anchor]['MAE_K'])} |
| Agent {agent} | {fmt(metrics[agent]['MAE_K'])} |
| 自动搜索 {control} | {fmt(metrics[control]['MAE_K'])} |

[完整中文汇报](REPORT_zh.md) · [English report](REPORT.md) · [全方案结果](comparison_table.csv) · [公开原数据](https://huggingface.co/datasets/fgh123654/3dsc-mp-tc-pilot)

![当前代码流程](figures/workflow_v2.png)

此旧验证队列此前已观察，结果属于开发比较。相同尝试数未匹配实际拟合计算成本；正 Tc OOF 筛选规则不保证验证子群不退步。详细子群结果、差值区间及独立复核在完整报告中。
''')
    manifest={'algorithm':'SHA256','excludes':['PACKAGE_MANIFEST.json','large local joblib models','private meeting media/transcripts'],'files':[{'path':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='PACKAGE_MANIFEST.json']}
    save(OUT/'PACKAGE_MANIFEST.json',manifest)
    print(json.dumps({'output':str(OUT),'files':len(manifest['files']),'bytes':sum(x['bytes'] for x in manifest['files']),'agent':agent,'control':control,'anchor':anchor},indent=2))
if __name__=='__main__':main()
