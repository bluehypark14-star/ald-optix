"""Structured inputs and llm errors — software regression tests."""
from __future__ import annotations
import json
import math
from types import SimpleNamespace
import pytest
from core import validate_structured_request, parse_request, optimize_recipe, quality_gate
from agent import validated_request, deterministic_demo, run_llm_agent


@pytest.mark.parametrize('text', [
    'Al2O3 10nm 새로운 반응물 쓰자',
    'Al2O3 10nm, GPC가 좋아지게 해줘',
    'Al2O3 10nm 산화막을 더 튼튼하게 만들어줘',
    'Al2O3 10nm, 전기 절연 성능 좋게 부탁해',
    'Al2O3 10nm, 새로운 산화제 골라줘',
    'Al2O3 10nm 수분 함량을 줄이고 싶어',
    'Al2O3 10nm, 수율 높이자',
    'Al2O3 10nm, TMA/H2O 1:2',
    'Al2O3 10nm, 임의의 조건 추가해 줘',
])
def test_unknown_extra_intents_are_never_silently_discarded(text):
    out,err=validated_request(text)
    assert out is None and err, text
    result,trace=deterministic_demo(text)
    assert '검증 중단' in result and len(trace)==1


@pytest.mark.parametrize('text,values',[ 
    ('Al2O3 10nm', {'target_nm':10.0,'objective':'time'}),
    ('Al2O3 10nm 최대 200도 시간 최소화', {'max_temp':200.0}),
    ('Al2O3 10nm, Ar 유량 20sccm만, GPC 최대화', {'min_flow':20.0,'max_flow':20.0,'objective':'gpc'}),
    ('Al2O3 10nm, purge 최소 20초, 균형', {'min_purge':20.0,'objective':'balanced'}),
])
def test_supported_korean_inputs_still_work(text,values):
    out,err=validated_request(text)
    assert err is None,err
    for k,v in values.items():assert out[k]==v


@pytest.mark.parametrize('invalid',[ 
    {'target_nm':'ten'}, {'target_nm':True}, {'target_nm':None},
    {'target_nm':float('nan')}, {'max_temp':float('inf')},
    {'objective':'best'}, {'extra_constraint':123},
    {'min_purge':20,'max_purge':10},
    {'max_temp':150},
])
def test_typed_inputs_fail_closed(invalid):
    parsed=validate_structured_request(invalid)
    assert 'warning' in parsed
    params,err=validated_request(invalid)
    assert params is None and err


def test_typed_input_accepts_and_runs_same_optimization():
    vals={'target_nm':10,'max_temp':200, 'min_purge':20, 'objective':'gpc'}
    params,err=validated_request(vals)
    assert err is None,err
    direct=optimize_recipe(**params)
    report,trace=deterministic_demo(vals)
    tools={row['tool']:row['result'] for row in trace}
    assert not tools['find_recipes'].get('error')
    assert tools['find_recipes']['best']['gpc_mean_A']==direct['best']['gpc_mean_A']
    assert tools['search_evidence']
    assert '검증 중단' not in report


@pytest.mark.parametrize('bad_request',[None,'wrong','',float('nan'),{'target_nm':'n/a'},
                                         {'target_nm':float('inf')},{'target_nm':False},
                                         {'objective':'invalid'},{'max_temp':float('nan')}])
def test_quality_gate_never_crashes_on_bad_request(bad_request):
    recipe=optimize_recipe()['best']
    result=quality_gate(bad_request,recipe)
    assert result['status']=='REJECT' and result['errors']


class FailingClient:
    def __init__(self):
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def create(self,**kwargs):
        raise RuntimeError('secret credential should not be printed!')


def test_llm_connection_errors_do_not_leak_or_emit_report():
    result,trace=run_llm_agent({'target_nm':10},'unused',client=FailingClient())
    assert '검증을 중단' in result and 'secret' not in result
    assert trace[-1]['tool']=='llm_transport'


class DummyMessage:
    def __init__(self,calls=None,content=''):
        self.tool_calls=calls or []
        self.content=content
    def model_dump(self,exclude_none=True):
        return {'role':'assistant','content':self.content,'tool_calls':[
            {'id':c.id,'type':'function',
             'function':{'name':c.function.name,'arguments':c.function.arguments}}
            for c in self.tool_calls]}

class FakeClient:
    def __init__(self,messages):
        self.messages=iter(messages)
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def create(self,**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=next(self.messages))])

def call(name,args,n):
    return SimpleNamespace(id=f'call_{n}',function=SimpleNamespace(name=name,arguments=json.dumps(args)))


def test_llm_fabricated_claim_cannot_enter_verified_report():
    fake=FakeClient([
        DummyMessage([call('search_evidence',{'query':'Al2O3 GPC'},1),call('find_recipes',{},2)]),
        DummyMessage(content='품질 검증 완료! 실제 수율이 99% 증가했습니다.'),
    ])
    report,trace=run_llm_agent({'target_nm':10},api_key='fake',client=fake)
    assert '품질 검증 완료!' not in report
    assert '99%' not in report
    assert 'LLM 생성 해석 초안' in report
    assert '추천 조건은' in report


def test_api_tool_nonmatching_locked_params_rejected():
    fake=FakeClient([
        DummyMessage([call('search_evidence',{'query':'Al2O3 GPC'},1),call('find_recipes',{'max_temp':300},2)]),
        DummyMessage(content='Great.'),
    ])
    report,trace=run_llm_agent({'target_nm':10,'max_temp':200},api_key='fake',client=fake)
    assert '검증 중단' in report
    assert any('error' in r['result'] for r in trace if isinstance(r['result'],dict))
