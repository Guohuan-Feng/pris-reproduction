# Published E3 COD cohort

[English](README.md) | [简体中文](README_zh.md)

180 byte-identical published POSCAR inputs: 30 COD experimental parents (P0) and all 150 deliberately damaged variants (S1–S5). No score-based selection. No GNoME structures are included.

Read `manifest.csv` for labels and paths and `manifest.json` for source commit, hashes, selection, and limitations. `upstream_selection.json` preserves the authors’ complete E3 selection, including its separately labeled GNoME entries which are not copied here.

P0 inputs are author-repackaged experimental-source coordinates, **not downloaded original CIFs**. Damaged S1–S5 inputs are synthetic controls. The `TASK.json` files are copied unchanged, so their `kind=experimental` field describes the parent’s provenance and must not be treated as the variant’s ground-truth label.

The DFT preregistration explicitly says these are **discovery-split** parents of at most 16 sites where all five damage operators apply. This selected DFT cross-check cohort permits a bounded run of the published classifier; it does not reproduce the full held-out benchmark or autonomous law discovery.
