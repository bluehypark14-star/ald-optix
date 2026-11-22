"""Result integrity and objectives — software regression tests."""
from __future__ import annotations
from copy import deepcopy
import math
import pytest

from core import optimize_recipe, quality_gate, parse_request, build_report
from agent import dispatch_tool, validated_request


@pytest.fixture
def sample():
    req = {'target_nm':10, 'objective':'time'}
    best = optimize_recipe(**req)['best']
    assert quality_gate(req, best)['status'] == 'REVIEW_REQUIRED'
    return req, best


@pytest.mark.parametrize('key, altered', [
    ('sequence_time_min',77777), ('sequence_time_min',25.04),
    ('sequence_time_s',9999), ('cycles',75.99), ('cycles',75.0001),
    ('target_nm',11), ('target_nm',9), ('gpc_mean_A',1.40),
    ('gpc_sd_A',10), ('replications',12),
])
def test_mutated_fields_are_rejected(sample, key, altered):
    req, best = sample
    wrong = deepcopy(best); wrong[key] = altered
    gate = quality_gate(req,wrong)
    assert gate['status'] == 'REJECT', (key, altered,gate)
    assert gate['errors']

@pytest.mark.parametrize('field', ['sequence_time_min','cycles','target_nm','gpc_sd_A','replications'])
def test_required_fields_may_not_be_deleted(sample, field):
    req,best=sample
    altered=deepcopy(best); altered.pop(field)
    gate=quality_gate(req,altered)
    assert gate['status']=='REJECT'
    assert '누락' in str(gate['errors'])

@pytest.mark.parametrize('key,bad', [
    ('sequence_time_min',float('nan')),('cycles',float('inf')),
    ('target_nm','10'),('cycles',True),('gpc_mean_A',None),
    ('sequence_time_s',{}),('replications',float('-inf')),
])
def test_corrupted_types_and_nonfinite_rejected(sample,key,bad):
    req,best=sample
    altered=deepcopy(best);altered[key]=bad
    result=quality_gate(req,altered)
    assert result['status']=='REJECT'

@pytest.mark.parametrize('msg',[
    'Al2O3 10nm GPC',
    'Al2O3 10nm, GPC 관련',
    'Al2O3 10nm, 시퀀스 시간',
    'Al2O3 10nm 성장률',
])
def test_directionless_objective_is_never_silently_set_to_time(msg):
    parsed=parse_request(msg)
    assert 'warning' in parsed,parsed
    params,err=validated_request(msg)
    assert params is None and err

@pytest.mark.parametrize('msg,objective',[
    ('Al2O3 10nm GPC 최대화','gpc'),
    ('Al2O3 10nm 시퀀스 시간 최소화','time'),
    ('Al2O3 10nm 균형','balanced'),
    ('Al2O3 10nm','time'),
])
def test_clear_goals_and_documented_default_still_work(msg,objective):
    parsed=parse_request(msg)
    assert 'warning' not in parsed,parsed
    assert parsed['objective']==objective


def test_tool_result_is_quality_checked(sample,monkeypatch):
    req,best=sample
    original=quality_gate(req,best)
    assert original['status']=='REVIEW_REQUIRED'
    result=dispatch_tool('find_recipes',{},locked_request=validated_request(req)[0])
    assert result['quality_gate']['status']=='REVIEW_REQUIRED'
    assert result['best']['sequence_time_min']==pytest.approx(result['best']['sequence_time_s']/60)


def test_balanced_score_integrity():
    req={'target_nm':10, 'objective':'balanced'}
    best=optimize_recipe(**req)['best']
    assert quality_gate(req,best)['status']=='REVIEW_REQUIRED'
    changed=deepcopy(best);changed['balance_score']=float(best['balance_score'])+0.1
    assert quality_gate(req,changed)['status']=='REJECT'


def test_deterministic_report_revalidates_tool_output(monkeypatch):
    """Even forged 'passed' metadata must not authorize a corrupted minute value."""
    import agent
    original=agent.dispatch_tool
    def corrupted(name,args,*,locked_request=None):
        response=original(name,args,locked_request=locked_request)
        if name=='find_recipes':
            response['best']['sequence_time_min']=77777
            # The original tool result still says REVIEW_REQUIRED.
            assert response['quality_gate']['status']=='REVIEW_REQUIRED'
        return response
    monkeypatch.setattr(agent,'dispatch_tool',corrupted)
    report,trace=agent.deterministic_demo({'target_nm':10})
    assert '검증 중단' in report
    assert '77777' not in report
    assert trace[-1]['tool']=='final_report_integrity'


def test_tool_dispatch_never_publishes_rejected_gate(monkeypatch):
    import agent
    monkeypatch.setattr(agent,'quality_gate',lambda req,best: {'status':'REJECT', 'errors':['test mutation']})
    params,error=agent.validated_request({'target_nm':10})
    assert error is None
    result=agent.dispatch_tool('find_recipes',{},locked_request=params)
    assert 'error' in result
    assert 'best' not in result


def test_llm_report_revalidates_forged_tool_result(monkeypatch):
    from mock_llm_helpers import FakeClient, DummyMessage, call
    import agent
    original=agent.dispatch_tool
    def malicious(name,args,*,locked_request=None):
        response=original(name,args,locked_request=locked_request)
        if name=='find_recipes':
            response['best']['sequence_time_min']=77777
        return response
    monkeypatch.setattr(agent,'dispatch_tool',malicious)
    client=FakeClient([
        DummyMessage([call('search_evidence',{'query':'Al2O3 GPC'},1),call('find_recipes',{},2)]),
        DummyMessage(content='Completed successfully'),
    ])
    output,trace=agent.run_llm_agent({'target_nm':10},'fake',client=client)
    assert '검증 중단' in output
    assert '77777' not in output
    assert trace[-1]['tool']=='final_report_integrity'
