"""Fail-closed submission exports and honest execution evidence.

This module is deliberately Streamlit-free, so the bytes downloaded by the
app can be checked in unit tests even where the Streamlit runtime is absent.
"""
from __future__ import annotations

import json
import hashlib
import math
from numbers import Real
import numpy as np
from functools import lru_cache
from typing import Any

from core import DOI, DATA_FILE, quality_gate, naive_v0, constraint_check, build_report
from agent import (REQUEST_FIELDS, _trusted_report, validated_request, dispatch_tool,
                   DETERMINISTIC_FOOTER, UNVERIFIED_LLM_NOTICE)


EXECUTION_MODES = {
    "Deterministic tools": "RULE_BASED_TOOLS__NOT_LLM",
    "LLM tool-calling": "LLM_API_REQUESTED__VERIFY_WITH_PROVIDER",
    "Mock LLM protocol": "SIMULATED_LLM_PROTOCOL__NOT_LIVE",
}


def _same_json_value(actual: Any, expected: Any) -> bool:
    """Compare JSON-shaped audit records without Python's bool == 1 pitfall.

    Numeric int/float representations remain interchangeable (JSON roundtrips
    legitimately normalize these), but a bool can only equal a bool. Nested
    mappings must have identical keys and lists identical lengths/order.
    Unknown non-JSON types and nonfinite numbers fail closed.
    """
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is bool and type(expected) is bool and actual == expected
    if actual is None or expected is None:
        return actual is None and expected is None
    if isinstance(actual, Real) or isinstance(expected, Real):
        return (isinstance(actual, Real) and isinstance(expected, Real)
                and math.isfinite(actual) and math.isfinite(expected)
                and actual == expected)
    if isinstance(actual, str) or isinstance(expected, str):
        return type(actual) is str and type(expected) is str and actual == expected
    if isinstance(actual, list) or isinstance(expected, list):
        return (isinstance(actual, list) and isinstance(expected, list)
                and len(actual) == len(expected)
                and all(_same_json_value(a, b) for a, b in zip(actual, expected)))
    if isinstance(actual, dict) or isinstance(expected, dict):
        return (isinstance(actual, dict) and isinstance(expected, dict)
                and all(isinstance(k, str) for k in actual)
                and all(isinstance(k, str) for k in expected)
                and actual.keys() == expected.keys()
                and all(_same_json_value(actual[k], expected[k]) for k in actual))
    return False


@lru_cache(maxsize=8)
def _reference_noarg_tool(tool_name: str, source_sha256: str) -> str:
    """Trusted no-argument analysis cached only for identical raw CSV bytes.

    Recalculation is relatively expensive (~0.6s for the model diagnostics
    and casebook). The cache is internal and never returned for client mutation.
    A source-file modification changes the cache key, then dispatch_tool still
    enforces the canonical 32-row dataset fingerprint.
    """
    if tool_name not in ('evaluate_models', 'audit_casebook'):
        raise ValueError('Invalid cached tool')
    # Cache immutable serialized bytes; a caller cannot mutate the reference.
    return json.dumps(dispatch_tool(tool_name, {}), ensure_ascii=False,
                      sort_keys=True, allow_nan=False)


def _recompute_for_audit(name: str, args: dict, params: dict) -> dict | list:
    if name in ('evaluate_models', 'audit_casebook'):
        if args:
            raise ValueError('No-argument tool received unexpected arguments')
        current_data_sha = hashlib.sha256(DATA_FILE.read_bytes()).hexdigest()
        return json.loads(_reference_noarg_tool(name, current_data_sha))
    return dispatch_tool(name, args, locked_request=params)


def make_recipe_review(request: dict, best: dict) -> str:
    """Create a downloadable report only after fresh, independent validation."""
    gate = quality_gate(request, best)
    if gate['status'] != 'REVIEW_REQUIRED':
        raise ValueError('Quality gate rejected the current recipe; no report exported')
    params, error = validated_request(request)
    if error or params is None:
        raise ValueError('Invalid request; no report exported')
    baseline = naive_v0(params['target_nm'])
    issues = constraint_check(baseline, **{
        key: params[key] for key in REQUEST_FIELDS if key not in ('target_nm', 'objective')
    })
    report = build_report(best, baseline, issues, params['objective'])
    report += '\n\n### 품질 게이트 (공정 승인 아님)\n```json\n' + json.dumps(
        gate, ensure_ascii=False, indent=2, default=float) + '\n```\n'
    return report


def audit_execution(mode: str, request: str | dict, report: str,
                    trace: list[dict]) -> dict[str, Any]:
    """Recompute every recorded tool result and compare the exact trusted report.

    A successful mock is *never* labeled as a live API execution. A purported
    live execution is described as a self-reported invocation, not independent
    verification of API provider logs.
    """
    if not isinstance(mode, str) or mode not in EXECUTION_MODES:
        raise ValueError('Unknown execution mode: cannot certify this run')
    if not isinstance(trace, list) or not isinstance(report, str):
        raise ValueError('Invalid run evidence')
    result = {
        'mode': mode,
        'mode_classification': EXECUTION_MODES[mode],
        'status': 'BLOCKED_OR_INCOMPLETE',
        'validated_report': False,
        'evidence_retrieved': False,
        'locked_recipe_queried': False,
        'steps': [entry.get('tool') if isinstance(entry.get('tool'), str)
                  else '<invalid>' for entry in trace if isinstance(entry, dict)],
        'study_data': DOI,
        'external_manufacturing_validation': False,
        'live_api_independently_verified': False,
        'trace_authenticity_independently_verified': False,
        'trace_mode_consistent': False,
        'trace_steps_verified': False,
    }
    params, error = validated_request(request)
    if error or params is None:
        result['reason'] = 'request_validation_failed'
        return result
    # This verifies internal trace *consistency*, NOT that an editable JSON
    # export came from a real API provider. Provider-side verification needs
    # independently obtained billing/request logs or signed server evidence.
    # Accept only success traces produced by the implemented tool orchestration.
    # The deterministic path has a fixed order; LLM paths may choose tool order
    # but are bounded by the same limits as run_llm_agent().
    if (not trace or any(not isinstance(x, dict) for x in trace)
            or trace[0].get('tool') != 'request_validation'):
        result['reason'] = 'invalid_trace_structure'
        return result
    records = trace
    known_success_tools = {'request_validation', 'search_evidence', 'find_recipes',
                           'evaluate_models', 'audit_casebook'}
    if any(not isinstance(entry.get('tool'), str) or
           entry['tool'] not in known_success_tools for entry in records):
        result['reason'] = 'unexpected_or_failed_tool_step'
        return result
    if (len(records) > (5 if mode == 'Deterministic tools' else 17)
            or any(not {'tool', 'input', 'result'}.issubset(x) for x in records)):
        result['reason'] = 'invalid_trace_structure'
        return result
    checks = [x for x in records if x.get('tool') == 'request_validation']
    if len(checks) != 1 or not isinstance(checks[0].get('result'), dict):
        result['reason'] = 'request_validation_not_documented'
        return result
    preflight = checks[0]
    metadata = preflight['result']
    required_metadata = {'parsed', 'locked', 'execution_origin', 'api_responses_received'}
    if (set(metadata) != required_metadata or not _same_json_value(metadata.get('parsed'), params)
            or metadata.get('locked') is not True):
        result['reason'] = 'request_validation_not_documented'
        return result
    # Compare the original input, not merely its parsed constraints. Strict
    # recursive value comparison permits legitimate finite NumPy real scalars
    # while rejecting bool/int substitution, extra keys and edited text.
    if not _same_json_value(request, preflight['input']):
        result['reason'] = 'original_request_trace_mismatch'
        return result
    if mode == 'Deterministic tools' and [x['tool'] for x in records] != [
            'request_validation', 'search_evidence', 'find_recipes',
            'evaluate_models', 'audit_casebook']:
        result['reason'] = 'deterministic_trace_sequence_mismatch'
        return result
    origin = checks[0]['result'].get('execution_origin')
    roundtrips = checks[0]['result'].get('api_responses_received')
    origin_by_mode = {
        'Deterministic tools': 'RULE_BASED',
        'Mock LLM protocol': 'INJECTED_CLIENT',
        'LLM tool-calling': 'OPENAI_SDK_CLIENT',
    }
    expected_roundtrips = (isinstance(roundtrips, int) and
                           not isinstance(roundtrips, bool) and
                           (roundtrips == 0 if mode == 'Deterministic tools' else 1 <= roundtrips <= 6))
    if origin != origin_by_mode[mode] or not expected_roundtrips:
        result['reason'] = 'execution_mode_or_transport_mismatch'
        return result
    result['trace_mode_consistent'] = True
    # Every successful tool record is untrusted until recomputed, including
    # optional CV diagnostics and casebook results. This is an internal
    # consistency check, never independent authentication of editable JSON.
    # Reject unexpected inputs for the no-argument tools as well.
    mismatches = {
        'search_evidence': 'evidence_trace_mismatch',
        'find_recipes': 'recipe_tool_trace_mismatch',
        'evaluate_models': 'model_tool_trace_mismatch',
        'audit_casebook': 'casebook_tool_trace_mismatch',
    }
    for record in records[1:]:
        name = record['tool']
        args = record['input']
        if (not isinstance(args, dict) or
                (name in ('evaluate_models', 'audit_casebook') and args)):
            result['reason'] = mismatches[name]
            return result
        try:
            expected = _recompute_for_audit(name, args, params)
        except Exception:
            # Data corruption or unexpected analysis failures must never
            # produce a green audit state or an unverified report.
            result['reason'] = 'tool_recomputation_failed'
            return result
        if not _same_json_value(record['result'], expected):
            result['reason'] = mismatches[name]
            return result
    result['trace_steps_verified'] = True
    evidence = [x for x in records if x['tool'] == 'search_evidence'
                and isinstance(x['result'], list) and x['result']]
    recipes = [x for x in records if x['tool'] == 'find_recipes'
               and isinstance(x['result'], dict) and 'error' not in x['result']]
    result['evidence_retrieved'] = bool(evidence)
    result['locked_recipe_queried'] = bool(recipes)
    if not evidence or not recipes:
        result['reason'] = 'missing_evidence_or_recipe'
        return result
    # One invalid attempted tool call poisons the workflow even if an earlier
    # result was valid. Don't present a subsequently recovered run as verified.
    if any(isinstance(x.get('result'), dict) and 'error' in x['result']
           for x in records):
        result['reason'] = 'tool_or_integrity_error'
        return result
    for record in recipes:
        try:
            trusted = _trusted_report(record['result'], params)
        except (ValueError, KeyError, TypeError, OverflowError):
            continue
        endings = ((DETERMINISTIC_FOOTER,) if mode == 'Deterministic tools'
                   else ('', UNVERIFIED_LLM_NOTICE))
        if report in {trusted + tail for tail in endings}:
            result['status'] = 'ENGINEERING_REPORT_VERIFIED'
            result['validated_report'] = True
            result['reason'] = 'final_report_recomputed_from_measured_data'
            return result
    result['reason'] = 'final_report_or_recipe_mismatch'
    return result


def _redact_nonfinite_for_export(value: Any, count: list[int]) -> Any:
    """Export JSON-safe evidence without coercing invalid types into readings.

    This sanitizes only the *export copy*. Request validation and the audit
    operate on the original object. Invalid NumPy booleans/complex values are
    preserved as explicit type markers, never 1.0 or a discarded imaginary part.
    """
    if isinstance(value, np.bool_):
        count[0] += 1
        return {'invalid_input_type': 'numpy.bool', 'original_repr': repr(value)}
    if isinstance(value, (complex, np.complexfloating)):
        count[0] += 1
        return {'invalid_input_type': type(value).__name__, 'original_repr': repr(value)}
    if isinstance(value, bool):
        return value
    if isinstance(value, Real):
        try:
            finite = math.isfinite(value)
        except (TypeError, ValueError, OverflowError):
            finite = False
        if not finite:
            count[0] += 1
            return '[INVALID_NUMBER]'
        if isinstance(value, (np.integer, np.floating)):
            # Preserve integer semantics; avoid turning measured cycle counts
            # into floating-point values by using json default=float.
            return value.item()
        return value
    if isinstance(value, dict):
        return {key: _redact_nonfinite_for_export(item, count)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_nonfinite_for_export(item, count) for item in value]
    if isinstance(value, (str, type(None))):
        return value
    count[0] += 1
    return {'invalid_input_type': type(value).__name__, 'original_repr': repr(value)[:240]}


def trace_download_json(mode: str, request: str | dict, report: str,
                        trace: list[dict]) -> str:
    """Exact audit export; redact nonfinite invalid input only in JSON copy."""
    summary = audit_execution(mode, request, report, trace)
    payload = {
        'schema_version': '1.0', 'audit': summary,
        'request': request, 'trace': trace,
        'note': ('실행 기록은 사용자가 편집할 수 있는 JSON으로 독립적인 API 호출 증명이 아닙니다. '
                 '모의 LLM은 실제 API 호출 증거가 아닙니다. '
                 'REVIEW_REQUIRED는 실험/양산 공정 승인 상태가 아닙니다.'),
    }
    redactions = [0]
    export_payload = _redact_nonfinite_for_export(payload, redactions)
    if redactions[0]:
        export_payload['export_redaction'] = {
            'invalid_numbers_redacted': redactions[0],
            'reason': 'invalid_input_types_or_nonfinite_numbers_not_exportable_as_measurements',
        }
        # A malformed or tampered trace must never carry a verified badge in
        # a downloaded record after sanitization, even if another audit path
        # mistakenly marked it as verified before encountering these values.
        export_payload['audit'] = dict(export_payload['audit'])
        export_payload['audit'].update({
            'status': 'BLOCKED_OR_INCOMPLETE',
            'validated_report': False,
            'trace_steps_verified': False,
            'reason': 'nonfinite_value_redacted_before_export',
        })
    return json.dumps(export_payload, ensure_ascii=False, indent=2,
                      allow_nan=False)
