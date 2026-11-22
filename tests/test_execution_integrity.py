"""Execution integrity — software regression tests."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from agent import deterministic_demo, run_llm_agent
from exports import audit_execution, trace_download_json
from mock_llm_helpers import FakeClient, DummyMessage, call

REQ = {'target_nm':10,'max_temp':200,'objective':'time'}


def mock_run():
    fake=FakeClient([
        DummyMessage([call('search_evidence', {'query':'Al2O3 GPC purge'}, 1),
                      call('find_recipes', {}, 2)]),
        DummyMessage(content='no equipment validation'),
    ])
    return run_llm_agent(REQ, 'dummy', client=fake)


def test_rule_based_cannot_be_relabeled_as_llm():
    report,trace=deterministic_demo(REQ)
    assert audit_execution('Deterministic tools',REQ,report,trace)['validated_report']
    for claimed_mode in ('Mock LLM protocol','LLM tool-calling'):
        wrong=audit_execution(claimed_mode,REQ,report,trace)
        assert not wrong['validated_report']
        assert wrong['reason']=='execution_mode_or_transport_mismatch'


def test_mock_never_claims_openai_sdk_path():
    report,trace=mock_run()
    good=audit_execution('Mock LLM protocol',REQ,report,trace)
    assert good['validated_report']
    assert good['trace_mode_consistent']
    assert not good['trace_authenticity_independently_verified']
    assert not good['live_api_independently_verified']
    assert trace[0]['result']['execution_origin']=='INJECTED_CLIENT'
    assert trace[0]['result']['api_responses_received']==2
    assert not audit_execution('LLM tool-calling',REQ,report,trace)['validated_report']


def test_missing_or_changed_provenance_fails_closed():
    report,trace=deterministic_demo(REQ)
    for change in ('remove_origin','bad_roundtrips','missing_roundtrips','duplicate_preflight'):
        tampered=deepcopy(trace)
        if change=='remove_origin': tampered[0]['result'].pop('execution_origin')
        if change=='bad_roundtrips': tampered[0]['result']['api_responses_received']=2
        if change=='missing_roundtrips': tampered[0]['result'].pop('api_responses_received')
        if change=='duplicate_preflight': tampered.append(deepcopy(tampered[0]))
        assert not audit_execution('Deterministic tools',REQ,report,tampered)['validated_report'],change


def test_forged_or_mismatched_evidence_is_not_accepted():
    report,trace=deterministic_demo(REQ)
    for variant in ('empty_spoof','arbitrary_evidence','query_changed','missing_query'):
        tampered=deepcopy(trace)
        evidence=next(x for x in tampered if x['tool']=='search_evidence')
        if variant=='empty_spoof': evidence['result']=[{'title':'Fake DOE','source':'unknown'}]
        elif variant=='arbitrary_evidence': evidence['result'][0]['title']='fabricated evidence'
        elif variant=='query_changed': evidence['input']['query']='unrelated fake external data'
        else: evidence['input'].pop('query')
        bad=audit_execution('Deterministic tools',REQ,report,tampered)
        assert not bad['validated_report'],variant
        assert bad['reason']=='evidence_trace_mismatch'


def test_damaged_trace_not_trusted_even_if_report_is_correct():
    report,trace=deterministic_demo(REQ)
    assert not audit_execution('Deterministic tools',REQ,report,[42,*trace])['validated_report']
    assert not audit_execution('Deterministic tools',REQ,report,[{},*trace])['validated_report']
    assert not audit_execution('Deterministic tools',REQ,report,[*trace,object()])['validated_report']


def test_transport_failure_has_zero_report_provenance():
    class BrokenClient:
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: (_ for _ in ()).throw(ConnectionError())))
    report,trace=run_llm_agent(REQ,'dummy',client=BrokenClient())
    assert '연결' in report
    assert trace[0]['result']['api_responses_received']==0
    assert not audit_execution('Mock LLM protocol',REQ,report,trace)['validated_report']


def test_malformed_assistant_serialization_is_handled():
    class BrokenMessage(DummyMessage):
        def model_dump(self,exclude_none=True): raise TypeError('bad message')
    fake=FakeClient([BrokenMessage([call('find_recipes',{},1)])])
    report,trace=run_llm_agent(REQ,'dummy',client=fake)
    assert '직렬화' in report
    assert trace[-1]['tool']=='llm_response_format'
    assert not audit_execution('Mock LLM protocol',REQ,report,trace)['validated_report']


def test_oversized_tool_call_batch_fails_before_dispatch():
    # Each call ID must be unique; budget check occurs before dispatch.
    calls=[call('find_recipes',{},n) for n in range(9)]
    fake=FakeClient([DummyMessage(calls)])
    report,trace=run_llm_agent(REQ,'dummy',client=fake)
    assert '호출량' in report
    assert trace[-1]['tool']=='llm_tool_budget'
    assert not any(x['tool']=='find_recipes' for x in trace)


def test_duplicate_tool_call_id_is_blocked():
    fake=FakeClient([DummyMessage([call('search_evidence',{'query':'Al2O3'},1),
                                   call('find_recipes',{},1)])])
    report,trace=run_llm_agent(REQ,'dummy',client=fake)
    assert '중복' in report
    assert trace[-1]['tool']=='llm_tool_call_id'
    assert not audit_execution('Mock LLM protocol',REQ,report,trace)['validated_report']


def test_trace_download_explicitly_denies_independent_proof():
    import json
    report,trace=mock_run()
    payload=json.loads(trace_download_json('Mock LLM protocol',REQ,report,trace))
    assert '독립적인 API 호출 증명이 아닙니다' in payload['note']
    assert not payload['audit']['live_api_independently_verified']

@pytest.mark.parametrize('field,forged', [
    ('n_feasible',999),
    ('source','https://unrelated.example.com/fake'),
    ('v0_constraint_issues', ['not the actual baseline violations']),
    ('limitations','real reactor validated!'),
])
def test_audit_recomputes_entire_recipe_tool_result(field,forged):
    report,trace=deterministic_demo(REQ)
    tampered=deepcopy(trace)
    row=next(x for x in tampered if x['tool']=='find_recipes')
    row['result'][field]=forged
    result=audit_execution('Deterministic tools',REQ,report,tampered)
    assert not result['validated_report']
    assert result['reason']=='recipe_tool_trace_mismatch'


def test_audit_rejects_inserted_fake_success_step():
    report,trace=deterministic_demo(REQ)
    forged=deepcopy(trace)
    forged.append({'tool':'external_api_success','result':{'validated':True}})
    result=audit_execution('Deterministic tools',REQ,report,forged)
    assert not result['validated_report']
    assert result['reason']=='unexpected_or_failed_tool_step'


def test_non_string_model_text_never_breaks_verified_calculation():
    fake=FakeClient([
        DummyMessage([call('search_evidence',{'query':'Al2O3 GPC'},1),
                      call('find_recipes',{},2)]),
        DummyMessage(content={'unexpected':'multimodal payload'}),
    ])
    report,trace=run_llm_agent(REQ,'dummy',client=fake)
    assert 'ALD-OPTIX 공정 검토 리포트' in report
    assert audit_execution('Mock LLM protocol',REQ,report,trace)['validated_report']
    assert 'multimodal' not in report
