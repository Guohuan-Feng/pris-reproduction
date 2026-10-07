"""Route raw decision arguments through the audit before Literal validation.

Installed MCPServer validates annotated arguments before a tool body runs. An
Extension interceptor runs before that argument-model validation, while the
registered tool continues publishing the accurate Literal enum schema.

Integration (after adding the installed MCP dependencies to the server path)::

    extension = AuditedDecisionInterceptor(audited_raw_decision)
    mcp = MCPServer('Materials evolving', extensions=[extension], ...)

    @mcp.tool()
    def record_cycle_decision(action: DecisionAction, reflection: str,
          scientific_status: ScientificStatus, scientific_conclusion: str,
          next_question: str, next_tool_plan: str, evidence_ids: list[str],
          decision_token: str) -> dict:
        # This publishes the schema. The interceptor handles stdio tools/call.
        return audited_raw_decision({...same arguments...})

The provided callback takes ONE raw argument dict, and MUST own the normal
serialized server tool-start/tool-finish ledger, unchanged-argument evidence,
tool-call budget, and DecisionStore submission. It must handle missing/extra
metadata fields through bounded metadata validation. It must not invoke science.
Only record_cycle_decision is intercepted. Other tools keep ordinary MCP schema
validation and scientific fail-closed behavior. Direct MCPServer.call_tool is
an internal convenience API and does not pass through request interceptors;
protocol tests must exercise the composed tools/call handler.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from typing import Callable

from mcp.server.extension import Extension
from mcp_types import CallToolResult, TextContent


class AuditedDecisionInterceptor(Extension):
    identifier = 'org.materials-research/audited-decision-metadata'

    def __init__(self, audited_handler: Callable[[dict], dict], *, tool_name='record_cycle_decision'):
        if tool_name != 'record_cycle_decision':
            raise ValueError('Only the metadata decision tool can bypass argument-model validation')
        self.audited_handler = audited_handler
        self.tool_name = tool_name

    def settings(self):
        return {'tool': self.tool_name, 'maximum_metadata_submissions': 2,
                'scope': 'Raw metadata audit before Literal validation; no scientific retries'}

    async def intercept_tool_call(self, params, ctx, call_next):
        if params.name != self.tool_name:
            return await call_next(ctx)
        arguments = dict(params.arguments or {})
        if inspect.iscoroutinefunction(self.audited_handler):
            result = await self.audited_handler(arguments)
        else:
            result = await asyncio.to_thread(self.audited_handler, arguments)
            if inspect.isawaitable(result):
                result = await result
        if not isinstance(result, dict):
            raise TypeError('Audited decision handler must return a JSON object')
        # Metadata validation failure is a completed protocol response, not a
        # transport failure: the response carries retry_metadata_only explicitly.
        rendered = json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False)
        return CallToolResult(content=[TextContent(type='text', text=rendered)],
                              structured_content=result, is_error=False)
