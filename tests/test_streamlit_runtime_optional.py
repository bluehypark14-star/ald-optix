"""Optional end-to-end Streamlit AppTest.

Runs automatically in GitHub Actions where requirements.txt installs Streamlit.
Skips in code-review containers that cannot install the app dependency.
This is not a substitute for a real browser or Cloudflare deployment check.
"""
from pathlib import Path
import pytest

streamlit=pytest.importorskip('streamlit',reason='streamlit package unavailable in this environment')
from streamlit.testing.v1 import AppTest


def test_app_can_start_and_render_all_tabs_without_exception():
    app=Path(__file__).resolve().parents[1]/'app.py'
    state=AppTest.from_file(str(app),default_timeout=60).run()
    assert not state.exception, [str(e.message) for e in state.exception]
    assert len(state.tabs)==5
