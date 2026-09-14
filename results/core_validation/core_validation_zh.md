# PRIS 核心分析器验证

[English](core_validation.md) | [简体中文](core_validation_zh.md)

来源：AI4QC/PRIS，commit `34e6c86c083759dc1ee594ae22238ea9b5ebd8f4`。

## 导入与测试审查

检查了 `tests/test_pris_analyze.py`、`tests/test_regressions.py`、公开入口 `src/pris_analyze.py`、其直接特征模块，以及通过 `phys_feat.py` / `polymorph_rank2.py` 间接导入的模块。

- 所选测试和分析器特征函数不执行网络调用、不启动子进程，也不执行 shell 命令。
- 分析器从提供的本地 CIF 文件读取结构；键价参数来自已提交的 `data/bvparm2020.cif`；PSS 系数和特征归一化参数来自已提交的 `agent_loop/frozen/20260814_f3_synth/F3_frozen.json`。
- 所选测试会创建临时 CIF 文件及临时 CSV 目录。导入 `fig3_anatomy` 时会导入 `paper_figs`，后者在 `paper/figs` 不存在时创建目录并配置 matplotlib；导入过程不会重新生成图。
- 本项验证没有修改上游源码。

## 独立检查

`scripts/validate_core.py` 创建最近邻距离已知的解析合成结构。这些是几何对照，不是独立实验数据。脚本用显式晶格平移枚举检查 pymatgen 的周期邻居结果，并纳入同一位点的周期镜像。

检查覆盖常规胞和原胞 NaCl、整体平移后的 NaCl 晶胞、NaCl 超胞、常规胞 MgO、双位点 CsCl，以及一个有意设置得很小的单原子立方晶胞。单原子晶胞用来说明：将整个距离矩阵对角线设为无穷大，会漏掉与自身周期镜像之间的接触。

脚本还检查整体平移不变性，并比较相同 NaCl 几何结构在不同晶胞表示下的结果。执行结果见下文。

## 回归测试结果

使用 Python 3.12.14 及预置 NumPy/Pandas 环境运行了 `tests/test_regressions.py` 中的六项上游测试。第一次运行四项通过、两项报错。其中一项报错源于 Windows cp1252 控制台编码无法打印中文；使用 `-X utf8` 运行 Python 即可解决这一环境问题，无需修改源码。

UTF-8 重运行结果为 **5 项通过、1 项报错**。剩余测试 `SplitDisciplineRegressionTests.test_bond_report_does_not_promote_unsplit_rows` 需要读取 `src/build_bonds.py`，但该文件既不在公开仓库中，也未出现在 `git ls-files` 列表中。这是上游测试所需源码或辅助文件缺失，不是结构分析数值断言失败。该测试未被修改或静默跳过。日志为 `work/upstream_regressions.log` 和 `work/upstream_regressions_utf8.log`。

执行命令，工作目录为 `work/PRIS`：

```powershell
& '<bundled-python>/python.exe' -X utf8 -m unittest discover -s tests -p test_regressions.py -v
```

## 所选上游 pytest 测试的完整结果

安装科学计算依赖后，合并运行了两个所选上游测试文件：

```powershell
python -X utf8 -m pytest tests/test_pris_analyze.py tests/test_regressions.py -q --tb=short
```

结果为 **15 项通过、1 项失败、28 条警告**，耗时 97.84 秒。全部 **10 项公开分析器测试通过**，包括论文 Fig. 3a 接触比、损坏检测、冻结的 PSS 权重、PSS 母体排序，以及错误 CIF 处理。唯一失败仍是上述缺失的 `src/build_bonds.py`。警告来自 spglib API 弃用提示，以及上游合成尖晶石序列化时产生的重复位点标签；分析器数值检查仍全部通过。本目录的 `upstream_core_pytest.log` 保留完整输出。

## 独立发现：对输入晶胞表示的依赖

七项解析周期距离检查全部通过。检查使用 -2 至 +2 的显式平移，这对这里的立方和面心立方对照足够；该枚举范围不被视为适用于任意倾斜晶胞的一般算法。

检查发现未经修改的公开分析器存在一个实质局限：Law 7 和部分 PSS 描述符依赖输入晶胞的表示。下面三种晶胞表示的是完全相同的理想 NaCl 晶体，常规晶格参数均为 5.64 Å，最小接触距离均为 2.82 Å：

| NaCl 晶胞表示 | 位点数 | Law 7 数值 | Set 4 判定 | PSS | poly_deg_max | frac_isolated |
|---|---:|---:|---|---:|---:|---:|
| 原胞 | 2 | 1.000 | implausible（不合理） | -1.905422 | 0 | 1 |
| 常规胞 | 8 | 0.250 | plausible（合理） | -1.787582 | 3 | 0 |
| 2×2×2 原胞超胞 | 16 | 0.125 | plausible（合理） | -1.663290 | 7 | 0 |

其余七条规则对应的量在 1e-5 容差内一致；对整个常规胞作平移不会改变判定。Law 7 计算对称等价位点轨道数除以输入晶胞位点数。复制晶胞增加了分母，却保持不同轨道的数量不变。`criteria` 函数还使用有限输入晶胞中的位点索引构建配位多面体之间的连接，因此原胞、常规胞和超胞表示会改变 `poly_deg_max` 与 `frac_isolated`。在 NaCl 原胞中，周期连接被概括为一个孤立多面体，尽管物理晶体实际是连通的周期网络。

这说明的是输入表示敏感性，不能据此认为 NaCl 原胞在物理上不合理。它会影响严格的 Set 4 判定和 PSS 数值。这一发现不否定作者 Fig. 3a 测试在本环境中通过的事实；本复现也没有静默修补这个问题。后续研究应先定义并冻结统一晶胞约定，修正周期图连接的计数方式，并在开发集上重新校准受影响的阈值和归一化参数，再讨论一般性能。

其他对照结果：常规胞 MgO 被判为合理；双位点 CsCl 因 Law 7 被拒绝；单元素单位点晶胞因为无法定义形式阳离子/阴离子电荷，得到 `no verdict`（不作判定）。微小单位点立方晶胞仍具有 0.8 Å 的最小周期距离，几何基线能够检出这个自身镜像距离。

本目录包含机器可读结果和全部七个生成的 CIF。可移植脚本 `scripts/validate_core.py` 使用原样打包的分析器，可重新生成结果。在复现包根目录运行：

```powershell
python -X utf8 scripts/validate_core.py
```

pytest 日志保留测试输出；发布时可能对机器特定的绝对路径前缀作隐去处理。可移植验证 JSON 只保存 CIF 文件名，不含机器特定路径。

两个所选测试文件和四个辅助模块也以原样文件打包在 `vendor/pris` 下。第二次使用这些打包文件运行时，全部 **10 项分析器测试通过**，耗时 6.19 秒；详见 `bundled_analyzer_pytest.log`。

```powershell
python -X utf8 -m pytest vendor/pris/tests/test_pris_analyze.py -q
```

较早的合并日志包含缺失源码导致的回归测试失败，并予以保留。除非作者补充 `src/build_bonds.py`，运行打包的两个测试文件组成的完整所选测试集仍会出现相同的已知失败。
