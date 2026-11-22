"""Opt-in *real* LLM protocol smoke test. Requires independent API billing.

Usage (MacBook, private shell):
  export OPENAI_API_KEY=...     # Never put this in the repository
  python scripts/llm_live_smoke.py --confirm-live

The script writes sanitized confirmation metadata to an ignored directory;
it never prints or saves your API key. This script has NOT been executed by
project authors in an environment with an API key.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent import run_llm_agent
from exports import audit_execution


def main():
    parser=argparse.ArgumentParser(description='Opt-in live LLM tool execution; API billed separately')
    parser.add_argument('--confirm-live', action='store_true', help='Explicitly authorize an API request')
    parser.add_argument('--model',default='gpt-4.1-mini', help='Model available in your OpenAI API account')
    opt=parser.parse_args()
    if not opt.confirm_live:
        parser.error('Live API traffic is disabled until --confirm-live is supplied')
    api_key=os.environ.get('OPENAI_API_KEY','').strip()
    if not api_key:
        parser.error('OPENAI_API_KEY environment variable is absent')
    request={'target_nm':10,'max_temp':200,'min_purge':20,'objective':'time'}
    report,trace=run_llm_agent(request,api_key=api_key,model=opt.model)
    audit=audit_execution('LLM tool-calling',request,report,trace)
    status='ENGINEERING_REPORT_VERIFIED' if audit['validated_report'] else 'BLOCKED'
    log={'at_utc':dt.datetime.now(dt.timezone.utc).isoformat(), 'model_requested':opt.model,
         'status':status,'audit':audit,
         'note':('Engineering calculations were independently recomputed by local code. '
                 'Editable tool traces do not independently authenticate OpenAI API requests. '
                 'Verify real API usage with your account provider logs. Not manufacturing approval.')}
    out=ROOT/'private_logs'/'live_smoke_summary.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(log,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Live call attempt finished: {status}; local metadata: {out}')
    print('Do not share raw API credentials, private trace, or billing details.')
    if status!='ENGINEERING_REPORT_VERIFIED':
        raise SystemExit(1)

if __name__=='__main__':main()
