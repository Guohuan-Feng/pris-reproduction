# Superconductivity Agent V2 protocol review

This review covers a bounded follow-up to the 2 October meeting: allow the Agent to choose a complete regression pipeline, including the input, target transform, estimator, and composition-based specialist routing. The concrete protocol is scientifically defensible as a development experiment. It cannot provide fresh independent confirmation on this historically inspected cohort.

## Data and evaluation separation

Use only the original 3,764 training rows, in their 1,117 strict chemical-system and parent connected components, for three-fold GroupKFold feedback. Record the exact fold assignments before search. Every fold must have no shared material ID, strict group, chemical system, parent, or canonical composition between its fitting and feedback rows.

The original 869 validation rows are held aside from this round's tool feedback. Freeze both search arms and all eligible specifications before fitting on the original training rows and evaluating these validation rows once. This is a held-aside development comparison, because the validation cohort and some descriptor choices have already influenced earlier work. Do not open the historical 1,140-row target file in this round.

Fixed weighting remains inverse canonical-composition multiplicity from the published snapshot. Report weighted MAE in kelvin, weighted positive-Tc MAE, reported-zero MAE, high-Tc MAE and bias, RMSE, and MSLE. Report subgroup row and strict-group counts. Reported zero is a dataset label; it does not establish that a material cannot superconduct.

## Shared pipeline menu

Both search arms have the same menu: 109 composition inputs or 109 composition inputs plus the repaired 12 E04 descriptors; ExtraTrees or HistGradientBoosting; raw Tc or log1p Tc; and no routing, three observed-composition routes, or training-fitted KMeans with three clusters. A routed pipeline specifies the global model and the model and target transform for every specialist.

ExtraTrees uses 160 trees, minimum leaf size 2, and one job. HistGradientBoosting uses 160 iterations, 15 maximum leaf nodes, minimum leaf size 20, learning rate 0.08, L2 regularization 1, and early_stopping=False. These are fixed design choices, not claimed optimal hyperparameters. Disable automatic random validation splitting, which would undermine strict grouped fitting.

Fit imputation, dropped-constant decisions, scaling, clustering, global estimators, and every specialist using only each fold's fitting rows. Raw predictions are clipped at zero; log predictions are clipped at zero before expm1. Apply the identical policy to all arms. Never use target-derived class labels, material IDs, parent IDs, source identifiers, or previously computed errors as predictors or routing inputs.

The observed-composition routing order is Cu and O present first; otherwise Fe and at least one of P, As, S, Se, or Te present; otherwise other. Presence is determined by element fractions greater than 1e-12, as fixed in the main protocol. These are composition templates, not validated physical family labels. The training cohort has 712 rows and 66 groups in the Cu/O route, 285 rows and 37 groups in the Fe route, and 2,767 rows and 1,016 groups in other. This read-only count used only original training targets and composition inputs.

For KMeans, use the 109 composition columns with training-only imputation and scaling, a fixed random seed and initialization count, and a recorded weighting policy. Sort fitted cluster identities by the centroid's comp_Z_mean, with a deterministic tie-break. Compute this ordering independently in each fitting fold. The names are ordinal cluster labels, not physical families; they need not denote identical populations across folds. An unseen row is assigned by its fitting-fold scaler and clusterer only.

A specialist is fitted only if that fitting fold's route has at least 80 rows and 12 distinct strict groups. Otherwise predict with the already fitted global model. Apply these thresholds before fitting, without examining that fold's feedback labels. Record route sample sizes, group counts, fallback decisions, and prediction counts.

## Controls and selection

Evaluate all eight global configurations in the shared menu before either search arm. Both arms receive these common results and retain the best global as an eligible fallback. Extra 11-descriptor and 28-structure references may be fixed diagnostics outside the menu; report them, and do not call the menu winner the strongest global model overall if an outside-menu reference performs better.

Precommit the seeded automated candidates before the Agent runs. Use the same permitted specifications and the same number of attempted additional pipelines as the Agent, up to five. Failed and duplicate attempts count toward the respective attempt budget, and their actual computation is recorded. Prefix truncation is acceptable if the Agent makes fewer attempts, provided this rule is fixed before search. All global configurations are already shared, so the automated additional sequence is composition routing, clustering, composition routing, clustering, composition routing. This distribution is deliberately limited to new routed choices; a global Agent attempt remains allowed and consumes an attempt even when it duplicates shared results. Disclose this sampling distribution and call the control limited randomized search rather than exhaustive AutoML.

Define the guard anchor as the single shared-menu global winner selected by minimum pooled OOF weighted MAE. A routed candidate is eligible only when its pooled positive-Tc OOF MAE is no worse than that same winner's positive-Tc OOF MAE. Do not construct an anchor by taking different subgroup minima from different models. Select minimum pooled overall weighted MAE among eligible candidates and the shared global fallback. Use a deterministic tie rule common to both arms. Do not rerank, change the guard, or select models after seeing the held-aside validation results.

Count attempted pipeline evaluations, actual model fits, elapsed fitting time, search-tool calls, LLM usage, and errors separately. Matching candidate attempts does not imply matched computational cost: specialist models require more fits, and LLM inference has additional cost. One Agent run compared with one seeded automated run does not identify a general causal benefit of agency or establish methodological novelty.

## Required verification before final evaluation

Verify every OOF fitting and feedback partition, all data identities and weights, and exact one-time prediction coverage. Verify that every preprocessing and router fit receives only fitting-fold rows. Test negative prediction clipping, raw and log inverse transforms, missing values, absent routes, specialist fallback, and deterministic cluster relabeling with small numerical fixtures. Verify that candidate choice uses only pooled OOF feedback and that validation targets are unavailable through tools.

Complete the descriptor rotation, translation, site permutation, equivalent-cell, and partial-occupancy checks before using repaired descriptors in any estimator. The old E04 directional feature was not rotation invariant, and its small-occupancy denominator floor had an equivalent-cell defect. Preserve the frozen first-round outputs; do not retrofit repaired values into its reported results.

After both specifications are locked, record specification and source hashes and produce one validation prediction table for the fixed comparisons. Paired strict-group bootstrap intervals are conditional on these fitted models and this historically inspected cohort. They exclude training variation, search variation, and the full effect of prior cohort inspection. A narrow interval alone does not repair the lack of independent confirmation.

## Interpretation and next decision

Compare the Agent with the original fixed predictor, the shared-menu global winner, the fixed extra references, and the equal-attempt automated arm. State exactly what the Agent changed, whether it selected specialists or a global fallback, and which subgroups improved or deteriorated. A failed routing hypothesis or negligible benefit is a valid result. If the bounded regression round remains unconvincing, prepare a separate, predeclared classification or anomaly-verification task; do not relabel large residuals as faulty labels or new superconductors.

This protocol responds to the meeting's suggestion to broaden Agent control. The professor's spoken 10 percent example is not a formal success threshold. The analysis must report actual effects and uncertainty rather than inventing an acceptance criterion.
