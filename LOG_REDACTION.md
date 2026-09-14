# Publication log redaction

On 2026-09-14, complete local directory prefixes in seven reproduction log
copies were replaced with placeholders before publication. This removes
machine-specific user and installation paths while retaining the diagnostic
filenames and the rest of each trace.

| Placeholder | Meaning | Replacements |
|---|---|---:|
| `<workspace>` | Local reproduction workspace root | 28 |
| `<python-runtime>` | Bundled Python installation root | 9 |
| `<temp>` | Local temporary-directory root | 1 |

The replacement handles ordinary paths and their JSON/traceback-escaped forms.
It matches complete known directory prefixes only. It does not replace user-ID
digits or other short strings that may also occur in atomic coordinates.

Changed log files:

- `results/author_figures/fig2_run.log`
- `results/core_validation/bundled_analyzer_pytest.log`
- `results/core_validation/core_validation_run.log`
- `results/core_validation/upstream_core_pytest.log`
- `results/core_validation/upstream_regressions.log`
- `results/core_validation/upstream_regressions_utf8.log`
- `results/run_logs/upstream_analyzer_tests.log`

Verification established that every character outside the replaced prefixes,
including all numerical results, timings, warnings, exception messages, and
line breaks, remained unchanged. The structured records in
`core_validation_run.log` still parse as JSON, and all fields except their
input-file paths are identical. Original diagnostic language is retained.
No local user-path matches remained in the result logs after redaction.

This cleanup did not modify raw scientific data, vendored source, test logic,
or numerical results. No files were deleted. Re-running the scripts may create
new machine-specific paths in logs; review those logs before publishing a new
run.

## 中文说明

发布前，仅将上述七个日志副本中的完整本地目录前缀替换为占位符，共 38 处。
`<workspace>` 表示复现工作目录，`<python-runtime>` 表示 Python 安装目录，
`<temp>` 表示临时目录。未对用户名数字等短字符串进行全局替换，避免误改原子坐标。

已验证：前缀之外的全部字符、数值、运行时间、警告、异常信息和换行均保持不变；
结构化日志仍可解析，除输入文件路径外的所有字段完全一致。原始诊断语言予以保留。
未修改原始科学数据、第三方源码或测试逻辑，也未删除文件。
