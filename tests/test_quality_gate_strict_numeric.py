"""Quality gate strict numeric — software regression tests."""
import warnings
import numpy as np
import pytest

from core import optimize_recipe, quality_gate, validate_structured_request
from exports import make_recipe_review


def _scenario(objective='time'):
    request = validate_structured_request({'target_nm':10, 'max_temp':200, 'objective':objective})
    assert 'warning' not in request
    best = optimize_recipe(**request)['best'].copy()
    return request,best


def test_valid_real_recipe_is_not_over_rejected():
    request,best=_scenario()
    assert quality_gate(request,best)['status'] == 'REVIEW_REQUIRED'


@pytest.mark.parametrize('name', ['target_nm','gpc_mean_A','cycles','sequence_time_s','replications','temperature_C'])
def test_complex_numeric_field_must_be_rejected(name):
    request,best=_scenario()
    best[name] = np.complex128(complex(float(best[name]),7.0))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', np.exceptions.ComplexWarning)
        assert quality_gate(request,best)['status'] == 'REJECT'


def test_complex_balanced_score_must_be_rejected():
    request,best=_scenario('balanced')
    best['balance_score']=np.complex128(complex(float(best['balance_score']),5.0))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', np.exceptions.ComplexWarning)
        assert quality_gate(request,best)['status'] == 'REJECT'


def test_downloadable_report_must_refuse_complex_recipe():
    request,best=_scenario()
    best['target_nm']=np.complex128(10+7j)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', np.exceptions.ComplexWarning)
        with pytest.raises(ValueError,match='Quality gate'):
            make_recipe_review(request,best)


@pytest.mark.parametrize('name', ['flow_sccm','pulse_ms','purge_s',
    'gpc_sd_A','sequence_time_min'])
def test_other_numeric_fields_reject_complex(name):
    request,best=_scenario()
    best[name] = np.complex64(complex(float(best[name]), 1.25))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', np.exceptions.ComplexWarning)
        assert quality_gate(request, best)['status'] == 'REJECT'


@pytest.mark.parametrize('scalar', [np.complex64(10+0j), np.complex128(10+0j)])
def test_even_zero_imaginary_part_is_not_a_real_scalar(scalar):
    request,best=_scenario()
    best['target_nm'] = scalar
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', np.exceptions.ComplexWarning)
        assert quality_gate(request, best)['status'] == 'REJECT'


@pytest.mark.parametrize('value', [np.complex64(0.1+0j), np.complex128(0.1+7j),
    True, np.bool_(True), '0.1', float('nan'), float('inf'), 10**400])
def test_balanced_score_requires_finite_real_number(value):
    request,best=_scenario('balanced')
    best['balance_score'] = value
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', np.exceptions.ComplexWarning)
        assert quality_gate(request, best)['status'] == 'REJECT'


@pytest.mark.parametrize('dtype', [np.int64, np.float32, np.float64])
def test_valid_numpy_real_best_fields_are_accepted(dtype):
    request,best=_scenario('balanced')
    # Cast only exact whole-number fields to all NumPy numeric types.
    # Converting fractional measurements to int is data corruption, and float32
    # necessarily loses some digits for large nonintegral sequence times.
    for key in ('target_nm', 'temperature_C', 'flow_sccm',
                'pulse_ms', 'purge_s', 'replications', 'cycles'):
        best[key] = dtype(best[key])
    if dtype is np.float64:
        for key in ('gpc_mean_A', 'gpc_sd_A', 'sequence_time_s',
                    'sequence_time_min', 'balance_score'):
            best[key] = dtype(best[key])
    assert quality_gate(request, best)['status'] == 'REVIEW_REQUIRED'
    assert '품질 게이트' in make_recipe_review(request, best)
