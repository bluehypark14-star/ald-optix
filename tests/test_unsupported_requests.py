"""Unsupported requests — software regression tests."""
import json
from types import SimpleNamespace
import pytest
from agent import validated_request, deterministic_demo, dispatch_tool, run_llm_agent
from core import parse_request, optimize_recipe, quality_gate

CHEMISTRY = [
    'Al2O3 10nm, 물 대신 오존을 산화제로 사용하고 싶어',
    'Al2O3 10nm, O3 산화제 사용',
    'Al₂O₃ 10 nm, ozone oxidation',
    'Al2O3 10nm, 산소 플라즈마 활용',
    'Al2O3 10nm, oxygen plasma ALD',
    'Al2O3 10nm, H2O 대신 O2',
    'Al2O3 10nm, TMA 대신 다른 전구체',
    'Al2O3 10nm, 과산화수소를 사용해',
    'Al2O3 10nm, H2O2 산화제 사용',
    'Al2O3 10nm, oxygen gas',
    'Al2O3 10nm, O₂ 사용',
]
QUALITATIVE = [
    'Al2O3 10nm, purge를 길게 해줘',
    'Al2O3 10nm purge 더 길게',
    'Al2O3 10nm, 퍼지 충분히',
    'Al2O3 10nm Ar 유량 높여',
    'Al2O3 10nm, 온도 낮게',
    'Al2O3 10nm, pulse 짧게',
    'Al2O3 10nm, longer purge please',
]

@pytest.mark.parametrize('text', CHEMISTRY)
def test_alternative_reactant_is_never_assumed_water(text):
    params,err=validated_request(text)
    assert params is None and err, text
    reply,trace=deterministic_demo(text)
    assert len(trace)==1 and '검증 중단' in reply

@pytest.mark.parametrize('text', QUALITATIVE)
def test_qualitative_constraint_refuses_to_guess(text):
    params,err=validated_request(text)
    assert params is None and err, text

@pytest.mark.parametrize('text,expected', [
    ('Al2O3 10nm 최대 200°C purge 최소 20초', ('max_temp',200.0)),
    ('Al₂O₃ 10 nm Ar 유량 20sccm만', ('min_flow',20.0)),
    ('Al2O3 10nm 20ms 펄스 정확히',('min_pulse',20.0)),
    ('Al2O3 10nm GPC 최대화',('objective','gpc')),
    ('Al2O3 10nm 200도 이상',('min_temp',200.0)),
])
def test_supported_numeric_request_still_works(text,expected):
    args,err=validated_request(text)
    assert err is None,err
    assert args[expected[0]]==expected[1]
    result=dispatch_tool('find_recipes',{},locked_request=args)
    assert 'error' not in result

class Message:
    def __init__(self,calls=None,content=''):
        self.tool_calls=calls or []
        self.content=content
    def model_dump(self,exclude_none=True):
        return {'role':'assistant','content':self.content,'tool_calls':[
            {'id':x.id,'type':'function','function':{'name':x.function.name,'arguments':x.function.arguments}}
            for x in self.tool_calls]}

def call(name,args,i):
    return SimpleNamespace(id=f'id_{i}',function=SimpleNamespace(name=name,arguments=json.dumps(args)))

class Client:
    def __init__(self,replies):
        self.replies=iter(replies)
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def create(self,**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=next(self.replies))])

def test_llm_invalid_call_after_good_calls_cannot_succeed():
    # Previously, a valid `verified` result could survive a later tool error.
    client=Client([
        Message([call('search_evidence',{'query':'Al2O3'},1),call('find_recipes',{},2)]),
        Message([call('find_recipes',{'max_purge':999},3)]),
        Message([],content='Everything is fine!')
    ])
    reply,trace=run_llm_agent('Al2O3 10nm purge 최소 20초',api_key='fake',client=client)
    assert '검증 중단' in reply
    assert any('error' in t['result'] for t in trace if isinstance(t['result'],dict))


def test_evidence_empty_query_cannot_be_used_to_fake_provenance():
    assert 'error' in dispatch_tool('search_evidence',{'query':' '})


def test_quality_gate_catches_tampered_measured_fields():
    req={'target_nm':10,'max_temp':200}
    best=dict(optimize_recipe(**req)['best'])
    assert quality_gate(req,best)['status']=='REVIEW_REQUIRED'
    bad=dict(best); bad['gpc_mean_A'] += .5
    assert quality_gate(req,bad)['status']=='REJECT'
    bad2=dict(best); bad2['cycles']+=4
    assert quality_gate(req,bad2)['status']=='REJECT'
    bad3=dict(best); bad3['sequence_time_s'] += 1234
    assert quality_gate(req,bad3)['status']=='REJECT'

@pytest.mark.parametrize('phrase',[
    'GPC를 최대화해줘','GPC가 가장 높은 조건','성장률을 최대한 높여줘',
    'highest GPC','maximize GPC','증착률 우선',
])
def test_explicit_gpc_objective_is_not_silently_ignored(phrase):
    req,err=validated_request('Al2O3 10nm, '+phrase)
    assert err is None,err
    assert req['objective']=='gpc'

@pytest.mark.parametrize('phrase',[
    'GPC 최소화','GPC 최대화 시퀀스 시간 최소화','전구체 다른 걸로 바꿔줘',
])
def test_unsupported_or_conflicting_objective_refuses(phrase):
    args,err=validated_request('Al2O3 10nm '+phrase)
    assert args is None and err

@pytest.mark.parametrize('corrupt', ['negative_gpc','nan_gpc','duplicate_run','missing_gpc'])
def test_source_data_validation_rejects_corruption(tmp_path,monkeypatch,corrupt):
    import pandas as pd
    import core
    d=pd.read_csv(core.DATA_FILE)
    if corrupt=='negative_gpc':d.loc[0,'gpc_A_per_cycle']=-0.1
    elif corrupt=='nan_gpc':d.loc[0,'gpc_A_per_cycle']=float('nan')
    elif corrupt=='duplicate_run':d.loc[1,'run_order']=d.loc[0,'run_order']
    else:d=d.drop(columns=['gpc_A_per_cycle'])
    target=tmp_path/'tampered.csv'
    d.to_csv(target,index=False)
    monkeypatch.setattr(core,'DATA_FILE',target)
    with pytest.raises(ValueError):core.load_data()


def test_quality_gate_missing_conditions_rejects_not_crashes():
    assert quality_gate({'target_nm':10},{'temperature_C':175})['status']=='REJECT'
