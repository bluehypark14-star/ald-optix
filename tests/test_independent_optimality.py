"""Independent optimality — software regression tests."""
from __future__ import annotations
import math
from pathlib import Path
import pandas as pd
import pytest
import core
from agent import validated_request, deterministic_demo, dispatch_tool, run_llm_agent
from core import optimize_recipe, quality_gate, independent_reference, parse_request, search_evidence
from test_input_and_llm_protocol import MockMessage, FakeClient, tool_call


@pytest.mark.parametrize('user_request', [
    'Al2O3 10nm, TMA/H2O 1:2 비율',
    'Al2O3 10nm, TMA/H2O 1:2',
    'Al2O3 10nm, H2O 1:2 반응비',
    'Al2O3 10nm, TMA/H2O 2:1',
    'Al2O3 10nm, 막 두께 균일하게',
    'Al2O3 10nm, roughness 낮춰줘',
    'Al2O3 10nm, 기판 면저항 낮게',
    'Al2O3 10nm, Cu 첨가',
    'Al2O3 10nm, 원자량 줄여줘',
    'Al2O3 10nm, 반응기 A 사용',
    'Al2O3 10nm, 내년 여름까지',
    'Al2O3 10nm, TMA/H2O 2.5:1',
    'Al2O3 10nm, 임의 숫자 3',
])
def test_out_of_scope_constraints_cannot_be_discarded(user_request):
    structured, error=validated_request(user_request)
    assert structured is None and error, user_request
    text, calls=deterministic_demo(user_request)
    assert '검증 중단' in text and len(calls)==1


@pytest.mark.parametrize('user_request,expect', [
    ('Al2O3 10nm', {'target_nm':10.,'objective':'time'}),
    ('Al2O3 10nm, purge 최소 20초', {'min_purge':20.}),
    ('Al2O3 10nm, Ar 20 sccm만', {'min_flow':20.,'max_flow':20.}),
    ('Al₂O₃ 10 nm 최대 200°C', {'max_temp':200.}),
    ('Al2O3 10nm, GPC 최대화', {'objective':'gpc'}),
    ('Al2O3 10nm, 시퀀스 시간 최소화', {'objective':'time'}),
    ('Al2O3 10nm, 균형', {'objective':'balanced'}),
])
def test_supported_requests_remain_usable(user_request,expect):
    p,err=validated_request(user_request)
    assert err is None,err
    for key,val in expect.items():
        assert p[key]==val,(user_request,key,p[key],val)


@pytest.mark.parametrize('target', [0.1, 5, 10, 20])
@pytest.mark.parametrize('objective', ['time','gpc','balanced'])
@pytest.mark.parametrize('max_temp,min_purge', [(175,10),(200,20),(275,10),(275,20)])
def test_all_objectives_match_independent_raw_csv_oracle(target,objective,max_temp,min_purge):
    req={'target_nm':target,'max_temp':max_temp,'min_purge':min_purge,'objective':objective}
    py=optimize_recipe(**req)
    oracle=independent_reference(req)
    assert 'error' not in py
    assert py['n_feasible']==oracle['n_feasible']
    for k in (*core.VAR_NAMES,'sequence_time_s','gpc_mean_A'):
        assert math.isclose(float(py['best'][k]),float(oracle['best'][k]),abs_tol=1e-7)
    assert quality_gate(req,py['best'])['status']=='REVIEW_REQUIRED'


def test_measured_but_suboptimal_recipe_rejected():
    req={'target_nm':10,'objective':'time'}
    result=optimize_recipe(**req)
    deliberately_wrong=result['ranking'].iloc[-1].to_dict()
    gate=quality_gate(req,deliberately_wrong)
    assert gate['status']=='REJECT'
    assert any('최상위 후보' in e for e in gate['errors'])


def test_data_fingerprint_detects_positive_silent_alteration(tmp_path,monkeypatch):
    data=pd.read_csv(core.DATA_FILE)
    data.loc[0,'gpc_A_per_cycle']=1.99  # positive/finite but NOT the published value
    target=tmp_path/'rewritten.csv'
    data.to_csv(target,index=False)
    monkeypatch.setattr(core,'DATA_FILE',target)
    with pytest.raises(ValueError,match='fingerprint'):
        core.load_data()


def test_evidence_search_cannot_invent_relevance():
    assert search_evidence('unrelatedbanana')==[]
    assert search_evidence('Al2O3 10nm')
    assert search_evidence('purge')
    assert search_evidence('')==[]
    assert dispatch_tool('search_evidence',{'query':'unrelatedbanana'})==[]


def test_llm_unrelated_evidence_never_authorizes_final_report():
    client=FakeClient([
        MockMessage([tool_call('search_evidence',{'query':'unrelatedbanana'},1),
                     tool_call('find_recipes',{},2)]),
        MockMessage([],content='I have proof, trust me!'),
    ])
    reply,trace=run_llm_agent('Al2O3 10nm',api_key='fake',client=client)
    assert '검증 중단' in reply
    assert not any('LLM 생성 해석 초안' in x for x in [reply])

@pytest.mark.parametrize('malformed',[float('nan'),float('inf'),'not-a-number',None])
def test_quality_gate_rejects_malformed_recipe_without_crashing(malformed):
    candidate=dict(optimize_recipe(10)['best'])
    candidate['temperature_C']=malformed
    outcome=quality_gate({'target_nm':10,'objective':'time'},candidate)
    assert outcome['status']=='REJECT'
    assert outcome['errors']


def test_quality_gate_fails_closed_when_no_recipe():
    outcome=quality_gate({'target_nm':10},None)
    assert outcome['status']=='REJECT' and outcome['errors']
