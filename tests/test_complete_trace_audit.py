"""Complete trace audit — software regression tests."""
from copy import deepcopy
import json

import pytest

from agent import deterministic_demo, run_llm_agent
from exports import audit_execution, trace_download_json
from mock_llm_helpers import FakeClient, DummyMessage, call

REQ = {'target_nm': 10, 'max_temp': 200, 'objective': 'time'}


@pytest.fixture(scope='module')
def valid_run():
    report, trace = deterministic_demo(REQ)
    approved = audit_execution('Deterministic tools', REQ, report, trace)
    assert approved['validated_report']
    assert approved['trace_steps_verified']
    assert not approved['trace_authenticity_independently_verified']
    return report, trace


def changed_record(trace, tool):
    result = deepcopy(trace)
    return result, next(item for item in result if item['tool'] == tool)


@pytest.mark.parametrize('tool', ['evaluate_models', 'audit_casebook'])
def test_tool_result_forgery_blocked(valid_run, tool):
    report, trace = valid_run
    altered, row = changed_record(trace, tool)
    row['result'] = {'fabricated_claim': 'fake industrial yield verified'}
    audit = audit_execution('Deterministic tools', REQ, report, altered)
    assert not audit['validated_report']
    assert audit['reason'] == ('model_tool_trace_mismatch' if tool == 'evaluate_models'
                               else 'casebook_tool_trace_mismatch')


def test_user_request_forgery_blocked(valid_run):
    report, trace = valid_run
    altered = deepcopy(trace)
    altered[0]['input'] = 'HfO2 1nm -- unrelated request'
    audit = audit_execution('Deterministic tools', REQ, report, altered)
    assert not audit['validated_report']
    assert audit['reason'] == 'original_request_trace_mismatch'


def test_missing_constraint_lock_blocked(valid_run):
    report, trace = valid_run
    altered = deepcopy(trace)
    altered[0]['result'].pop('locked')
    audit = audit_execution('Deterministic tools', REQ, report, altered)
    assert not audit['validated_report']
    assert audit['reason'] == 'request_validation_not_documented'


@pytest.mark.parametrize('bad_marker', [None, False, 0, 1, 'true', {}, []])
def test_malformed_lock_marker_blocked(valid_run, bad_marker):
    report, trace = valid_run
    altered = deepcopy(trace)
    altered[0]['result']['locked'] = bad_marker
    assert not audit_execution('Deterministic tools', REQ, report, altered)['validated_report']


@pytest.mark.parametrize('modification', ['extra_metadata', 'missing_origin',
                                             'missing_roundtrips', 'different_parsed'])
def test_preflight_metadata_exact_schema(valid_run, modification):
    report, trace = valid_run
    altered = deepcopy(trace)
    row = altered[0]['result']
    if modification == 'extra_metadata':
        row['independently_verified_provider'] = True
    elif modification == 'missing_origin':
        row.pop('execution_origin')
    elif modification == 'missing_roundtrips':
        row.pop('api_responses_received')
    else:
        row['parsed']['max_temp'] = 275
    assert not audit_execution('Deterministic tools', REQ, report, altered)['validated_report']


@pytest.mark.parametrize('tool', ['evaluate_models', 'audit_casebook'])
def test_optional_tool_deep_field_mutation_blocked(valid_run, tool):
    report, trace = valid_run
    altered, row = changed_record(trace, tool)
    if tool == 'evaluate_models':
        row['result']['exploratory']['model_MAE_A'] = 0.0
    else:
        row['result'][0]['v1_status'] = 'FABRICATED'
    assert not audit_execution('Deterministic tools', REQ, report, altered)['validated_report']


@pytest.mark.parametrize('tool', ['evaluate_models', 'audit_casebook'])
def test_optional_tools_must_have_no_arguments(valid_run, tool):
    report, trace = valid_run
    altered, row = changed_record(trace, tool)
    row['input']['extra_parameter'] = 'ignored by code'
    audit = audit_execution('Deterministic tools', REQ, report, altered)
    assert not audit['validated_report']
    assert audit['reason'].endswith('_tool_trace_mismatch')


@pytest.mark.parametrize('manipulation', ['remove_search', 'remove_model',
                                               'swap_steps', 'duplicate_casebook'])
def test_deterministic_sequence_is_fixed(valid_run, manipulation):
    report, trace = valid_run
    altered = deepcopy(trace)
    if manipulation == 'remove_search':
        altered = [x for x in altered if x['tool'] != 'search_evidence']
    elif manipulation == 'remove_model':
        altered = [x for x in altered if x['tool'] != 'evaluate_models']
    elif manipulation == 'swap_steps':
        altered[2], altered[3] = altered[3], altered[2]
    else:
        altered.append(deepcopy(altered[-1]))
    assert not audit_execution('Deterministic tools', REQ, report, altered)['validated_report']


def test_exact_string_user_request_valid_and_changed_string_is_not():
    req = 'Al2O3 10nm, 최대 200°C, 시퀀스 시간 최소화'
    report, trace = deterministic_demo(req)
    assert audit_execution('Deterministic tools', req, report, trace)['validated_report']
    altered = deepcopy(trace)
    altered[0]['input'] = 'Al2O3 10nm, 최대 200°C, 시퀀스 시간 최소화!'
    assert not audit_execution('Deterministic tools', req, report, altered)['validated_report']


def test_request_dict_key_order_does_not_cause_false_alarm(valid_run):
    report, trace = valid_run
    reordered = deepcopy(trace)
    reordered[0]['input'] = {'objective': 'time', 'max_temp': 200, 'target_nm': 10}
    assert audit_execution('Deterministic tools', REQ, report, reordered)['validated_report']


def test_json_roundtrip_preserves_audit_and_original_request(valid_run):
    report, trace = valid_run
    payload = json.loads(trace_download_json('Deterministic tools', REQ, report, trace))
    result = audit_execution('Deterministic tools', payload['request'], report,
                             payload['trace'])
    assert result['validated_report']
    assert result['trace_steps_verified']
    assert result['live_api_independently_verified'] is False


def test_valid_mock_llm_trace_without_optional_tools_passes():
    fake = FakeClient([
        DummyMessage([call('search_evidence', {'query': 'Al2O3 GPC purge'}, 1),
                      call('find_recipes', {}, 2)]),
        DummyMessage(content='Not independently verified.'),
    ])
    report, trace = run_llm_agent(REQ, 'fake', client=fake)
    result = audit_execution('Mock LLM protocol', REQ, report, trace)
    assert result['validated_report']
    assert result['trace_steps_verified']
    assert not result['trace_authenticity_independently_verified']


def test_transport_roundtrip_count_out_of_bounds_is_rejected(valid_run):
    report, trace = valid_run
    mutated = deepcopy(trace)
    mutated[0]['result']['api_responses_received'] = 10
    assert not audit_execution('Deterministic tools', REQ, report, mutated)['validated_report']


def test_missing_tool_input_and_result_blocked(valid_run):
    report, trace = valid_run
    for missing in ('input', 'result'):
        altered = deepcopy(trace)
        altered[3].pop(missing)
        assert not audit_execution('Deterministic tools', REQ, report, altered)['validated_report']


def test_cached_analysis_cannot_be_mutated_by_caller():
    from exports import _recompute_for_audit
    for tool in ('evaluate_models', 'audit_casebook'):
        r1 = _recompute_for_audit(tool, {}, REQ)
        if tool == 'evaluate_models':
            r1['exploratory']['model_MAE_A'] = -9999
        else:
            r1[0]['source'] = 'fake source'
        r2 = _recompute_for_audit(tool, {}, REQ)
        assert r1 != r2


def test_malformed_trace_tool_name_fails_without_exception(valid_run):
    report, trace = valid_run
    altered = deepcopy(trace)
    altered[1]['tool'] = ['unhashable', 'tool-name']
    result = audit_execution('Deterministic tools', REQ, report, altered)
    assert not result['validated_report']
    assert result['status'] == 'BLOCKED_OR_INCOMPLETE'


def test_nonfinite_llm_argument_cannot_poison_downloaded_json():
    from types import SimpleNamespace
    # Python json.loads would otherwise accept the illegal literal NaN.
    dangerous = SimpleNamespace(id='nan-1', function=SimpleNamespace(
        name='find_recipes', arguments='{"max_temp": NaN}'))
    fake = FakeClient([DummyMessage([dangerous])])
    report, trace = run_llm_agent(REQ, 'fake', client=fake)
    assert not audit_execution('Mock LLM protocol', REQ, report, trace)['validated_report']
    output = json.loads(trace_download_json('Mock LLM protocol', REQ, report, trace))
    assert output['audit']['status'] == 'BLOCKED_OR_INCOMPLETE'
    assert 'NaN' not in json.dumps(output)
