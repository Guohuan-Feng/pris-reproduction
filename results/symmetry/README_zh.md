# E4 晶体坐标与 Law 7 结果复算

[English](README.md) | [简体中文](README_zh.md)

**从作者公开的 520 个结构文件重新计算，复现了 260 对晶体的全部公开空间群编号和位点比例。** 逐结构比较没有差异。此处重新做的是对称性分析，DFT 弛豫后的坐标来自作者，未重新运行 DFT。

| 指标 | 论文公开结果 | 本次从坐标复算 |
|---|---:|---:|
| 结构对数 | 260 | 260 |
| 生成态通过 Law 7 | 61 | 61 |
| DFT 弛豫后通过 Law 7 | 113 | 113 |
| 弛豫后由未通过变为通过 | 52 | 52 |
| 弛豫后由通过变为未通过 | 0 | 0 |
| 生成态位点比例中位数 | 1.00 | 1.00 |
| 弛豫后位点比例中位数 | 0.75 | 0.75 |

三类角色的弛豫后通过率也一致：control 0.4167、priority 0.5786、screened 0.1167。弛豫后的全部空间群分布一致。

## 数据与方法

- 数据来源：AI4QC/PRIS，commit `34e6c86c083759dc1ee594ae22238ea9b5ebd8f4`。
- 生成态：`dft/E4_design/tasks/E4-candidate_*/POSCAR.init`；弛豫态：`outputs/20260828_dft_supplementary_structures/structures/*.cif`。
- 使用作者公开附录 index 中全部 260 对，不按结果选择样本。E4 原先选择 261 个候选，`candidate_0248` 没有对应的公开弛豫 CIF。
- 独立脚本直接读取结构坐标，使用 pymatgen / spglib 计算对称等价位点轨道；Law 7 为 `等价位点轨道数 / 输入晶胞原子数 <= 2/3`，空间容差 0.01 Å，角度容差采用 pymatgen 默认值 5°。
- 所有结构 SHA256 在计算前核验。公开的数值 index 和 SUMMARY 只在特征计算完成之后用于比较。
- 环境：pymatgen 2026.5.4、spglib 2.7.0、NumPy 2.5.3。未发生计算错误。

## 晶胞约定的敏感性

这组公开 SUMMARY 是由 `src/dft_supplementary_data.py` 生成的，其计算**直接使用输入晶胞**。另一个 `dft/analyze.py:spacegroup_and_economy` 函数先取标准原胞，两者不是同一约定。

额外运行标准原胞方案，得到 66→110 个通过、44 个新增通过、0 个丢失通过。与输入晶胞方案比较，有 9 个生成态和 3 个弛豫态的 Law 7 判定变化。这一操作包含容差内的坐标对称化，因此它是独立报告的敏感性分析，未替代论文的输入晶胞约定。

这与 `results/core_validation` 中理想 NaCl 的实验一起，说明后续研究应明确晶胞表示与标准化流程；原始程序对某些等价晶胞给出不同 Law 7 / PSS 数值。本次没有修改阈值，也没有用标准化后的结果覆盖作者算法的结果。

## 文件

- `recomputed_symmetry.csv`：260 行逐结构计算值，包括输入晶胞与标准原胞两种方案。
- `summary.json`：汇总、公开结果逐项比较、版本和计算时间。
- `standardization_verdict_changes.csv`：标准化后判定变化的 12 条记录及对应空间群、原子数、位点比例。
- `run.log`：运行日志。
- `../../data/symmetry/provenance.json`：每个结构的来源路径与 SHA256；同目录包含全部 520 个结构文件。
- `../../scripts/recompute_symmetry.py`：独立、可移植的复算脚本。

在复现包目录运行：

```powershell
python -X utf8 scripts/recompute_symmetry.py
```
