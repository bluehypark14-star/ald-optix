"""Numeric types and project paths — software regression tests."""
import json
import warnings
import numpy as np
from core import optimize_recipe, validate_structured_request, sensitivity_analysis
from agent import deterministic_demo
from exports import trace_download_json
from pathlib import Path


def test_complex_numpy_thickness_is_rejected_by_structured_preflight():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        result = validate_structured_request({'target_nm': np.complex64(10+7j)})
    assert 'warning' in result, 'Complex imaginary part was discarded and accepted as a valid thickness'


def test_complex_numpy_thickness_is_rejected_by_optimizer():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        result = optimize_recipe(target_nm=np.complex128(10+7j))
    assert 'error' in result, 'Optimizer silently accepted complex numerical input'


def test_extreme_integer_optimizer_returns_safe_error_instead_of_raising():
    result = optimize_recipe(target_nm=10**400)
    assert 'error' in result


def test_extreme_integer_sensitivity_returns_safe_error_instead_of_raising():
    result = sensitivity_analysis(target_nm=10**400)
    assert 'error' in result


def test_invalid_numpy_boolean_not_exported_as_real_measurement():
    request={'target_nm': np.bool_(True)}
    report, trace = deterministic_demo(request)
    assert report.startswith('⚠️')
    payload=json.loads(trace_download_json('Deterministic tools', request, report, trace))
    assert payload['audit']['validated_report'] is False
    assert type(payload['request']['target_nm']) is not float, 'Invalid numpy boolean serialized as 1.0'


def test_latest_run_guide_points_to_current_folder_and_verification_docs():
    root=Path(__file__).resolve().parents[1]
    guide=(root/'RUN_GUIDE.md').read_text(encoding='utf-8')
    app=(root/'app.py').read_text(encoding='utf-8')
    readme=(root/'README.md').read_text(encoding='utf-8')
    assert 'cd ~/Downloads/ALD_OPTIX' in guide
    assert 'RUN_GUIDE.md' in readme
    document=root/'docs'/'validation.md'
    assert document.is_file()
    assert 'docs/validation.md' in app


def test_numpy_boolean_failure_export_preserves_invalid_type():
    request = {'target_nm': np.bool_(True)}
    report, trace = deterministic_demo(request)
    payload = json.loads(trace_download_json('Deterministic tools', request, report, trace))
    assert payload['audit']['validated_report'] is False
    assert payload['request']['target_nm']['invalid_input_type'] == 'numpy.bool'
    assert payload['export_redaction']['invalid_numbers_redacted'] >= 1


def test_numpy_complex_failure_export_keeps_imaginary_part():
    request = {'target_nm': np.complex64(10 + 7j)}
    report, trace = deterministic_demo(request)
    payload = json.loads(trace_download_json('Deterministic tools', request, report, trace))
    assert payload['audit']['validated_report'] is False
    assert '7j' in payload['request']['target_nm']['original_repr']
    assert payload['request']['target_nm']['invalid_input_type'] == 'complex64'


def test_supported_numpy_real_request_keeps_audit_valid():
    from exports import audit_execution
    for target in (np.int64(10), np.float32(10)):
        request = {'target_nm': target}
        report, trace = deterministic_demo(request)
        audit = audit_execution('Deterministic tools', request, report, trace)
        assert audit['validated_report'], audit
        exported = json.loads(trace_download_json('Deterministic tools', request, report, trace))
        assert exported['audit']['validated_report'] is True
        assert exported['request']['target_nm'] == 10
