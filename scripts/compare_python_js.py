"""Compare published static-site JS recipe calculation to Python core on 210 cases.

Requires Node.js only (not Chromium). This tests numeric output, NOT browser UI.
"""
from __future__ import annotations
import itertools, json, subprocess
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core import optimize_recipe

cases=[{'targetNm':thick,'maxTemp':temp,'minPurge':purge,'objective':obj}
       for thick,temp,purge,obj in itertools.product([0.1,1,5,10,12.5,50,100],
             [150,175,200,275,300],[10,20],['time','gpc','balanced'])]
code='''
const fs=require('fs'),vm=require('vm');
const context={window:{},document:{readyState:'loading',addEventListener:()=>{}},URL:URL,console:console};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8')+'\\nthis.chooseRecipe=chooseRecipe;',context);
const data=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const requests=JSON.parse(fs.readFileSync(0,'utf8'));
console.log(JSON.stringify(requests.map(r=>context.chooseRecipe(data,r))));
'''
result=subprocess.run(['node','-e',code,str(ROOT/'site'/'main.js'),str(ROOT/'site'/'data.json')],
          input=json.dumps(cases),text=True,capture_output=True,check=True)
js=json.loads(result.stdout)
for i,(query,actual) in enumerate(zip(cases,js)):
    py=optimize_recipe(query['targetNm'],max_temp=query['maxTemp'],min_purge=query['minPurge'],objective=query['objective'])
    if 'error' in py:
        assert 'error' in actual, (i,query,actual,py)
    else:
        assert 'best' in actual,(i,query,actual)
        assert actual['feasible']==py['n_feasible'],(i,query,'feasible mismatch')
        for key in ('temperature_C','flow_sccm','pulse_ms','purge_s'):
            assert actual['best'][key]==py['best'][key],(i,query,key,actual['best'][key],py['best'][key])
        assert abs(actual['best']['sequence_time_s']-py['best']['sequence_time_s'])<1e-7,(i,query,'time mismatch')
print(f'PASS: {len(cases)} deterministic Python–JavaScript query comparisons')
