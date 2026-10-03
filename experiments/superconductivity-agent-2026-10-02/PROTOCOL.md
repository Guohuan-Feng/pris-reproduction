# Superconductivity Agent modeling pilot 2026 10 02

This bounded development experiment follows the 2 October meeting. The Agent may choose model inputs, the regression estimator and target transform, and routing to composition-specific or training-fitted cluster specialists. It does not author new features. The repaired first-round descriptors are fixed before any model scores. The experiment tests this concrete expansion of Agent control, not the novelty or general causal value of agents.

## Data and information boundary

Use the original 3,764 training records and their 1,117 strict chemical-system/MP-parent connected components for three-fold shuffled GroupKFold with seed 20261002. These exact folds are fixed before scores. The tools return pooled out-of-fold training feedback only. Every predictor transformation, clusterer and estimator is fitted on that fold's fitting rows; no fitting uses its feedback rows. IDs, formula, upstream class, group, parent, weights, split and targets are not predictors or routing inputs. Formula can appear in diagnostic counterexamples only.

After both search arms are frozen, fit each eligible pipeline on the original training cohort and evaluate the original 869 validation records once this round. This is a held-aside DEVELOPMENT comparison: the full public cohort and original validation have already influenced earlier work. It cannot be described as fresh independent validation, even though it is unavailable to this round's scientific tools. The original 1,140 retrospective target records are not opened or used this round. Their label-free structures may be precomputed in the repair audit, with split metadata only.

Preserve the original inverse canonical-composition multiplicity weights. Do not recompute weights using feedback targets. Primary score is pooled weighted MAE in K. Report RMSE, MSLE, recorded-zero MAE, positive-Tc MAE, Tc>=40K MAE and signed prediction bias, subgroup counts and component counts. These diagnostic thresholds are not new experimental labels or universal evidence of nonsuperconductivity.

## Fixed input repair

Retain 109 original composition predictors. Fixed repaired inputs optionally add the 12 E04-derived descriptors. Normalize every positive occupancy sum by that sum; zero-weight moments become missing. Replace Cartesian-diagonal anisotropy with `(3 tr(Q^2)-1)/2`, Q the full occupation-weighted unit-direction tensor. Preserve mixed species, absolute occupancies and complete periodic neighbor images. Audit rotation, origin translation, permutation, equivalent supercells and low-occupancy boundaries before fitting.

The repair includes a semantic change: undefined short-neighborhood moments previously encoded as zero now become missing. All improvements from the repaired block include that change; they cannot be attributed solely to anisotropy or normalization. The 11-descriptor ablation removes only invariant anisotropy from the same repaired block. Finite audit cases do not prove correctness on all possible structures. The original first-round outputs remain unchanged.

## Shared menu and fixed estimators

Inputs: `composition` (109) or `composition_repaired` (109+12). Models: `extra_trees` or `hist_gradient_boosting`. Target transforms: raw Tc or log1p Tc, available separately for the global estimator and each specialist. Routing: global, `chemistry`, or `kmeans3`. A specialist configuration is explicit; unspecified or insufficiently populated routes use the global estimator fitted on all fitting rows.

ExtraTrees: 160 estimators, min_samples_leaf=2, max_features=1.0 (all feature columns; not integer one), n_jobs=1, seed 20261002. HistGradientBoosting: max_iter=160, max_leaf_nodes=15, min_samples_leaf=20, learning_rate=.08, l2_regularization=1, early_stopping=False, seed 20261002. Both use squared-error fitting with original weights. All numerical thread limits are one. These choices are fixed, not claimed optimal. Clip raw predictions at zero; inverse log predictions with expm1(max(predicted_log,0)).

Composition routing is mutually exclusive, in this priority order: Cu and O present (`cu_o`); otherwise Fe and any P, As, S, Se or Te present (`fe_anion`); otherwise `other`. Presence is a fraction greater than 1e-12. These are observed composition templates, not confirmed physical families. A specialist requires at least 80 fitting rows and 12 strict groups, determined without feedback labels.

KMeans has three clusters, fixed seed and 10 initializations. Fit imputation and standardization on fitting-row composition inputs only, independently of the model's feature block. Cluster fitting is unweighted, as an explicitly fixed geometry-of-inputs choice; estimator fitting and all scores remain weighted. Sort fitted centroids by the comp_Z_mean coordinate, tie-breaking by original cluster index. Cluster names are ordinal and may represent different populations across folds; they do not establish material families.

## References and bounded searches

Before the Agent, compute eight global references: two shared input blocks times two estimators times two target transforms. Both search arms retain the single best global by overall OOF weighted MAE as their fallback and guard anchor. Four additional fixed diagnostics sit outside the menu: composition+11 repaired descriptors with ExtraTrees raw/log, and composition+28 conventional structure features with ExtraTrees raw/log. Report them; do not call the shared-menu winner the strongest global overall if an outside-menu reference does better.

One GPT scientific session uses the existing Codex account, with at most 18 processed tool calls, five attempted pipelines and 900 seconds. Tools: describe_data, run_strategy, counterexamples, compare_strategies and record_conclusion. Prefer three to five informative routed strategies, including revision after error feedback. Failed and duplicate attempts consume the budget. No shell, web, credentials, external services or additional agents are available to that scientific session. The outer collaborator and numerical workers implement the protocol; they are not additional search sessions.

Precommit five seeded automated configurations before the Agent, from the same input/estimator/target/routing menu. Their routing sequence is chemistry, kmeans3, chemistry, kmeans3, chemistry, avoiding redundant global attempts because all eight globals are already known. Inputs, global configuration and all route-specialist configurations are sampled by a recorded seeded generator. After the Agent finishes, run only the prefix matching its total attempted-pipeline count. This controls attempted configurations, not actual fit counts, runtime, priors or strategy distribution. Record all fits and timings. This is one limited randomized search, not exhaustive AutoML or a general estimate of the value of agency.

## Selection and final development comparison

The guard anchor is the SAME single shared-menu global winner selected by overall OOF MAE. A candidate is eligible only when its positive-Tc pooled OOF MAE is no worse than that winner's positive-Tc MAE. Select minimum overall OOF weighted MAE among eligible candidates and the shared global fallback. Ties use lower fit count then candidate ID. The rule is identical for Agent and automated arms. The fallback means no demonstrated gain when no new candidate qualifies or improves it. The professor's spoken 10 percent example is not an acceptance threshold.

Freeze protocol, source hashes, candidate specifications, both selections and the complete Agent record before held-aside validation access. Save final predictions before opening held-aside targets. No refit on validation, post-validation reranking, target-informed routing or second search is allowed. Report fixed comparisons even when the Agent selects the fallback.

Paired component bootstrap intervals (1,000 draws) are conditional on fitted and selected models on this previously observed development cohort. They exclude training/search uncertainty and prior data inspection. Report positive and high-Tc tradeoffs and route fallbacks. The next decision is whether the concrete routing intervention merits more evidence, or whether to design a separate classification/anomaly verification task. No claim of new superconductors, error labels, synthesis, DFT, phonons or established mechanisms follows from this pilot.
