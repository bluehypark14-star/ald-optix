"""One-command local release gate for Mac + GitHub CI.

By default it reports Streamlit unavailability honestly rather than counting
an import-skipped UI test as success. Use --strict for mandatory Streamlit.
"""
from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def run_command(label,command):
    print(f'\n== {label} ==',flush=True)
    proc=subprocess.run(command,cwd=ROOT,check=False)
    return proc.returncode==0


def run():
    parser=argparse.ArgumentParser()
    parser.add_argument('--strict',action='store_true',
                        help='Fail if Streamlit is not installed or its integration tests cannot run')
    parser.add_argument('--browser',action='store_true',
                        help='Also run offline Chromium desktop/mobile smoke test')
    args=parser.parse_args()
    statuses={}
    installed=importlib.util.find_spec('streamlit') is not None
    print('Streamlit available:',installed)
    statuses['python_tests']=run_command('All Python tests', [sys.executable,'-m','pytest','-q'])
    if installed:
        statuses['streamlit_apptest']=run_command('Real Streamlit AppTest integration suite',[
            sys.executable,'-m','pytest','-q',
            'tests/test_streamlit_runtime_optional.py',
            'tests/test_streamlit_interactions_optional.py'])
    else:
        statuses['streamlit_apptest']=None
        print('NOT VERIFIED: Streamlit not installed; six AppTest cases remain unexecuted.')
    if shutil.which('node'):
        statuses['js_parity']=run_command('210 Python-JavaScript parity comparisons',[
            sys.executable,'scripts/compare_python_js.py'])
    else:
        statuses['js_parity']=None
        print('NOT VERIFIED: Node.js missing. Install Node.js to run JS parity.')
    if args.browser:
        try:
            import playwright # noqa: F401
            statuses['offline_browser']=run_command('Offline desktop/mobile Chromium UI smoke',[
                sys.executable,'scripts/browser_offline_mock.py'])
        except ImportError:
            statuses['offline_browser']=None
            print('NOT VERIFIED: Playwright not installed; cannot run optional browser smoke.')
    print('\n== RELEASE SUMMARY ==')
    for key,value in statuses.items():
        print(f'{key}: {"PASS" if value is True else "FAIL" if value is False else "NOT VERIFIED"}')
    if any(value is False for value in statuses.values()):
        raise SystemExit(1)
    if args.strict and any(value is None for value in statuses.values()):
        raise SystemExit(2)

if __name__=='__main__':run()
