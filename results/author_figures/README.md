# Local reruns of the authors' figures

[English](README.md) | [简体中文](README_zh.md)

Source: AI4QC/PRIS, commit `34e6c86c083759dc1ee594ae22238ea9b5ebd8f4`. The runner is included as `scripts/replot_author_figures.py`. The authors' source code, input aggregates, and thresholds were unchanged; only the output directory was redirected, and specific plotting functions were invoked.

| Paper figure | Status and outputs | Scope of this rerun |
|---|---|---|
| Fig. 1 | Success; `fig1_agentic_law_learning.png/pdf/svg` | Replots published investigation-history and rule-space aggregates. Autonomous discovery was not rerun. |
| Fig. 2 | Failed; `fig2_run.log` | The upstream checkout lacks `outputs/20260815_threshold_transfer/transfer.json`. Missing values were not invented, and the published figure was not substituted for a new result. |
| Fig. 3 | Success; `fig3_anatomy.png/pdf` | Recomputes the MgAl2O4 example constructed by the authors' script and five fixed-seed perturbations. Other panels use the authors' aggregates and published E1 DFT energies. |
| Fig. 5 | Success; the author script retains the historical output name `fig6_deployment.png/pdf/svg` | Replots published generator, MLIP, and E2/E3 DFT results. No generation model, MLIP, or DFT calculation was run. |

Newly computed Fig. 3 values are stored in `fig3_anatomy_readings.json` and `fig3_structure_recompute.csv`. The crystal is an author-constructed illustration, not an independently sampled experimental structure. The S2 cation-exchange example triggers no rule and is correctly shown as passing; the five examples must not be described as all detected.

Each PNG was visually reviewed and opened successfully, with no blank panels or obvious clipping. `manifest.json` records exit codes, execution times, source and output hashes, and the level of reproduction. Standard output and errors are preserved in the corresponding logs.

The runner requires a full upstream checkout at the recorded commit. From the reproduction bundle root, run:

```text
python -X utf8 scripts/replot_author_figures.py --repo /path/to/PRIS --only fig1 fig3 fig5
```

Including `fig2` in `--only` reproduces the documented missing-input failure unless the upstream input file has been supplied.
