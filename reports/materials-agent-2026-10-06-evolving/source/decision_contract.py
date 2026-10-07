"""Durable, bounded metadata-only decision save; this module never executes science.

The MCP tool should annotate scientific_status with ScientificStatus, pass its
arguments as payload, and return submit's structured response without discarding
retry_metadata_only. A correction is allowed only for an explicit validation
failure, within this same attempt. No scientific operation may be replayed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from typing import Callable, Literal
import uuid

ScientificStatus = Literal['supported', 'unsupported', 'mixed', 'pending']
DecisionAction = Literal['continue', 'stop']
SCIENTIFIC_STATUSES = ('supported', 'unsupported', 'mixed', 'pending')
MAX_METADATA_ATTEMPTS = 2


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(',', ':'))


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


class DecisionValidationError(ValueError):
    """A known metadata error. Safe to correct without executing scientific work."""


def validate_decision(payload: dict) -> None:
    """Validate shared fields; a server can impose additional read-only checks."""
    if not isinstance(payload, dict):
        raise DecisionValidationError('Decision payload must be an object')
    if payload.get('action') not in ('continue', 'stop'):
        raise DecisionValidationError('action must be continue or stop')
    if payload.get('scientific_status') not in SCIENTIFIC_STATUSES:
        raise DecisionValidationError('scientific_status must be one of: ' + ', '.join(SCIENTIFIC_STATUSES))
    for field in ('reflection', 'scientific_conclusion', 'next_question', 'next_tool_plan'):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise DecisionValidationError(field + ' must be a nonempty string')
    evidence = payload.get('evidence_ids')
    if (not isinstance(evidence, list) or not evidence
            or any(not isinstance(item, str) or not item.strip() for item in evidence)
            or len(evidence) != len(set(evidence))):
        raise DecisionValidationError('evidence_ids must contain unique, nonempty evidence IDs')
    reserved = {'decision_token', 'decision_payload_sha256', 'metadata_attempt',
                'recorded_utc', 'decision_schema_version'}
    if reserved.intersection(payload):
        raise DecisionValidationError('Payload contains reserved decision persistence fields')


class DecisionStore:
    """One serialized writer per session, with disk-backed attempts and idempotency.

    context_validator must be read-only. It can raise DecisionValidationError or
    ValueError to permit metadata correction; unexpected errors stop the session.
    The server retains its normal tool-start/tool-finish ledger in addition to
    this full-argument decision audit. Two submissions means initial plus one
    correction, never two additional retries. Replays of a saved identical
    token/payload are zero-write successes and do not consume another attempt.
    """
    def __init__(self, attempt_dir, *, expected_token: str | None = None,
                 filename: str = 'cycle_decision.json'):
        self.attempt = Path(attempt_dir).resolve()
        if Path(filename).name != filename:
            raise ValueError('Decision filename must be a single filename')
        self.path = self.attempt / filename
        self.audit_path = self.attempt / 'decision_metadata_attempts.jsonl'
        self.expected_token = expected_token
        self.lock = threading.RLock()

    def _append(self, event):
        self.attempt.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open('a', encoding='utf-8', newline='\n') as stream:
            stream.write(canonical({'utc': now(), **event}) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

    def _events(self):
        if not self.audit_path.exists():
            return []
        # A truncated audit is an unknown outcome, never a fresh start.
        return [json.loads(line) for line in self.audit_path.read_text(encoding='utf-8').splitlines() if line.strip()]

    def _save_exclusive(self, decision):
        # Hard-link publication is atomic and cannot overwrite an existing save.
        temp = self.attempt / ('decision_pending_' + uuid.uuid4().hex + '.json')
        with temp.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(decision, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, self.path)
        temp.unlink()

    def submit(self, decision_token: str, payload: dict,
               context_validator: Callable[[dict], None] | None = None) -> dict:
        """Save once, or report the exact narrow correction that remains permitted."""
        with self.lock:
            arguments = {'decision_token': decision_token, 'payload': payload}
            try:
                argument_hash = digest(arguments)
                payload_hash = digest(payload)
                events = self._events()
            except Exception as exc:
                return self._failure('unknown', f'Unserializable arguments or unreadable audit: {type(exc).__name__}', False, 0)
            if self.path.exists():
                try:
                    saved = json.loads(self.path.read_text(encoding='utf-8'))
                    same = (saved['decision_token'] == decision_token
                            and saved['decision_payload_sha256'] == payload_hash
                            and digest({k: v for k, v in saved.items() if k not in {
                                'decision_token', 'decision_payload_sha256', 'metadata_attempt',
                                'recorded_utc', 'decision_schema_version'}}) == payload_hash)
                except Exception as exc:
                    return self._failure('unknown', f'Saved decision is unreadable: {type(exc).__name__}', False, 0)
                if same:
                    return {'saved': True, 'idempotent_replay': True, 'metadata_attempt': saved['metadata_attempt'],
                            'decision': saved, 'retry_metadata_only': False, 'new_fit_retry_allowed': False}
                self._append({'event': 'decision_replay_conflict', 'arguments': arguments, 'arguments_sha256': argument_hash})
                return self._failure('conflict', 'Decision already saved with a different token or payload', False, 0)
            starts = [e for e in events if e.get('event') == 'metadata_attempt_started']
            terminal_numbers = {e.get('metadata_attempt') for e in events
                                if e.get('event') in ('metadata_validation_failed', 'metadata_saved', 'metadata_unknown')}
            if any(e['metadata_attempt'] not in terminal_numbers for e in starts):
                return self._failure('unknown', 'Prior metadata submission has an unknown outcome; stop and recover evidence', False, 0)
            if any(e.get('event') == 'metadata_unknown' for e in events):
                return self._failure('unknown', 'Prior persistence outcome is unknown; no retry', False, 0)
            number = len(starts) + 1
            if number > MAX_METADATA_ATTEMPTS:
                self._append({'event': 'metadata_attempt_limit_rejected', 'arguments': arguments, 'arguments_sha256': argument_hash})
                return self._failure('limit', 'At most two metadata submissions are permitted in this session', False, 0)
            self._append({'event': 'metadata_attempt_started', 'metadata_attempt': number,
                          'arguments': arguments, 'arguments_sha256': argument_hash,
                          'payload_sha256': payload_hash, 'scientific_fits': 0})
            try:
                if not isinstance(decision_token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', decision_token):
                    raise DecisionValidationError('decision_token must be the supplied session save token')
                if self.expected_token is not None and decision_token != self.expected_token:
                    raise DecisionValidationError('decision_token differs from this session save token')
                valid_prior_tokens = [e['arguments']['decision_token'] for e in starts
                                      if isinstance(e['arguments']['decision_token'], str)
                                      and re.fullmatch(r'[A-Za-z0-9_-]{16,128}', e['arguments']['decision_token'])]
                if valid_prior_tokens and decision_token != valid_prior_tokens[0]:
                    raise DecisionValidationError('Use the same decision_token when correcting metadata')
                validate_decision(payload)
                if context_validator:
                    context_validator(payload)
            except ValueError as exc:
                remaining = MAX_METADATA_ATTEMPTS - number
                self._append({'event': 'metadata_validation_failed', 'metadata_attempt': number,
                              'arguments_sha256': argument_hash, 'error': str(exc),
                              'remaining_metadata_attempts': remaining, 'scientific_fits': 0})
                return self._failure('metadata_validation', str(exc), remaining > 0, remaining)
            except Exception as exc:
                self._append({'event': 'metadata_unknown', 'metadata_attempt': number,
                              'arguments_sha256': argument_hash, 'error': f'{type(exc).__name__}: {exc}'})
                return self._failure('unknown', 'Unexpected decision context error; stop', False, 0)
            decision = {**payload, 'decision_token': decision_token,
                        'decision_payload_sha256': payload_hash, 'metadata_attempt': number,
                        'recorded_utc': now(), 'decision_schema_version': 1}
            try:
                self._save_exclusive(decision)
                self._append({'event': 'metadata_saved', 'metadata_attempt': number,
                              'arguments_sha256': argument_hash, 'payload_sha256': payload_hash,
                              'scientific_fits': 0})
            except Exception as exc:
                # A save might have succeeded just before audit I/O failed. Replay
                # only the identical saved token/payload; never redo science.
                try:
                    self._append({'event': 'metadata_unknown', 'metadata_attempt': number,
                                  'arguments_sha256': argument_hash, 'error': f'{type(exc).__name__}: {exc}'})
                except Exception:
                    pass
                return self._failure('unknown', 'Decision persistence outcome is unknown; stop and inspect saved evidence', False, 0)
            return {'saved': True, 'idempotent_replay': False, 'metadata_attempt': number,
                    'decision': decision, 'retry_metadata_only': False, 'new_fit_retry_allowed': False}

    @staticmethod
    def _failure(kind, error, retry, remaining):
        return {'saved': False, 'failure_kind': kind, 'error': error,
                'retry_metadata_only': retry, 'remaining_metadata_attempts': remaining,
                'new_fit_retry_allowed': False,
                'instruction': ('Correct only record_cycle_decision metadata using the same save token. '
                                'Do not repeat any scientific tool or fit.' if retry else
                                'Stop. Preserve the completed or unknown scientific operation; do not rerun it.')}
