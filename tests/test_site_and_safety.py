"""Cross-check public corporate homepage with the Python analysis + scope guards."""
from __future__ import annotations
import json
from pathlib import Path
from html.parser import HTMLParser
import pytest

from core import condition_means, cross_validate, nested_cross_validate, request_scope_error, engineering_casebook
from agent import deterministic_demo, run_llm_agent

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


class IDAndLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.local_links = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            assert attrs["id"] not in self.ids, f"Duplicate HTML id: {attrs['id']}"
            self.ids.add(attrs["id"])
        if tag == "a" and attrs.get("href", "").startswith("#"):
            self.local_links.append(attrs["href"][1:])


def test_static_website_exports_exactly_the_observed_condition_means():
    data = json.loads((SITE / "data.json").read_text(encoding="utf-8"))
    actual = condition_means()
    assert data["recipe_count"] == 16 and len(data["recipes"]) == 16
    assert data["experiment_count"] == 32
    for row in data["recipes"]:
        found = actual
        for k in ("temperature_C", "flow_sccm", "pulse_ms", "purge_s"):
            found = found.loc[found[k] == row[k]]
        assert len(found) == 1
        assert row["gpc_mean_A"] == pytest.approx(found.iloc[0].gpc_mean_A)
        assert row["replications"] == 2


def test_static_website_metrics_match_core_evaluation():
    data = json.loads((SITE / "data.json").read_text(encoding="utf-8"))
    exploration, _ = cross_validate()
    nested, _ = nested_cross_validate()
    assert data["baseline_MAE_A"] == pytest.approx(exploration["baseline_MAE_A"], abs=0.000001)
    assert data["initial_complex_MAE_A"] == pytest.approx(exploration["initial_complex_MAE_A"], abs=0.000001)
    assert data["nested_MAE_A"] == pytest.approx(nested["MAE_A_per_cycle"], abs=0.000001)
    assert data["comparison_10nm"]["best_min"] == pytest.approx(25.05)
    assert data["comparison_10nm"]["baseline_min"] == pytest.approx(47.428)


def test_website_bundle_is_complete_and_local_navigation_is_valid():
    for filename in ("index.html", "styles.css", "main.js", "config.js", "favicon.svg", "data.json", "_headers"):
        assert (SITE / filename).is_file(), filename
    html = (SITE / "index.html").read_text(encoding="utf-8")
    parser = IDAndLinkParser()
    parser.feed(html)
    assert set(parser.local_links).issubset(parser.ids)
    assert 'step="0.1" value="10"' in html  # prevent browser-native form validation blocking submit
    assert "실제 장비" in html
    assert "Cloudflare Pages" in html and "Streamlit" in html


def test_other_material_is_rejected_before_any_recipe_lookup():
    assert request_scope_error("HfO2 10nm ALD")
    assert request_scope_error("ZnO 10nm 공정")
    assert request_scope_error("스퍼터링으로 Al2O3 10nm")
    assert request_scope_error("Al2O3 10nm ALD 200도 이하") is None
    text, trace = deterministic_demo("ZnO 박막 10nm를 추천해줘")
    assert "지원하지 않는" in text
    assert len(trace) == 1 and trace[0]["tool"] == "request_validation"
    assert "error" in trace[0]["result"]


def test_llm_scope_guard_requires_no_api_import_or_network_call():
    # For unsupported material, reject before trying to import openai or spend tokens.
    text, trace = run_llm_agent("HfO2 10nm", api_key="not-an-actual-key")
    assert "지원하지 않는" in text and "검증 중단" in text
    assert trace[0]["tool"] == "request_validation"


def test_casebook_export_matches_core():
    data=json.loads((SITE / 'data.json').read_text(encoding='utf-8'))
    exported=data['engineering_cases']
    expected=engineering_casebook()
    assert len(exported)==len(expected)==8
    assert [(c['case_id'], c['v0_pass'], c['v1_pass']) for c in exported] == [
        (c['case_id'], c['v0_pass'], c['v1_pass']) for c in expected]
    assert (SITE/'main.js').read_text(encoding='utf-8').count('casebook-body')>=1
    assert 'id="casebook-body"' in (SITE/'index.html').read_text(encoding='utf-8')
