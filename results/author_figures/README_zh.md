# 作者原图的本地重运行

[English](README.md) | [简体中文](README_zh.md)

来源：AI4QC/PRIS，commit `34e6c86c083759dc1ee594ae22238ea9b5ebd8f4`。执行脚本已打包为 `scripts/replot_author_figures.py`；未修改作者的源码、输入汇总数据或阈值，只将输出目录重定向到本文件夹，并调用指定作图函数。

| 论文图号 | 状态与输出 | 本次实际计算范围 |
|---|---|---|
| Fig. 1 | 成功；`fig1_agentic_law_learning.png/pdf/svg` | 使用已发布的调查历史和规则空间汇总数据重新作图；没有重跑自主发现过程。 |
| Fig. 2 | 失败；`fig2_run.log` | 上游仓库缺少 `outputs/20260815_threshold_transfer/transfer.json`。未填造缺失数值，也未把论文原图冒充新结果。 |
| Fig. 3 | 成功；`fig3_anatomy.png/pdf` | 重新计算作者脚本构造的 MgAl2O4 示例和五种固定种子扰动；其余面板使用作者汇总数据、已发布的 E1 DFT 能量。 |
| Fig. 5 | 成功；作者实际输出沿用旧文件名 `fig6_deployment.png/pdf/svg` | 用已发布的生成器、MLIP、E2/E3 DFT 结果重新作图；未运行生成模型、MLIP 或 DFT。 |

Fig. 3 的新计算数值保存在 `fig3_anatomy_readings.json` 和 `fig3_structure_recompute.csv`。这是作者构造的说明性晶体，不是独立抽取的实验样本。阳离子交换示例 S2 没有触发规则；图中据实显示为通过，不能将五个示例概括为全部检出。

PNG 已逐图目视检查，可打开、无空白面板或明显裁切。`manifest.json` 记录退出码、运行时间、源文件哈希、输出哈希和复现层级；各次标准输出及报错保存在对应日志中。

执行器需要上述 commit 的完整上游仓库。在复现包根目录运行：

```text
python -X utf8 scripts/replot_author_figures.py --repo /path/to/PRIS --only fig1 fig3 fig5
```

如果在 `--only` 中加入 `fig2`，且没有补充上游缺失输入文件，将复现已记录的缺失输入报错。
