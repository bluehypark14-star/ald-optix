"""Constraint completeness — software regression tests."""
from copy import deepcopy
import pytest

from core import optimize_recipe, quality_gate, parse_request
from agent import validated_request, deterministic_demo, run_llm_agent
from mock_llm_helpers import FakeClient, DummyMessage, call


@pytest.mark.parametrize('message', [
    'Al2O3 10nm 온도',
    'Al2O3 10nm, purge',
    'Al2O3 10nm, Ar 유량',
    'Al2O3 10nm pulse',
    'Al2O3 10nm, temperature',
    'Al2O3 10nm, Ar flow',
    'Al2O3 10nm, 200°C, purge',
    'Al2O3 10nm, 20초 purge, 온도',
    'Al2O3 10nm, 유량 20sccm, pulse',
    'Al2O3 10nm, 시퀀스 시간 최소화, 온도',
])
def test_bare_process_variable_fails_closed(message):
    parsed=parse_request(message)
    assert 'warning' in parsed, (message, parsed)
    request,error=validated_request(message)
    assert request is None and error
    report,trace=deterministic_demo(message)
    assert '검증 중단' in report
    assert len(trace)==1


@pytest.mark.parametrize('message,expected', [
    ('Al2O3 10nm', 'time'),
    ('Al2O3 10nm, 온도 최대 200°C', 'time'),
    ('Al2O3 10nm, Ar 유량 20sccm, GPC 최대화', 'gpc'),
    ('Al2O3 10nm, 최대 200°C, pulse 20ms, purge 20초', 'time'),
    ('Al2O3 10nm, purge 최소 20초, 균형', 'balanced'),
])
def test_quantified_inputs_remain_supported(message,expected):
    result=parse_request(message)
    assert 'warning' not in result, (message,result)
    assert result['objective']==expected


def test_balanced_score_is_mandatory():
    req={'target_nm':10,'objective':'balanced'}
    best=optimize_recipe(**req)['best']
    assert quality_gate(req,best)['status']=='REVIEW_REQUIRED'
    missing=deepcopy(best);missing.pop('balance_score')
    gate=quality_gate(req,missing)
    assert gate['status']=='REJECT'
    assert any('balance_score' in e or '균형' in e for e in gate['errors'])


def test_balanced_score_is_not_allowed_for_other_objectives():
    for objective in ['time','gpc']:
        req={'target_nm':10,'objective':objective}
        best=deepcopy(optimize_recipe(**req)['best'])
        best['balance_score']=0.0
        assert quality_gate(req,best)['status']=='REJECT'


@pytest.mark.parametrize('mutated', [None,'0.25',float('nan'),float('inf'),False])
def test_invalid_balanced_score_is_rejected(mutated):
    req={'target_nm':10,'objective':'balanced'}
    best=deepcopy(optimize_recipe(**req)['best'])
    best['balance_score']=mutated
    assert quality_gate(req,best)['status']=='REJECT'


def test_nonbalanced_report_is_normal():
    report,trace=deterministic_demo({'target_nm':10, 'objective':'time'})
    assert '추천 조건은' in report
    assert '검증 중단' not in report
    assert any(e.get('tool')=='find_recipes' for e in trace)


def test_balanced_report_rechecks_missing_score(monkeypatch):
    import agent
    original=agent.dispatch_tool
    def forged(name,args,*,locked_request=None):
        result=original(name,args,locked_request=locked_request)
        if name=='find_recipes':
            assert result['quality_gate']['status']=='REVIEW_REQUIRED'
            result['best'].pop('balance_score')
        return result
    monkeypatch.setattr(agent,'dispatch_tool',forged)
    report,trace=deterministic_demo({'target_nm':10,'objective':'balanced'})
    assert '검증 중단' in report
    assert trace[-1]['tool']=='final_report_integrity'


def test_llm_balanced_report_rechecks_missing_score(monkeypatch):
    import agent
    original=agent.dispatch_tool
    def forged(name,args,*,locked_request=None):
        result=original(name,args,locked_request=locked_request)
        if name=='find_recipes':
            assert result['quality_gate']['status']=='REVIEW_REQUIRED'
            result['best'].pop('balance_score')
        return result
    monkeypatch.setattr(agent,'dispatch_tool',forged)
    fake=FakeClient([
        DummyMessage([call('search_evidence',{'query':'Al2O3 GPC'},1),call('find_recipes',{},2)]),
        DummyMessage(content='Looks good')
    ])
    report,trace=run_llm_agent({'target_nm':10,'objective':'balanced'},'fake',client=fake)
    assert '검증 중단' in report
    assert trace[-1]['tool']=='final_report_integrity'
