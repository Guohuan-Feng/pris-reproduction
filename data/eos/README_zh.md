# E4 数值复算输入

[English](README.md) | [简体中文](README_zh.md)

原始研究：Zhilong Song 和 Lixue Cheng，*Autonomous discovery of new structure-plausibility laws for explainable and rapid crystal diagnosis and screening*，arXiv:2609.01209v1，[论文页面](https://arxiv.org/abs/2609.01209)。

仓库：[AI4QC/PRIS](https://github.com/AI4QC/PRIS)
Commit：`34e6c86c083759dc1ee594ae22238ea9b5ebd8f4`

- `stage_b_collected.json`：原样复制的 `dft/E4_design/stage_b/collected.json`。
- `published_bulk_moduli.json`：原样复制的 `dft/E4_design/bulk_moduli.json`。
- `manifest.json`：来源路径与 SHA256 哈希。

这些文件是作者已公开的计算输出和拟合参考结果。复现包不包含 VASP 二进制文件或 PAW 势内容。本目录的 `UPSTREAM_LICENSE` 保留上游代码及论文许可证；本包不改变第三方结构数据的许可证。

安装 Python 3.10+、numpy 和 scipy 后，在复现包根目录运行：

```text
python scripts/refit_eos.py
```

默认输出为 `results/eos/per_candidate.csv`、`energy_volume_points.csv` 和 `summary.json`。可通过 `--input-dir` 和 `--output-dir` 指定输入及输出目录。

脚本独立拟合同一个三阶 Birch–Murnaghan 状态方程，对能量作中心化处理，并使用 SciPy `least_squares`。它沿用来源数据中 complete/unconverged 两种状态的纳入规则，使用最终静态能量及未四舍五入的最终晶胞体积，每次拟合至少需要四个体积点。脚本不导入或运行上游分析脚本，不训练模型，也不运行 DFT。与作者已发布体模量之间的浮点优化差异会被测量并记录。

E4 候选集合有意过采样 UMA 预测体模量较大的结构，测得比例只适用于这些已选择候选。原始 400 GPa 阈值和按 `400 × DFT/UMA 比值中位数` 计算的重标度阈值是不同的量；本复算同时报告两者。
