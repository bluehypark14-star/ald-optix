"""Request scope and ui state — software regression tests."""
from pathlib import Path
import pytest

from agent import validated_request, deterministic_demo
from core import parse_request
from ui_state import workflow_is_current


@pytest.mark.parametrize('user_text', [
    'Al2O3 10nm, 혼합비 바꿔줘',
    'Al2O3 10nm, TMA와 물의 비율을 높여줘',
    'Al2O3 10nm, 기판을 glass로 바꿔줘',
    'Al2O3 10nm, 공정 환경 변경해줘',
    'Al2O3 10nm, 10% 허용 오차',
    'Al2O3 10nm, 목표 두께 허용 오차 ±0.5nm',
    'Al2O3 10nm, 1Å 막두께',
    'Al2O3 10nm, 가스 혼합비를 2:1로',
    'Al2O3 10nm, 기판 재료를 바꾸고 싶어',
    'Al2O3 10nm, 증착 압력 바꿔줘',
    'Al2O3 10nm, Si 기판 말고 유리 기판',
    'Al2O3 10nm, precursor ratio 조정',
])
def test_unknown_critical_requirements_fail_closed(user_text):
    params, error = validated_request(user_text)
    assert params is None and error, user_text
    response, trace = deterministic_demo(user_text)
    assert '검증 중단' in response and len(trace) == 1


@pytest.mark.parametrize('user_text,field,value', [
    ('Al2O3 10nm, 시퀀스 시간 최소화', 'objective', 'time'),
    ('Al2O3 10nm, GPC 최대화', 'objective', 'gpc'),
    ('Al2O3 10nm, 최대 200 C purge 최소 20초', 'max_temp', 200.0),
    ('Al2O3 10nm, Ar 유량 20sccm만', 'min_flow', 20.0),
    ('Al2O3 10nm, 40ms pulse', 'min_pulse', 40.0),
])
def test_supported_intents_still_pass(user_text, field, value):
    params, error = validated_request(user_text)
    assert error is None
    assert params[field] == value


def test_cached_workflow_belongs_only_to_exact_request_and_mode():
    artifact = {'request':'Al2O3 10nm', 'mode':'Deterministic tools',
                'response':'OK', 'trace':[{'tool':'request_validation'}]}
    assert workflow_is_current(artifact, 'Al2O3 10nm', 'Deterministic tools')
    assert not workflow_is_current(artifact, 'Al2O3 20nm', 'Deterministic tools')
    assert not workflow_is_current(artifact, 'Al2O3 10nm', 'LLM tool-calling')
    assert not workflow_is_current(('old response', [], 'Deterministic tools'), 'Al2O3 10nm','Deterministic tools')
    assert not workflow_is_current(None, 'Al2O3 10nm','Deterministic tools')


def test_document_links_reference_existing_project_files():
    root=Path(__file__).resolve().parents[1]
    assert (root/'docs'/'validation.md').is_file()
    assert (root/'README.md').is_file()
    assert (root/'site'/'index.html').is_file()
