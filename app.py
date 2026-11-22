"""ALD-OPTIX | Virtual-company website + reproducible engineering demo.

No deployment key is bundled. A guided workflow (ML + audited Python) always works;
server-side LLM requires protected Streamlit secrets and a separate demo access code.
"""
from __future__ import annotations

import json
import os
import hmac
import hashlib
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import (
    load_data, condition_means, optimize_recipe, naive_v0, constraint_check,
    cross_validate, nested_cross_validate, quality_gate, scenario_suite,
    build_report, EVIDENCE, SOURCE, DOI, sensitivity_analysis, engineering_casebook,
)
from agent import deterministic_demo, run_llm_agent, validated_request
from ui_state import workflow_is_current
from exports import make_recipe_review, trace_download_json, audit_execution

st.set_page_config(
    page_title="ALD-OPTIX | Process Intelligence Lab", page_icon="🧪",
    layout="wide", initial_sidebar_state="collapsed",
)

# No external fonts or images are required for rendering.
st.markdown("""
<style>
:root {--ink:#173d2b;--grass:#135636;--secondary:#496858;--paper:#f6f8f5;--line:#dae3db}
[data-testid="stAppViewContainer"]{background:#f6f8f5;color:#152e22}
[data-testid="stHeader"]{background:rgba(246,248,245,.94)}
.block-container{max-width:1220px;padding-top:1.45rem;padding-bottom:5rem}
html,body,[class*="css"]{font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans CJK KR",sans-serif}
h1,h2,h3{color:#123c27!important;letter-spacing:-.035em!important}
h1{font-size:2.25rem!important}
h2{font-size:1.65rem!important}
p,li{line-height:1.7}
a{color:#136238!important}
[data-testid="stMetric"]{background:#fff;border:1px solid #dce6dd;border-radius:15px;padding:1.15rem;box-shadow:0 3px 10px rgba(23,61,43,.035)}
[data-testid="stMetricValue"]{color:#145e3b!important}
[data-testid="stMetricLabel"] p{color:#486154!important;font-size:.85rem}
.stTabs [data-baseweb="tab-list"]{gap:5px;overflow-x:auto;border-bottom:1px solid #d8e4d9}
.stTabs [data-baseweb="tab"]{font-weight:650;color:#50695b;padding:12px 15px}
.stTabs [aria-selected="true"]{color:#12452d!important;border-color:#135b38!important;background:#e2eee4}
div.stButton>button[kind="primary"]{background:#145b3b;color:white;border:none;font-weight:700;border-radius:10px}
div.stButton>button{border-radius:10px}
[data-testid="stExpander"]{background:white;border-radius:11px}
.hero{background:linear-gradient(117deg,#0c3324 8%,#18533a 76%,#22734b 100%);color:white!important;border-radius:22px;padding:41px 42px;margin-bottom:22px;position:relative;overflow:hidden}
.hero:after{content:'';position:absolute;right:-78px;top:-135px;width:390px;height:390px;border-radius:50%;border:90px solid rgba(181,237,184,.09)}
.hero .eyebrow{font-size:12px;font-weight:800;letter-spacing:.22em;color:#b7e7c6}
.hero h1{font-size:clamp(34px,4.8vw,59px)!important;letter-spacing:-.045em!important;color:white!important;margin:14px 0 14px;line-height:1.15}
.hero p{font-size:16px;max-width:735px;line-height:1.85;color:#e2f2e7}
.hero .capsules{margin-top:22px}
.hero .capsule{display:inline-block;padding:6px 12px;border:1px solid #7eab8c;border-radius:22px;color:#e9f8ee;font-size:12px;margin:0 6px 6px 0}
.suptitle{font-size:12px;letter-spacing:.18em;color:#257348;font-weight:800;margin-bottom:2px}
.k-card{border-radius:15px;background:#fff;border:1px solid #dbe6de;padding:21px;min-height:155px}
.k-card h4{color:#12452f;font-size:16px;margin:0 0 10px;font-weight:750}
.k-card p{color:#536b5d;font-size:13px;margin:0;line-height:1.72}
.section-lead{font-size:14px;color:#5b6e61;line-height:1.8}
.note{background:#e9f1e9;border-left:4px solid #236e49;border-radius:8px;padding:13px 15px;color:#31513b;margin:16px 0;font-size:13px}
.eyebrow{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:#266b44;font-weight:800}
.bar-number{font-size:28px;font-weight:850;color:#0e5334;line-height:1.25}
hr{border-color:#dce6de!important}
[data-testid="stDataFrame"]{border-radius:10px;overflow:hidden}
</style>
""", unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def fetch_data():
    return load_data(), condition_means()

@st.cache_data(show_spinner=False)
def compute_cv():
    e, pred = cross_validate()
    n, n_pred = nested_cross_validate()
    return e, pred, n, n_pred

D, MEANS = fetch_data()

st.markdown("""<div class='hero'>
<div class='eyebrow'>ALD-OPTIX  /  MATERIALS INTELLIGENCE</div>
<h1>From process data<br/>to defensible decisions.</h1>
<p>고객이 원하는 박막 두께와 공정 제약을 입력하면, 공개 실험 데이터의 범위에서 레시피 후보를 비교하고<br/>AI·계산 도구·검증 기록을 하나의 엔지니어링 워크플로로 연결합니다.</p>
<div class='capsules'><span class='capsule'>Al₂O₃ · TMA / H₂O</span><span class='capsule'>16 experimentally observed settings</span><span class='capsule'>Model & evidence audit</span></div>
</div>""", unsafe_allow_html=True)
st.caption("가상 기업 프로젝트 · 공개 논문 데이터 기반 · 실험 전 검토 전용. 실제 장비 제어/막 품질 승인/양산 처리량 입증이 아닙니다.")

t0,t1,t2,t3,t4=st.tabs([
    "01  COMPANY", "02  RECIPE STUDIO", "03  AI WORKFLOW",
    "04  VALIDATION LAB", "05  EVIDENCE & SCOPE",
])

with t0:
    st.markdown("<div class='suptitle'>INDUSTRY PROBLEM</div>",unsafe_allow_html=True)
    st.header("좋은 레시피는 GPC 하나로 결정되지 않습니다.")
    st.markdown("<div class='section-lead'>ALD-OPTIX는 반도체용 ALD 박막 공정의 데이터 기반 의사결정을 지원하는 가상 B2B 기업입니다. 새로운 목표 두께가 주어지면 엔지니어는 기존 연구에서 조건을 찾고, 장비 제한과 실험 데이터의 적용 범위를 확인해야 합니다.</div>",unsafe_allow_html=True)
    s1,s2,s3=st.columns(3)
    with s1:st.markdown("<div class='k-card'><h4>01 / 기존 업무</h4><p>논문·레시피를 하나씩 대조하고, 측정값의 단위·조건을 재확인하며 후보 레시피를 수작업으로 선택합니다.</p></div>",unsafe_allow_html=True)
    with s2:st.markdown("<div class='k-card'><h4>02 / 핵심 문제</h4><p>기존 단순 규칙 v0는 평균 GPC가 가장 높은 조건만 선택해 cycle 수와 purge 시간을 비롯한 제약을 놓칠 수 있습니다.</p></div>",unsafe_allow_html=True)
    with s3:st.markdown("<div class='k-card'><h4>03 / 개선 방향</h4><p>측정된 레시피만 검색하고, 목표·제약에 따라 순위를 계산한 뒤 검증 경고와 인용 근거를 함께 반환합니다.</p></div>",unsafe_allow_html=True)
    st.write("")
    st.subheader("5단계 엔지니어링 워크플로")
    steps=st.columns(5)
    labels=[("01","REQUEST","목표 두께·제약"),("02","RETRIEVE","출처 및 실험조건"),("03","COMPUTE","cycle·시퀀스 추정"),("04","VALIDATE","범위·한계·모델"),("05","REPORT","검토 기록·다운로드")]
    for col,(n,title,detail) in zip(steps,labels):
        with col:
            st.markdown(f"<div class='k-card' style='min-height:122px;padding:16px'><div class='eyebrow'>{n} / {title}</div><p>{detail}</p></div>",unsafe_allow_html=True)
    st.markdown("<div class='note'>핵심 기술: 실제 DOE 데이터 + Python 계산 + 제약조건 검증 + ML 모델 비교 + 선택형 LLM 도구 호출. LLM 미연결 시에는 ‘규칙 기반 가이드 워크플로’로 명확히 표시합니다.</div>",unsafe_allow_html=True)

with t1:
    st.markdown("<div class='suptitle'>DECISION SUPPORT</div>",unsafe_allow_html=True)
    st.header("Recipe Studio")
    st.markdown("논문 Table 5에서 **직접 측정된 16개 조건** 중 후보를 선택해요. 값이 없는 임의의 온도나 공정조건은 생성하지 않습니다.")
    a,b,c=st.columns(3)
    with a: target=st.number_input("목표 두께 (nm)",min_value=0.1,max_value=1000.0,value=10.0,step=0.5,key='target')
    with b: max_temp=st.slider("최대 증착 온도 (°C)",min_value=150,max_value=300,value=275,step=25,key='max_temp')
    with c: objective=st.selectbox("최적화 목표",["시퀀스 시간 최소화","GPC 최대화","균형 (시간 65% + GPC 35%)"])
    d,e,f,h=st.columns(4)
    with d: min_purge=st.selectbox("최소 purge (s)",[10,20],index=0,key='min_purge')
    with e: max_purge=st.selectbox("최대 purge (s)",[10,20],index=1,key='max_purge')
    with f: flow=st.selectbox("Ar 유량 (sccm)",["제한 없음","10만 허용","20만 허용"])
    with h: pulse=st.selectbox("Pulse (ms)",["제한 없음","20만 허용","40만 허용"])
    oflag={"시퀀스 시간 최소화":"time","GPC 최대화":"gpc","균형 (시간 65% + GPC 35%)":"balanced"}[objective]
    min_flow,max_flow=(10,20) if flow=="제한 없음" else ((10,10) if flow.startswith("10") else (20,20))
    min_pulse,max_pulse=(20,40) if pulse=="제한 없음" else ((20,20) if pulse.startswith("20") else (40,40))
    req=dict(target_nm=target,max_temp=max_temp,min_flow=min_flow,max_flow=max_flow,
             min_purge=min_purge,max_purge=max_purge,min_pulse=min_pulse,max_pulse=max_pulse,objective=oflag)
    rs=optimize_recipe(**req)
    baseline=naive_v0(target)
    if 'error' in rs:
        st.error("요청 거부 · " + rs['error'])
        st.caption("해당 요청은 실측 조건을 벗어났거나 제약이 충돌하므로, 사용 가능한 레시피를 발명하지 않습니다.")
    else:
        best=rs['best']
        gate=quality_gate(req,best)
        violated=constraint_check(baseline,max_temp,min_flow,max_flow,min_purge,max_purge,
                                  min_pulse=min_pulse,max_pulse=max_pulse)
        if gate['status'] == 'REJECT':
            st.error('추천 결과의 독립 품질 검증에 실패해 계산 결과와 보고서 발행을 중단했습니다.')
            for error in gate['errors']:
                st.error(error)
        else:
            st.markdown("### 선택된 공정 후보")
            m1,m2,m3,m4=st.columns(4)
            m1.metric("실측 평균 GPC",f"{best['gpc_mean_A']:.3f} Å/cycle")
            m2.metric("목표 두께 환산",f"{int(best['cycles'])} cycles")
            m3.metric("가정한 시퀀스 시간",f"{best['sequence_time_min']:.2f} min")
            m4.metric("실측 범위 내 후보",f"{rs['n_feasible']} / 16")
            st.markdown(f"<div class='note'><b>추천:</b> {best['temperature_C']:.0f} °C · Ar {best['flow_sccm']:.0f} sccm · TMA/H₂O 각각 {best['pulse_ms']:.0f} ms pulse · 각 {best['purge_s']:.0f} s purge<br/><b>검토상태:</b> {gate['status']} — 공정 적합성 승인은 별도 실험이 필요합니다.</div>",unsafe_allow_html=True)
            base_label="v0 (제약 위반 가능)" if violated else "v0 (제약 내)"
            data=pd.DataFrame([
              {"방식":base_label,"GPC (Å/cycle)":baseline['gpc_mean_A'],"Cycles":int(baseline['cycles']),"가정 시퀀스 (분)":baseline['sequence_time_s']/60,"제약 위반":len(violated)},
              {"방식":"v1 (목적·제약 반영)","GPC (Å/cycle)":best['gpc_mean_A'],"Cycles":int(best['cycles']),"가정 시퀀스 (분)":best['sequence_time_min'],"제약 위반":0},
            ])
            st.markdown("#### 기존 v0와 개선 v1 비교")
            st.dataframe(data.style.format({"GPC (Å/cycle)":"{:.3f}","가정 시퀀스 (분)":"{:.2f}"}),hide_index=True,use_container_width=True)
            if violated: st.warning("v0는 입력 제약을 위반했습니다. 아래 수치 비교는 해당 제약하에서의 공정 대안 비교로 해석하면 안 됩니다.")
            g=rs['ranking'].copy()
            g['label']=g.apply(lambda x:f"{int(x.temperature_C)}°C · Ar {int(x.flow_sccm)} · {int(x.pulse_ms)}ms/{int(x.purge_s)}s",axis=1)
            g['Temp group']=g.temperature_C.astype(int).astype(str)+' °C'
            fig=px.scatter(g,x='sequence_time_min',y='gpc_mean_A',color='Temp group',hover_name='label',
                           color_discrete_map={'175 °C':'#1B6B45','275 °C':'#D4934D'},
                           labels={'sequence_time_min':'가정 시퀀스 시간 (분)','gpc_mean_A':'실측 평균 GPC (Å/cycle)'},
                           title='Feasible DOE recipes | GPC ↔ sequence time')
            fig.update_traces(marker=dict(size=11,line=dict(width=1,color='white')))
            fig.add_trace(go.Scatter(x=[best['sequence_time_min']],y=[best['gpc_mean_A']],mode='markers+text',text=['v1 선택'],textposition='top center',marker=dict(size=18,color='#134A31',symbol='star',line=dict(width=1,color='white')),name='선택된 후보'))
            fig.update_layout(height=400,plot_bgcolor='#FFFFFF',paper_bgcolor='#FFFFFF',margin=dict(l=12,r=18,t=55,b=20),legend=dict(orientation='h',y=1.12),font=dict(color='#244b35'))
            st.plotly_chart(fig,use_container_width=True)
            with st.expander("모든 실측 후보 데이터 및 반복측정 편차"):
                st.dataframe(g[['temperature_C','flow_sccm','pulse_ms','purge_s','gpc_mean_A','gpc_sd_A','cycles','sequence_time_min']].round(3),hide_index=True,use_container_width=True)
            st.markdown("#### 가정 민감도 · cycle당 추가 지연시간")
            overhead=st.slider("가정한 추가 지연시간 (초/cycle) — 실측치 아님",min_value=0,max_value=600,value=0,step=10,key='overhead')
            sens=sensitivity_analysis(target_nm=target,overhead_s_per_cycle=overhead,
                                      max_temp=max_temp,min_purge=min_purge,max_purge=max_purge,
                                      min_flow=min_flow,max_flow=max_flow,min_pulse=min_pulse,max_pulse=max_pulse)
            if 'error' not in sens:
                br=sens['best']
                st.info(f"가정한 {overhead}초/cycle을 추가하면 최단 후보: {int(br['temperature_C'])}°C / pulse {int(br['pulse_ms'])}ms / purge {int(br['purge_s'])}s · 총 추정 {br['estimated_total_s']/60:.2f}분")
            with st.expander("Independent quality gate · 필수 검증 체크리스트"):
                st.markdown("**상태: `REVIEW_REQUIRED`는 합격이나 승인 판정이 아닙니다.**")
                for line in gate['errors']: st.error(line)
                for line in gate['warnings']:st.write("• "+line)
            report=make_recipe_review(req,best)
            st.download_button("공정 검토 보고서 (.md)",report,file_name='ALD_OPTIX_recipe_review.md',mime='text/markdown')
            st.download_button("후보 레시피 (.csv)",g.to_csv(index=False).encode('utf-8-sig'),file_name='ALD_OPTIX_candidate_recipes.csv',mime='text/csv')
    st.caption("※ 간소화 시간 = cycle 수 × [2×pulse(ms)/1000 + 2×purge(s)]. 논문 200-cycle 실험 GPC를 목표 두께로 환산했고, 장비 실제 overhead·막 품질·포화 여부는 측정하지 않았습니다.")

with t2:
    st.markdown("<div class='suptitle'>AGENTIC WORKFLOW</div>",unsafe_allow_html=True)
    st.header("AI Engineering Workflow")
    st.write("구조화 요청 또는 제한된 자연어 → 근거 검색 → 실측 조건 필터링 → 모델·검증 실행 → 보고서 생성. 도구 호출 기록을 공개합니다.")
    st.markdown("**실행 모드 선택**")
    selected_mode=st.radio("방식",["규칙 기반 워크플로 (무료·기본)","실제 LLM 도구 호출 (선택 사항)"],horizontal=True,label_visibility='collapsed')
    api_key=''
    llm_chosen=selected_mode.startswith('실제 LLM')
    if llm_chosen:
        st.warning("LLM 모드는 별도 API 자격 증명이 필요합니다. ChatGPT 구독만으로 자동 연결되지 않습니다. 호출 비용이 발생할 수 있습니다. 접근 코드 제한은 세션 기준이므로 공개 서비스의 전역 비용 제한을 대신하지 않습니다.")
        st.caption("보안을 위해 방문자의 API 키 입력은 받지 않습니다. 앱 운영자의 서버 비밀 설정과 시연 접근 코드가 필요합니다.")
        server_key=os.getenv('OPENAI_API_KEY','')
        server_passcode=os.getenv('DEMO_ACCESS_CODE','')
        demo_enabled=os.getenv('ENABLE_LLM_DEMO','').strip().lower() in ('1','true','yes')
        try:
            server_key=server_key or st.secrets.get('OPENAI_API_KEY','')
            server_passcode=server_passcode or st.secrets.get('DEMO_ACCESS_CODE','')
            demo_enabled=demo_enabled or str(st.secrets.get('ENABLE_LLM_DEMO','')).strip().lower() in ('1','true','yes')
        except Exception:
            pass
        if not demo_enabled:
            st.info('공개 데모에서는 실시간 LLM 호출이 기본 비활성화되어 있습니다. 운영자가 ENABLE_LLM_DEMO=true를 설정했을 때만 연결됩니다.')
        if demo_enabled and server_key and server_passcode:
            attempts=st.session_state.get('llm_access_failures',0)
            if attempts>=5:
                st.error('이 세션의 접근 코드 확인 횟수를 초과했습니다. 운영자에게 문의하세요.')
            else:
                passcode=st.text_input('운영자 시연 접근 코드',type='password')
                if passcode:
                    if hmac.compare_digest(passcode,server_passcode):
                        api_key=server_key
                        st.success('운영자 시연 접근이 승인되었습니다.')
                    elif hashlib.sha256(passcode.encode('utf-8')).hexdigest() != st.session_state.get('last_failed_code_sha'):
                        st.session_state['llm_access_failures']=attempts+1
                        st.session_state['last_failed_code_sha']=hashlib.sha256(passcode.encode('utf-8')).hexdigest()
                        st.error('접근 코드가 일치하지 않습니다.')
        if st.session_state.get('llm_live_calls',0)>=5:
            st.warning('이 세션의 실시간 LLM 도구 호출 횟수(5회)를 소진했습니다.')
            api_key='' 
        if not api_key:
            st.info("운영자가 서버 비밀 설정(ENABLE_LLM_DEMO, OPENAI_API_KEY, DEMO_ACCESS_CODE)을 연결하고 올바른 접근 코드를 입력한 경우에만 실시간 LLM 도구 호출이 실행됩니다. 그 외에는 규칙 기반 모드를 이용하세요.")
    input_mode=st.radio('요청 입력 방식', ['구조화 입력 (권장)', '제한된 자연어 입력'], horizontal=True,
                        help='구조화 입력은 수치·단위를 명확하게 전달하며 누락된 제약을 임의 추측하지 않습니다.')
    if input_mode.startswith('구조화'):
        st.caption('사용하는 데이터는 Al₂O₃·TMA/H₂O·Si 기판의 16개 측정 조건뿐입니다. 미측정 조건을 생성하지 않습니다.')
        x1,x2,x3=st.columns(3)
        with x1:
            wf_target=st.number_input('목표 두께 (nm) · 워크플로', 0.1, 1000.0, 10.0, 0.5, key='wf_target')
        with x2:
            wf_max_temp=st.selectbox('최대 온도 (°C) · 워크플로', [150,175,200,225,250,275], index=2,key='wf_temp')
        with x3:
            wf_objective=st.selectbox('최적화 목표 · 워크플로', ['time','gpc','balanced'],
                        format_func=lambda x:{'time':'시퀀스 시간 최소화','gpc':'GPC 최대화','balanced':'균형 (설계 가중치 65:35)'}[x],key='wf_obj')
        x4,x5,x6=st.columns(3)
        with x4:
            wf_flow=st.selectbox('Ar 유량 제한 (sccm)', ['제한 없음', '10 고정','20 고정'],key='wf_flow')
        with x5:
            wf_pulse=st.selectbox('Pulse 제한 (ms)', ['제한 없음', '20 고정','40 고정'],key='wf_pulse')
        with x6:
            wf_purge=st.selectbox('Purge 제한 (s)', ['제한 없음', '10 고정','20 고정'],key='wf_purge')
        wf_flow_bounds=(10,20) if wf_flow=='제한 없음' else ((10,10) if wf_flow.startswith('10') else (20,20))
        wf_pulse_bounds=(20,40) if wf_pulse=='제한 없음' else ((20,20) if wf_pulse.startswith('20') else (40,40))
        wf_purge_bounds=(10,20) if wf_purge=='제한 없음' else ((10,10) if wf_purge.startswith('10') else (20,20))
        prompt={'target_nm':wf_target, 'min_temp':175, 'max_temp':wf_max_temp,
                'min_flow':wf_flow_bounds[0], 'max_flow':wf_flow_bounds[1],
                'min_pulse':wf_pulse_bounds[0], 'max_pulse':wf_pulse_bounds[1],
                'min_purge':wf_purge_bounds[0], 'max_purge':wf_purge_bounds[1],
                'objective':wf_objective}
    else:
        prompt=st.text_area('공정 엔지니어 업무 요청 (지원 범위 제한)',
              value='Al2O3 10nm, 최대 200°C, 시퀀스 시간 최소화',height=90)
        st.caption('일반적인 자연어를 완전히 이해하지 않습니다. 해석 범위를 벗어난 단어·조건이 있으면 추천을 중단합니다. 입력 예: Al2O3 10nm, Ar 유량 20sccm만, GPC 최대화')
    current_mode = 'LLM tool-calling' if llm_chosen else 'Deterministic tools'
    # A Streamlit rerun preserves session_state. Never display an earlier analysis
    # after the user edits ANY prompt character or switches execution mode.
    if not workflow_is_current(st.session_state.get('last_workflow'), prompt, current_mode):
        st.session_state.pop('last_workflow', None)
    parsed_preview,parse_error=validated_request(prompt)
    if parse_error:
        st.warning("요청 사전 검증: " + parse_error)
    else:
        with st.expander("자연어 요청에서 해석된 조건 · 실제 검색에 반영",expanded=False):
            st.json(parsed_preview)
    if st.button("워크플로 실행",type="primary",use_container_width=True,disabled=llm_chosen and not api_key):
        st.session_state.pop('last_workflow', None)  # failure must not preserve stale output
        with st.spinner("실행 기록 생성 중..."):
            try:
                if llm_chosen:
                    st.session_state['llm_live_calls']=st.session_state.get('llm_live_calls',0)+1
                response, trace=run_llm_agent(prompt,api_key) if llm_chosen else deterministic_demo(prompt)
                st.session_state['last_workflow']={
                    'response':response, 'trace':trace,
                    'mode':current_mode, 'request':prompt,
                }
            except Exception as exc:
                st.error(f"분석 실행 실패: {type(exc).__name__}. API 사용 권한/네트워크/호출 제한을 확인해 주세요.")
    if 'last_workflow' in st.session_state:
        saved=st.session_state['last_workflow']
        response,trace,active=saved['response'],saved['trace'],saved['mode']
        st.caption("현재 요청에 대해 실행한 분석 · 실행 모드: "+active)
        st.code(json.dumps(saved['request'],ensure_ascii=False,indent=2) if isinstance(saved['request'],dict) else saved['request'],language='json' if isinstance(saved['request'],dict) else None)
        st.markdown(response)
        audit=audit_execution(active,saved['request'],response,trace)
        if audit['validated_report']:
            st.success('계산 보고서 검증 완료 · 공정 성능 승인 아님')
        else:
            st.warning('검증된 계산 보고서 없음 · 입력/도구 오류 또는 검토 중단')
        st.caption('실행 분류: '+audit['mode_classification']+' · 실제 API 공급자 기록은 별도 확인 필요')
        with st.expander(f"실제 도구 실행 기록 · {len(trace)} calls",expanded=True):
            for i,record in enumerate(trace,1):
                st.markdown(f"**{i:02d}. `{record['tool']}`**")
                st.json(record)
        st.download_button("도구 실행 기록 다운로드",trace_download_json(active,saved['request'],response,trace),file_name='ALD_OPTIX_tool_trace.json',mime='application/json')

with t3:
    st.markdown("<div class='suptitle'>EVIDENCE & VERIFICATION</div>",unsafe_allow_html=True)
    st.header("Verification Lab")
    st.write("같은 공정조건을 2번 측정한 자료가 학습·검증 양쪽에 섞이면 과도하게 좋은 점수가 나올 수 있어요. **조건 단위 교차검증**과 **중첩 모델 선택**을 모두 제공합니다.")
    exploratory,pred,nested,nested_pred=compute_cv()
    m1,m2,m3,m4=st.columns(4)
    m1.metric("평균 기준 MAE",f"{exploratory['baseline_MAE_A']:.3f} Å/cycle")
    m2.metric("초기 복잡 모델",f"{exploratory['initial_complex_MAE_A']:.3f}")
    m3.metric("단순 주효과 모델",f"{exploratory['model_MAE_A']:.3f}")
    m4.metric("Nested CV 모델",f"{nested['MAE_A_per_cycle']:.3f}")
    st.markdown("<div class='note'><b>개선의 핵심:</b> 4개 주효과 + 6개 교호작용 모델에서 교차검증 오차가 증가했습니다. 주효과 모델로 단순화했고, 다시 바깥 평가 폴드를 분리해 모델 선택이 새어 들어가지 않는지 확인했습니다. 이 데이터에선 내부 선택 16회 모두 주효과 모델을 택했습니다.</div>",unsafe_allow_html=True)
    frame=pd.DataFrame([
        {"모델":"평균 기준","MAE":exploratory['baseline_MAE_A'],"RMSE":exploratory['baseline_RMSE_A']},
        {"모델":"초기 복잡 회귀","MAE":exploratory['initial_complex_MAE_A'],"RMSE":exploratory['initial_complex_RMSE_A']},
        {"모델":"주효과 회귀","MAE":exploratory['model_MAE_A'],"RMSE":exploratory['model_RMSE_A']},
        {"모델":"Nested 선택","MAE":nested['MAE_A_per_cycle'],"RMSE":nested['RMSE_A_per_cycle']},
    ])
    fig=px.bar(frame,x='모델',y='MAE',text_auto='.3f',color='모델',color_discrete_sequence=['#99B6A1','#C68661','#1C6B46','#123D2A'])
    fig.update_layout(height=380,plot_bgcolor='#FFFFFF',paper_bgcolor='#FFFFFF',showlegend=False,margin=dict(l=12,r=12,t=16,b=12),yaxis_title='MAE (Å/cycle) · 낮을수록 좋음')
    st.plotly_chart(fig,use_container_width=True)
    st.caption("외부 ALD 장비·다른 실험 조건에 대한 일반화 성능은 검증하지 않았습니다. 16개 조건으로 이루어진 단일 소규모 데이터셋에서의 내부 평가입니다.")
    st.subheader("어떤 변수가 GPC에 영향을 주었을까?")
    effect=[]
    for name,title in [('temperature_C','온도'),('flow_sccm','Ar 유량'),('pulse_ms','Pulse'),('purge_s','Purge')]:
        means=D.groupby(name)['gpc_A_per_cycle'].mean().sort_index()
        effect.append({'변수':title,'high-low GPC (Å/cycle)':float(means.iloc[-1]-means.iloc[0])})
    effects=pd.DataFrame(effect)
    ef=px.bar(effects,x='변수',y='high-low GPC (Å/cycle)',text_auto='.3f',color='변수',color_discrete_sequence=['#276E4B','#609D70','#D0AD69','#8AA999'])
    ef.update_layout(height=310,plot_bgcolor='white',paper_bgcolor='white',showlegend=False,margin=dict(l=12,r=12,t=14,b=5))
    st.plotly_chart(ef,use_container_width=True)
    st.caption("그림은 고수준 평균 − 저수준 평균의 관측 차이입니다. 이 그래프 하나로 인과관계나 통계적 유의성을 새로 주장하지 않습니다. 원 논문은 온도만 유의한 주효과로 보고합니다.")
    st.subheader("실무 의사결정 사례집 · v0와 v1 비교")
    cases = pd.DataFrame(engineering_casebook())
    c0, c1, c2 = st.columns(3)
    c0.metric("사전 정의된 요청", f"{len(cases)}건")
    c1.metric("기존 v0 목적·제약 충족", f"{int(cases.v0_pass.sum())}/{len(cases)}건")
    c2.metric("개선 v1 올바른 후보 검토·거부", f"{int(cases.v1_pass.sum())}/{len(cases)}건")
    st.caption("통과 기준: 실측 후보 내 목적 최적·제약 준수 또는 적절한 추천 거부. 개발자가 설계한 8개 기능 테스트이며 산업 현장 성공률/수율 지표가 아닙니다.")
    case_view=cases[["case_id","scenario","feasible_candidates","v0_pass","v1_pass","v1_action","diagnosis"]].copy()
    case_view.columns=["사례","고객 요청","유효 후보","기존 v0 통과","개선 v1 통과","v1 판단","v0 실패 이유"]
    st.dataframe(case_view, hide_index=True, use_container_width=True)
    st.download_button("8개 업무 사례 비교 다운로드 (.csv)", case_view.to_csv(index=False).encode('utf-8-sig'), file_name="ALD_OPTIX_engineering_cases.csv",mime="text/csv")
    st.info("업무 개선의 핵심은 무조건 추천하는 것이 아니라, 고객 제약과 실측 범위를 함께 평가하여 타당한 후보를 선택하거나 근거를 제시하고 거부하는 것입니다.")
    st.markdown("#### 기존 5개 경계조건 검사")

    suites=pd.DataFrame(scenario_suite())
    st.dataframe(suites.rename(columns={'scenario':'요청','status':'결과','n_candidates':'유효 후보','recommended':'선정조건','note':'판정 사유'}),hide_index=True,use_container_width=True)
    st.markdown("**오류 주입 테스트:** 실측 온도보다 낮은 상한(150°C) 및 서로 충돌하는 Purge 제약(최소 20s·최대 10s)에 대해 추천을 생성하지 않는지 확인합니다.")
    with st.expander("논문 원시 측정 32회 · 코드값↔실제값"):
        st.dataframe(D,hide_index=True,use_container_width=True)
    st.download_button("Nested CV 예측 결과 (.csv)",nested_pred.to_csv(index=False).encode('utf-8-sig'),file_name='ALD_OPTIX_nested_cv.csv',mime='text/csv')
    st.download_button("자동 시나리오 평가 (.csv)",suites.to_csv(index=False).encode('utf-8-sig'),file_name='ALD_OPTIX_acceptance_tests.csv',mime='text/csv')

with t4:
    st.markdown("<div class='suptitle'>TRANSPARENCY</div>",unsafe_allow_html=True)
    st.header("Evidence & scope")
    st.write("결과의 근거를 끝까지 추적할 수 있어야 재현 가능한 프로젝트입니다. 사용한 실험값의 출처와 추정의 범위를 공개합니다.")
    st.markdown(f"**원문:** [{SOURCE}]({DOI}) · Table 4–5 · Pan & Lei (2025)")
    st.markdown("**실험:** Al₂O₃ thermal ALD / TMA + H₂O / Si substrate / Ar purge / 실험조건 16개 × 반복 2회")
    for item in EVIDENCE:
        with st.expander(f"{item['id']}  ·  {item['title']} ({item['type']})"):
            st.write(item['text'])
            st.markdown(f"[근거 논문 원문]({item['source']})")
    st.markdown("#### 데이터의 해석 경계")
    st.markdown("""
- **관측:** Table 5의 GPC 32개 값, Table 4의 설계 인자·수준.
- **계산:** 2회 평균 GPC, 목표 두께에 대한 cycle 수, 두 pulse·두 purge로 단순화한 시간.
- **예측:** 주효과 Ridge 회귀의 교차검증 오차. 관측하지 않은 조건의 양산 성능을 예측·인증하지 않음.
- **미검증:** ALD saturation, 박막 균일도·전기적 특성, 실제 공정시간·수율·원가, 다른 장비로의 전이.
- **AI 관련:** 무료 기본 모드는 ML + 규칙 기반 도구 워크플로. LLM 도구 호출은 API가 연결되어 실제 실행했을 때만 그 명칭으로 보고.
""")
    st.info("본 웹사이트는 가상 기업의 대학 수업 과제이며, 실제 상용 제조 시스템이나 Pan & Lei 연구진의 공식 서비스가 아닙니다.")
    st.markdown("**검증 기록:** GitHub repository의 `docs/validation.md` 참고. 실제 LLM 호출 기록은 운영자 실행 후에만 확보됩니다.")
