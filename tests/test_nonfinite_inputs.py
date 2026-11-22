"""Nonfinite inputs — software regression tests."""
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from core import sensitivity_analysis
from agent import run_llm_agent
from exports import trace_download_json
from mock_llm_helpers import DummyMessage, FakeClient
from types import SimpleNamespace


def test_json_numeric_exponent_overflow_keeps_failed_llm_trace_downloadable():
    bad = SimpleNamespace(
        id='call_1',
        function=SimpleNamespace(name='find_recipes', arguments='{"target_nm": 1e999}')
    )
    client = FakeClient([DummyMessage([bad]), DummyMessage(content='done')])
    request = {'target_nm': 10}
    report, trace = run_llm_agent(request, 'fake', client=client)
    assert '검증 중단' in report
    # Even failed workflows must produce well-formed downloadable JSON logs.
    output = trace_download_json('Mock LLM protocol', request, report, trace)
    assert 'Infinity' not in output and 'NaN' not in output


def test_sensitivity_analysis_rejects_boolean_overhead():
    # True is a Boolean, not a user-provided 1-second overhead.
    with pytest.raises(ValueError):
        sensitivity_analysis(overhead_s_per_cycle=True)
