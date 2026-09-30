# Tool-using scientific-agent pilot — protocol fixed before discovery

The purpose is to implement and observe a GPT agent that inspects development
data, proposes mechanistic hypotheses, authors new numerical descriptors from
crystal structures, executes experiments, requests counterexamples, and revises
its hypotheses. This extends our earlier two tool-free template calls. It is
inspired by PRIS; it is not a replication of its full discovery campaign.

## Data and boundaries

Use 3,600 public Materials Project records with formation energies and energy
above hull from the Matbench Discovery public MP snapshot. Exclude chemical
systems used in earlier MP experiments, the V4/V5 cohort and available prior
3DSC parent systems. Select by a fixed identity hash, restrict ordered structures
to at most 60 sites, and require complete original 30 inputs before splitting.
No target-value filtering. Split chemical systems 60/20/20 into train,
validation and test. The validation set is adaptive development data.

The source structures are DFT-relaxed. The tasks are formation energy regression
(eV/atom; lower MAE is better) and on-hull classification (energy above hull
<=1e-8 eV/atom; lower clipped log loss is better). Neither task measures
superconductivity, experimental synthesizability or pre-DFT screening savings.

Discovery tools load only development structures and labels. Test structures and
labels have no discovery tool endpoint. Disable Codex general shell, web, apps,
plugins, memory, subagent and computer tools in the isolated CLI invocation;
audit actual events. The evaluator is a trusted process with access to files.
This application-level boundary is not a hostile-code OS security guarantee.
Public dataset exposure in model pretraining cannot be ruled out.

## Scientific actions and budget

One continuous Codex CLI discovery run, requested GPT-5.6-sol with medium
reasoning and existing ChatGPT login. No professor API key is used. At most
24 processed scientific tool invocations and 6 descriptor experiment attempts, including
failed code. At most 12 scalar descriptors per experiment, 180 seconds per
descriptor worker and 900 seconds for the entire discovery run. Transport
retries inside the CLI may occur; no automated second scientific run. These
are execution limits, not a monetary spending guarantee. Calls rejected after
the processed-call budget are logged separately; the worker has no memory cap.

Tools: describe_data, inspect_records, run_experiment, counterexamples,
compare_experiments, record_conclusion. GPT writes its own pure numerical
`featurize(s)` function. A bounded Python AST and numerical API permit loops,
array operations, distances, site chemistry and periodic neighbor statistics.
There are no imports, file/network operations or target inputs to the function.
Each hypothesis must name its mechanism, expected benefit, scope, falsification
criterion and revision parent. Failed attempts are retained.

Periodic neighbors include image multiplicity within a fixed 6 Angstrom cutoff.
Pair distance matrices alone do not give full coordination counts. Distances
and cell geometry come from the same relaxed structure for all arms.

## Evaluation

Baseline: all 30 earlier composition/global-geometry features. Fixed Huber
(alpha=1,epsilon=1.35) predicts formation energy; fixed logistic regression
(C=1) predicts on-hull probability. Each candidate adds its descriptors to all
30 inputs with the same estimators. Use train-only standardization. New columns
with partial missingness get train-median imputation and a train-defined
missingness indicator; reject all-missing columns. All arms use identical rows.

A fixed histogram gradient boosting model using the same 30 raw features is
an additional nonlinear control. There is no claim of GPT-specific superiority
over matched descriptor search, because such a control is not included here.

Select the best validation candidate separately for each task, with the raw
baseline available as a no-change option. Freeze code, selected models and the
complete agent transcript before computing test descriptor values and reading
test labels. No refitting on validation and no test-driven revisions. Evaluate
the single frozen selection per task against raw and HGB on all test rows.
Use 1,000 paired chemical-system bootstrap resamples for loss differences.
Intervals are conditional on this cohort/search and do not cover all adaptive
researcher choices or repeated datasets. Do not report discarded candidates'
test performance. A negative result is an admissible outcome.

## Evidence

Save source/data hashes, exact CLI command and model request, every tool's
arguments and response, code for each descriptor attempt, worker errors,
numerical development results, frozen selections, one final test and observed
token-usage events. Describe only capabilities observed in actual tool calls.
Reports must be bilingual and distinguish predictive associations from laws.

Sources: [PRIS](https://arxiv.org/html/2609.01209v1),
[public MP snapshot](https://doi.org/10.6084/m9.figshare.22715158.v38),
[Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
