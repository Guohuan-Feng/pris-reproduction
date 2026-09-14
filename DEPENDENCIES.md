# Dependency validation and input availability

English | [中文](DEPENDENCIES_zh.md)

Assessment date: September 14, 2026. Upstream reference: [AI4QC/PRIS](https://github.com/AI4QC/PRIS), commit `34e6c86c083759dc1ee594ae22238ea9b5ebd8f4`.

## 1. Validated software environment

The portable six-step reproduction was installed and executed in a fresh Python 3.12.14 virtual environment on Windows AMD64. System site packages were disabled; `PYTHONPATH` and `PYTHONHOME` were removed from child-process environments, and the user site was disabled. Execution used a separate copy of the reproduction bundle. These controls exclude dependence on the original working environment's installed scientific packages.

All **48 pinned distributions** in `requirements-lock.txt` installed successfully. `pip check` returned **“No broken requirements found.”** The automatic entry point, `bootstrap.py`, completed with exit code 0, and all six scientific/test steps completed with exit code 0. The regenerated E3 metric table, per-candidate EOS fit table, and per-structure symmetry table were byte-identical to the archived results.

The environment checker verifies exact package versions, SHA256 hashes for 20 vendored source files, and 703 archived input/reference files: 180 E3 structures, 520 E4 structures, and three EOS/reference-license files. The included reference index and required data manifests are also checked for availability. This check concerns the bundled workflow; it does not establish completeness of the original upstream research environment.

Evidence: [environment validation](results/environment/clean_environment_validation.json), [dependency and integrity check](results/environment/dependency_check.json), and [bootstrap execution log](results/environment/bootstrap.log). Complete local directory prefixes in the published log are replaced with placeholders; numerical output is unchanged.

## 2. Installation and preflight entry points

```text
python bootstrap.py --workers 4
```

The entry point creates `.venv`, installs the pinned packages, checks dependency consistency and archived input integrity, and runs the reproduction. `--install-only` performs environment preparation without the scientific rerun. `--env-dir PATH` selects another virtual environment. Python 3.12 is required by the validated dependency set.

The preflight checker can also examine an existing full upstream checkout:

```text
python scripts/check_environment.py --upstream /path/to/PRIS --json-out dependency_check.json
```

`bundled_workflow_ready` refers only to the portable reproduction. Missing optional upstream files are reported separately. A complete upstream checkout is not required for the bundled six-step workflow.

## 3. Retrieval assessment for missing upstream inputs

The retrieval audit examined all eight public main-branch commits, the `english-only` branch, GitHub release and tag inventories, and the official [arXiv source archive](https://arxiv.org/src/2609.01209v1). Additional searches examined the public AI4QC Hugging Face inventory and Zenodo records associated with the paper identifier/title. The audit identified no publicly retrievable copy of the missing full feature store or score shards in these sources.

| Missing item | Category | Consequence | Retrieval result |
|---|---|---|---|
| `src/build_bonds.py` | Upstream source code | One historical split-discipline regression test cannot load its target source | No file history on either public branch; absent from the inspected initial public tree |
| `outputs/20260815_threshold_transfer/transfer.json` | Derived experimental data | Complete regeneration of Fig. 2 requires exact threshold-transfer values and verdict-flip rates | No path-history commits on either branch; absent from the arXiv source archive |
| `PRIS_FEATURES/provenance.parquet` and associated feature/structure stores | Original research inputs | The 5,297/3,612 held-out benchmark and 440-parent deployment benchmark cannot be independently reconstructed | Excluded from the public repository; no alternative complete distribution located |
| Full 1,081-candidate inverse-design scores and structure archive | Original generated cohort | Full-pool queue reduction cannot be recomputed from the selected E4 cohort | Only the released selected cohort and aggregates were available |
| Positive–unlabelled score shards | Derived model outputs | Complete recomputation of Fig. 4 and several supplementary analyses remains unavailable | Explicitly excluded by the upstream release documentation |
| VASP executable and licensed potentials | External licensed software/data | New first-principles calculations require an independently provisioned VASP environment | Not distributed in the public repository or this bundle |

The source archive contains 260 relaxed CIFs, an index, and a summary. Their text matches the already archived supplementary data after CRLF/LF normalization; the archive does not supply the missing full datasets. File manifests record the bytes preserved from the pinned checkout. Textual equality across archives does not imply identical archive or Git-blob hashes when line endings differ.

The [upstream README](https://github.com/AI4QC/PRIS/blob/34e6c86c083759dc1ee594ae22238ea9b5ebd8f4/README.md) explicitly excludes the feature store and PU score shards. [Upstream pull request #1](https://github.com/AI4QC/PRIS/pull/1) also documents unavailable research inputs and historical test targets. Exact retrieval endpoints, checked inventories, and archive comparisons are recorded in [the public-input audit](results/environment/public_input_audit.json).

## 4. Interpretation

The portable reproduction's software dependencies are installed, version-locked, and independently validated. The remaining limitations arise primarily from unpublished research inputs, unavailable upstream source, and separately licensed computation. Installing additional Python libraries cannot reconstruct those inputs. No substitute `build_bonds.py`, approximate transfer table, or rendered-figure extraction was introduced as an authentic upstream artifact.

The original symbolic-regression and tree-search stack is outside the validated six-step workflow. PySR/Julia or solver installation would constitute additional environment preparation, not recovery of the excluded feature stores or reproduction of the sealed discovery process. Any future extension requires its own input provenance and validation.
