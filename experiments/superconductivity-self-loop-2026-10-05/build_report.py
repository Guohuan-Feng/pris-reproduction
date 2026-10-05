"""Render advisor reports from one read-only training-loop state snapshot.

Reads no validation files, changes no runtime state, and makes no model calls.
Evidence links assume the publication package preserves runtime paths in evidence/.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import html
import json
import math
from pathlib import Path
import re
import sqlite3
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_state(root):
    """Prefer authoritative SQLite; one transaction gives a coherent live snapshot."""
    for name in ("memory.sqlite", "status.sqlite"):
        path = root / name
        if path.exists():
            connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=20)
            try:
                connection.execute("PRAGMA query_only=ON")
                connection.execute("BEGIN")
                row = connection.execute("SELECT payload FROM state WHERE id=1").fetchone()
                if row is None:
                    raise ValueError("Runtime has no persisted state")
                return json.loads(row[0]), name
            finally:
                connection.close()
    return load(root / "status.json"), "status.json"


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def metric(cycle, positive=False):
    metrics = cycle.get("evaluation", {}).get("metrics", {})
    if positive:
        return metrics.get("subgroups", {}).get("positive_tc", {}).get("MAE_K")
    return metrics.get("MAE_K")


def duplicate(cycle):
    result = cycle.get("evaluation", {})
    return bool(result.get("proposal_was_duplicate", result.get("reused", False)))


def completed_unique(cycles):
    seen, accepted = set(), []
    for cycle in cycles:
        result = cycle.get("evaluation", {})
        if result.get("status") == "failed" or result.get("scientific_evidence_available") is False or duplicate(cycle):
            continue
        if not isinstance(cycle.get("specification"), dict) or not isinstance(cycle.get("reflection"), dict):
            continue
        if not finite(metric(cycle)) or not finite(metric(cycle, True)):
            continue
        fingerprint = json.dumps(cycle["specification"], sort_keys=True, separators=(",", ":"))
        if fingerprint not in seen:
            seen.add(fingerprint)
            accepted.append(cycle)
    return accepted


def f(value, digits=6):
    return f"{value:.{digits}f}" if finite(value) else "—"


def cell(value):
    return html.escape(str(value), quote=False).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def pair(config):
    if not isinstance(config, dict):
        return "—"
    estimator = {"extra_trees": "ET", "hist_gradient_boosting": "HGB"}.get(config.get("model"), config.get("model", "?"))
    return estimator + "/" + str(config.get("target", "?"))


def input_name(name, zh):
    names = {"composition": ("成分 109", "composition 109"),
             "composition_repaired": ("成分 109 + 修复结构 12", "composition 109 + repaired structure 12")}
    return names.get(name, (str(name), str(name)))[0 if zh else 1]


def routing_name(name, zh):
    names = {"global": ("全局", "global"), "chemistry": ("成分规则", "chemistry rules"), "kmeans3": ("KMeans 三组", "KMeans 3")}
    return names.get(name, (str(name), str(name)))[0 if zh else 1]


def specification(root, cid):
    if not isinstance(cid, str) or not re.fullmatch(r"[A-Z]\d+", cid):
        return None
    path = root / "workbench" / "candidates" / cid / "specification.json"
    return load(path) if path.exists() else None


def compact_test(root, cycle, zh):
    """Describe the exact intervention, without elevating model prose to fact."""
    current = cycle.get("specification") or {}
    parent = specification(root, cycle.get("revision_of"))
    if not parent:
        return "检验所列配置能否产生合格改进" if zh else "Test whether this configuration yields an eligible improvement"
    changes = []
    if parent.get("input") != current.get("input"):
        changes.append(("输入改为 " if zh else "input → ") + input_name(current.get("input"), zh))
    if parent.get("routing") != current.get("routing"):
        changes.append(("分组改为 " if zh else "routing → ") + routing_name(current.get("routing"), zh))
    if parent.get("global") != current.get("global"):
        changes.append(("全局改为 " if zh else "global → ") + pair(current.get("global")))
    old, new = parent.get("experts", {}), current.get("experts", {})
    for route in sorted(set(old) | set(new)):
        if old.get(route) != new.get(route):
            value = pair(new[route]) if route in new else ("回退全局" if zh else "global fallback")
            changes.append(route + " → " + value)
    change = "; ".join(changes) if changes else ("相同配置" if zh else "same configuration")
    return (("相对 " + str(cycle.get("revision_of")) + "：" + change + "；检验能否合格改进") if zh
            else ("vs " + str(cycle.get("revision_of")) + ": " + change + "; test eligible improvement"))


def fits(cycle):
    result = cycle.get("evaluation", {})
    return result.get("candidate_total_regressor_fits", result.get("actual_new_regressor_fits"))


def count_fits(cycles):
    return sum(int(fits(c)) for c in cycles if finite(fits(c)))


def table_metrics(cycles, unique_ids, zh):
    columns = (["实验", "整体 MAE K", "正 Tc MAE K", "约束", "更新最佳", "回归器拟合", "计入新增完成数"] if zh
               else ["Experiment", "Overall MAE K", "Positive Tc MAE K", "Guard", "Incumbent update", "Regressor fits", "Counts toward minimum"])
    rows = ["| " + " | ".join(columns) + " |", "| --- | ---: | ---: | --- | --- | ---: | --- |"]
    for cycle in cycles:
        result, cid = cycle.get("evaluation", {}), cycle["candidate_id"]
        yes, no = ("是", "否") if zh else ("yes", "no")
        if finite(metric(cycle, True)):
            guard = ("通过" if result.get("guard_eligible") else "未通过") if zh else ("pass" if result.get("guard_eligible") else "FAIL")
        else:
            guard = "无数值结果" if zh else "no measured result"
        values = [f"[{cid}](evidence/cycles/{cid}/evaluation.json)", f(metric(cycle)), f(metric(cycle, True)), guard,
                  yes if result.get("improved_incumbent") else no, str(fits(cycle)) if fits(cycle) is not None else "—", yes if cid in unique_ids else no]
        rows.append("| " + " | ".join(values) + " |")
    if not cycles:
        rows.append("| " + ("暂无新增完成循环" if zh else "No new completed cycles yet") + " | — | — | — | — | — | — |")
    return "\n".join(rows)


def table_config(root, cycles, zh):
    columns = (["实验", "实际输入", "分组", "全局模型", "专家模型", "待检验问题"] if zh
               else ["Experiment", "Actual inputs", "Routing", "Global", "Experts", "Configuration-level hypothesis"])
    rows = ["| " + " | ".join(columns) + " |", "| --- | --- | --- | --- | --- | --- |"]
    for cycle in cycles:
        spec = cycle.get("specification") or {}
        experts = "; ".join(key + "=" + pair(value) for key, value in sorted(spec.get("experts", {}).items())) or ("无" if zh else "none")
        values = [cycle["candidate_id"], input_name(spec.get("input"), zh), routing_name(spec.get("routing"), zh), pair(spec.get("global")), experts, compact_test(root, cycle, zh)]
        rows.append("| " + " | ".join(cell(x) for x in values) + " |")
    if not cycles:
        rows.append("| " + ("暂无新增完成循环" if zh else "No new completed cycles yet") + " | — | — | — | — | — |")
    return "\n".join(rows)


def plot(snapshot, output):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import font_manager
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    font = Path("C:/Windows/Fonts/msyh.ttc")
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        family = font_manager.FontProperties(fname=str(font)).get_name()
        plt.rcParams["font.family"] = family
    plt.rcParams.update({"axes.unicode_minus": False, "svg.fonttype": "path"})
    cycles, inherited = snapshot["cycles"], set(snapshot["inherited_ids"])
    fig, axes = plt.subplots(2, 1, figsize=(12.7, 8.1), sharex=True, gridspec_kw={"height_ratios": [1.1, 1]})
    fig.patch.set_facecolor("#f8fafc")
    colours = {"pass": "#2369a2", "fail": "#c2473d", "best": "#1e8b69", "duplicate": "#977632"}
    initial = snapshot["baseline"]["MAE_K"]
    incumbent, trajectory = initial, []
    for number, cycle in enumerate(cycles, 1):
        result = cycle.get("evaluation", {})
        if result.get("improved_incumbent") and finite(metric(cycle)):
            incumbent = metric(cycle)
        trajectory.append(incumbent)
        for ax, positive in zip(axes, [False, True]):
            value = metric(cycle, positive)
            if not finite(value):
                continue
            passed = bool(result.get("guard_eligible"))
            marker, colour = ("o", colours["pass"]) if passed else ("X", colours["fail"])
            if duplicate(cycle):
                marker, colour = "^", colours["duplicate"]
            ax.scatter([number], [value], marker=marker, color=colour, s=65, zorder=4,
                       edgecolors="white", linewidths=.6, alpha=.6 if cycle["candidate_id"] in inherited else 1)
    axes[0].step([0] + list(range(1, len(cycles)+1)), [initial] + trajectory, where="post", color=colours["best"], lw=2.1, zorder=3)
    axes[0].axhline(initial, color="#64748b", lw=1.2, linestyle="--")
    axes[1].axhline(snapshot["guard"], color=colours["fail"], lw=1.4, linestyle="--")
    for ax in axes:
        ax.set_facecolor("white")
        ax.grid(axis="y", alpha=.2)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_xlim(-.2, max(4.2, len(cycles)+.7))
        inherited_positions = [i for i, c in enumerate(cycles, 1) if c["candidate_id"] in inherited]
        if inherited_positions:
            ax.axvspan(.5, max(inherited_positions)+.5, color="#e2e8f0", alpha=.55, zorder=0)
    axes[0].set_ylabel("整体加权 MAE / K", fontsize=11.5)
    axes[1].set_ylabel("正 Tc 子组加权 MAE / K", fontsize=11.5)
    axes[1].set_xlabel("已完成循环编号；灰色区域为继承的旧两轮", fontsize=11)
    axes[1].set_xticks(list(range(1, len(cycles)+1)), [x["candidate_id"] for x in cycles], rotation=50 if len(cycles)>12 else 0, fontsize=9)
    handles = [Line2D([], [], color=colours["pass"], marker="o", linestyle="none", label="通过正 Tc 约束"),
               Line2D([], [], color=colours["fail"], marker="X", linestyle="none", label="未通过正 Tc 约束"),
               Line2D([], [], color=colours["best"], lw=2, label="按规则保留的最佳方案"),
               Line2D([], [], color="#64748b", lw=1.2, linestyle="--", label="初始最佳 A05")]
    if any(duplicate(c) for c in cycles):
        handles.append(Line2D([], [], color=colours["duplicate"], marker="^", linestyle="none", label="重复配置，不计入完成数"))
    axes[0].legend(handles=handles, loc="best", fontsize=9, ncol=2)
    axes[1].text(.98, .97, f"固定正 Tc 上限：{snapshot['guard']:.6f} K", transform=axes[1].transAxes, ha="right", va="top", color=colours["fail"], fontsize=10,
                 bbox={"facecolor": "white", "edgecolor": "none", "alpha": .85, "pad": 3})
    banner = "完成" if snapshot["completed"] else ("RUNNING · 运行中" if snapshot["state"]["status"] == "running" else "INCOMPLETE · 尚未完成")
    fig.suptitle(f"超导 Agent 自循环训练反馈  |  {banner}\n新增有效实验 {snapshot['new_unique_count']} / {snapshot['required_new']}；所有数值均为同一训练划分上的自适应 OOF", fontsize=15, color="#17334d", y=.98)
    fig.text(.5, .012, "红叉仍显示实测误差，但该方案不能更新最佳模型。失败或未完成的循环没有伪造的数值点。", ha="center", fontsize=9.2, color="#516172")
    fig.subplots_adjust(left=.09, right=.98, top=.865, bottom=.155 if len(cycles)>12 else .12, hspace=.10)
    output.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "svg"):
        fig.savefig(output / ("progress." + extension), dpi=170, facecolor=fig.get_facecolor())
    plt.close(fig)


def snapshot(root):
    state, state_source = read_state(root)
    lineage = load(root / "lineage.json")
    parent = load(root / "lineage" / "parent" / "status.json")
    cycles = state.get("completed_cycles", [])
    inherited_ids = {c["candidate_id"] for c in parent.get("completed_cycles", [])}
    new = [c for c in cycles if c["candidate_id"] not in inherited_ids]
    unique = completed_unique(cycles)
    new_unique = [c for c in unique if c["candidate_id"] not in inherited_ids]
    policy = lineage["policy"]
    required_new = policy["required_additional_completed_unique_experiments"]
    completed = (len(new_unique) >= required_new
                 and len(unique) >= policy["required_total_completed_unique_experiments"]
                 and state.get("status") == "stopped" and state.get("phase") == "propose"
                 and state.get("stop_reason") == "minimum_completed_experiments_reached"
                 and all(state.get(key) is None for key in ("pending_call", "pending_plan", "pending_result")))
    baseline = load(root / "workbench" / "candidates" / "A05" / "result.json")["metrics"]
    audit = load(root / "workbench" / "data" / "data_audit.json")
    passed = [c for c in new_unique if c.get("evaluation", {}).get("guard_eligible")]
    record = min(passed, key=lambda c: metric(c)) if passed else None
    state_hash = hashlib.sha256(json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()
    successful_calls = 0
    for receipt_path in (root / "calls").glob("*/receipt.json"):
        match = re.fullmatch(r"(\d+)_(propose|reflect)", receipt_path.parent.name)
        if match and lineage["inherited_counters"]["llm_calls"] < int(match[1]) <= state["llm_calls"]:
            successful_calls += load(receipt_path).get("completed") is True
    generated = dt.datetime.now(dt.timezone.utc)
    return {"state": state, "state_source": state_source, "lineage": lineage, "cycles": cycles, "new": new,
            "inherited_ids": sorted(inherited_ids), "new_unique": new_unique, "new_unique_count": len(new_unique), "unique_ids": {c["candidate_id"] for c in unique},
            "required_new": required_new, "completed": completed, "baseline": baseline, "best_new": record,
            "guard": state["guard"]["positive_MAE_K"], "train_rows": audit["train_rows"], "train_groups": audit["train_groups"],
            "snapshot_sha256": state_hash, "new_successful_model_calls": successful_calls,
            "generated_utc": generated.isoformat(),
            "generated_local": generated.astimezone(ZoneInfo("America/New_York")).isoformat()}


def report(root, s, zh):
    state, cfg, lineage = s["state"], s["state"]["config"], s["lineage"]
    inherited = lineage["inherited_counters"]
    new_calls = state["llm_calls"] - inherited["llm_calls"]
    new_time = state["elapsed_seconds"] - inherited["elapsed_seconds"]
    improved = [c for c in s["new"] if c.get("evaluation", {}).get("improved_incumbent")]
    guard_fail = sum(finite(metric(c, True)) and not c.get("evaluation", {}).get("guard_eligible") for c in s["new"])
    gain = s["baseline"]["MAE_K"] - state["best"]["MAE_K"]
    best_new = s["best_new"]
    banner = ("COMPLETE · 已完成" if zh else "COMPLETE") if s["completed"] else (("RUNNING · 运行中，非最终结果" if zh else "RUNNING — provisional snapshot") if state["status"] == "running" else ("INCOMPLETE · 尚未达到完整交付状态" if zh else "INCOMPLETE — completion requirement not yet satisfied"))
    if zh:
        text = f'''# 超导 Agent 新增二十轮自循环实验

**{banner}**。本报告记录继承旧两轮记忆后，新增至少 20 个成功完成、配置不重复的实验。当前新增完成 **{s['new_unique_count']} / {s['required_new']}**，继承 {len(s['inherited_ids'])} 个旧实验。当前最佳方案为 **{state['best']['id']}，训练折外加权 MAE {f(state['best']['MAE_K'])} K**。

快照生成时间：**{s['generated_local']}，America/New_York**。运行状态 `{state['status']}`，当前阶段 `{state['phase']}`；停止原因 `{state.get('stop_reason') or '尚未停止'}`。正在执行但尚未完成反思的实验不计入完成数。{'' if s['completed'] else '后续结果以更新后的报告为准。'}

## 数据集和评价范围

| 项目 | 内容 |
| --- | --- |
| 数据来源 | [3DSC MP Tc pilot](https://huggingface.co/datasets/fgh123654/3dsc-mp-tc-pilot) |
| 训练反馈 | {s['train_rows']:,} 条记录，{s['train_groups']:,} 个严格关联组；固定 3 折分组交叉验证 |
| 实际输入 | 成分 109 列，或成分 109 列加修复后的结构 12 列 |
| 主指标 | 加权训练折外 MAE，单位 K；越低越好 |
| 正 Tc 约束 | MAE 不超过固定 G01 基线的 {f(s['guard'])} K |
| 独立验证 | 本续跑没有读取验证标签，也没有重新计算验证结果 |

`composition_repaired` 实际指“成分特征 + 修复后的结构特征”，不是“修复后的成分表示”。成分规则和 KMeans 是操作性分组，不等同于经验证的物理材料族。模型生成的假设和反思是待检验解释，不能作为机制证据。

数据、特征和样本划分均沿用冻结的第二版来源，归属与再使用说明见[数据来源记录](../superconductivity-agent-2026-10-02/DATA_PROVENANCE.md)和[上游许可](../superconductivity-agent-2026-10-02/UPSTREAM_LICENSE.md)。

## 自循环和本次继续条件

```mermaid
flowchart TD
    A["读取旧两轮记忆与训练证据"] --> B["模型自主提出假设与配置"]
    B --> C["数值工作进程执行三折实验"]
    C --> D["检查误差、正 Tc 约束和配置重复"]
    D --> E["模型反思并写入持久记忆"]
    E --> F{{"新增成功且独特的配置达到 20 个？"}}
    F -- 否 --> B
    F -- 是 --> G["记录完成状态与报告"]
    H["用户停止、资源上限或异常"] --> I["暂停或停止并保留记录"]
```

程序自主选择下一轮的输入、目标变换、路由和回归器。本次在新增 20 个有效实验完成前，延后模型主动停止和连续停滞停止；失败和重复尝试不充数。用户停止与资源上限始终生效。包括旧两轮的总完成下限为 {cfg['min_completed_experiments']}；达到下限后自动停止。

本次累计上限为 {cfg['max_experiments']} 次尝试、{cfg['max_llm_calls']} 次模型调用、{cfg['max_seconds']:,.0f} 秒子进程运行时间；单次模型调用 / 数值工作进程上限为 {cfg['max_call_seconds']:g} / {cfg['max_fit_seconds']:g} 秒。旧运行计数被继承，没有重置。更新最佳方案仍需通过正 Tc 约束，并至少降低 {cfg['min_improvement_K']:g} K。

## 当前结果

| 项目 | 快照结果 |
| --- | ---: |
| 新增有效实验 / 要求 | {s['new_unique_count']} / {s['required_new']} |
| 新增已完成循环，含失败或重复 | {len(s['new'])} |
| 新增已完成循环的回归器拟合 | {count_fits(s['new'])} |
| 新增成功模型调用，已有完成回执 | {s['new_successful_model_calls']} |
| 新增模型调用，含在途已预留调用 | {new_calls} |
| 新增已计入的子进程时间 | {new_time:.1f} 秒 |
| 新增循环未通过正 Tc 约束 | {guard_fail} |
| 新增循环触发最佳方案更新 | {len(improved)} |
| 当前最佳方案相对初始 A05 的 MAE 降幅 | {gain:.6f} K |

初始 A05 的整体 MAE 为 {f(s['baseline']['MAE_K'])} K，正 Tc MAE 为 {f(s['baseline']['subgroups']['positive_tc']['MAE_K'])} K。'''
        if best_new:
            text += f"新增实验中，通过正 Tc 约束的最低整体 MAE 为 **{best_new['candidate_id']}：{f(metric(best_new))} K**。"
        else:
            text += "当前尚无新增完成且通过正 Tc 约束的独特配置。"
        text += "\n\n以上均为同一训练划分反复参与方案选择后的 OOF 开发结果；不能据此宣称独立泛化提升或发现新的超导机制。报告中的改进计数是控制程序按固定规则的记录，完整性审计仍应以发布包中的核验记录为准。\n\n"
        text += "![逐轮误差和最佳方案轨迹](figures/progress.png)\n\n[下载矢量图](figures/progress.svg)。灰色区域标出继承的旧两轮；红叉标出未通过正 Tc 约束的实测配置。\n\n## 新增实验结果矩阵\n\n"
        text += table_metrics(s["new"], s["unique_ids"], True)
        text += "\n\n拟合次数来自完成候选的回归器计数，不含 KMeans；在途或中断未完成的工作不混入该统计。\n\n## 每轮配置与待检验问题\n\nET 为 Extra Trees，HGB 为直方图梯度提升；`raw` 与 `log1p` 表示目标变换。未列出的专家组使用全局模型。下表按实际配置变化整理待检验问题，原始模型假设与反思见[完整状态记录](evidence/status.json)。\n\n"
        text += table_config(root, s["new"], True)
        text += "\n\n## 代码与可追溯记录\n\n"
        text += "[旧两轮及原自循环流程](../superconductivity-self-loop-2026-10-02/README_zh.md)和[第二版冻结实验](../superconductivity-agent-2026-10-02/REPORT_zh.md)保持原样。`fork_run.py` 复制经过核验的父运行并保存谱系；`controller.py` 执行完成下限与自动循环；`llm_client.py` 负责模型决策；`worker.py` 与 `workbench_adapter.py` 执行训练实验。\n\n[运行谱系](evidence/lineage.json)记录父运行状态和哈希；[状态快照](evidence/status.json)记录每轮提案、结果、反思及预算。暂停或崩溃恢复沿用相同运行状态，不能通过恢复重置预算。\n\n"
    else:
        text = f'''# Twenty additional autonomous superconductivity experiments

**{banner}.** This continuation inherits two earlier cycles and requires at least 20 additional successful, unique, evaluated-and-reflected configurations. Current additional completion: **{s['new_unique_count']} / {s['required_new']}**. The retained incumbent is **{state['best']['id']} with weighted training OOF MAE {f(state['best']['MAE_K'])} K**.

Snapshot generated: **{s['generated_local']}, America/New_York**. State: `{state['status']}`; phase: `{state['phase']}`; stop reason: `{state.get('stop_reason') or 'not stopped'}`. A cycle awaiting reflection is not counted as completed.

## Data and evaluation scope

The feedback set contains **{s['train_rows']:,} records and {s['train_groups']:,} linked-identity groups**, with the fixed three-fold split from the [frozen V2 experiment](../superconductivity-agent-2026-10-02/REPORT.md). The source dataset is [3DSC MP Tc pilot](https://huggingface.co/datasets/fgh123654/3dsc-mp-tc-pilot). The allowed inputs are 109 composition features, or those 109 features plus 12 repaired structural features. In particular, `composition_repaired` means composition plus repaired structure, not a repaired composition representation.

The data, prepared features, and cohort split reuse the frozen V2 source. Attribution and reuse terms are documented in the [data provenance](../superconductivity-agent-2026-10-02/DATA_PROVENANCE.md) and [upstream license](../superconductivity-agent-2026-10-02/UPSTREAM_LICENSE.md).

Selection uses weighted training OOF MAE. The positive-Tc MAE guard remains **{f(s['guard'])} K**, fixed from G01. Incumbent updates require guard eligibility and at least **{cfg['min_improvement_K']:g} K** improvement. No validation labels or new validation scores are used in this continuation. Adaptive reuse of these folds does not provide independent evidence of generalization. Model hypotheses and reflections are interpretations, not established physical mechanisms; operational routes are not verified material families.

## Continuation policy and observed progress

`fork_run.py` preserves the parent and inherits its memory, counters, and two successful unique cycles. `controller.py` autonomously proposes, executes, evaluates, reflects, saves memory, and continues. Before the total minimum of {cfg['min_completed_experiments']} is reached, model-directed and stagnation stops are deferred. Failed and duplicate proposals do not count toward the minimum. Operator cancellation, resource limits, and unresolved execution errors still apply. Reaching the minimum triggers an automatic stop.

The cumulative limits are {cfg['max_experiments']} attempts, {cfg['max_llm_calls']} model calls, and {cfg['max_seconds']:,.0f} active child-process seconds, including the inherited counters. Per-call and per-worker limits are {cfg['max_call_seconds']:g} and {cfg['max_fit_seconds']:g} seconds respectively. The model chooses configurations; the report generator neither chooses experiments nor invokes the model.

| Measure | Snapshot |
| --- | ---: |
| Additional successful unique configurations / required | {s['new_unique_count']} / {s['required_new']} |
| Additional completed cycles, including failures or duplicates | {len(s['new'])} |
| Regressor fits in additional completed cycles | {count_fits(s['new'])} |
| Additional successful model calls with completed receipts | {s['new_successful_model_calls']} |
| Additional model calls, including reserved calls in flight | {new_calls} |
| Additional accounted child-process seconds | {new_time:.1f} |
| Additional guard failures | {guard_fail} |
| Additional incumbent updates | {len(improved)} |
| Retained incumbent MAE reduction from initial A05 | {gain:.6f} K |

Initial A05: overall MAE {f(s['baseline']['MAE_K'])} K; positive-Tc MAE {f(s['baseline']['subgroups']['positive_tc']['MAE_K'])} K. '''
        text += (f"The lowest guard-eligible MAE among the new unique configurations is **{best_new['candidate_id']}: {f(metric(best_new))} K**." if best_new else "No new unique guard-eligible configuration has completed yet.")
        text += " Controller-recorded gains remain training-development results; provenance and integrity claims should be checked against the package audit.\n\n![Per-cycle MAE and retained incumbent](figures/progress.png)\n\n[Vector figure](figures/progress.svg). The shaded region marks the inherited cycles; red crosses mark measured guard failures.\n\n## Additional experiment matrix\n\n"
        text += table_metrics(s["new"], s["unique_ids"], False)
        text += "\n\nFit counts are completed candidate regressor fits, excluding KMeans and unfinished work.\n\n## Configurations and testable interventions\n\nET means Extra Trees; HGB means histogram gradient boosting. `raw` and `log1p` describe the target transform. Omitted routes use the global fallback. The table summarizes actual configuration changes, not physical mechanisms. Original hypotheses and reflections remain in the [state export](evidence/status.json).\n\n"
        text += table_config(root, s["new"], False)
        text += "\n\n## Evidence and use\n\nThe [previous two-cycle report](../superconductivity-self-loop-2026-10-02/README.md) and frozen V2 experiment remain unchanged. [Lineage](evidence/lineage.json) identifies the preserved parent, inherited counters, policy, and hashes. The [state export](evidence/status.json) contains cycle history and budgets.\n\nUse the prepared V2 scientific environment and authenticated Codex CLI. For a local continuation already created by `fork_run.py`:\n\n```sh\npython controller.py resume --run-dir ~/tc-self-loop/runs/continuation-20 --source-dir ../superconductivity-agent-2026-10-02\npython controller.py status --run-dir ~/tc-self-loop/runs/continuation-20\npython controller.py stop --run-dir ~/tc-self-loop/runs/continuation-20\n```\n\n`resume` does not reset counters. Unknown outcomes of interrupted model requests remain inspectable instead of being blindly resubmitted. Publication exports are evidence, not a substitute for the full resumable runtime.\n\n"
    if zh:
        text += "[44 项程序测试](verification.json)覆盖控制、恢复、最少完成次数和训练适配器；这些测试中的模型决策与数值实验使用模拟对象，不能代替真实运行证据。[最终独立运行审计](run_audit.json)重新计算已保存的训练折外指标、重放事件，并核对模型回执、候选配置和文件哈希。\n\n最终完成要求为：至少新增 20 个成功且配置不同的完整循环、累计至少 22 个；运行因 `minimum_completed_experiments_reached` 停止，且没有待完成调用、提案、结果或数值工作。最终审计中的 `checks_passed` 和 `final_completion_verified` 均须为 `true`。可在发布目录执行：\n\n```sh\npython audit_run.py --run-dir evidence --output audit_check.json\n```\n\n"
    else:
        text += "The [44 program tests](verification.json) exercise controller, runtime, continuation, fork, and adapter behavior with mocked model decisions and numerical experiments. The [final independent run audit](run_audit.json) separately recomputes saved training OOF metrics, replays events, and checks model receipts, specifications, and hashes.\n\nFinal completion requires at least 20 additional successful unique cycles and 22 in total, a `minimum_completed_experiments_reached` stop, and no pending model call, proposal, result, or numerical work. The final audit must report both `checks_passed: true` and `final_completion_verified: true`. Recheck the publication package with:\n\n```sh\npython audit_run.py --run-dir evidence --output audit_check.json\n```\n\n"
    text += (("重新生成报告" if zh else "Regenerate the report") + ":\n\n```sh\npython build_report.py --run-dir ~/tc-self-loop/runs/continuation-20\n```\n\n")
    label = "本报告从只读状态快照生成；状态内容的规范 JSON SHA256：" if zh else "Generated from a read-only state snapshot; canonical state JSON SHA256: "
    text += label + f"`{s['snapshot_sha256']}`" + ("。\n" if zh else ".\n")
    text += f"\nUTC: `{s['generated_utc']}`.\n"
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    args = parser.parse_args()
    root, output = args.run_dir.expanduser().resolve(), args.output_dir.expanduser().resolve()
    if output == root or output.is_relative_to(root):
        raise ValueError("Reports must be generated outside the active runtime")
    data = snapshot(root)
    output.mkdir(parents=True, exist_ok=True)
    plot(data, output / "figures")
    for zh, name in ((True, "README_zh.md"), (False, "README.md")):
        (output / name).write_text(report(root, data, zh), encoding="utf-8", newline="\n")
    print(json.dumps({"status": data["state"]["status"], "new_unique_completed": data["new_unique_count"],
                      "required_new": data["required_new"], "final_completion": data["completed"],
                      "snapshot_sha256": data["snapshot_sha256"], "generated_local": data["generated_local"],
                      "generated_utc": data["generated_utc"], "output_dir": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
