"""Symbolic constraints — software regression tests."""
import pytest
from agent import validated_request


@pytest.mark.parametrize('symbolic,worded', [
    ('Al2O3 10nm purge < 20초', 'Al2O3 10nm purge 20초 미만'),
    ('Al2O3 10nm purge > 10초', 'Al2O3 10nm purge 10초 초과'),
    ('Al2O3 10nm 온도 > 175°C', 'Al2O3 10nm 온도 175°C 초과'),
    ('Al2O3 10nm 온도 < 275°C', 'Al2O3 10nm 온도 275°C 미만'),
    ('Al2O3 10nm Ar 유량 < 20sccm', 'Al2O3 10nm Ar 유량 20sccm 미만'),
    ('Al2O3 10nm purge <= 20초', 'Al2O3 10nm purge 20초 이하'),
    ('Al2O3 10nm 온도 >= 175°C', 'Al2O3 10nm 온도 175°C 이상'),
    ('Al2O3 10nm purge >= 10초 GPC 최대화', 'Al2O3 10nm purge 10초 이상 GPC 최대화'),
    ('Al2O3 10nm 온도 ≤ 275°C', 'Al2O3 10nm 온도 275°C 이하'),
    ('Al2O3 10nm purge ≥ 10초 GPC 최대화', 'Al2O3 10nm purge 10초 이상 GPC 최대화'),
])
def test_comparison_symbol_must_mean_same_as_words_or_be_rejected(symbolic,worded):
    normal, normal_error = validated_request(worded)
    assert normal_error is None, f'control phrase was not parsed: {worded}: {normal_error}'
    actual,error = validated_request(symbolic)
    assert error is not None or actual == normal, (
        f'symbolic comparison silently changed user constraints: {symbolic}: {actual};'
        f' equivalent word form: {normal}'
    )


@pytest.mark.parametrize('prompt', [
    'Al2O3 10nm 온도 ≠ 175°C',
    'Al2O3 10nm 온도 != 175°C',
])
def test_unsupported_exclusion_syntax_must_not_select_excluded_level(prompt):
    actual,error=validated_request(prompt)
    assert error is not None or actual['min_temp'] > 175, (
        f'unsupported exclusion was silently turned into a positive exact match: {actual}'
    )

# Acceptance tests: each supported sign must preserve the meaning
# of a Korean worded comparison for every DOE variable and optimization goal.
from core import optimize_recipe, quality_gate
from agent import deterministic_demo

_LEVEL_CASES = [
    ('온도', '°C', (175, 200, 275)),
    ('Ar 유량', 'sccm', (10, 15, 20)),
    ('pulse', 'ms', (20, 30, 40)),
    ('purge', '초', (10, 15, 20)),
]
_SYMBOL_WORD_CASES = [
    ('<', '미만'), ('<=', '이하'), ('≤', '이하'),
    ('>', '초과'), ('>=', '이상'), ('≥', '이상'),
    ('=', '고정'),
]


@pytest.mark.parametrize('field,unit,levels', _LEVEL_CASES)
@pytest.mark.parametrize('symbol,word', _SYMBOL_WORD_CASES)
@pytest.mark.parametrize('value_index', [0, 1, 2])
def test_complete_symbolic_semantics(field, unit, levels, symbol, word, value_index):
    threshold=levels[value_index]
    value=f'{threshold}{unit}'
    symbolic=f'Al2O3 10nm {field} {symbol} {value} GPC 최대화'
    worded=f'Al2O3 10nm {field} {value} {word} GPC 최대화'
    expected, expected_error=validated_request(worded)
    actual, error=validated_request(symbolic)
    assert bool(error)==bool(expected_error), (symbolic, error, worded, expected_error)
    if error:
        assert actual is None
    else:
        assert actual==expected, (symbolic,actual,worded,expected)
        outcome=optimize_recipe(**actual)
        assert 'error' not in outcome
        assert quality_gate(actual, outcome['best'])['status']=='REVIEW_REQUIRED'


@pytest.mark.parametrize('symbol', ['!=', '≠', '==', '=<', '=>', '<>', '><', '≈', '≦', '≧', '≲', '≳', '∼', '~', '＜', '＞'])
def test_unknown_operator_always_rejected(symbol):
    req,error=validated_request(f'Al2O3 10nm purge {symbol} 10초')
    assert req is None and error, symbol


@pytest.mark.parametrize('prompt', [
    'Al2O3 10nm purge <',
    'Al2O3 10nm purge > 10',
    'Al2O3 10nm purge 10초 <',
    'Al2O3 10nm purge < < 20초',
    'Al2O3 10nm purge >> 20초',
    'Al2O3 10nm purge <= >= 20초',
    'Al2O3 < 10nm',
    'Al2O3 10nm purge >= 10초 이하',
    'Al2O3 10nm purge <= 10초 이상',
    'Al2O3 10nm 온도 > 275°C',
    'Al2O3 10nm purge < 10초',
    'Al2O3 10nm 온도 <= -175°C',
    'Al2O3 10nm purge ≠ 10초',
])
def test_unsafe_or_impossible_comparison_rejected(prompt):
    req,error=validated_request(prompt)
    assert req is None and error, (prompt,req)


def test_combined_conditions_survive_the_full_workflow():
    prompt='Al2O3 10nm, 온도 <= 200°C, purge >= 10초, Ar 유량 < 20sccm, GPC 최대화'
    req,error=validated_request(prompt)
    assert not error, error
    assert req['objective']=='gpc'
    assert req['max_temp']==200
    assert req['min_purge']==10
    assert req['max_flow']<20
    result=optimize_recipe(**req)
    assert 'error' not in result
    best=result['best']
    assert best['temperature_C']<=200 and best['flow_sccm']<20
    assert quality_gate(req,best)['status']=='REVIEW_REQUIRED'
    report,trace=deterministic_demo(prompt)
    assert '검증 중단' not in report
    assert any(step['tool']=='find_recipes' for step in trace)


def test_non_supported_exclusion_prohibits_report_issue():
    report,trace=deterministic_demo('Al2O3 10nm 온도 != 175°C')
    assert '검증 중단' in report
    assert len(trace)==1


@pytest.mark.parametrize('symbol', ['≮', '≯', '≰', '≱', '≡', '⋚', '⩽', '⩾', '∈', '∉', '≉', '≪', '≫'])
def test_unrecognized_unicode_relations_are_not_silently_erased(symbol):
    req,error=validated_request(f'Al2O3 10nm purge {symbol} 20초')
    assert req is None and error, (symbol,req)
