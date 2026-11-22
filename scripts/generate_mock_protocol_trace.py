"""Create clearly labeled OFFLINE mock LLM protocol evidence.

No OpenAI API request is made and no real credentials are required.
Used to demonstrate protocol flow in the classroom without misrepresenting
an externally operated LLM service.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent import run_llm_agent
from exports import trace_download_json

class MockMessage:
    def __init__(self, calls=None, content=''):
        self.tool_calls=calls or []
        self.content=content
    def model_dump(self,exclude_none=True):
        return {'role':'assistant','content':self.content,'tool_calls':[
            {'id':c.id,'type':'function','function':{'name':c.function.name,
                                                    'arguments':c.function.arguments}}
            for c in self.tool_calls]}

class MockClient:
    def __init__(self,messages):
        self.responses=iter(messages)
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def create(self,**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=next(self.responses))])


def function_call(name,args,number):
    return SimpleNamespace(id='mock_call_'+str(number),
        function=SimpleNamespace(name=name,arguments=json.dumps(args,ensure_ascii=False)))


def mocked_run(attack=False):
    request={'target_nm':10,'min_purge':20,'max_temp':200,'objective':'time'}
    calls=[function_call('search_evidence',{'query':'Al2O3 GPC purge DOE'},1),
           function_call('find_recipes',{'min_purge':10} if attack else {},2)]
    fake=MockClient([
        MockMessage(calls=calls),
        MockMessage(content='Actual manufacturing outcomes remain unverified.'),
    ])
    report,trace=run_llm_agent(request,'mock-not-a-secret',client=fake)
    return trace_download_json('Mock LLM protocol',request,report,trace)


def run():
    destination=ROOT/'docs'/'mock_llm_protocol.json'
    payload={
        'warning':'OFFLINE MOCK PROTOCOL ONLY. NO LIVE LLM API REQUEST WAS PERFORMED.',
        'success_case':json.loads(mocked_run(attack=False)),
        'blocked_constraint_attack':json.loads(mocked_run(attack=True)),
    }
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(f'Generated {destination.relative_to(ROOT)} (offline mock; not live API).')
    return payload

if __name__=='__main__': run()
