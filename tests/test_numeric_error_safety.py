"""Numeric error safety — software regression tests."""
import json
import math
from types import SimpleNamespace
import numpy as np
import pytest
from agent import run_llm_agent
from core import sensitivity_analysis
from exports import trace_download_json
from mock_llm_helpers import DummyMessage, FakeClient


def mock_call(raw_args):
    bad = SimpleNamespace(id='call_1', function=SimpleNamespace(name='find_recipes', arguments=raw_args))
    return FakeClient([DummyMessage([bad]), DummyMessage(content='done')])


@pytest.mark.parametrize('raw_args', [
    '{"target_nm":1e999}',
    '{"target_nm":-1e999}',
    '{"target_nm":1e309}',
    '{"target_nm":NaN}',
    '{"target_nm":Infinity}',
    '{"target_nm":-Infinity}',
    '{"target_nm":10,"irrelevant":[-1e999]}',
    '{"target_nm":10,"irrelevant":{"deep":1e999}}',
])
def test_nonfinite_llm_arguments_are_rejected_and_trace_downloadable(raw_args):
    request={'target_nm':10}
    report, trace=run_llm_agent(request,'fake',client=mock_call(raw_args))
    assert '검증 중단' in report
    assert trace[-1]['result'].get('error')
    payload=trace_download_json('Mock LLM protocol', request, report, trace)
    parsed=json.loads(payload, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    assert parsed['audit']['validated_report'] is False
    assert 'Infinity' not in payload and 'NaN' not in payload


@pytest.mark.parametrize('value', [True, False, None, '10', '0', float('nan'),
                                   float('inf'), -float('inf'), complex(1, 0),
                                   -1, 601, 10**400, np.bool_(True)])
def test_sensitivity_bad_overhead_rejected_as_value_error(value):
    with pytest.raises(ValueError):
        sensitivity_analysis(overhead_s_per_cycle=value)


def test_sensitivity_valid_boundaries_and_numpy_number():
    for value in [0, 600, 1.5, np.float64(1), np.float32(3)]:
        result=sensitivity_analysis(overhead_s_per_cycle=value)
        assert 'best' in result
        assert math.isfinite(result['best']['estimated_total_s'])


@pytest.mark.parametrize('bad_value', [float('nan'),float('inf'),-float('inf')])
def test_structured_nonfinite_request_failure_can_be_downloaded(bad_value):
    request={'target_nm':bad_value}
    report, trace=run_llm_agent(request,'fake',client=mock_call('{}'))
    assert '검증 중단' in report
    output=json.loads(trace_download_json('Mock LLM protocol', request, report, trace))
    assert output['audit']['validated_report'] is False
    assert output['export_redaction']['invalid_numbers_redacted'] >= 1
    assert output['request']['target_nm']=='[INVALID_NUMBER]'
    assert output['audit']['reason']=='nonfinite_value_redacted_before_export'


def test_successful_healthy_trace_not_redacted():
    from agent import deterministic_demo
    request={'target_nm':10}
    report,trace=deterministic_demo(request)
    payload=json.loads(trace_download_json('Deterministic tools',request,report,trace))
    assert payload['audit']['validated_report'] is True
    assert 'export_redaction' not in payload
