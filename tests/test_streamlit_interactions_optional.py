"""Streamlit interactions optional — software regression tests."""
from pathlib import Path
import pytest

pytest.importorskip('streamlit', reason='Streamlit unavailable: run in GitHub Actions/Mac')
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'app.py'


def started():
    state=AppTest.from_file(str(APP),default_timeout=120).run()
    assert not state.exception, [str(getattr(x, "message", x)) for x in state.exception]
    assert len(state.tabs)==5
    return state


def control(state,kind,label):
    candidates=[item for item in getattr(state,kind) if item.label==label]
    assert len(candidates)==1,(kind,label,[(x.label) for x in getattr(state,kind)])
    return candidates[0]


def session_record(state):
    try:
        return state.session_state['last_workflow']
    except KeyError:
        return None


def test_studio_initial_then_150C_refusal():
    state=started()
    assert any('1.340' in x.value for x in state.metric)
    control(state,'slider','최대 증착 온도 (°C)').set_value(150).run()
    assert not state.exception
    assert any('요청 거부' in x.value for x in state.error)
    assert not any('선택된 공정 후보' in x.value for x in state.markdown)


def test_structured_workflow_and_trace_download_visible():
    state=started()
    control(state,'button','워크플로 실행').click().run()
    assert not state.exception
    rec=session_record(state)
    assert rec is not None
    assert rec['request']['max_temp']==200
    assert rec['mode']=='Deterministic tools'
    assert 'ALD-OPTIX 공정 검토' in rec['response']
    assert any(r['tool']=='find_recipes' for r in rec['trace'])
    assert any('계산 보고서 검증 완료' in x.value for x in state.success)


def test_stale_workflow_hidden_after_request_change():
    state=started()
    control(state,'button','워크플로 실행').click().run()
    assert session_record(state) is not None
    control(state,'selectbox','최대 온도 (°C) · 워크플로').set_value(150).run()
    assert not state.exception
    assert session_record(state) is None
    assert any('요청 사전 검증' in x.value for x in state.warning)
    control(state,'button','워크플로 실행').click().run()
    assert not state.exception
    assert '검증 중단' in session_record(state)['response']


def test_objective_gpc_is_distinct_from_time_in_workflow():
    state=started()
    control(state,'selectbox','최적화 목표 · 워크플로').set_value('gpc').run()
    control(state,'button','워크플로 실행').click().run()
    assert not state.exception
    rec=session_record(state)
    assert rec['request']['objective']=='gpc'
    best=next(x['result']['best'] for x in rec['trace'] if x['tool']=='find_recipes')
    assert best['gpc_mean_A']==pytest.approx(1.410)


def test_natural_language_refuses_unknown_conditions():
    state=started()
    control(state,'radio','요청 입력 방식').set_value('제한된 자연어 입력').run()
    control(state,'text_area','공정 엔지니어 업무 요청 (지원 범위 제한)').set_value(
        'Al2O3 10nm, 새로운 산화제를 쓰자').run()
    assert not state.exception
    assert any('요청 사전 검증' in x.value for x in state.warning)
    control(state,'button','워크플로 실행').click().run()
    assert not state.exception
    rec=session_record(state)
    assert rec is not None and '검증 중단' in rec['response']
    assert not any(r['tool']=='find_recipes' for r in rec['trace'])
