# V2 numerical input provenance

## Provenance and attribution

The source is [aimat-lab/3DSC](https://github.com/aimat-lab/3DSC), pinned at commit [`2471dd51a298a854cb4f365ebd39e72c7cbf3634`](https://github.com/aimat-lab/3DSC/tree/2471dd51a298a854cb4f365ebd39e72c7cbf3634). The upstream file is `superconductors_3D/data/final/MP/3DSC_MP.csv`, SHA-256 `353b86f9c60505d11a3e25df8312da02ff88fd8e27af05b632dec4739d52eb24`.

The [upstream license statement](https://github.com/aimat-lab/3DSC/blob/2471dd51a298a854cb4f365ebd39e72c7cbf3634/README.md#license) licenses 3DSC MP data under **[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)** and identifies the source SuperCon/Stanev and Materials Project data. This release contains the MP branch only; it contains no ICSD structures. Changes made for this snapshot are the row identifiers, prepared features and structure payloads, strict grouped split, evaluation weights, joined viewer tables, and documentation. These prepared data are released under CC BY 4.0 with upstream attribution. Upstream software has a separate MIT license.

Please acknowledge the original data authors when reusing this snapshot:

- Sommer, T., Willa, R., Schmalian, J. and Friederich, P. *3DSC — A New Dataset of Superconductors Including Crystal Structures*. [arXiv:2212.06071](https://doi.org/10.48550/arXiv.2212.06071) (2022).
- Stanev, V. et al. *Machine learning modeling of superconducting critical temperature*. [npj Computational Materials 4, 29](https://doi.org/10.1038/s41524-018-0085-8) (2018).
- [Materials Project](https://materialsproject.org/) and [SuperCon](https://doi.org/10.48505/nims.3739).

For the preparation and fixed split, also cite this repository by its exact Hugging Face revision and link the GitHub report. Release curator: **Guohuan Feng (`fgh123654`)**.


This V2 package adds fixed three-fold training assignments, repaired occupancy-normalized and invariant-direction descriptors, missing undefined moments, pipeline specifications and prediction evidence. It preserves the original Tc labels and inverse-composition weights. No new experimental labels, measured structures or superconductors are introduced. The data inherit CC BY 4.0 with the upstream attribution above; see UPSTREAM_LICENSE.md. Full 5,773-record structures and original prepared payloads remain at https://huggingface.co/datasets/fgh123654/3dsc-mp-tc-pilot.
