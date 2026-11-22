"""Data and trace types — software regression tests."""
from copy import deepcopy
from pathlib import Path
import subprocess
import pytest

from agent import deterministic_demo
from exports import audit_execution
import core


def test_trace_parsed_number_changed_to_boolean_must_be_rejected():
    req = {'target_nm': 1.0, 'objective': 'time'}
    report, trace = deterministic_demo(req)
    assert audit_execution('Deterministic tools', req, report, trace)['validated_report']
    tampered = deepcopy(trace)
    tampered[0]['result']['parsed']['target_nm'] = True  # True == 1.0 in Python
    assert not audit_execution('Deterministic tools', req, report, tampered)['validated_report']


def test_trace_measured_candidate_count_changed_to_boolean_must_be_rejected():
    req = {'target_nm': 10.0, 'max_temp': 175, 'min_flow': 10, 'max_flow': 10,
           'min_pulse': 20, 'max_pulse': 20, 'min_purge': 10, 'max_purge': 10,
           'objective': 'time'}
    report, trace = deterministic_demo(req)
    assert audit_execution('Deterministic tools', req, report, trace)['validated_report']
    tampered = deepcopy(trace)
    tool = next(row for row in tampered if row['tool'] == 'find_recipes')
    assert tool['result']['n_feasible'] == 1
    tool['result']['n_feasible'] = True
    assert not audit_execution('Deterministic tools', req, report, tampered)['validated_report']


def test_source_csv_additional_precision_cannot_bypass_integrity(monkeypatch, tmp_path):
    original = core.DATA_FILE.read_text(encoding='utf-8')
    modified = original.replace(',0.96\n', ',0.96000001\n', 1)
    assert modified != original
    modified_csv = tmp_path / 'modified.csv'
    modified_csv.write_text(modified, encoding='utf-8')
    monkeypatch.setattr(core, 'DATA_FILE', modified_csv)
    with pytest.raises(ValueError, match='fingerprint|hash|source'):
        core.load_data()


def test_static_homepage_rejects_tampered_gpc_in_loaded_json():
    source_dir = Path(core.__file__).parent
    js = r'''
const fs = require('fs'); const vm = require('vm');
const source = fs.readFileSync('site/main.js','utf8');
const data = JSON.parse(fs.readFileSync('site/data.json','utf8'));
const ctx = {document:{readyState:'loading',addEventListener:()=>{}},window:{},console};
vm.createContext(ctx);
vm.runInContext(source+'\nthis.choose=chooseRecipe;',ctx);
data.recipes[0].gpc_mean_A = 999; // not an experimental GPC in Table 5
const output = ctx.choose(data,{targetNm:10,maxTemp:275,minPurge:10,objective:'gpc'});
if (!output.error) { console.error('Invalid data accepted:',output.best.gpc_mean_A); process.exit(12); }
'''
    completed = subprocess.run(['node', '-e', js], cwd=source_dir,
                               text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
