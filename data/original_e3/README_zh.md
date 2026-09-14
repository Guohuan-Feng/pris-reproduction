# 已公开的 E3 COD 样本组

[English](README.md) | [简体中文](README_zh.md)

包含 180 个与公开文件逐字节一致的 POSCAR 输入：30 个 COD 实验来源母体（P0）和全部 150 个有意破坏的变体（S1–S5）。没有根据评分筛选样本，也没有纳入 GNoME 结构。

`manifest.csv` 记录标签和路径，`manifest.json` 记录来源 commit、哈希、样本选择与局限。`upstream_selection.json` 保留作者完整的 E3 选择清单，其中包含单独标记的 GNoME 条目；这些 GNoME 结构未复制到本样本组。

P0 输入是作者重新保存的实验来源晶体坐标，**不是直接下载的原始 CIF 文件**。S1–S5 受损输入是合成对照。`TASK.json` 保持原样复制，因此其中的 `kind=experimental` 描述母体来源，不能当作每个变体的真实标签。

DFT 预注册明确说明：这些母体来自 **discovery split（发现集）**，每个结构最多 16 个位点，且五种损坏算子均可适用。这个经过选择的 DFT 交叉检查样本组可以用于小规模运行已发布分类器；它不等同于完整留出集基准复现或自主定律发现过程复现。
