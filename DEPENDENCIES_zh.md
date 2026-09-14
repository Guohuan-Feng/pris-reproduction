# 依赖环境验证与输入数据可获取性评估

[English](DEPENDENCIES.md) | 中文

评估日期：2026 年 9 月 14 日。上游基准：[AI4QC/PRIS](https://github.com/AI4QC/PRIS)，固定提交 `34e6c86c083759dc1ee594ae22238ea9b5ebd8f4`。

## 1. 软件环境验证

本复现的六步流程在 Windows AMD64 平台新建的 Python 3.12.14 虚拟环境中完成安装与执行。该环境禁用系统 site-packages；子进程环境移除了 `PYTHONPATH` 和 `PYTHONHOME`，并禁用用户级 site-packages。计算使用复现包的独立目录副本。这些控制用于排除对原工作环境中已安装科学计算包的依赖。

`requirements-lock.txt` 中的 **48 个固定版本软件发行包**全部安装成功。`pip check` 返回 **“No broken requirements found.”** 自动执行入口 `bootstrap.py` 的退出码为 0，六项科学计算或测试步骤的退出码也全部为 0。重新生成的 E3 指标表、逐候选 EOS 拟合表和逐结构对称性表与归档结果逐字节一致。

环境检查程序核验软件包精确版本、20 个所引用源码文件的 SHA256，以及 703 个归档输入或参考文件：180 个 E3 结构、520 个 E4 结构和 3 个 EOS/参考许可文件。程序还检查参考索引及必需数据清单是否存在。该检查针对本复现包，不代表原始研究的完整上游环境已经具备。

验证证据包括[独立环境验证记录](results/environment/clean_environment_validation.json)、[依赖与完整性检查](results/environment/dependency_check.json)和[自动执行日志](results/environment/bootstrap.log)。公开日志中的完整本地目录前缀已替换为占位符，数值输出未改变。

## 2. 安装与预检入口

```text
python bootstrap.py --workers 4
```

该入口创建 `.venv`，安装固定版本依赖，检查依赖一致性及归档输入完整性，然后执行复现流程。`--install-only` 仅准备环境，不重新计算；`--env-dir PATH` 指定其他虚拟环境目录。经过验证的依赖组合要求 Python 3.12。

预检程序也可检查已有的完整上游仓库：

```text
python scripts/check_environment.py --upstream /path/to/PRIS --json-out dependency_check.json
```

`bundled_workflow_ready` 仅表示本复现包的执行条件是否满足。可选上游文件的缺失情况单独记录。运行本包的六步流程不需要完整上游仓库。

## 3. 缺失上游输入的检索评估

检索覆盖公开主分支的全部 8 个提交、`english-only` 分支、GitHub Release 和 Tag 清单，以及官方 [arXiv 源文件归档](https://arxiv.org/src/2609.01209v1)。补充检索包括 AI4QC 的公开 Hugging Face 清单，以及与论文编号或题名相关的 Zenodo 记录。上述来源中未发现缺失完整特征库或分数分片的可公开获取副本。

| 缺失项 | 类别 | 对复现的影响 | 检索结果 |
|---|---|---|---|
| `src/build_bonds.py` | 上游源代码 | 一个历史数据分割纪律回归测试无法读取目标源码 | 两个公开分支均无该文件的提交历史；已检查的初始公开树中也不存在 |
| `outputs/20260815_threshold_transfer/transfer.json` | 派生实验数据 | Fig. 2 完整重绘需要精确的阈值迁移数值及判定变化率 | 两个分支均无该路径的提交记录；arXiv 归档中不存在 |
| `PRIS_FEATURES/provenance.parquet` 及相关特征和结构存储 | 原始研究输入 | 无法独立重建 5,297/3,612 留出集及 440 个母体的部署基准 | 被排除在公开仓库之外，未发现其他完整发布来源 |
| 完整 1,081 个逆向设计候选的分数与结构归档 | 原始生成样本总体 | 选定的 E4 子集不能用于复算完整候选队列削减率 | 仅获得已发布的选定样本及汇总值 |
| 正例—无标签学习分数分片 | 派生模型输出 | Fig. 4 及部分补充分析仍无法完整重算 | 上游发布说明明确未提供 |
| VASP 可执行文件及授权赝势 | 外部授权软件与数据 | 新的第一性原理计算需要另行配置 VASP 环境 | 公开仓库和本复现包均未分发 |

arXiv 源文件归档包含 260 个弛豫后 CIF、索引和汇总表。统一 CRLF/LF 换行后，其文本与已经归档的补充数据一致，因此并未补充缺失的完整数据集。文件清单记录固定版本检出副本中保留的字节；换行不同的文件可以在文本上相同，但其归档文件或 Git 对象哈希不一定一致。

[上游 README](https://github.com/AI4QC/PRIS/blob/34e6c86c083759dc1ee594ae22238ea9b5ebd8f4/README.md) 明确说明特征库及 PU 分数分片未纳入发布。[上游 Pull Request #1](https://github.com/AI4QC/PRIS/pull/1) 亦记录了不可获取的研究输入及历史测试目标。具体检索端点、清单与归档比较结果见[公开输入审计记录](results/environment/public_input_audit.json)。

## 4. 评估结论

本复现包的软件依赖已经完成安装、版本固定及独立验证。其余限制主要涉及未发布的研究输入、不可获取的上游源码，以及需要单独授权的计算环境。增加 Python 软件包不能恢复这些输入。本次工作未将替代性 `build_bonds.py`、近似阈值迁移表或从成品图中提取的数值作为作者原始材料。

原始符号回归及决策树搜索环境不属于已验证的六步流程。安装 PySR/Julia 或求解器属于额外的环境配置，并不等同于恢复被排除的特征库或复现已封存的发现过程。后续扩展仍需独立记录其输入来源及验证结果。
