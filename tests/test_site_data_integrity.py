"""Site data integrity — software regression tests."""
import subprocess
from pathlib import Path
import json
import hashlib
import core

ROOT = Path(__file__).resolve().parents[1]


def test_static_data_mutations_are_rejected_even_if_values_look_plausible():
    js = r'''
const fs = require('fs'), vm = require('vm');
const js = fs.readFileSync('site/main.js', 'utf8');
const clean = JSON.parse(fs.readFileSync('site/data.json','utf8'));
const context = {document:{readyState:'loading',addEventListener:()=>{}},window:{},console};
vm.createContext(context);
vm.runInContext(js + '\nthis.chooseRecipe=chooseRecipe;', context);
const req = {targetNm:10,maxTemp:275,minPurge:10,objective:'time'};
const copy = () => JSON.parse(JSON.stringify(clean));
if (context.chooseRecipe(clean,req).error) throw Error('Shipped data rejected');
const cases = [
  x => {x.recipes[0].gpc_mean_A = 999},
  x => {x.recipes[0].gpc_mean_A = 1.3400001},
  x => {x.recipes[0].gpc_sd_A = 0.001},
  x => {x.recipes[0].replications = true},
  x => {x.recipes[0].temperature_C = 180},
  x => {x.recipes[0] = x.recipes[1]},
  x => {delete x.recipes[0].gpc_mean_A},
  x => {x.recipes[0].gpc_mean_A = NaN},
  x => {x.baseline_MAE_A = 0.00001},
  x => {x.comparison_10nm.model_sequence_reduction_pct = 99.99},
  x => {x.engineering_cases[0].v0_pass = false},
  x => {x.engineering_cases[0].diagnosis = 'Fake manufacturing evidence'},
  x => {x.nested_selection.main = 100},
  x => {x.recipe_count = 15},
  x => {delete x.recipes},
];
for (let i = 0; i < cases.length; i++) {
  const x = copy(); cases[i](x);
  const y = context.chooseRecipe(x,req);
  if (!y.error || y.best) throw Error('Corrupt payload accepted #' + i);
}
const invalidReq = [null,{}, {targetNm:10,maxTemp:NaN,minPurge:10,objective:'time'},
  {targetNm:10,maxTemp:275,minPurge:10,objective:'unknown'}];
for(const r of invalidReq) if (!context.chooseRecipe(clean,r).error) throw Error('Invalid request accepted');
console.log('PASS: 15 corrupt payloads and 4 bad requests fail closed');
'''
    run = subprocess.run(['node', '-e', js], text=True, capture_output=True,
                         cwd=ROOT, check=False, timeout=20)
    assert run.returncode == 0, run.stderr


def test_expected_source_bytes_are_fixed_and_reported():
    expected = 'f61d6f101c6d48dfd4677a9c131c6b383c55186c3d17d93e726de1bf463342ec'
    assert core.EXPECTED_SOURCE_CSV_SHA256 == expected
    assert hashlib.sha256(core.DATA_FILE.read_bytes()).hexdigest() == expected


def test_source_csv_any_one_byte_change_is_rejected(tmp_path, monkeypatch):
    raw = core.DATA_FILE.read_bytes()
    variants = [raw.replace(b'0.96\n',b'0.96000001\n',1),
                raw.replace(b'0.96\n',b'0.97\n',1),
                raw.replace(b'\n',b'\r\n')]
    for candidate in variants:
        assert candidate != raw
        path = tmp_path / 'changed.csv'
        path.write_bytes(candidate)
        monkeypatch.setattr(core, 'DATA_FILE', path)
        try:
            core.load_data()
        except ValueError as exc:
            assert 'fingerprint' in str(exc)
        else:
            raise AssertionError('Modified CSV unexpectedly passed raw integrity check')
