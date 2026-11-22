"use strict";
const $ = (selector) => document.querySelector(selector);
const element = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

function configureAppLink() {
  const link = $('#launch-app');
  const hint = $('#app-hint');
  const raw = String(window.ALD_OPTIX_APP_URL || '').trim();
  let url;
  try { url = new URL(raw); } catch { url = null; }
  if (url && url.protocol === 'https:' && url.hostname.endsWith('.streamlit.app')) {
    link.href = url.toString();
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.removeAttribute('aria-disabled');
    link.innerHTML = 'AI 분석 앱 열기 <span aria-hidden="true">↗</span>';
    hint.textContent = 'Streamlit Community Cloud에서 구동하는 상세 분석 서비스가 새 탭에서 열립니다.';
  } else {
    link.href = '#lab';
    link.setAttribute('aria-disabled', 'true');
    link.addEventListener('click', (event) => event.preventDefault());
    hint.textContent = 'Streamlit 공개 URL을 site/config.js에 등록하면 상세 분석 앱 버튼이 자동 활성화됩니다. 현재 브라우저 미리보기는 독립적으로 동작합니다.';
  }
}

// Fixed, independently pinned published DOE summary. This constant is NOT
// read from the potentially corrupted data.json payload. A deliberate revision
// of Table 5 requires rechecking the paper and explicitly updating this table.
const PINNED_MEASURED_RECIPES = Object.freeze(
  [[175,10,20,10,1.34,0.0,2],[175,10,20,20,1.27,0.01414,2],[175,10,40,10,1.04,0.05657,2],[175,10,40,20,1.41,0.01414,2],[175,20,20,10,1.225,0.00707,2],[175,20,20,20,1.205,0.02121,2],[175,20,40,10,1.32,0.0,2],[175,20,40,20,1.265,0.00707,2],[275,10,20,10,1.145,0.00707,2],[275,10,20,20,0.965,0.00707,2],[275,10,40,10,1.22,0.0,2],[275,10,40,20,1.165,0.00707,2],[275,20,20,10,1.04,0.0,2],[275,20,20,20,0.95,0.0,2],[275,20,40,10,1.1,0.0,2],[275,20,40,20,1.01,0.01414,2]]
);
const RECIPE_FIELDS = Object.freeze(['temperature_C','flow_sccm','pulse_ms',
  'purge_s','gpc_mean_A','gpc_sd_A','replications']);

// Static diagnostic claims and the eight developer-defined acceptance cases
// are pinned too: a damaged data.json must not display fabricated performance.
const PINNED_SUMMARY = Object.freeze({"source":"Pan & Lei, Materials 2025, 18(9), 1918, Tables 4–5","doi":"https://doi.org/10.3390/ma18091918","scope":"Al2O3 thermal ALD, TMA/H2O, one published experiment","baseline_MAE_A":0.122854,"initial_complex_MAE_A":0.159204,"nested_MAE_A":0.089867});
const PINNED_10NM_COMPARISON = Object.freeze({"baseline_gpc_A":1.41,"baseline_cycles":71,"baseline_min":47.428,"best_gpc_A":1.34,"best_cycles":75,"best_min":25.05,"model_sequence_reduction_pct":47.1831});
const PINNED_CASEBOOK_DISPLAY = Object.freeze([["C01","GPC 최우선",16,true,true,"후보 검토","v0/v1 모두 독립 참조 후보와 일치 (막 특성 승인 아님)"],["C02","GPC 최우선 · 200°C 이하",8,true,true,"후보 검토","v0/v1 모두 독립 참조 후보와 일치 (막 특성 승인 아님)"],["C03","시퀀스 최단",16,false,true,"후보 검토","v0는 요구 조건 또는 독립 참조의 목적별 최적 후보와 불일치"],["C04","시퀀스 최단 · 200°C 이하",8,false,true,"후보 검토","v0는 요구 조건 또는 독립 참조의 목적별 최적 후보와 불일치"],["C05","Ar 20 sccm 필수",8,false,true,"후보 검토","v0는 요구 조건 또는 독립 참조의 목적별 최적 후보와 불일치"],["C06","Purge 10초 이하",8,false,true,"후보 검토","v0는 요구 조건 또는 독립 참조의 목적별 최적 후보와 불일치"],["C07","150°C 이하",0,false,true,"추천 거부","실측 후보 없음 또는 입력 충돌: 추천 거부가 정답"],["C08","Purge 상·하한 충돌",0,false,true,"추천 거부","실측 후보 없음 또는 입력 충돌: 추천 거부가 정답"]]);

function validatedSiteSummary(payload) {
  if (!Object.entries(PINNED_SUMMARY).every(([name,value]) => payload[name] === value)) return false;
  const comp = payload.comparison_10nm;
  if (!comp || typeof comp !== 'object' || Array.isArray(comp) ||
      !Object.entries(PINNED_10NM_COMPARISON).every(([name,value]) => comp[name] === value)) return false;
  if (!payload.nested_selection || payload.nested_selection.main !== 16 ||
      Object.keys(payload.nested_selection).length !== 1) return false;
  const cases = payload.engineering_cases;
  if (!Array.isArray(cases) || cases.length !== PINNED_CASEBOOK_DISPLAY.length) return false;
  return cases.every((c,index) => {
    if (!c || typeof c !== 'object' || Array.isArray(c)) return false;
    const actual = [c.case_id,c.scenario,c.feasible_candidates,c.v0_pass,c.v1_pass,c.v1_action,c.diagnosis];
    const expected = PINNED_CASEBOOK_DISPLAY[index];
    return actual.every((value,i) => value === expected[i] && typeof value === typeof expected[i]);
  });
}

function validatedMeasuredData(payload) {
  if (!payload || !Array.isArray(payload.recipes) ||
      payload.recipes.length !== PINNED_MEASURED_RECIPES.length ||
      payload.recipe_count !== 16 || payload.experiment_count !== 32) return false;
  const expected = new Map(PINNED_MEASURED_RECIPES.map(row =>
    [row.slice(0,4).join(':'), row]));
  const seen = new Set();
  for (const recipe of payload.recipes) {
    if (!recipe || typeof recipe !== 'object' || Array.isArray(recipe) ||
        Object.keys(recipe).length !== RECIPE_FIELDS.length ||
        !RECIPE_FIELDS.every(name => Object.prototype.hasOwnProperty.call(recipe,name))) return false;
    const fields = RECIPE_FIELDS.map(name => recipe[name]);
    if (!fields.every(value => typeof value === 'number' && Number.isFinite(value))) return false;
    const key = fields.slice(0,4).join(':');
    const trusted = expected.get(key);
    if (!trusted || seen.has(key) || !fields.every((value,index) => value === trusted[index])) return false;
    seen.add(key);
  }
  return seen.size === 16 && validatedSiteSummary(payload);
}

const cyclesFor = (nm, gpcA) => Math.ceil(nm * 10 / gpcA);
const sequenceSeconds = (r, cycles) => cycles * (2 * r.pulse_ms / 1000 + 2 * r.purge_s);

function chooseRecipe(payload, req) {
  // An invalid static payload must never produce a plausible-looking recipe.
  if (!validatedMeasuredData(payload)) {
    return {error: '실측 데이터 무결성 검증에 실패했습니다. 추천을 중단합니다.'};
  }
  if (!req || !Number.isFinite(req.targetNm) ||
      !Number.isFinite(req.maxTemp) || !Number.isFinite(req.minPurge) ||
      !['time','gpc','balanced'].includes(req.objective)) {
    return {error: '유효한 두께, 온도, purge 및 최적화 목표를 지정해 주세요.'};
  }
  const all = payload.recipes;
  if (!Number.isFinite(req.targetNm) || req.targetNm < 0.1 || req.targetNm > 1000) {
    return {error: '목표 두께는 0.1~1000 nm 범위에서 입력해 주세요.'};
  }
  const filtered = all.filter(r => r.temperature_C <= req.maxTemp && r.purge_s >= req.minPurge);
  if (!filtered.length) return {error:'해당 제한조건에 맞는 실측 레시피가 없습니다. 미측정 조건을 만들어 추천하지 않습니다.'};
  const scored = filtered.map(r => {
    const cycles = cyclesFor(req.targetNm, r.gpc_mean_A);
    return {...r, cycles, sequence_time_s: sequenceSeconds(r, cycles)};
  });
  if (req.objective === 'balanced') {
    const times = scored.map(r => r.sequence_time_s), gpcs = scored.map(r => r.gpc_mean_A);
    const tmin = Math.min(...times), tmax = Math.max(...times), gmin = Math.min(...gpcs), gmax = Math.max(...gpcs);
    scored.forEach(r => {r.balance_score = 0.65 * (r.sequence_time_s - tmin) / Math.max(1, tmax - tmin) + 0.35 * (gmax - r.gpc_mean_A) / Math.max(.001, gmax - gmin);});
    scored.sort((a,b) => a.balance_score - b.balance_score || a.sequence_time_s - b.sequence_time_s);
  } else if (req.objective === 'gpc') {
    scored.sort((a,b) => b.gpc_mean_A - a.gpc_mean_A || a.sequence_time_s - b.sequence_time_s);
  } else {
    scored.sort((a,b) => a.sequence_time_s - b.sequence_time_s || b.gpc_mean_A - a.gpc_mean_A);
  }
  return {best: scored[0], feasible: scored.length};
}

function displayRecipe(result, payload) {
  const root = $('#recipe-output');
  root.replaceChildren();
  const status = $('#model-status');
  if (result.error) {
    status.textContent = '미측정 조건 거부';
    root.append(element('p','lab-error', '⚠ '+result.error));
    root.append(element('p','output-warning','추천을 생성하지 않았습니다. 조건을 수정하거나 추가 실험을 검토하세요.'));
    return;
  }
  status.textContent = '실측 범위 검토';
  const r = result.best;
  root.append(element('h3','', '선택된 공정 후보'));
  const main = element('div','metric-big',`${r.temperature_C}°C`);
  const unit = element('span','',`Ar ${r.flow_sccm} sccm`);
  main.append(unit); root.append(main);
  root.append(element('p','metric-sub',`TMA/H₂O 각각 ${r.pulse_ms} ms pulse · 각 ${r.purge_s} s purge`));
  const metrics = element('div','output-metrics');
  [
    [`${r.gpc_mean_A.toFixed(3)}`, '관측 평균 GPC (Å/cycle)'],
    [`${r.cycles}`, '목표 두께 환산 cycles'],
    [`${(r.sequence_time_s / 60).toFixed(2)}`, '가정 시퀀스 시간 (분)'],
  ].forEach(([value,label]) => {const box = element('div');box.append(element('strong','',value),element('span','',label));metrics.append(box)});
  root.append(metrics);
  root.append(element('p','output-warning',`유효한 실측 후보 ${result.feasible}/16개. 값은 2회 반복 측정한 GPC 평균을 이용한 계산으로, 장비 지연시간·포화 여부·막 품질은 반영하지 않았습니다.`));
  root.append(element('p','output-warning',`비교 기준 v0(제약 무시/GPC 최대화)는 동일 목표에서도 반드시 최단 시퀀스 조건이 아닙니다. 자세한 모델 검증은 상세 분석 앱에서 확인할 수 있습니다.`));
}

async function boot() {
  configureAppLink();
  const output = $('#recipe-output');
  try {
    const response = await fetch('./data.json', {cache:'no-store'});
    if (!response.ok) throw new Error('데이터 파일을 불러오지 못했습니다.');
    const payload = await response.json();
    if (!validatedMeasuredData(payload)) throw new Error('실측 데이터 값 또는 DOE 조건이 원자료와 다릅니다.');
    if (![payload.baseline_MAE_A, payload.initial_complex_MAE_A,
          payload.nested_MAE_A].every(n => typeof n === 'number' && Number.isFinite(n) && n > 0)) {
      throw new Error('모델 검증 수치가 유효하지 않습니다.');
    }
    // The casebook is derived from the same Python core and published with data.json.
    const cases = payload.engineering_cases || [];
    if (cases.length === 8) {
      $('#case-v0-count').textContent = `${cases.filter(c => c.v0_pass).length}/8`;
      $('#case-v1-count').textContent = `${cases.filter(c => c.v1_pass).length}/8`;
      const body = $('#casebook-body');
      body.replaceChildren();
      cases.forEach(c => {
        const tr = document.createElement('tr');
        const cells = [c.scenario, c.v0_pass ? '통과' : '미통과', c.v1_pass ? '통과' : '미통과', c.diagnosis];
        cells.forEach((value, idx) => {
          const td = element('td', idx === 1 ? (c.v0_pass ? 'pass' : 'fail') : idx === 2 ? (c.v1_pass ? 'pass' : 'fail') : '', value);
          tr.appendChild(td);
        });
        body.appendChild(tr);
      });
    }
    $('#nested-mae').textContent = payload.nested_MAE_A.toFixed(3);
    $('#baseline-mae').textContent = payload.baseline_MAE_A.toFixed(3);
    $('#complex-mae').textContent = payload.initial_complex_MAE_A.toFixed(3);
    $('#nested-mae-mini').textContent = payload.nested_MAE_A.toFixed(3);
    const maxValue = Math.max(payload.baseline_MAE_A, payload.initial_complex_MAE_A, payload.nested_MAE_A);
    const graphRows = document.querySelectorAll('.mini-chart > div');
    [payload.baseline_MAE_A, payload.initial_complex_MAE_A, payload.nested_MAE_A].forEach((value,index) => {
      const bar = graphRows[index]?.querySelector('i');
      if (bar) bar.style.setProperty('--w', `${(100*value/maxValue).toFixed(2)}%`);
    });
    function render(event) {
      if (event) event.preventDefault();
      const req = {targetNm:Number($('#target-nm').value),maxTemp:Number($('#max-temp').value),objective:$('#objective').value,minPurge:Number($('#min-purge').value)};
      displayRecipe(chooseRecipe(payload, req), payload);
    }
    $('#recipe-form').addEventListener('submit', render);
    render();
  } catch (err) {
    $('#model-status').textContent = '데이터 오류';
    output.replaceChildren(element('p','lab-error','실측 데이터 로딩 또는 무결성 검사에 실패했습니다. 원시 CSV와 data.json의 일치 여부를 확인해 주세요.'));
    console.error('ALD-OPTIX dataset load error:',err);
  }
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',boot); else boot();
