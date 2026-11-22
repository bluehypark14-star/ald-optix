import json
from types import SimpleNamespace
class DummyMessage:
    def __init__(self,calls=None,content=''):
        self.tool_calls=calls or []
        self.content=content
    def model_dump(self,exclude_none=True):
        return {'role':'assistant','content':self.content,'tool_calls':[
            {'id':c.id,'type':'function',
             'function':{'name':c.function.name,'arguments':c.function.arguments}}
            for c in self.tool_calls]}
class FakeClient:
    def __init__(self,messages):
        self.messages=iter(messages)
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def create(self,**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=next(self.messages))])
def call(name,args,n):
    return SimpleNamespace(id=f'call_{n}',function=SimpleNamespace(name=name,arguments=json.dumps(args)))
