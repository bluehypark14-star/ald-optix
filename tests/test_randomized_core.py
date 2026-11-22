"""Randomized core — software regression tests."""
from __future__ import annotations
import random
import math
from copy import deepcopy

from core import optimize_recipe, independent_reference, quality_gate, validate_structured_request


def test_24_seeded_constraint_requests_have_correct_optimum_or_safe_refusal():
    rng=random.Random(20261121)
    for _ in range(24):
        req={
            'target_nm':rng.choice([0.1,0.7,1,5,10,12.5,50,100,1000]),
            'min_temp':rng.choice([175,200,275]),
            'max_temp':rng.choice([150,175,200,225,275]),
            'min_flow':rng.choice([10,15,20]),
            'max_flow':rng.choice([10,15,20]),
            'min_pulse':rng.choice([20,30,40]),
            'max_pulse':rng.choice([20,30,40]),
            'min_purge':rng.choice([10,15,20]),
            'max_purge':rng.choice([10,15,20]),
            'objective':rng.choice(['time','gpc','balanced']),
        }
        actual=optimize_recipe(**req)
        oracle=independent_reference(req)
        if oracle['best'] is None:
            assert 'error' in actual,req
            assert 'warning' in validate_structured_request(req),req
            continue
        assert 'error' not in actual, (req,actual)
        assert actual['n_feasible']==oracle['n_feasible'],req
        assert quality_gate(req,actual['best'])['status']=='REVIEW_REQUIRED',req
        for field in ('temperature_C','flow_sccm','pulse_ms','purge_s','gpc_mean_A','sequence_time_s'):
            assert math.isclose(float(actual['best'][field]),float(oracle['best'][field]),abs_tol=1e-7), (req,field)
        if req['objective']=='balanced':
            assert math.isclose(actual['best']['balance_score'],oracle['best']['balance_score'],abs_tol=1e-7),req


def test_published_display_fields_cannot_be_tampered_independently():
    request={'target_nm':10,'max_temp':200,'objective':'balanced'}
    best=optimize_recipe(**request)['best']
    assert quality_gate(request,best)['status']=='REVIEW_REQUIRED'
    mutations={
        'target_nm': 11, 'cycles': float(best['cycles'])+0.5,
        'gpc_mean_A': best['gpc_mean_A']+0.1,
        'gpc_sd_A': best['gpc_sd_A']+0.02,
        'replications':1, 'sequence_time_s':77777,
        'sequence_time_min':77777, 'balance_score':0.42,
        'temperature_C':999, 'flow_sccm':999,
        'pulse_ms':999,'purge_s':999,
    }
    for field,new_value in mutations.items():
        forged=deepcopy(best)
        forged[field]=new_value
        assert quality_gate(request,forged)['status']=='REJECT',field
