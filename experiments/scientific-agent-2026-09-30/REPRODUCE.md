# Reproduction and replay / 重放与重建

## Saved numerical results / 已保存数值结果

Install the pinned [requirements](requirements.txt) in a Python 3.12 environment.
Run these commands from this experiment directory:

```powershell
python -m pip install -r requirements.txt
python audit_run.py --stage final --authorize-final --out replay_audit.json
python test_descriptor_runtime.py
python test_evaluator.py
python plot_results.py
```

The final audit reconstructs predictions from saved preprocessing and model
parameters and checks metrics and bootstrap intervals. It performs no model
training or LLM calls. Prepared data, authored programs, fitted models and full
call records are included. HGB joblib files require the recorded scikit-learn
version; load only the trusted files in this repository.

最终审计从保存的预处理参数与模型重建预测，核查指标和自助法区间，不重新拟合，
也不调用大语言模型。所需的预计算数据、候选代码、模型和调用记录均已包含。
审计与绘图脚本会更新其对应输出文件；如需保留原始归档字节，应在副本中运行。

## Fresh discovery / 新的代理发现实验

The frozen folder is deliberately single-use. `run_agent.py`, `finalize.py`
and the evaluator refuse to overwrite completed experiments or reopen a final
test. A new scientific run requires a new output directory, a separately
registered cohort/split and a new protocol. The six development tools are
implemented in `scientific_server.py`; Codex connects over local stdio MCP.
Codex CLI 0.159.2 and the existing ChatGPT login were used in this run. No
professor project API key was used. The MCP SDK was installed into a separate
local target directory; ordinary installation of the pinned package is also
supported by the import path. Code-mode host must remain enabled for MCP routing.

该目录按单次实验设计，禁止覆盖已完成实验或反复打开最终测试。开展新研究时，
需要新目录、新的数据划分及实验方案。当前实现使用本地 MCP 连接 Codex，
保留了真实调用记录和失败启动记录。执行次数限制不等于金额上限。

## Rebuilding the cohort from source / 从原始数据重建

`data_prepare.py` preserves the original workspace layout and prior exclusion
history. It is not a standalone downloader. [source_dependencies.zip](source_dependencies.zip)
contains its small helper modules and identity/exclusion manifests, with paths
relative to the original workspace root. Extract into a separate reconstruction
workspace, restore this experiment at `outputs/pris_scientific_agent_2026-09-30/`,
and place the following official files under `work/mp_rule_pilot/raw/`:

- [2025-02-01-mp-energies.csv.gz](https://ndownloader.figshare.com/files/52080797)
- [2023-02-07-mp-computed-structure-entries.json.gz](https://ndownloader.figshare.com/files/40344436)
- [2023-02-07-mp-elemental-reference-entries.json.gz](https://ndownloader.figshare.com/files/40387775)

Check their hashes against the [dataset manifest](data/dataset_manifest.json)
before running `python data_prepare.py`. Original source archives are not
duplicated in this small experiment package. Identity-based exclusions preserve
the sequence of prior experiments. Broader family overlap, cross-provider
physical duplicates without an ID mapping and public-data pretraining exposure
cannot be fully excluded.

原始数据重建依赖既往实验的身份排除清单。依赖压缩包保留这些清单和小型源模块；
完整 MP 原始压缩包需从上述公开链接取得。应在独立重建目录恢复原有路径，
避免覆盖冻结结果。常规结果核查直接使用已包含的预计算数据即可。

## Provenance / 来源

Sources: [PRIS paper](https://arxiv.org/html/2609.01209v1),
[Matbench Discovery public release v38](https://doi.org/10.6084/m9.figshare.22715158.v38),
[Materials Project thermodynamic stability documentation](https://docs.materialsproject.org/methodology/materials-methodology/thermodynamic-stability/phase-diagrams-pds).
Data attribution is retained in [DATA_LICENSE.md](DATA_LICENSE.md).
