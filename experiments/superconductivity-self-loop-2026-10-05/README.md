# Twenty additional autonomous superconductivity experiments

**COMPLETE.** This continuation inherits two earlier cycles and requires at least 20 additional successful, unique, evaluated-and-reflected configurations. Current additional completion: **20 / 20**. The retained incumbent is **A05 with weighted training OOF MAE 7.752599 K**.

Snapshot generated: **2026-10-05T11:23:20.208615-04:00, America/New_York**. State: `stopped`; phase: `propose`; stop reason: `minimum_completed_experiments_reached`. A cycle awaiting reflection is not counted as completed.

## Data and evaluation scope

The feedback set contains **3,764 records and 1,117 linked-identity groups**, with the fixed three-fold split from the [frozen V2 experiment](../superconductivity-agent-2026-10-02/REPORT.md). The source dataset is [3DSC MP Tc pilot](https://huggingface.co/datasets/fgh123654/3dsc-mp-tc-pilot). The allowed inputs are 109 composition features, or those 109 features plus 12 repaired structural features. In particular, `composition_repaired` means composition plus repaired structure, not a repaired composition representation.

The data, prepared features, and cohort split reuse the frozen V2 source. Attribution and reuse terms are documented in the [data provenance](../superconductivity-agent-2026-10-02/DATA_PROVENANCE.md) and [upstream license](../superconductivity-agent-2026-10-02/UPSTREAM_LICENSE.md).

Selection uses weighted training OOF MAE. The positive-Tc MAE guard remains **8.832166 K**, fixed from G01. Incumbent updates require guard eligibility and at least **0.01 K** improvement. No validation labels or new validation scores are used in this continuation. Adaptive reuse of these folds does not provide independent evidence of generalization. Model hypotheses and reflections are interpretations, not established physical mechanisms; operational routes are not verified material families.

## Continuation policy and observed progress

`fork_run.py` preserves the parent and inherits its memory, counters, and two successful unique cycles. `controller.py` autonomously proposes, executes, evaluates, reflects, saves memory, and continues. Before the total minimum of 22 is reached, model-directed and stagnation stops are deferred. Failed and duplicate proposals do not count toward the minimum. Operator cancellation, resource limits, and unresolved execution errors still apply. Reaching the minimum triggers an automatic stop.

The cumulative limits are 42 attempts, 105 model calls, and 14,400 active child-process seconds, including the inherited counters. Per-call and per-worker limits are 360 and 900 seconds respectively. The model chooses configurations; the report generator neither chooses experiments nor invokes the model.

| Measure | Snapshot |
| --- | ---: |
| Additional successful unique configurations / required | 20 / 20 |
| Additional completed cycles, including failures or duplicates | 20 |
| Regressor fits in additional completed cycles | 165 |
| Additional successful model calls with completed receipts | 40 |
| Additional model calls, including reserved calls in flight | 40 |
| Additional accounted child-process seconds | 1752.6 |
| Additional guard failures | 10 |
| Additional incumbent updates | 0 |
| Retained incumbent MAE reduction from initial A05 | 0.000000 K |

Initial A05: overall MAE 7.752599 K; positive-Tc MAE 8.505080 K. The lowest guard-eligible MAE among the new unique configurations is **L007: 7.761155 K**. Controller-recorded gains remain training-development results; provenance and integrity claims should be checked against the package audit.

![Per-cycle MAE and retained incumbent](figures/progress.png)

[Vector figure](figures/progress.svg). The shaded region marks the inherited cycles; red crosses mark measured guard failures.

## Additional experiment matrix

| Experiment | Overall MAE K | Positive Tc MAE K | Guard | Incumbent update | Regressor fits | Counts toward minimum |
| --- | ---: | ---: | --- | --- | ---: | --- |
| [L003](evidence/cycles/L003/evaluation.json) | 8.006128 | 8.710481 | pass | no | 9 | yes |
| [L004](evidence/cycles/L004/evaluation.json) | 7.838040 | 8.501694 | pass | no | 6 | yes |
| [L005](evidence/cycles/L005/evaluation.json) | 7.827243 | 8.835551 | FAIL | no | 6 | yes |
| [L006](evidence/cycles/L006/evaluation.json) | 7.883749 | 8.864591 | FAIL | no | 9 | yes |
| [L007](evidence/cycles/L007/evaluation.json) | 7.761155 | 8.461477 | pass | no | 9 | yes |
| [L008](evidence/cycles/L008/evaluation.json) | 7.957731 | 8.338205 | pass | no | 9 | yes |
| [L009](evidence/cycles/L009/evaluation.json) | 8.558511 | 11.037285 | FAIL | no | 9 | yes |
| [L010](evidence/cycles/L010/evaluation.json) | 7.792985 | 8.669032 | pass | no | 12 | yes |
| [L011](evidence/cycles/L011/evaluation.json) | 7.889043 | 8.829194 | pass | no | 12 | yes |
| [L012](evidence/cycles/L012/evaluation.json) | 8.280389 | 9.016631 | FAIL | no | 12 | yes |
| [L013](evidence/cycles/L013/evaluation.json) | 7.988238 | 8.949617 | FAIL | no | 6 | yes |
| [L014](evidence/cycles/L014/evaluation.json) | 7.913146 | 8.875420 | FAIL | no | 6 | yes |
| [L015](evidence/cycles/L015/evaluation.json) | 8.204372 | 8.855926 | FAIL | no | 6 | yes |
| [L016](evidence/cycles/L016/evaluation.json) | 8.267920 | 8.586141 | pass | no | 6 | yes |
| [L017](evidence/cycles/L017/evaluation.json) | 8.223005 | 9.256742 | FAIL | no | 6 | yes |
| [L018](evidence/cycles/L018/evaluation.json) | 8.006869 | 8.968596 | FAIL | no | 6 | yes |
| [L019](evidence/cycles/L019/evaluation.json) | 8.005762 | 9.022514 | FAIL | no | 6 | yes |
| [L020](evidence/cycles/L020/evaluation.json) | 7.802085 | 8.514591 | pass | no | 9 | yes |
| [L021](evidence/cycles/L021/evaluation.json) | 7.801541 | 8.625429 | pass | no | 12 | yes |
| [L022](evidence/cycles/L022/evaluation.json) | 7.873843 | 8.767759 | pass | no | 9 | yes |

Fit counts are completed candidate regressor fits, excluding KMeans and unfinished work.

## Configurations and testable interventions

ET means Extra Trees; HGB means histogram gradient boosting. `raw` and `log1p` describe the target transform. Omitted routes use the global fallback. The table summarizes actual configuration changes, not physical mechanisms. Original hypotheses and reflections remain in the [state export](evidence/status.json).

| Experiment | Actual inputs | Routing | Global | Experts | Configuration-level hypothesis |
| --- | --- | --- | --- | --- | --- |
| L003 | composition 109 + repaired structure 12 | chemistry rules | ET/raw | cu_o=ET/raw; other=ET/raw | vs A05: input → composition 109 + repaired structure 12; test eligible improvement |
| L004 | composition 109 | chemistry rules | ET/raw | cu_o=ET/raw | vs A05: other → global fallback; test eligible improvement |
| L005 | composition 109 | chemistry rules | ET/raw | other=ET/raw | vs A05: cu_o → global fallback; test eligible improvement |
| L006 | composition 109 | chemistry rules | ET/raw | cu_o=ET/raw; other=ET/log1p | vs A05: other → ET/log1p; test eligible improvement |
| L007 | composition 109 | chemistry rules | ET/raw | cu_o=ET/raw; other=HGB/raw | vs A05: other → HGB/raw; test eligible improvement |
| L008 | composition 109 | chemistry rules | ET/raw | cu_o=HGB/raw; other=ET/raw | vs A05: cu_o → HGB/raw; test eligible improvement |
| L009 | composition 109 | chemistry rules | ET/raw | cu_o=HGB/log1p; other=ET/raw | vs L008: cu_o → HGB/log1p; test eligible improvement |
| L010 | composition 109 | chemistry rules | ET/raw | cu_o=ET/raw; fe_anion=ET/log1p; other=ET/raw | vs A05: fe_anion → ET/log1p; test eligible improvement |
| L011 | composition 109 | chemistry rules | ET/raw | cu_o=ET/raw; fe_anion=HGB/log1p; other=ET/raw | vs L010: fe_anion → HGB/log1p; test eligible improvement |
| L012 | composition 109 | KMeans 3 | ET/raw | cluster0=ET/raw; cluster1=ET/raw; cluster2=ET/raw | vs G01: routing → KMeans 3; cluster0 → ET/raw; cluster1 → ET/raw; cluster2 → ET/raw; test eligible improvement |
| L013 | composition 109 | KMeans 3 | ET/raw | cluster2=ET/raw | vs L012: cluster0 → global fallback; cluster1 → global fallback; test eligible improvement |
| L014 | composition 109 | KMeans 3 | ET/raw | cluster0=ET/raw | vs L012: cluster1 → global fallback; cluster2 → global fallback; test eligible improvement |
| L015 | composition 109 | KMeans 3 | ET/raw | cluster1=ET/raw | vs L012: cluster0 → global fallback; cluster2 → global fallback; test eligible improvement |
| L016 | composition 109 | KMeans 3 | ET/raw | cluster1=HGB/raw | vs L015: cluster1 → HGB/raw; test eligible improvement |
| L017 | composition 109 | KMeans 3 | ET/raw | cluster0=HGB/raw | vs L014: cluster0 → HGB/raw; test eligible improvement |
| L018 | composition 109 | KMeans 3 | ET/raw | cluster2=HGB/raw | vs L013: cluster2 → HGB/raw; test eligible improvement |
| L019 | composition 109 | KMeans 3 | ET/raw | cluster2=ET/log1p | vs L013: cluster2 → ET/log1p; test eligible improvement |
| L020 | composition 109 | chemistry rules | HGB/raw | cu_o=ET/raw; other=HGB/raw | vs L007: global → HGB/raw; test eligible improvement |
| L021 | composition 109 | chemistry rules | ET/raw | cu_o=ET/raw; fe_anion=ET/log1p; other=HGB/raw | vs L007: fe_anion → ET/log1p; test eligible improvement |
| L022 | composition 109 | chemistry rules | ET/log1p | cu_o=ET/raw; other=HGB/raw | vs L021: global → ET/log1p; fe_anion → global fallback; test eligible improvement |

## Evidence and use

The [previous two-cycle report](../superconductivity-self-loop-2026-10-02/README.md) and frozen V2 experiment remain unchanged. [Lineage](evidence/lineage.json) identifies the preserved parent, inherited counters, policy, and hashes. The [state export](evidence/status.json) contains cycle history and budgets.

Use the prepared V2 scientific environment and authenticated Codex CLI. For a local continuation already created by `fork_run.py`:

```sh
python controller.py resume --run-dir ~/tc-self-loop/runs/continuation-20 --source-dir ../superconductivity-agent-2026-10-02
python controller.py status --run-dir ~/tc-self-loop/runs/continuation-20
python controller.py stop --run-dir ~/tc-self-loop/runs/continuation-20
```

`resume` does not reset counters. Unknown outcomes of interrupted model requests remain inspectable instead of being blindly resubmitted. Publication exports are evidence, not a substitute for the full resumable runtime.

The [44 program tests](verification.json) exercise controller, runtime, continuation, fork, and adapter behavior with mocked model decisions and numerical experiments. The [final independent run audit](run_audit.json) separately recomputes saved training OOF metrics, replays events, and checks model receipts, specifications, and hashes.

Final completion requires at least 20 additional successful unique cycles and 22 in total, a `minimum_completed_experiments_reached` stop, and no pending model call, proposal, result, or numerical work. The final audit must report both `checks_passed: true` and `final_completion_verified: true`. Recheck the publication package with:

```sh
python audit_run.py --run-dir evidence --output audit_check.json
```

Regenerate the report:

```sh
python build_report.py --run-dir ~/tc-self-loop/runs/continuation-20
```

Generated from a read-only state snapshot; canonical state JSON SHA256: `04c9fb4a3c2246f7d1610c8b3268b88d2cef1b4c6cb8addc70f0592d4eeab75f`.

UTC: `2026-10-05T15:23:20.208615+00:00`.
