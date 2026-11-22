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
  // Reject corrupted experiments before using any values.
  if (!validatedMeasuredData(payload)) {
    return {error: '실측 데이터 무결성 검증에 실패했습니다. 추천을 중단합니다.'};
  }
  if (!req || typeof req !== 'object') return {error: '공정 조건을 입력해 주세요.'};
  // Backward-compatible defaults for the public regression comparison harness.
  const normalized = {
    targetNm: req.targetNm, objective: req.objective,
    minTemp: req.minTemp === undefined ? 175 : req.minTemp,
    maxTemp: req.maxTemp,
    flowChoice: req.flowChoice === undefined ? 'any' : req.flowChoice,
    pulseChoice: req.pulseChoice === undefined ? 'any' : req.pulseChoice,
    minPurge: req.minPurge,
    maxPurge: req.maxPurge === undefined ? 20 : req.maxPurge,
  };
  if (!['targetNm','minTemp','maxTemp','minPurge','maxPurge'].every(k =>
        typeof normalized[k] === 'number' && Number.isFinite(normalized[k])) ||
      !['time','gpc','balanced'].includes(normalized.objective) ||
      !['any',10,20].includes(normalized.flowChoice) ||
      !['any',20,40].includes(normalized.pulseChoice)) {
    return {error: '목표 두께와 공정 제약을 올바르게 지정해 주세요.'};
  }
  if (normalized.targetNm < 0.1 || normalized.targetNm > 1000) {
    return {error: '목표 두께는 0.1~1000 nm 범위에서 입력해 주세요.'};
  }
  if (normalized.minTemp < 0 || normalized.maxTemp > 1000 ||
      normalized.maxTemp < 0 || normalized.minTemp > 1000 ||
      normalized.minPurge < 0 || normalized.maxPurge < 0 ||
      normalized.minPurge > 3600 || normalized.maxPurge > 3600) {
    return {error: '온도는 0~1000°C, purge는 0~3600초 범위로 입력해 주세요.'};
  }
  if (normalized.minTemp > normalized.maxTemp || normalized.minPurge > normalized.maxPurge) {
    return {error: '제약조건의 상한과 하한이 충돌합니다. 범위를 수정해 주세요.'};
  }
  const all = payload.recipes;
  const filtered = all.filter(r =>
    r.temperature_C >= normalized.minTemp && r.temperature_C <= normalized.maxTemp &&
    r.purge_s >= normalized.minPurge && r.purge_s <= normalized.maxPurge &&
    (normalized.flowChoice === 'any' || r.flow_sccm === normalized.flowChoice) &&
    (normalized.pulseChoice === 'any' || r.pulse_ms === normalized.pulseChoice));
  if (!filtered.length) return {error:'해당 제한조건에 맞는 실측 레시피가 없습니다. 미측정 조건을 만들어 추천하지 않습니다.'};
  const scored = filtered.map(r => {
    const cycles = cyclesFor(normalized.targetNm, r.gpc_mean_A);
    return {...r, cycles, sequence_time_s: sequenceSeconds(r, cycles)};
  });
  if (normalized.objective === 'balanced') {
    const times = scored.map(r => r.sequence_time_s), gpcs = scored.map(r => r.gpc_mean_A);
    const tmin = Math.min(...times), tmax = Math.max(...times), gmin = Math.min(...gpcs), gmax = Math.max(...gpcs);
    scored.forEach(r => {r.balance_score = 0.65 * (r.sequence_time_s - tmin) / Math.max(1, tmax - tmin) + 0.35 * (gmax - r.gpc_mean_A) / Math.max(.001, gmax - gmin);});
    scored.sort((a,b) => a.balance_score - b.balance_score || a.sequence_time_s - b.sequence_time_s);
  } else if (normalized.objective === 'gpc') {
    scored.sort((a,b) => b.gpc_mean_A - a.gpc_mean_A || a.sequence_time_s - b.sequence_time_s);
  } else {
    scored.sort((a,b) => a.sequence_time_s - b.sequence_time_s || b.gpc_mean_A - a.gpc_mean_A);
  }
  return {best:scored[0], feasible:scored.length, ranked:scored, request:normalized};
}

function constraintDescription(req) {
  const parts = [`${req.targetNm} nm`, `온도 ${req.minTemp}~${req.maxTemp}°C`,
    `purge ${req.minPurge}~${req.maxPurge}s`];
  if (req.flowChoice !== 'any') parts.push(`Ar ${req.flowChoice}sccm`);
  if (req.pulseChoice !== 'any') parts.push(`pulse ${req.pulseChoice}ms`);
  return parts.join(' · ');
}

function displayRecipe(result) {
  const root = $('#recipe-output');
  root.replaceChildren();
  const status = $('#model-status');
  if (result.error) {
    status.textContent = '추천 보류 · 입력 검토';
    root.append(element('p','lab-error', '⚠ '+result.error));
    root.append(element('p','output-warning','조건을 수정해 주세요. 현재 요청으로 보고 가능한 후보는 생성하지 않았습니다.'));
    return;
  }
  status.textContent = `실측 ${result.feasible}/16 후보 검토`;
  const r = result.best;
  root.append(element('p','decision-eyebrow','RECOMMENDATION / VERIFIED DOE CANDIDATE'));
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
  ].forEach(([value,label]) => {const box=element('div');box.append(element('strong','',value),element('span','',label));metrics.append(box);});
  root.append(metrics);
  const evidence=element('div','decision-evidence');
  evidence.append(element('span','',`GPC 표준편차 ±${r.gpc_sd_A.toFixed(5)} Å/cycle (n=${r.replications})`));
  evidence.append(element('span','',`일치하는 실측 후보 ${result.feasible} / 전체 16개`));
  root.append(evidence);
  const rationale = result.request.objective === 'gpc'
    ? '허용 후보 중 평균 GPC가 최대인 조건을 선택했습니다. 동일 GPC일 때만 시간을 비교합니다.'
    : result.request.objective === 'balanced'
      ? '허용 후보 내 시간 65%·GPC 35%의 정규화된 점수를 비교했습니다. 가중치는 프로젝트 설계값이며 품질 인증이 아닙니다.'
      : '허용 후보 중 계산상 시퀀스 시간이 최소인 조건을 선택했습니다. 동률이면 평균 GPC를 비교합니다.';
  const box=element('div','decision-rationale');
  box.append(element('strong','','선정 근거'),element('p','',rationale),element('small','',`적용 조건: ${constraintDescription(result.request)}`));
  root.append(box);
  root.append(element('p','output-warning',`이 결과는 논문 실측 GPC의 2회 반복 평균으로 계산했습니다. 장비 지연시간, 포화·균일도·불순물 및 실제 막 품질은 검증되지 않았습니다.`));
}

let currentRanked = [];
let showAllCandidates = false;
let lastRequest = null;
function updateCandidateRows() {
  const body = $('#candidate-rows');
  body.replaceChildren();
  const shown = showAllCandidates ? currentRanked : currentRanked.slice(0,6);
  shown.forEach((r,i) => {
    const row = element('tr',i===0?'candidate-best':'');
    const values=[`${i+1}${i===0?' · 추천':''}`,`${r.temperature_C}°C`,`${r.flow_sccm} sccm`,
      `${r.pulse_ms} ms`,`${r.purge_s} s`,`${r.gpc_mean_A.toFixed(3)} ± ${r.gpc_sd_A.toFixed(5)}`,
      `${r.cycles}`,`${(r.sequence_time_s/60).toFixed(2)}분`];
    values.forEach(v => row.append(element('td','',v)));
    body.append(row);
  });
  const toggle = $('#toggle-candidates');
  toggle.hidden = currentRanked.length<=6;
  toggle.textContent = showAllCandidates ? '상위 6개만 보기' : `전체 ${currentRanked.length}개 보기`;
}
function displayCandidates(result) {
  const panel=$('#candidate-panel');
  if (result.error) {
    currentRanked=[]; lastRequest=null; showAllCandidates=false;
    $('#candidate-rows').replaceChildren();
    panel.hidden=true;
    return;
  }
  currentRanked=result.ranked;
  lastRequest=result.request;
  showAllCandidates=false;
  const objLabel={time:'시간 최소화',gpc:'GPC 최대화',balanced:'시간 65% + GPC 35% 균형'}[result.request.objective];
  $('#candidate-intro').textContent = `${constraintDescription(result.request)} · ${objLabel} 기준으로 ${result.feasible}개 후보를 정렬했습니다.`;
  panel.hidden=false;
  updateCandidateRows();
}
// Charts use only verified, observed recipes passed through chooseRecipe.
// No new process settings or GPC values are inferred by these visualizations.
const SVG_NS = 'http://www.w3.org/2000/svg';
const FACTORS = Object.freeze({
  temperature_C: ['온도', '°C'], flow_sccm: ['Ar 유량', 'sccm'],
  pulse_ms: ['Pulse', 'ms'], purge_s: ['Purge', 's']
});
function svgNode(tag, attrs = {}, textValue) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, String(value));
  if (textValue !== undefined) node.textContent = String(textValue);
  return node;
}
function asMinutes(r) { return r.sequence_time_s / 60; }
function isDominated(recipe, all) {
  return all.some(other => other !== recipe &&
    other.sequence_time_s <= recipe.sequence_time_s &&
    other.gpc_mean_A >= recipe.gpc_mean_A &&
    (other.sequence_time_s < recipe.sequence_time_s || other.gpc_mean_A > recipe.gpc_mean_A));
}
function chartText(x, y, textValue, extra = {}) {
  return svgNode('text', {x, y, 'font-size': '13', fill:'#587062', ...extra}, textValue);
}
function drawTradeoff(result) {
  const graph = $('#tradeoff-chart');
  graph.replaceChildren();
  const all = result.ranked;
  const plot = {left:74, top:25, width:525, height:244};
  const mins = all.map(asMinutes), gpcs = all.map(r => r.gpc_mean_A);
  const rawXMin = Math.min(...mins), rawXMax = Math.max(...mins);
  const rawYMin = Math.min(...gpcs), rawYMax = Math.max(...gpcs);
  const xPad = Math.max((rawXMax - rawXMin) * 0.12, 1);
  const yPad = Math.max((rawYMax - rawYMin) * 0.15, 0.025);
  const xMin = Math.max(0, rawXMin - xPad), xMax = rawXMax + xPad;
  const yMin = Math.max(0, rawYMin - yPad), yMax = rawYMax + yPad;
  const xPos = value => plot.left + (value - xMin) / (xMax - xMin) * plot.width;
  const yPos = value => plot.top + (yMax - value) / (yMax - yMin) * plot.height;
  graph.append(svgNode('rect',{x:plot.left,y:plot.top,width:plot.width,height:plot.height,rx:8,fill:'#f8fbf7'}));
  for (let i = 0; i <= 4; i++) {
    const x = plot.left + plot.width * i / 4, y = plot.top + plot.height * i / 4;
    graph.append(svgNode('line',{x1:x,x2:x,y1:plot.top,y2:plot.top+plot.height,stroke:'#e5eee6','stroke-width':1}));
    graph.append(svgNode('line',{x1:plot.left,x2:plot.left+plot.width,y1:y,y2:y,stroke:'#e5eee6','stroke-width':1}));
    graph.append(chartText(x,plot.top+plot.height+23,(xMin+(xMax-xMin)*i/4).toFixed(1),{'text-anchor':'middle'}));
    graph.append(chartText(plot.left-11,y+4,(yMax-(yMax-yMin)*i/4).toFixed(3),{'text-anchor':'end'}));
  }
  graph.append(chartText(plot.left+plot.width/2,334,'가정 시퀀스 시간 (분)',{'text-anchor':'middle','font-size':14,'font-weight':650}));
  graph.append(chartText(18,plot.top+plot.height/2,'GPC (Å/cycle)',{'text-anchor':'middle',transform:`rotate(-90 18 ${plot.top+plot.height/2})`,'font-size':13,'font-weight':650}));
  const frontier = all.filter(r=>!isDominated(r,all));
  // Plot rejected candidates first so that the recommended marker remains visible.
  const order = [...all.slice(1),all[0]];
  order.forEach(r => {
    const best = r===all[0], pareto = !isDominated(r,all);
    const color = best ? '#14764d' : pareto ? '#db9c3b' : '#9cb4a6';
    const circle = svgNode('circle',{
      cx:xPos(asMinutes(r)),cy:yPos(r.gpc_mean_A),r: best ? 9 : 6.5,
      fill:color, stroke:'#fff','stroke-width':best ? 3 : 1.8,
      opacity:best ? 1 : .90
    });
    circle.append(svgNode('title',{},`${best?'추천 · ':''}${r.temperature_C}°C · Ar ${r.flow_sccm} · pulse ${r.pulse_ms} ms · purge ${r.purge_s} s · GPC ${r.gpc_mean_A.toFixed(3)} Å/cycle · ${asMinutes(r).toFixed(2)}분`));
    graph.append(circle);
    if (best) graph.append(chartText(Math.min(595,xPos(asMinutes(r))+11),Math.max(15,yPos(r.gpc_mean_A)-12),'추천',{'font-size':12,'font-weight':800,fill:'#116643'}));
  });
  $('#tradeoff-summary').textContent = `검토 후보 ${all.length}개 중 Pareto 비지배 후보 ${frontier.length}개. 추천 조건은 ${result.request.objective==='gpc'?'최대 GPC':result.request.objective==='time'?'최단 시간':'설정된 균형 점수'} 기준이며, 막 품질 검증을 뜻하지 않습니다.`;
}
function drawFactorBars(result) {
  const key = $('#factor-select').value;
  const [name, unit] = FACTORS[key] || FACTORS.temperature_C;
  const box = $('#factor-chart');
  box.replaceChildren();
  const groups = new Map();
  result.ranked.forEach(r => {
    const level = r[key];
    const prev = groups.get(level) || {sum:0,count:0};
    prev.sum += r.gpc_mean_A;
    prev.count++;
    groups.set(level,prev);
  });
  const levels = [...groups.keys()].sort((a,b)=>a-b);
  const values = levels.map(level => groups.get(level).sum / groups.get(level).count);
  const maxValue = Math.max(...values,0.01);
  levels.forEach((level,i) => {
    const avg = values[i], count = groups.get(level).count;
    const row = element('div','factor-bar-row');
    const label = element('div','factor-bar-meta');
    label.append(element('strong','',`${level} ${unit}`),element('span','',`${avg.toFixed(3)} Å/cycle · 후보 ${count}개`));
    const track = element('div','factor-track');
    const fill = element('div','factor-fill');
    fill.style.width = `${100 * avg / maxValue}%`;
    fill.setAttribute('role','img');
    fill.setAttribute('aria-label',`${name} ${level} ${unit}의 후보 평균 GPC ${avg.toFixed(3)} Å/cycle`);
    track.append(fill);
    row.append(label,track);
    box.append(row);
  });
  $('#factor-summary').textContent = `${name} 수준 ${levels.length}개, 실측 후보 ${result.ranked.length}개를 사용한 단순 그룹 평균입니다. 다른 공정 인자가 섞여 있을 수 있으므로 독립적인 인과효과나 미측정 레시피의 예측값으로 해석하지 마세요.`;
}
function drawComparison(result) {
  const summary = $('#analysis-quickstats');
  const comparison = $('#analysis-comparison');
  summary.replaceChildren();comparison.replaceChildren();
  const all = result.ranked, best = all[0];
  const frontierCount = all.filter(r=>!isDominated(r,all)).length;
  const cards = [
    [String(all.length),'통과한 실측 조건'],
    [String(frontierCount),'Pareto 비지배 조건'],
    [`${(best.cycles * best.gpc_mean_A / 10).toFixed(2)} nm`,'추천 조건의 계산상 최종 두께']
  ];
  cards.forEach(([value,label]) => {
    const card=element('div','analysis-stat');
    card.append(element('strong','',value),element('span','',label));
    summary.append(card);
  });
  const title = element('h4','', '상위 후보 성능 비교');
  comparison.append(title);
  if (all.length < 2) {
    comparison.append(element('p','', '현재 제약을 만족하는 실측 후보가 하나뿐이므로 차순위 후보와 비교할 수 없습니다.'));
    return;
  }
  const second = all[1];
  const table=element('table','analysis-compare-table');
  const thead=element('thead');
  const thr=element('tr');
  ['지표','추천 1위','2위 후보'].forEach(t=>thr.append(element('th','',t)));
  thead.append(thr);table.append(thead);
  const tbody=element('tbody');
  const rows = [
    ['공정 조건',`${best.temperature_C}°C · Ar ${best.flow_sccm} · ${best.pulse_ms}ms / ${best.purge_s}s`,`${second.temperature_C}°C · Ar ${second.flow_sccm} · ${second.pulse_ms}ms / ${second.purge_s}s`],
    ['평균 GPC',`${best.gpc_mean_A.toFixed(3)} Å/cycle`,`${second.gpc_mean_A.toFixed(3)} Å/cycle`],
    ['목표 두께 cycles',`${best.cycles}회`,`${second.cycles}회`],
    ['가정 시퀀스 시간',`${asMinutes(best).toFixed(2)}분`,`${asMinutes(second).toFixed(2)}분`]
  ];
  rows.forEach((values,i)=>{
    const tr=element('tr');
    values.forEach((t,j)=>tr.append(element(j===0?'th':'td','',t)));
    tbody.append(tr);
  });
  table.append(tbody);
  const wrap=element('div','analysis-compare-wrap');wrap.append(table);comparison.append(wrap);
  comparison.append(element('p','analysis-compare-note','순위는 현재 목적함수에 따른 것이므로 2위가 모든 지표에서 열세라는 뜻은 아닙니다. GPC와 시간의 우열을 별도로 확인하세요.'));
}
function displayAnalysis(result) {
  const panel=$('#analysis-panel');
  if (result.error) {
    panel.hidden=true;
    $('#tradeoff-chart').replaceChildren();
    $('#factor-chart').replaceChildren();
    $('#analysis-quickstats').replaceChildren();
    $('#analysis-comparison').replaceChildren();
    return;
  }
  panel.hidden=false;
  drawTradeoff(result);
  drawFactorBars(result);
  drawComparison(result);
}

function downloadCandidatesCsv() {
  if (!currentRanked.length) return;
  const headings=['rank','temperature_C','flow_sccm','pulse_ms','purge_s','gpc_mean_A_per_cycle','gpc_sd_A_per_cycle','replications','cycles','sequence_time_min'];
  const lines=[headings.join(',')];
  currentRanked.forEach((r,i) => lines.push([i+1,r.temperature_C,r.flow_sccm,r.pulse_ms,r.purge_s,
    r.gpc_mean_A,r.gpc_sd_A,r.replications,r.cycles,(r.sequence_time_s/60).toFixed(3)].join(',')));
  const file=new Blob(['\uFEFF'+lines.join('\n')],{type:'text/csv;charset=utf-8'});
  const url=URL.createObjectURL(file);
  const a=document.createElement('a');a.href=url;a.download='ald-optix-observed-candidates.csv';
  document.body.append(a);a.click();a.remove();URL.revokeObjectURL(url);
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
        const cells = [c.scenario, c.v0_pass ? '통과' : '미통과', c.v1_pass ? '통과' : '미통과'];
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
      const numeric = (id) => {
        const value = $(id).value.trim();
        return value === '' ? NaN : Number(value);
      };
      const req = {
        targetNm:numeric('#target-nm'),
        minTemp:numeric('#min-temp'),maxTemp:numeric('#max-temp'),
        flowChoice:$('#flow-choice').value === 'any' ? 'any' : Number($('#flow-choice').value),
        pulseChoice:$('#pulse-choice').value === 'any' ? 'any' : Number($('#pulse-choice').value),
        minPurge:numeric('#min-purge'),maxPurge:numeric('#max-purge'),
        objective:$('#objective').value,
      };
      const result=chooseRecipe(payload,req);
      displayRecipe(result);
      displayCandidates(result);
      displayAnalysis(result);
    }
    const form=$('#recipe-form');
    form.addEventListener('submit', render);
    form.addEventListener('change', render);
    ['#target-nm','#min-temp','#max-temp','#min-purge','#max-purge'].forEach(id=>$(id).addEventListener('input',render));
    $('#factor-select').addEventListener('change',()=>{
      if (currentRanked.length && lastRequest) drawFactorBars({ranked:currentRanked,request:lastRequest});
    });
    $('#reset-recipe').addEventListener('click',()=>{form.reset();render();});
    $('#toggle-candidates').addEventListener('click',()=>{showAllCandidates=!showAllCandidates;updateCandidateRows();});
    $('#download-candidates').addEventListener('click',downloadCandidatesCsv);
    render();
  } catch (err) {
    $('#model-status').textContent = '데이터 오류';
    output.replaceChildren(element('p','lab-error','실측 데이터 로딩 또는 무결성 검사에 실패했습니다. 원시 CSV와 data.json의 일치 여부를 확인해 주세요.'));
    displayCandidates({error:'data error'});
    displayAnalysis({error:'data error'});
    console.error('ALD-OPTIX dataset load error:',err);
  }
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',boot); else boot();
