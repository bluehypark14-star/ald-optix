"""Exports and execution — software regression tests."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from core import optimize_recipe
from agent import deterministic_demo, run_llm_agent
from exports import (audit_execution, trace_download_json, make_recipe_review)
from mock_llm_helpers import FakeClient, DummyMessage, call


def test_studio_markdown_export_is_exactly_quality_gated():
    request={'target_nm':10,'max_temp':200,'objective':'time'}
    best=optimize_recipe(**request)['best']
    result=make_recipe_review(request,best)
    assert '공정 검토' in result
    assert 'REVIEW_REQUIRED' in result
    forged=deepcopy(best)
    forged['sequence_time_min']=77777
    with pytest.raises(ValueError,match='Quality gate rejected'):
        make_recipe_review(request,forged)
    with pytest.raises(ValueError):
        make_recipe_review({'target_nm':10,'max_temp':150},best)


def test_deterministic_trace_has_no_llm_claim_and_is_recheckable():
    req={'target_nm':10,'objective':'balanced','max_temp':200}
    report,trace=deterministic_demo(req)
    aud=audit_execution('Deterministic tools',req,report,trace)
    assert aud['validated_report'] is True
    assert aud['status']=='ENGINEERING_REPORT_VERIFIED'
    assert aud['mode_classification']=='RULE_BASED_TOOLS__NOT_LLM'
    assert not aud['live_api_independently_verified']
    payload=json.loads(trace_download_json('Deterministic tools',req,report,trace))
    assert payload['audit']==aud
    assert payload['request']==req
    assert payload['trace']==trace


def test_bad_report_or_trace_cannot_be_labeled_verified():
    req={'target_nm':10,'objective':'time'}
    report,trace=deterministic_demo(req)
    assert not audit_execution('Deterministic tools',req,'제조 수율 99% 향상',trace)['validated_report']
    assert not audit_execution('Deterministic tools',req,report+'\n양산 수율 99% 개선',trace)['validated_report']
    forged=deepcopy(trace)
    for entry in forged:
        if entry['tool']=='find_recipes':
            entry['result']['best']['sequence_time_min']=77777
    assert not audit_execution('Deterministic tools',req,report,forged)['validated_report']
    with pytest.raises(ValueError,match='Unknown execution mode'):
        trace_download_json('unknown_mode',req,report,trace)


def test_mock_protocol_success_is_never_misreported_as_live_api():
    req={'target_nm':10,'max_temp':200,'min_purge':20,'objective':'time'}
    fake=FakeClient([
        DummyMessage([call('search_evidence',{'query':'Al2O3 GPC purge'},1),
                      call('find_recipes',{},2)]),
        DummyMessage(content='실제 장비의 수율은 확인되지 않았습니다.'),
    ])
    report,trace=run_llm_agent(req,'fake',client=fake)
    aud=audit_execution('Mock LLM protocol',req,report,trace)
    assert aud['validated_report'] is True
    assert aud['mode_classification']=='SIMULATED_LLM_PROTOCOL__NOT_LIVE'
    assert aud['live_api_independently_verified'] is False
    assert '실제 장비의 수율은 확인되지 않았습니다.' not in report


def test_mock_protocol_locked_constraint_attack_is_blocked():
    req={'target_nm':10,'max_temp':200,'min_purge':20}
    fake=FakeClient([
        DummyMessage([call('search_evidence',{'query':'Al2O3 GPC purge'},1),
                      call('find_recipes',{'min_purge':10},2)]),
        DummyMessage(content='approved'),
    ])
    report,trace=run_llm_agent(req,'fake',client=fake)
    aud=audit_execution('Mock LLM protocol',req,report,trace)
    assert aud['status']=='BLOCKED_OR_INCOMPLETE'
    assert not aud['validated_report']
    assert 'approved' not in report


def test_audit_rejects_invalid_or_missing_provenance():
    report,trace=deterministic_demo({'target_nm':10})
    for records in ([],[{'tool':'find_recipes','result':{}}]):
        summary=audit_execution('Deterministic tools',{'target_nm':10},report,records)
        assert summary['status']=='BLOCKED_OR_INCOMPLETE'
    invalid=audit_execution('Deterministic tools',{'target_nm':10,'max_temp':150},report,trace)
    assert invalid['reason']=='request_validation_failed'


def test_audit_rejects_badly_formed_trace_without_crashing():
    report,trace=deterministic_demo({'target_nm':10})
    altered=deepcopy(trace)
    altered[0]['result']='not-an-object'
    assert audit_execution('Deterministic tools',{'target_nm':10},report,altered)['status']=='BLOCKED_OR_INCOMPLETE'
