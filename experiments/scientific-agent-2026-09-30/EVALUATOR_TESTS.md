# Numerical evaluator tests

Run with the existing scientific Python environment:

```powershell
work/pris_clean_env/Scripts/python.exe -B outputs/pris_scientific_agent_2026-09-30/test_evaluator.py
```

All four synthetic suites passed before any real candidate evaluation:

1. Train-only imputation and standardization, missing indicators, rejection of all-missing/infinite inputs, and affine-duplicate removal.
2. Independent prediction reconstruction from saved standardized coefficients for formation Huber regression and hull logistic regression.
3. Classification confusion counts/log loss and paired chemical-system bootstrap on an analytically known constant loss difference.
4. End-to-end synthetic prepare, candidate fitting, ID reordering, validation-only counterexamples, mandatory completed-call audit before selection freeze, blocked post-freeze development, explicit final-test authorization, prediction freezing before label parsing, and refusal of repeated test access.

The test fixtures are generated independently in a temporary directory under this experiment folder and removed afterward. They do not load the real sealed test labels. Real baseline preparation used 2,164 training and 715 development-validation rows; no real test evaluation was performed by these tests.

The numerical procedure fixes Huber alpha=1/epsilon=1.35, logistic C=1, and a separate raw-input HGB reference. Every candidate uses the same development IDs. Original 30 inputs must be finite; a newly proposed descriptor with no finite training value is rejected. Partial missing new descriptors use training medians and training-missing indicators. All fitted preprocessing is saved for replay. Adaptive validation results and counterexamples are not independent confirmation.

The MCP server must expose only prepare/evaluate_candidate/get_counterexamples. Selection freeze and final_test are root-only operations. The server owns the overall six-attempt budget (including code/parser failures) and must serialize mutation tools; the evaluator adds a directory-based budget safeguard.
