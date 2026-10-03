# Persistent superconductivity research agent

This controller runs an autonomous sequence of proposal, numerical experiment, reflection, and revision. A model chooses each next experiment from measured feedback; the controller persists memory and starts the next cycle without a human continuation prompt. See the [Chinese advisor report and workflow](README_zh.md).

The current deliverable is the persistent research loop. Its predictive benefit has not been established by this implementation. This work continues development on previously observed training folds and leaves the frozen V2 evaluation unchanged.

## Data and decisions

The controller imports allowlisted evidence from the adjacent [V2 experiment](../superconductivity-agent-2026-10-02/REPORT.md): 3,764 training records, 1,117 linked-identity groups, fixed three-fold assignments, predictor schema, evaluation code, and completed training OOF candidate results. Files and candidate predictions are checked against hashes and training identities. Validation inputs, validation labels, and final evaluation results are excluded from the isolated workbench.

The decision menu contains composition features or composition plus 12 repaired structural features; Extra Trees or histogram gradient boosting; raw or `log1p` targets; global, chemistry-rule, or three-cluster KMeans routing; and optional route experts. Estimator hyperparameters, folds, and metrics remain fixed. The agent does not generate arbitrary executable code.

The initial eligible incumbent is A05, with weighted training OOF MAE **7.752598771 K** and positive-Tc MAE **8.505079847 K**. G01 fixes the positive-Tc guard at **8.832165508 K**. A new candidate updates the incumbent only when it passes that guard and improves overall MAE by at least the configured tolerance. Cached duplicate proposals spend an attempt and do not count as new improvements.

## Requirements and usage

Use the scientific Python environment for the V2 experiment, with `numpy`, `pandas`, `scikit-learn`, `scipy`, `joblib`, `threadpoolctl`, and the upstream structure-processing dependency `pymatgen`. The loop consumes prepared features; it does not regenerate crystal descriptors. Model decisions require an installed, authenticated Codex CLI supporting the flags and structured-output schema used in `llm_client.py`; the implementation was developed with CLI `0.160.0`. Default model: `gpt-5.6-sol`.

Run these commands from this directory. The source path assumes this folder is published beside `superconductivity-agent-2026-10-02`. Override it for a different checkout layout. Keep the runtime directory on a local drive outside cloud-synced folders.

```sh
python controller.py run --source-dir ../superconductivity-agent-2026-10-02 --run-dir ~/tc-self-loop/runs/example
python controller.py status --run-dir ~/tc-self-loop/runs/example
python controller.py stop --run-dir ~/tc-self-loop/runs/example
python controller.py resume --source-dir ../superconductivity-agent-2026-10-02 --run-dir ~/tc-self-loop/runs/example
```

For a deliberately small integration run:

```sh
python controller.py run --source-dir ../superconductivity-agent-2026-10-02 --run-dir ~/tc-self-loop/runs/two-cycle-demo --max-experiments 2 --max-llm-calls 6 --max-seconds 1200 --patience 4
```

`run` requires a fresh runtime directory. `resume` retains the original configuration, cumulative counters, phase, and memory. A paused run can continue after its stop marker is cleared by `resume`. An unresolved model-call outcome still requires artifact inspection; resuming does not blindly repeat a potentially completed request. Budget, stagnation, or agent-directed terminal stops remain terminal. Use a new run directory for a separately budgeted continuation.

## Loop and budgets

The state machine advances through `propose`, `execute`, and `reflect`. The next proposal receives the incumbent, fixed guard, available budget, known specifications, recent cycles, and previous reflection. Reflections receive actual OOF metrics, subgroup results, and training counterexamples. The model states a hypothesis, falsification criterion, revision parent, and action; code enforces admissibility and numerical selection independently.

| Setting | Default | Startup option |
| --- | ---: | --- |
| Experiment attempts | 12 | `--max-experiments` |
| Model calls | 30 | `--max-llm-calls` |
| Cumulative active child-process seconds | 3,600 | `--max-seconds` |
| Consecutive attempts without an eligible improvement | 4 | `--patience` |
| Minimum eligible MAE gain | 0.01 K | `--min-improvement-K` |
| Decision model | `gpt-5.6-sol` | `--model` |

Each proposal and reflection uses one model call. Failed or duplicate attempts consume the corresponding budget and increase stagnation. Per-call and per-worker limits are 240 seconds. Time accounting covers managed child processes, not every second of controller preparation or idle time. The model can also stop with a reason. `stop` requests cancellation of the current managed child and persists a paused state.

## Code and durable evidence

| File or runtime artifact | Purpose |
| --- | --- |
| `controller.py` | State machine, cumulative budgets, deterministic guard, incumbent, stopping |
| `llm_client.py` | Structured proposal/reflection through the existing Codex login |
| `worker.py` and `workbench_adapter.py` | Isolated training evaluation, cache, provenance and OOF verification |
| `runtime.py` and `child_runner.py` | SQLite state, atomic JSON exports, process cancellation and exclusive run ownership |
| `memory.sqlite` | Authoritative persisted state and append-only event history |
| `status.json` and `memory_export.json` | Readable state and event exports |
| `calls/` | Frozen model context, schema, response, receipt and normalized decision |
| `cycles/` | Experiment request and observed outcome |
| `workbench/candidates/` | Configuration, measured metrics and OOF predictions |

Completed decisions and experiment evidence are reused during recovery. Exclusive controller and child locks prevent concurrent owners from duplicating work in the same run. Source, fold, predictor and evidence hashes are checked before reuse. A partially executed fit may need to be rerun; an interrupted model request with an unknown completion outcome pauses for inspection. The implementation does not promise exactly-once external billing or recovery of incomplete fitting work.

## Run evidence

Two consecutive real cycles completed with `gpt-5.6-sol`: proposal, fit, reflection, next proposal from that feedback, second fit and reflection. No human continuation prompt was needed between cycles.

| Candidate | Weighted training OOF MAE | Positive-Tc MAE | New regressor fits | Incumbent update |
| --- | ---: | ---: | ---: | --- |
| Starting A05 | 7.752599 K | 8.505080 K | 0 | Initial incumbent |
| L001 | 7.793528 K | 8.558194 K | 9 | No |
| L002 | 7.801821 K | 8.544867 K | 12 | No |

L001 changed the Fe-anion fallback to a global raw-target HGB. Its unfavorable result motivated L002, which used a route-specific raw-target HGB expert while restoring the other A05 settings. Both passed the fixed positive-Tc guard but worsened overall MAE. A05 remains the incumbent. This demonstrates loop operation, not improved prediction or generalization.

The demonstration intentionally allowed two experiments (the default is 12), six model-call reservations and 1,200 active seconds. It completed four real model calls and 21 regressor fits in 223.108 managed child-process seconds. Five call reservations were consumed because a local CLI configuration rejection before remote submission was retained in the journal and then repaired. A separate earlier missing-executable startup attempt also never started a remote model. The final agent stop coincided with the demonstration's two-experiment budget.

31 local behavior and data tests passed. Inspect the [run summary](evidence/run_summary.json), [state and cycles](evidence/status.json), [first reflection](evidence/calls/003_reflect/decision.json), [feedback-driven next proposal](evidence/calls/004_propose/decision.json) and [test record](verification.json) and [independent evidence verification](demo_verification.json). Run `python verify_demo.py` to verify the exported demo evidence and independently recompute MAE.

Audit correction: the final raw model reflection describes the fixed menu as exhausted. That is unsupported: only the two-experiment run budget was exhausted, not the action space. The original response is preserved, but that wording is not adopted as a scientific conclusion. Absolute runtime/source paths are redacted in text exports; numerical evidence and decisions are retained. Fitted model binaries, the runtime database and local process command records are omitted.

All subsequent OOF improvements remain adaptive development results. They require a separately designed evaluation before any claim of improved generalization or scientific discovery.
