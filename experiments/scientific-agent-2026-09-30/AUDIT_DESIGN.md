# Scientific-agent design and interface audit

Reviewed 2026-09-30, before any model call by this reviewer. This is an application-interface and experimental-design review, not a hostile-code penetration test or proof of operating-system isolation. The protocol accurately calls the evaluator a trusted process. No prior experiment was modified.

## Main finding

A local stdio MCP server can provide the intended inspect–hypothesize–execute–revise loop while withholding test data through its interface. Disabling only `shell_tool`, `multi_agent` and `memories` is insufficient to establish that the agent has no other file-access surface. An MCP tool allowlist restricts that server's exposed tools; it does not sandbox the server process or arbitrary Python. The report should describe an audited restricted interface and the observed tool trace, not claim comprehensive filesystem isolation.

The six-attempt search is a useful bounded discovery pilot. Validation feedback, counterexamples and revisions are adaptive development evidence. Only the frozen final selection can receive one held-out assessment. A predictive gain would still not establish a physical law, GPT-specific superiority over matched descriptor search, or independence from public-data pretraining.

## What was verified locally

- Installed CLI: `codex-cli 0.159.2`. Local `exec --help` documents `--ignore-user-config` as skipping the user configuration while retaining the authentication location. It is not described as disabling every project or host capability.
- `codex -c '<mcp table>' mcp get pris --json` successfully parsed an override containing `command`, `args`, `cwd`, `env`, `env_vars`, `enabled_tools`, and timeouts, and returned those fields. Dummy paths were used; no process or model was started. `required` and approval mode were accepted in the input but not echoed, so their runtime behavior was not established by this probe.
- `--strict-config` is supported by `exec` but rejected by `mcp get`. The probe was rerun without it. Do not describe this as a strict-schema runtime smoke test.
- Local `features list` showed shell, apps, plugins, browser, computer use, code-mode host, image and other capabilities enabled in the inspected configuration. This inventory loaded the current configuration; it is not the final isolated invocation's tool inventory.
- The synthetic [runtime checks](descriptor_runtime_checks.json) and [test script](test_descriptor_runtime.py) exercise the descriptor boundary without loading MP data, test labels, an MCP server or a model. Check the result's runtime hash before interpreting it against a later code revision.

## Exact MCP configuration pattern

The official CLI MCP configuration supports a command, argument array, working directory, explicit environment additions, a tool allowlist, and startup/tool timeouts. `required = true` requests startup failure when the server cannot initialize. `disabled_tools` is applied after `enabled_tools`. These settings belong to each server table. See the [official MCP reference](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

```toml
[mcp_servers.scientific]
command = "C:/absolute/path/to/python.exe"
args = ["-I", "-u", "C:/absolute/path/to/scientific_server.py"]
cwd = "C:/absolute/path/to/empty-agent-directory"
env = { PYTHONIOENCODING = "utf-8", OPENBLAS_NUM_THREADS = "1" }
env_vars = []
enabled = true
required = true
enabled_tools = ["describe_data", "inspect_records", "run_experiment", "counterexamples", "compare_experiments", "record_conclusion"]
default_tools_approval_mode = "approve"
startup_timeout_sec = 30
tool_timeout_sec = 240
```

This is a runner pattern, not a claim that a saved user config will load under `--ignore-user-config`: supply the table through explicit `-c` overrides in that invocation. Python `-I` ignores Python-specific ambient paths but does not restrict operating-system file access. `env_vars = []` is not proof that every ambient variable has been removed. The descriptor worker's explicit environment allowlist is a separate control.

Use `exec --ignore-user-config --ignore-rules --no-daemon --ephemeral --strict-config --sandbox read-only --ask-for-approval never`, an empty working directory, and explicit `web_search="disabled"`. Candidate feature disables, all present in the installed feature inventory:

```text
shell_tool unified_exec shell_snapshot multi_agent multi_agent_v2 memories
apps plugins remote_plugin browser_use browser_use_external
browser_use_full_cdp_access in_app_browser computer_use image_generation
code_mode view_image hooks skill_search
skill_mcp_dependency_install workspace_dependencies tool_suggest
```

Pass each as `--disable FEATURE`. `--enable skip_host_skill_discovery` is also available locally, but is under development and needs prompt/inventory verification. Do not use removed flags such as `apply_patch_freeform` or `js_repl` as purported safety controls. This reviewer did not launch an inference request.

**Observed startup correction:** the initial recommendation also disabled `code_mode_host`. The implementation owner's first actual CLI invocation then failed before any scientific MCP call, reporting that the code-mode host was disabled. Consequently, retain `code_mode_host` and keep `code_mode` disabled for the infrastructure retry; other controls need not change without evidence. This corrects unverified feature advice, not a failed scientific hypothesis. Preserve the original invocation and its usage (reported input 17,880 tokens and output 585 tokens), record zero scientific attempts, and audit the actual host-exposed tool inventory after the retry. Host routing availability is not, by itself, evidence that a shell/file executor is exposed or absent.

The official configuration reference distinguishes command networking from MCP/app/hosted-tool traffic. Therefore command sandbox settings do not imply a global tool-network deny rule. See the [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference). A read-only sandbox also permits file reads; approval policy controls prompting rather than removing all access. See [agent approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security).

## Code review and remaining boundaries

`scientific_server.py` loads development structures and labels, filters the feature frame to those IDs and offers no test-record endpoint. `descriptor_runtime.py` passes only an explicit structure-field allowlist to `featurize(s)`: no material ID, split, target energy or arbitrary CSE metadata. Development labels are intentionally available through discovery tools; they are absent from the descriptor function's input. The evaluator's own file accesses require its separate audit.

Two issues reported during review were corrected before the synthetic run: reserved descriptor names can no longer overwrite material IDs/targets/raw feature names, and counters are persisted before starting work using atomic replacement. The synthetic suite also checks one known intensive descriptor under site permutation, fractional translation, rigid rotation and cell replication. It does not establish those properties for every generated descriptor.

Additional points to verify against final code:

- Attribute writes to the shared `np` namespace were subsequently rejected and a regression check was added. Otherwise a function could update `np.pi` between rows, contradicting the pure-function contract. Check the saved suite's runtime hash for the tested revision.
- The 24-call wrapper limits processed calls. Calls rejected after exhaustion must be logged separately or the protocol should avoid claiming at most 24 total MCP invocations.
- A worker timeout does not impose a memory ceiling. Bounded output width does not bound intermediate arrays. The restricted numerical API, AST checks and sanitized environment reduce accidental misuse but are not an OS security boundary.
- Keep MCP resources/templates empty or explicitly restricted, and do not add arbitrary file paths, shell commands, URL fetching, evaluator imports or a test endpoint to tool arguments.
- A descriptor may still use cell size, site order or coordinate conventions unless invariance is tested. Test proposed functions on synthetic transformations or development structures without labels; document any known representation dependence.

## Scientific checks before final selection

1. Count failed, invalid and timed-out descriptor submissions against the six attempts; retain code, hypotheses, errors and every development response. Fix the maximum twelve scalar outputs, estimator, missing-value treatment, coverage policy and task-specific selection rule before discovery.
2. Keep label-free structure inputs separate from raw `ComputedStructureEntry` objects, which carry energy and provenance fields. Never pass evaluator state, source metadata with target information, row index, split identity or unrestricted material IDs into the generated function.
3. Fit standardization, imputation and missingness handling using training data only. Compare raw features and raw-plus-descriptors on exactly the same rows. Preserve the raw model as a no-change selection and the stated nonlinear control. A gain over a linear baseline alone has a narrower meaning than a gain over a strong nonlinear predictor.
4. Freeze descriptor code, selected model coefficients, thresholds, preprocessing and the complete agent transcript before computing test descriptors or reading test targets. Do not rerun discovery after a test failure. Any test-time descriptor failure must follow the predeclared coverage/fallback policy, not a new code revision.
5. Report the full attempted search, adaptive validation status, final cohort/chemical-system counts, conditional group-bootstrap uncertainty and negative results. Hypothesis falsification statements require their specified check; coefficient signs and aggregate errors do not independently prove a mechanism.
6. State that these inputs are DFT-relaxed public MP structures. This experiment concerns prediction on a specified snapshot, not synthesizability, a new DFT calculation, pre-DFT screening savings or superconductivity.

## Practical smoke test, without inference first

After the evaluator is ready, use a plain JSON-RPC stdio client to initialize the server, inspect its six tool schemas and check that resources/templates provide no unintended access. Exercise invalid arguments and an unavailable ID against a disposable synthetic fixture, not the real experiment state. Confirm unknown tools and exhausted budgets fail closed, emitted logs contain no sealed labels, and worker failures retain their attempt count. This reviewer did not start that server while evaluator setup was pending. The implementation owner subsequently reported a successful initialization and six-tool listing without calling a data tool; that report is separate from this reviewer's synthetic tests.

The later authorized CLI smoke should capture the actual available-tool inventory or prompt metadata plus emitted events, not merely the features configuration. Confirm that only the intended scientific tools can perform work and that unexpected shell, file, browser, app or subagent capabilities are absent or rejected. Trace absence by itself is evidence of what was used, not proof that an unused capability was impossible.

中文结论：这个设计可验证“通过受限工具进行提出假设、计算、查看开发集反馈和修订”的实际工作流，但不能把关闭几个 CLI 开关或 AST 检查说成操作系统级隔离。验证集反馈属于自适应开发；最终代码和模型冻结后的一次测试才是保留集评估。结果需限定为公开 MP 快照中已 DFT 弛豫结构的预测表现，并如实保留失败尝试和无收益结果。
