# Infrastructure recovery before scientific execution

The initial CLI launch at 2026-09-30 21:06 UTC failed to dispatch MCP tools
because `code_mode_host` had been disabled. The model produced a blocked final
response. There were **zero scientific tool calls, zero descriptor attempts and
no new test access**. The failed invocation, transcript, original runner and
protocol are preserved in `agent/`.

Before any scientific experiment, the runner was corrected to retain the code
mode host needed for MCP dispatch while continuing to disable shell, web,
apps/plugins and the other general tools. One manual infrastructure recovery
is recorded in `agent/recovered/`; it is not a second search selected after
unfavorable scientific results. The scientific budget remains six descriptor
attempts and 24 processed tool calls for the single working discovery session.
Usage reporting includes both launches. No claim of an OS security boundary
is made. Actual event logs are audited after the recovered session.
