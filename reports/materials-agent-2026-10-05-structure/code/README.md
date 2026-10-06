# 实际执行源码的审阅快照

这里的 7 个 Python 文件均按原始字节复制；哈希列在 `../source_snapshot_receipt.json`。Agent 函数的运行时 SHA 按 LF 源码文本计算，公开文件保留原 CRLF 字节，两种哈希分别记录。

| 文件 | 在实际流程中的作用 |
|---|---|
| `approved_compute.py` | 实际隔离 Agent 编写并提交的 16 列局部键角函数 |
| `descriptor_runtime.py` | 数值接口、周期近邻、语义及不变性检查、受限工作进程 |
| `pilot_evaluation.py` | 四项预注册特征／模型对比的评估工具 |
| `controller.py` | 将结果、反思与下一步计划传递给后续隔离 Agent 会话 |
| `parser_control_adapter.py` | 相同浮点读取方式下的旧 42 列数值对照 |
| `nested_residual_adapter.py` | 严格内外层 OOF 的残差修正与缓存核验 |
| `frozen_legacy_evaluation.py` | 被锁定的原 E011 评估实现 |

这是供导师审阅的源码快照。`approved_compute.py` 依赖运行时注入的 `closest_neighbors`；评估文件依赖冻结数据、折分与配置；控制器还依赖原 backend、session、MCP 和运行记录。本目录不是可单独启动的完整复跑包。

最后一轮原始决策保存因状态枚举不匹配失败，原源码及失败记录均保留。补充元数据仅把实际 Agent 提交的 `completed_no_promotion` 映射为已有的 `unsupported`，未增加模型拟合或 LLM 会话。源码中原问题没有被事后改写。
