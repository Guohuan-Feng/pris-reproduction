"""Generic isolated authenticated Codex CLI transport, with no automatic replay.

Scientific tools and the server are explicitly supplied by the controller. Tool
counts come from the durable server call ledger and are reconciled against the
actual CLI event stream, never a copied research-state counter.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Callable
import uuid

sys.dont_write_bytecode = True
DISABLED = ('shell_tool', 'unified_exec', 'shell_snapshot', 'multi_agent', 'multi_agent_v2',
            'memories', 'apps', 'plugins', 'remote_plugin', 'browser_use', 'browser_use_external',
            'browser_use_full_cdp_access', 'in_app_browser', 'computer_use', 'image_generation',
            'code_mode', 'view_image', 'hooks', 'skill_search', 'skill_mcp_dependency_install',
            'workspace_dependencies', 'tool_suggest', 'goals', 'sleep_tool')
STRIPPED_ENV = ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'AZURE_OPENAI_API_KEY')


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(path, value, *, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive and path.exists():
        raise FileExistsError(str(path))
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    if exclusive:
        os.link(temporary, path)
        temporary.unlink()
    else:
        for attempt in range(6):
            try:
                temporary.replace(path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.05 * (attempt + 1))


class WindowsJob:
    """Kill CLI/MCP descendants when this owner closes or dies; fail closed."""
    def __init__(self, process):
        self.handle = None
        if os.name != 'nt':
            return
        import ctypes
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong),
                        ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                        ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                        ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ('ReadOperationCount', 'WriteOperationCount',
                        'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

        class Extended(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', Basic), ('IoInfo', IO), ('ProcessMemoryLimit', ctypes.c_size_t),
                        ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemoryUsed', ctypes.c_size_t),
                        ('PeakJobMemoryUsed', ctypes.c_size_t)]

        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.kernel, self.handle = kernel, handle
        info = Extended()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not kernel.AssignProcessToJobObject(handle, int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.handle is not None:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def terminate_owned(process):
    if process.poll() is None:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           capture_output=True, timeout=20)
        else:
            process.kill()


def stripped_environment(extra=None):
    environment = os.environ.copy()
    environment.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    environment.update(extra or {})
    for key in STRIPPED_ENV:
        environment.pop(key, None)
    return environment


def _validate_location(run_root, attempt_dir):
    root = Path(run_root).resolve()
    attempt = Path(attempt_dir).resolve()
    if (not attempt.is_relative_to(root) or attempt.parents[2] != root
            or attempt.parent.parent.name != 'cycles'
            or not re.fullmatch(r'cycle_\d{3,}', attempt.parent.name)
            or not re.fullmatch(r'attempt_\d{3,}', attempt.name)):
        raise ValueError('Attempt must be run_root/cycles/cycle_NNN/attempt_NNN')
    return root, attempt


def build_command(executable, root, attempt, empty, *, server_name, enabled_tools,
                  server_script, model, reasoning_effort, tool_timeout_seconds=600):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', server_name):
        raise ValueError('Invalid MCP server name')
    tools = tuple(enabled_tools)
    if not tools or len(set(tools)) != len(tools) or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', t) for t in tools):
        raise ValueError('Explicit unique tool allowlist required')
    script = Path(server_script).resolve()
    if not script.is_relative_to(root) or not script.is_file():
        raise ValueError('Server script must exist within this run root')
    if reasoning_effort not in ('low', 'medium', 'high', 'xhigh', 'max', 'ultra'):
        raise ValueError('Invalid reasoning effort')
    timeout = int(tool_timeout_seconds)
    if not 1 <= timeout <= 1200:
        raise ValueError('Tool timeout must be between 1 and 1200 seconds')
    server = '{' + server_name + '={command=' + json.dumps(str(Path(sys.executable).resolve()).replace('\\', '/'))
    server += ',args=' + json.dumps(['-I', '-u', str(script).replace('\\', '/')])
    server += ',cwd=' + json.dumps(str(empty).replace('\\', '/'))
    server += ',env={MATERIALS_CYCLE_DIR=' + json.dumps(str(attempt).replace('\\', '/'))
    server += ',MATERIALS_RUN_ROOT=' + json.dumps(str(root).replace('\\', '/')) + '}'
    server += ',enabled=true,required=true,enabled_tools=' + json.dumps(list(tools))
    server += ',default_tools_approval_mode="approve",startup_timeout_sec=90,tool_timeout_sec=' + str(timeout) + '}}'
    command = [executable, '--no-daemon', '-a', 'never', 'exec', '--skip-git-repo-check', '--ephemeral',
               '--ignore-user-config', '--ignore-rules', '--strict-config', '-m', model, '-s', 'read-only',
               '-c', 'model_reasoning_effort=' + json.dumps(reasoning_effort), '-c', 'project_doc_max_bytes=0',
               '-c', 'skills.max_context_tokens=1000', '-c', 'web_search="disabled"', '-c', 'mcp_servers=' + server,
               '--enable', 'skip_host_skill_discovery', '--enable', 'code_mode_host']
    for flag in DISABLED:
        command += ['--disable', flag]
    return command + ['--json', '--color', 'never', '-o', str(attempt / 'final_response.md'), '-C', str(empty), '-']


def event_audit(path, *, server_name, enabled_tools):
    events, malformed = [], []
    for number, line in enumerate(Path(path).read_text(encoding='utf-8', errors='replace').splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError('Nonobject event')
            events.append(event)
        except Exception:
            malformed.append(number)
    completed = [e for e in events if e.get('type') == 'turn.completed']
    errors = [e for e in events if e.get('type') in ('error', 'turn.failed')]
    tools = [e['item'] for e in events if e.get('type') == 'item.completed'
             and e.get('item', {}).get('type') not in ('agent_message', 'reasoning', 'error')]
    foreign = [i for i in tools if i.get('type') != 'mcp_tool_call'
               or i.get('server') != server_name or i.get('tool') not in enabled_tools]
    usage = [e.get('usage', {}) for e in completed]
    invalid_usage = any(any(not isinstance(u.get(k), int) or u[k] < 0 for k in
                           ('input_tokens', 'cached_input_tokens', 'output_tokens'))
                        or u.get('cached_input_tokens', 0) > u.get('input_tokens', 0) for u in usage)
    deliveries=[]
    for item in tools:
        payload=item.get('result',{}).get('structured_content') if isinstance(item.get('result'),dict) else None
        if not isinstance(payload,dict) or 'evidence_id' not in payload:
            decoded=[]
            for block in (item.get('result') or {}).get('content',[]):
                if block.get('type')=='text':
                    try:value=json.loads(block.get('text',''))
                    except Exception:continue
                    if isinstance(value,dict) and 'evidence_id' in value:decoded.append(value)
            payload=decoded[0] if len(decoded)==1 else None
        deliveries.append({'tool':item.get('tool'),'item_id':item.get('id'),'client_status':item.get('status'),'arguments':item.get('arguments'),'payload':payload})
    return {'completed_events': len(completed), 'errors': errors, 'foreign_tools': foreign,
            'malformed_lines': malformed, 'tool_event_count': len(tools),
            'mcp_tool_names': [t.get('tool') for t in tools], 'usage': usage,
            'deliveries':deliveries,
            'invalid_usage': invalid_usage,
            'uncached_input_tokens': sum(u.get('input_tokens', 0) - u.get('cached_input_tokens', 0) for u in usage) if not invalid_usage else 0,
            'output_tokens': sum(u.get('output_tokens', 0) for u in usage) if not invalid_usage else 0}


def server_snapshot(root):
    path = Path(root) / 'state/server_state.json'
    value = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'tool_calls': 0, 'calls': []}
    calls = value.get('calls')
    if not isinstance(calls, list) or value.get('tool_calls') != len(calls):
        raise RuntimeError('Authoritative server tool_calls does not equal durable call records')
    ids = [call.get('evidence_id') for call in calls]
    if any(not isinstance(eid, str) or not eid for eid in ids) or len(ids) != len(set(ids)):
        raise RuntimeError('Server evidence IDs are missing or repeated')
    return value


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def reconcile_tools(before, after, audit,root,attempt):
    previous = before['calls']
    current = after['calls']
    if current[:len(previous)] != previous:
        raise RuntimeError('Prior server call evidence changed during the session')
    new = current[len(previous):]
    count = len(new)
    if audit['tool_event_count'] != count:
        raise RuntimeError('CLI MCP call count differs from authoritative server call count')
    if [c.get('tool') for c in new] != audit['mcp_tool_names']:
        raise RuntimeError('CLI MCP call order differs from server ledger')
    finished={e['evidence_id']:e for e in map(json.loads,(Path(root)/'state/server_ledger.jsonl').read_text(encoding='utf-8').splitlines()) if e.get('event')=='tool_finished'}
    decision=json.loads((Path(attempt)/'cycle_decision.json').read_text(encoding='utf-8')) if (Path(attempt)/'cycle_decision.json').exists() else {}
    direct=[];recoveries=[]
    for position,(call,delivery) in enumerate(zip(new,audit['deliveries'])):
        if canonical_hash(delivery['arguments'])!=call['arguments_sha256']:raise RuntimeError('Actual CLI tool arguments differ from audited server arguments')
        payload=delivery['payload'];eid=call['evidence_id']
        if delivery['client_status']=='completed' and isinstance(payload,dict) and payload.get('evidence_id')==eid and payload.get('status')==call['status'] and canonical_hash(payload.get('result'))==call['response_sha256']:
            direct.append(eid);continue
        if delivery['client_status']!='failed' or call['tool']!='evaluate_candidate' or call['status']!='complete':raise RuntimeError('Unreconciled actual client/server result delivery')
        expected=finished[eid]['response'];cid=expected['candidate_id'];matched=None
        for later_call,later_delivery in zip(new[position+1:],audit['deliveries'][position+1:]):
            if later_call['tool']=='evaluate_candidate':raise RuntimeError('Scientific evaluation repeated after a client delivery error')
            if later_call['tool']!='research_context' or later_call['status']!='complete' or later_delivery['client_status']!='completed':continue
            recovered=later_delivery['payload']
            if not isinstance(recovered,dict) or recovered.get('evidence_id')!=later_call['evidence_id'] or canonical_hash(recovered.get('result'))!=later_call['response_sha256']:continue
            context=recovered['result']['state'];actual=context.get('completed_results',{}).get(cid);artifact=context.get('completed_result_artifacts',{}).get(cid)
            compact={k:v for k,v in expected.items() if k not in {'complete_prediction_sha256','fit_reservation'}}
            if actual!=compact or not artifact or artifact['result_sha256']!=expected['complete_result_sha256'] or artifact['OOF_predictions_sha256']!=expected['complete_prediction_sha256']:continue
            if context['active_operation'] or context['stop_reason'] or context['incomplete_results']:continue
            if not {eid,later_call['evidence_id']}<=set(decision.get('evidence_ids',[])):continue
            matched={'failed_client_evidence_id':eid,'candidate_id':cid,'recovery_context_evidence_id':later_call['evidence_id'],'completed_result_sha256':artifact['result_sha256'],'OOF_predictions_sha256':artifact['OOF_predictions_sha256'],'scientific_refits':0};break
        if matched is None:raise RuntimeError('Completed server evaluation was not actually reconciled through later delivered read-only context and saved decision')
        recoveries.append(matched)
    return count,new,{'direct_successful_deliveries':direct,'known_completed_evaluation_delivery_recoveries':recoveries,'unknown_delivery_count':0}


def run_one(run_root, attempt_dir, prompt: str, context_reader: Callable[[], dict], *,
            server_name='materials_evolving', enabled_tools,
            server_script=None, decision_filename='cycle_decision.json',
            model='gpt-6-astra', reasoning_effort='medium',
            session_wall_cap=1200, tool_timeout_seconds=600):
    """Exactly one CLI invocation. Unknown or scientific failures are not retried."""
    root, attempt = _validate_location(run_root, attempt_dir)
    if Path(decision_filename).name != decision_filename:
        raise ValueError('Decision filename must be a single filename')
    request = json.loads((attempt / 'session_request.json').read_text(encoding='utf-8'))
    wall = min(float(request['remaining_wall_seconds']), float(session_wall_cap))
    if not 0 < wall <= 7200:
        raise ValueError('Positive bounded remaining wall required')
    if (attempt / 'invocation.json').exists():
        raise RuntimeError('Attempt already invoked; recover evidence instead of repeating session')
    before = context_reader()
    before_server = server_snapshot(root)
    if any(c.get('status') == 'started' and c.get('evidence_id') != 'T0073' for c in before_server['calls']) or before.get('active_operation'):
        raise RuntimeError('Prior scientific operation is unknown; do not start another session')
    empty = root / 'isolated_session'
    empty.mkdir(exist_ok=True)
    executable = shutil.which('codex')
    if not executable:
        raise RuntimeError('Authenticated Codex CLI unavailable')
    command = build_command(executable, root, attempt, empty, server_name=server_name,
                            enabled_tools=enabled_tools, server_script=server_script or root / 'science_server.py',
                            model=model, reasoning_effort=reasoning_effort, tool_timeout_seconds=tool_timeout_seconds)
    dump(attempt / 'transport_before.json', {'context': before, 'authoritative_server': before_server}, exclusive=True)
    (attempt / 'prompt.txt').write_text(prompt, encoding='utf-8')
    meta = {'started_utc': now(), 'model': model, 'reasoning_effort': reasoning_effort,
            'cli_version': subprocess.check_output([executable, '--version'], text=True, timeout=20).strip(),
            'authentication': 'Existing local ChatGPT login. Project API credentials removed.',
            'command': command, 'hard_wall_seconds': wall, 'before_counters': before.get('counters', {}),
            'authoritative_tool_calls_before': before_server['tool_calls'], 'completed': False,
            'no_session_retry': True}
    dump(attempt / 'invocation.json', meta, exclusive=True)
    environment = stripped_environment({'MATERIALS_CYCLE_DIR': str(attempt), 'MATERIALS_RUN_ROOT': str(root)})
    start = time.monotonic()
    timeout = False
    process = None
    job = None
    transport_error = None
    with (attempt / 'events.jsonl').open('xb') as output, (attempt / 'stderr.log').open('xb') as error:
        try:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=output, stderr=error, env=environment,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            job = WindowsJob(process)
            dump(attempt / 'process.json', {'pid': process.pid, 'started_utc': now(),
                                           'windows_job_kill_on_close': os.name == 'nt'}, exclusive=True)
            try:
                process.communicate(prompt.encode('utf-8'), timeout=wall)
            except subprocess.TimeoutExpired:
                timeout = True
                job.close()
                terminate_owned(process)
                process.communicate(timeout=30)
        except BaseException as exc:
            transport_error = f'{type(exc).__name__}: {exc}'
        finally:
            if job is not None:
                job.close()
            if process is not None:
                terminate_owned(process)
    audit = event_audit(attempt / 'events.jsonl', server_name=server_name, enabled_tools=enabled_tools)
    reconciliation_error = None
    after = None
    after_server = None
    tool_count = None
    new_calls = []
    delivery_reconciliation=None
    try:
        after = context_reader()
        after_server = server_snapshot(root)
        tool_count, new_calls,delivery_reconciliation = reconcile_tools(before_server, after_server, audit,root,attempt)
    except Exception as exc:
        reconciliation_error = f'{type(exc).__name__}: {exc}'
    cli_completed = (process is not None and process.returncode == 0 and not timeout and not transport_error
                     and audit['completed_events'] == 1 and not audit['errors'] and not audit['foreign_tools']
                     and not audit['malformed_lines'] and not audit['invalid_usage'])
    known = (after is not None and not reconciliation_error
             and not after.get('incomplete_scientific_calls') and not after.get('active_operation')
             and after.get('ledger_consistent', True) and all(c.get('status') in ('complete', 'failed') for c in new_calls))
    has_decision = (attempt / decision_filename).is_file()
    completed = bool(cli_completed and known and has_decision)
    if completed:
        failure_kind = None
    elif reconciliation_error or audit['foreign_tools'] or audit['malformed_lines'] or audit['invalid_usage']:
        failure_kind = 'protocol'
    elif new_calls or not known:
        failure_kind = 'protocol' if cli_completed and known else 'research'
    else:
        failure_kind = 'transport'
    counters = {key: after.get('counters', {}).get(key, 0) - before.get('counters', {}).get(key, 0)
                for key in ('experiments', 'investigations')} if after else {'experiments': None, 'investigations': None}
    result = {'completed': completed, 'failure_kind': failure_kind,
              'research_tool_calls': tool_count, 'authoritative_tool_calls_after': after_server['tool_calls'] if after_server else None,
              **counters, 'uncached_input_tokens': audit['uncached_input_tokens'], 'output_tokens': audit['output_tokens'],
              'usage_complete': audit['completed_events'] == 1 and not audit['invalid_usage'],
              'scientific_activity_known': known, 'cli_turn_completed': cli_completed,
              'decision_saved': has_decision, 'transport_error': transport_error,
              'reconciliation_error': reconciliation_error, 'no_session_retry': True,
              'delivery_reconciliation':delivery_reconciliation,
              'audit_path': str(attempt / 'invocation.json')}
    meta.update(finished_utc=now(), elapsed_seconds=time.monotonic() - start,
                returncode=process.returncode if process else None, timeout=timeout,
                after_counters=after.get('counters', {}) if after else None, audit=audit, result=result,
                completed=completed)
    dump(attempt / 'invocation.json', meta)
    return result
