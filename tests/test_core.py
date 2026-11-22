"""Reproducible engineering tests. All model claims are internal to one paper."""
import math
import numpy as np
import pandas as pd
import pytest
from core import (
    load_data, condition_means, estimated_cycles, minimum_sequence_time_s,
    optimize_recipe, naive_v0, constraint_check, cross_validate,
    nested_cross_validate, parse_request, quality_gate, scenario_suite,
    sensitivity_analysis, search_evidence, DOI, engineering_casebook,
)
from agent import deterministic_demo, dispatch_tool


def test_published_factorial_structure():
    d=load_data()
    assert len(d)==32
    assert d.run_order.is_unique and d.standard_order.is_unique
    assert d.groupby(['temperature_C','flow_sccm','pulse_ms','purge_s']).size().eq(2).all()
    assert set(d.temperature_C)=={175,275}
    assert set(d.flow_sccm)=={10,20}
    assert set(d.pulse_ms)=={20,40}
    assert set(d.purge_s)=={10,20}
    assert np.isclose(d.gpc_A_per_cycle.mean(),1.166875)


def test_source_document_values_from_table_5():
    # Spot-check published Table 5 at PMC12072700 (run 1, 22, 23, 24, 32).
    by=load_data().set_index('run_order')
    expected={1:(26,0.96),22:(1,1.34),23:(13,1.40),24:(29,1.42),32:(4,1.04)}
    for run,(std,gpc) in expected.items():
        assert by.loc[run,'standard_order']==std
        assert by.loc[run,'gpc_A_per_cycle']==pytest.approx(gpc)


def test_unit_conversion_and_ceiling():
    assert estimated_cycles(10,1.34)==75
    assert estimated_cycles(0.1,1.0)==1
    assert minimum_sequence_time_s(75,20,10)==pytest.approx(1503)
    with pytest.raises(ValueError): estimated_cycles(0,1.0)
    with pytest.raises(ValueError): estimated_cycles(10,0)


def test_baseline_and_time_priority_results():
    v0=naive_v0(10)
    r=optimize_recipe(10,objective='time')['best']
    assert v0['gpc_mean_A']==pytest.approx(1.41)
    assert v0['cycles']==71
    assert v0['sequence_time_s']/60==pytest.approx(47.428)
    assert r['gpc_mean_A']==pytest.approx(1.34)
    assert int(r['cycles'])==75
    assert r['sequence_time_min']==pytest.approx(25.05)
    assert (v0['sequence_time_s']-r['sequence_time_s'])/v0['sequence_time_s']*100==pytest.approx(47.18,abs=0.03)


def test_constraints_enforced_and_no_invention():
    rs=optimize_recipe(10,max_temp=200,min_flow=20,max_flow=20,min_purge=10,max_purge=10)
    assert 'error' not in rs
    assert rs['n_feasible'] == 2
    assert rs['best']['temperature_C']==175
    assert rs['best']['flow_sccm']==20
    assert rs['best']['purge_s']==10
    assert not constraint_check(rs['best'],max_temp=200,min_flow=20,max_flow=20,max_purge=10)
    assert 'error' in optimize_recipe(10,max_temp=150)
    assert 'error' in optimize_recipe(10,min_purge=20,max_purge=10)
    assert 'error' in optimize_recipe(10,min_flow=20,max_flow=10)
    assert 'error' in optimize_recipe(10,objective='unknown')
    assert 'error' in optimize_recipe(2000)


def test_balance_and_gpc_objective():
    r_gpc=optimize_recipe(10,objective='gpc')['best']
    r_time=optimize_recipe(10,objective='time')['best']
    r_bal=optimize_recipe(10,objective='balanced')['best']
    assert r_gpc['gpc_mean_A'] >= r_time['gpc_mean_A']
    assert r_bal['gpc_mean_A'] in condition_means()['gpc_mean_A'].to_list()


def test_grouped_loo_cv_and_metrics():
    metrics,rows=cross_validate()
    assert len(rows)==32 and metrics['n_conditions']==16
    assert metrics['baseline_MAE_A']==pytest.approx(.12285416666666)
    assert metrics['model_MAE_A']==pytest.approx(.08986730905)
    assert metrics['initial_complex_MAE_A']>metrics['baseline_MAE_A']
    # Replicated measurements for each condition got the SAME held-out prediction.
    for _,g in rows.groupby(['temperature_C','flow_sccm','pulse_ms','purge_s']):
        assert g['regression_pred_A'].nunique()==1


def test_nested_cv_avoids_selection_leakage():
    metrics,rows=nested_cross_validate()
    assert len(rows)==32 and metrics['n_conditions']==16
    assert metrics['MAE_A_per_cycle']==pytest.approx(.08986730905)
    assert sum(metrics['model_choices'].values())==16
    assert metrics['model_choices']=={'main':16}
    for _,g in rows.groupby(['temperature_C','flow_sccm','pulse_ms','purge_s']):
        assert g['nested_pred_A_per_cycle'].nunique()==1


def test_quality_gate_rejects_extrapolation():
    fake={'temperature_C':180,'flow_sccm':10,'pulse_ms':20,'purge_s':10}
    assert quality_gate({'target_nm':10},fake)['status']=='REJECT'
    assert quality_gate({'target_nm':10})['status']=='REJECT'
    real=optimize_recipe()['best']
    assert quality_gate({'target_nm':10},real)['status']=='REVIEW_REQUIRED'
    assert quality_gate({'target_nm':10,'max_temp':150},real)['status']=='REJECT'


def test_request_parsing_is_safe_fallback():
    p=parse_request('Al2O3 10nm 200도 이하에서 시간 최소화')
    assert p['target_nm']==10 and p['max_temp']==200 and p['objective']=='time'
    q=parse_request('200도 이상에서 10nm 증착하고 싶어')
    assert 'warning' in q and 'max_temp' not in q
    response,trace=deterministic_demo('200도 이상에서 10nm')
    assert '지원하지 않는' in response
    assert trace[0]['tool']=='request_validation'


def test_run_scenario_acceptance_suite():
    r=scenario_suite()
    assert len(r)==5
    assert r[0]['n_candidates']==16
    assert r[1]['n_candidates']==8
    assert r[2]['n_candidates']==8
    assert r[3]['n_candidates']==0
    assert r[4]['n_candidates']==0


def test_overhead_sensitivity_and_bounds():
    a=sensitivity_analysis(overhead_s_per_cycle=0)['best']
    b=sensitivity_analysis(overhead_s_per_cycle=600)['best']
    assert a['purge_s']==10
    assert b['purge_s']==20
    assert b['cycles']<a['cycles']
    with pytest.raises(ValueError): sensitivity_analysis(overhead_s_per_cycle=-1)
    with pytest.raises(ValueError): sensitivity_analysis(overhead_s_per_cycle=1000)


def test_tool_workflow_is_reproducible_and_labelled():
    r,t=deterministic_demo('Al2O3 10nm 최대 200도 시간 최소화')
    assert len(t)==5
    assert [x['tool'] for x in t]==['request_validation','search_evidence','find_recipes','evaluate_models','audit_casebook']
    assert '규칙 기반' in r
    assert 'Å/cycle' in r
    m=dispatch_tool('evaluate_models',{})
    assert 'nested_selection' in m
    assert dispatch_tool('other',{})['error']


def test_evidence_is_traceable():
    evidence=search_evidence('온도 GPC 관련 연구',3)
    assert len(evidence)==3
    assert all(e['source']==DOI for e in evidence)


def test_engineering_casebook_compares_user_objectives_and_constraints():
    cases=engineering_casebook()
    assert len(cases)==8
    assert [c['case_id'] for c in cases]==[f'C{i:02}' for i in range(1,9)]
    assert sum(c['v0_pass'] for c in cases)==2
    assert sum(c['v1_pass'] for c in cases)==8
    assert cases[0]['v0_pass'] and cases[1]['v0_pass']
    assert cases[4]['feasible_candidates']==8
    assert cases[5]['feasible_candidates']==8
    assert cases[-1]['v1_action']=='추천 거부'
    assert all(c['diagnosis'] for c in cases)


def test_llm_unmeasured_minimum_temperature_blocked_before_api():
    from agent import run_llm_agent
    response, trace=run_llm_agent('Al2O3 10nm 300도 이상에서 추천', api_key='invalid_test_key')
    assert '검증 중단' in response
    assert len(trace)==1 and trace[0]['tool']=='request_validation'
