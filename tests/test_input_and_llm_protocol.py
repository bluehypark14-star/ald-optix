"""Input and llm protocol — software regression tests."""
from __future__ import annotations
import copy
import json
from types import SimpleNamespace
import pytest
import core
from core import (parse_request, request_scope_error, optimize_recipe,
                  constraint_check, quality_gate, sensitivity_analysis, engineering_casebook)
from agent import validated_request, dispatch_tool, deterministic_demo, run_llm_agent

@pytest.mark.parametrize('input_request,field,expected',[
    ('Al2O3 10nm, purge는 최소 20초 이상, 시퀀스 시간 최소화','min_purge',20),
    ('Al2O3 10nm, Ar 유량 20sccm만 사용','min_flow',20),
    ('Al2O3 10nm, pulse 40ms만 사용','min_pulse',40),
    ('Al2O3 10nm, 최대 200°C','max_temp',200),
    ('Al2O3 10nm, 최대 200 C','max_temp',200),
    ('Al2O3 10nm, 200도 이상','min_temp',200),
    ('Al2O3 10nm, purge 10초 이하','max_purge',10),
])
def test_language_request_constraints_actually_change_optimizer(input_request,field,expected):
    parsed=parse_request(input_request)
    assert 'warning' not in parsed
    assert parsed[field]==expected
    reply,trace=deterministic_demo(input_request)
    assert trace[0]['result']['locked'] is True
    outcome=next(t['result'] for t in trace if t['tool']=='find_recipes')
    assert 'error' not in outcome
    assert not constraint_check(outcome['best'],**{k:v for k,v in parsed.items() if k not in ('target_nm','objective')})

@pytest.mark.parametrize('user_query',[ 
    'Ta2O5 박막 10nm', 'SnO2 박막 10nm','CoO 박막 10nm','HfO2 박막 10nm',
    'ZnO 박막 10nm','GaN 박막 10nm', '10nm 막을 만들어줘',
    'Al2O3 10nm purge가 15초 이상 10초 이하',
    'Al2O3 10nm 압력 1 Torr 조건',
    'Al2O3 10nm 퍼지 15초만',
    'Al2O3 10nm, 온도 올려줘',
])
def test_unsupported_or_ambiguous_request_never_recommends(user_query):
    response,trace=deterministic_demo(user_query)
    assert '검증 중단' in response
    assert len(trace)==1
    assert 'error' in trace[0]['result']


def test_pulse_range_is_honored_in_optimization_and_quality_gate():
    chosen=optimize_recipe(10,min_pulse=40,max_pulse=40)
    assert 'error' not in chosen
    assert chosen['best']['pulse_ms']==40
    assert quality_gate({'target_nm':10,'min_pulse':40,'max_pulse':40},chosen['best'])['status']=='REVIEW_REQUIRED'
    tampered=dict(chosen['best']);tampered['pulse_ms']=20
    assert quality_gate({'target_nm':10,'min_pulse':40},tampered)['status']=='REJECT'


def test_sensitivity_preserves_all_user_constraints_and_no_leaky_max_purge():
    r=sensitivity_analysis(10,600,max_temp=200,min_purge=10,
                           min_flow=20,max_flow=20,max_purge=10,min_pulse=40,max_pulse=40)
    assert 'error' not in r
    assert r['best']['purge_s']==10 and r['best']['pulse_ms']==40
    assert r['best']['flow_sccm']==20 and r['best']['temperature_C']==175
    assert 'error' in sensitivity_analysis(10,600,max_purge=10,min_purge=20)


def test_strict_numeric_input_validation():
    for invalid in (float('nan'),float('inf'),True, '10'):
        assert 'error' in optimize_recipe(target_nm=invalid)
    assert 'error' in optimize_recipe(10,min_pulse=40,max_pulse=20)
    assert 'error' in optimize_recipe(10,min_temp=275,max_temp=175)


def test_independent_oracle_catches_optimizer_regression(monkeypatch):
    assert all(x['v1_pass'] for x in engineering_casebook())
    original=core.optimize_recipe
    def faulty(*a,**kw):
        result=original(*a,**kw)
        if 'best' in result:
            result['best']=dict(result['best'])
            result['best']['temperature_C']=999
        return result
    monkeypatch.setattr(core,'optimize_recipe',faulty)
    assert not all(x['v1_pass'] for x in engineering_casebook())


def test_untrusted_tool_args_cannot_override_locked_user_request():
    params,error=validated_request('Al2O3 10nm purge는 최소 20초 이상 Ar 유량 20sccm만')
    assert error is None
    reject=dispatch_tool('find_recipes',{'min_purge':10},locked_request=params)
    assert 'error' in reject and '완화 거부' in reject['error']
    result=dispatch_tool('find_recipes',{},locked_request=params)
    assert result['best']['purge_s']==20 and result['best']['flow_sccm']==20
    assert 'error' in dispatch_tool('find_recipes',{'max_temp':float('nan')},locked_request=params)
    assert 'error' in dispatch_tool('find_recipes',{'fake':5},locked_request=params)
    assert 'error' in dispatch_tool('arbitrary_python',{},locked_request=params)

class MockMessage:
    def __init__(self,calls=None,content=''):
        self.tool_calls=calls or []
        self.content=content
    def model_dump(self,exclude_none=True):
        return {'role':'assistant','content':self.content,'tool_calls':[
            {'id':c.id,'type':'function','function':{'name':c.function.name,'arguments':c.function.arguments}}
            for c in self.tool_calls]}

def tool_call(name,args,index):
    return SimpleNamespace(id=f'call_{index}',function=SimpleNamespace(name=name,arguments=json.dumps(args)))

class FakeClient:
    def __init__(self, replies):
        self.queue=list(replies)
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.generate))
        self.calls=0
    def generate(self,**kwargs):
        self.calls+=1
        return SimpleNamespace(choices=[SimpleNamespace(message=self.queue.pop(0))])


def test_offline_mock_llm_tool_protocol_executes_and_shows_trusted_report():
    req='Al2O3 10nm purge 최소 20초 시간 최소화'
    client=FakeClient([
       MockMessage([tool_call('search_evidence',{'query':'Al2O3 GPC'},1),tool_call('find_recipes',{},2)]),
       MockMessage([],content='추가 실험이 필요합니다.'),
    ])
    response,trace=run_llm_agent(req,api_key='fake',client=client)
    assert client.calls==2
    assert [x['tool'] for x in trace]==['request_validation','search_evidence','find_recipes']
    assert trace[-1]['result']['best']['purge_s']==20
    assert 'ALD-OPTIX 공정 검토 리포트' in response
    assert 'LLM 생성 해석 초안' in response


def test_offline_mock_llm_cannot_loosen_purge_constraints():
    req='Al2O3 10nm purge 최소 20초'
    client=FakeClient([
        MockMessage([tool_call('search_evidence',{'query':'Al2O3'},1),
                     tool_call('find_recipes',{'min_purge':10},2)]),
        MockMessage([],content='안전하지 않은 추천'),
    ])
    response,trace=run_llm_agent(req,api_key='fake',client=client)
    assert '검증 중단' in response
    assert '완화 거부' in trace[-1]['result']['error']


def test_offline_mock_llm_cannot_skip_tool_calls():
    client=FakeClient([MockMessage([tool_call('search_evidence',{'query':'GPC'},1)]),MockMessage([],content='임의 답변')])
    response,trace=run_llm_agent('Al2O3 10nm',api_key='fake',client=client)
    assert '검증 중단' in response

@pytest.mark.parametrize('input_request',[
    'Al2O3 -10nm 시간 최소화',
    'Al2O3 10nm purge -10초',
    'Al2O3 10nm purge 10s',
    'Al2O3 10nm 200K',
    'Al2O3 10nm Ar 5sccm',
    'Al2O3 10nm 20nm',
])
def test_unparsed_quantity_or_invalid_unit_fails_closed(input_request):
    params,error=validated_request(input_request)
    assert params is None and error


def test_report_marks_baseline_non_comparable_when_constraints_violated():
    from agent import deterministic_demo
    report,_=deterministic_demo('Al2O3 10nm Ar 20sccm만')
    assert '[비교 제한]' in report
    report2,_=deterministic_demo('Al2O3 10nm')
    assert '[단순화 수식 내 비교]' in report2
