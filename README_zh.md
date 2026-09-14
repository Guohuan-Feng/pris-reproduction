# PRIS 论文复现

[English](README.md) | [简体中文](README_zh.md)

复现日期：2026-09-14。作者原仓库：[AI4QC/PRIS](https://github.com/AI4QC/PRIS)，固定提交 `34e6c86c083759dc1ee594ae22238ea9b5ebd8f4`。论文：[arXiv:2609.01209](https://arxiv.org/abs/2609.01209)。

完整报告提供[中文版](REPORT_zh.md)和[英文版](REPORT.md)。本仓库保存实际执行的复现代码、公开原始结构、数值结果、图表、日志以及未经修改的作者分析器。**这是对公开输入完整部分的独立、部分复现，并非官方 PRIS 仓库。**没有重跑原始 200 万次候选搜索或 VASP，也没有复现缺少输入的完整留出集。

## 主要结果

| 实验 | 重新计算的结果 | 适用范围 |
|---|---|---|
| E3 晶体筛选 | Set 4 保留 27/30 个母体，检出 119/150 个受损结构 | 经过选择的 discovery 子集，不能视为独立留出集性能 |
| E4 体模量独立拟合 | 260/260 个拟合成功；与作者结果最大绝对差 0.000233 GPa | 使用公开能量—体积数据，没有新运行 DFT |
| E4 对称性 | 520 个结构重新计算；Law 7 通过数 61→113，逐结构无差异 | 按输入晶胞口径，对应 260 对公开结构 |
| 周期几何与实现检查 | 7 个周期几何控制和 10 个作者分析器测试通过 | 另有 1 个历史回归测试因上游文件缺失而失败 |
| 晶胞表示敏感性 | 同一 NaCl 晶体的不同晶胞表示得到不同 Set 4 判断 | 记录公开分析器行为，没有修改规则 |

打包后的六步运行全部以退出码 0 完成，见[运行摘要](results/run_logs/summary.json)。报告详细说明了分母、缺失值处理、样本筛选条件以及尚未公开的输入。

![E3 选定子集的筛选结果](results/structure_benchmark/structure_benchmark.png)

## 重新运行

使用 Python 3.12，在仓库根目录执行：

```text
python bootstrap.py --workers 4
```

该入口创建 `.venv`，安装 48 个固定版本依赖，运行 `pip check`，核验所引用源码及科学输入的哈希，然后执行六步复现流程。`python bootstrap.py --install-only` 仅安装并验证环境，不重新计算。已有的无关目录不会被覆盖。独立环境验证及上游输入的可获取性详见[依赖说明](DEPENDENCIES_zh.md)。

等价的手动安装步骤如下：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-compile -r requirements-lock.txt
.\.venv\Scripts\python.exe run_all.py --workers 4
```

macOS/Linux 将 `.\.venv\Scripts\python.exe` 替换为 `.venv/bin/python`。依赖文件记录此次运行实际使用的精确版本，并非作者未完整固定的原始环境。安装依赖需要联网；默认复现使用仓库内的数据，不调用模型 API 或 DFT 程序。

`run_all.py` 顺序运行周期几何控制、180 个 E3 结构、260 个 E4 状态方程拟合、E4 成对结构对称性审计、报告图表以及 10 个作者分析器测试。每一步的退出码保存在 `results/run_logs/summary.json`，结果写入 `results/`。

## 单独执行实验

```text
python scripts/validate_core.py
python scripts/run_structure_benchmark.py --workers 4
python scripts/refit_eos.py
python scripts/recompute_symmetry.py
python scripts/make_report_figures.py
python -m pytest -q vendor/pris/tests/test_pris_analyze.py
```

使用作者分析器处理新的 CIF/POSCAR：

```text
python vendor/pris/src/pris_analyze.py path/to/structure.cif
```

E3 输入是作者发布的 POSCAR，保留原始字节。单独构造的 NaCl/MgO/CsCl 明确属于几何控制，不是实验数据集条目。未修改作者分析器以改变其判断。

## 重绘作者图表（可选，需完整仓库）

已完成的 Fig. 1、3、5 导出文件位于 `results/author_figures/`。若要重新生成，需要获取固定版本的完整上游仓库，因为部分汇总输入没有重复放入本精简仓库：

```text
git clone https://github.com/AI4QC/PRIS.git upstream-full
git -C upstream-full checkout 34e6c86c083759dc1ee594ae22238ea9b5ebd8f4
python scripts/replot_author_figures.py --repo upstream-full --only fig1 fig3 fig5
```

仅重定向输出目录变量。Fig. 1 和 Fig. 5 使用公开汇总数据重绘。Fig. 3 重新计算说明性的尖晶石及其扰动，其他面板使用公开汇总和 DFT 数值。正文 Fig. 5 的脚本保留了旧文件名 `fig6_deployment`。

Fig. 2 已尝试执行，但发布材料缺少 `outputs/20260815_threshold_transfer/transfer.json`，因此失败。Fig. 4 需要未公开的分数分片，没有补造这些数据。

## 文件与来源

- `REPORT.md` / `REPORT_zh.md`：中英文完整结果、解释、限制与后续研究方向。
- `REPRODUCTION_AUDIT.md` / `REPRODUCTION_AUDIT_zh.md`：中英文来源及实验协议审计。
- `data/original_e3/`：30 个 COD 来源母体及 150 个归档扰动变体，附标签和哈希。
- `data/eos/`：公开能量—体积记录、参考体模量以及来源哈希。
- `data/symmetry/`：生成态与弛豫后结构配对及来源。
- `vendor/pris/`：未修改的作者分析器、选定测试及原始许可声明。
- `results/`：计算得到的测量值、比较表、图像与日志。
- `vendor_manifest.json`：所引用上游文件的来源及哈希。
- `FILE_MANIFEST.json`：最终验证后的交付文件哈希。
- `LOG_REDACTION.md`：公开日志中本机路径的脱敏说明。
- `DEPENDENCIES.md` / `DEPENDENCIES_zh.md`：独立环境验证及上游输入可获取性说明。
- `bootstrap.py`：隔离环境创建、依赖安装、核验和执行入口。
- `scripts/check_environment.py`：精确版本、源码与输入完整性以及可选上游文件检查。

首页、完整报告、来源审计及各数据/结果目录的说明均有中英文版本。机器可读数值和未经修改的上游源文件保留原始语言；两种语言的报告引用同一份计算结果。

上游代码采用随附的 MIT 许可。COD 来源结构归属于对应 COD 记录。`vendor/pris/data/bvparm2020.cif` 保留 I. D. Brown 的键价参数表声明，包括其中的非商业再分发条款。仓库不包含 ICSD 数据库、专有赝势、API 密钥或用户会议录屏。
