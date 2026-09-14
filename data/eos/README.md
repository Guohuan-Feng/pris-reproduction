# E4 numerical replay inputs

[English](README.md) | [简体中文](README_zh.md)

Original work: Zhilong Song and Lixue Cheng, *Autonomous discovery of new structure-plausibility laws for explainable and rapid crystal diagnosis and screening*, arXiv:2609.01209v1, https://arxiv.org/abs/2609.01209.

Repository: https://github.com/AI4QC/PRIS
Commit: `34e6c86c083759dc1ee594ae22238ea9b5ebd8f4`

- `stage_b_collected.json`: verbatim copy of `dft/E4_design/stage_b/collected.json`.
- `published_bulk_moduli.json`: verbatim copy of `dft/E4_design/bulk_moduli.json`.
- `manifest.json`: source paths and SHA256 hashes.

These are published collected computational outputs and fitted reference results. This bundle contains no VASP binaries or PAW potential content. The upstream code/manuscript licence is included as `UPSTREAM_LICENSE` in this directory. Third-party structural data licences are not changed by this bundle.

Run from the reproduction bundle root after installing Python 3.10+, numpy and scipy:

```text
python scripts/refit_eos.py
```

Default outputs are `results/eos/per_candidate.csv`, `energy_volume_points.csv` and `summary.json`. Inputs and output paths may be overridden with `--input-dir` and `--output-dir`.

The script independently refits the same third-order Birch–Murnaghan equation using centered energy and SciPy least_squares. It retains the source's complete/unconverged statuses, uses final static energies and unrounded final-cell volumes, and requires at least four volume points. It does not import or run upstream analysis scripts, train models, or run DFT. Floating-point optimizer differences are measured against the published fitted moduli and recorded in the output.

The E4 candidates intentionally oversample large UMA-predicted moduli. The measured fractions apply to these selected candidates. The original 400 GPa threshold and the rescaled threshold calculated as 400 times the median DFT/UMA ratio are distinct; both are reported.
