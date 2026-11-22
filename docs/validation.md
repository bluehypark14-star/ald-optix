# ALD-OPTIX 검증 보고서

## 검증 범위

공개 실험 데이터를 이용한 교육용 공정 의사결정 지원 소프트웨어의 계산 정확성, 입력 처리, 기록 일관성 및 화면 경로를 점검한다. 제조 공정의 실제 품질·수율을 인증하는 검사가 아니다.

## 검증 방법

- 원시 CSV의 바이트 SHA-256 및 실험 조건 구조 검사
- 원시 데이터 기반 독립 참조 계산과 후보·GPC·cycle·시퀀스 시간·균형 목적 비교
- 반복 실험 조건을 그룹으로 분리한 교차검증 및 중첩 교차검증
- 잘못된 수치, 자료형, 자연어 제약, 부등호, 미지원 요구, 데이터 및 결과 변조의 거부 검사
- 도구 호출 인자의 제약 잠금 및 감사 기록의 재계산 검사 (오프라인 모의 클라이언트)
- Python과 HTML/JavaScript의 공통 계산 경로 비교
- Streamlit AppTest 및 선택형 오프라인 Chromium 화면 검사

## 계산 및 모델 평가

데이터: Pan & Lei (2025), *Materials*, 18(9), 1918, Tables 4–5, DOI `10.3390/ma18091918`. 16개 DOE 조건, 32회 측정. 원시 CSV SHA-256: `f61d6f101c6d48dfd4677a9c131c6b383c55186c3d17d93e726de1bf463342ec`.

기준 규칙(v0)과 제약·목적 반영 방식(v1)은 사전 정의한 8개 요청에서 각각 2건, 8건을 충족했다. 이는 기능 검증이며, 실제 생산 결과가 아니다. 10 nm 기본 시간 최소화 사례의 이론 시퀀스 시간은 약 25.05분이다. 기준 GPC 최대화 방식은 약 47.43분이다. 실제 장비 가동 시간 및 막 품질을 대변하지 않는다.

GPC 모델의 그룹 교차검증 MAE는 평균 기준 약 0.123 Å/cycle, 초기 복잡 회귀 약 0.159 Å/cycle이다. 중첩 교차검증에 의한 모델 선택 결과의 MAE는 약 0.090 Å/cycle이며, 모든 외부 fold에서 주효과 모델이 선택되었다. 단일 문헌 데이터에 대한 내부 평가이다.

## 실행 기록

검증 결과는 아래에 기재한다. 실시간 LLM API 및 실제 공개 서비스에 대한 검증은 코드 검사와 별개이다.

| 검사 항목 | 결과 |
|---|---|
| Python 전체 회귀 테스트 | 554개 통과, 2개 테스트 모듈 건너뜀 (홈페이지 콘텐츠 보완 후 재실행 30.37초) |
| Python–JavaScript 계산 비교 | 210건 일치 |
| Python 및 JavaScript 구문 검사 | 통과 |
| 원시 CSV, 홈페이지 데이터, 모의 호출 기록 | 데이터 재생성 전후 SHA-256 일치 |
| 오프라인 Chromium | PC 1440×900, 모바일 390×844에서 계산·제약 거부·GPC 전환·가로 넘침 검사 통과; 변조 데이터의 추천 차단 확인 |
| 홈페이지 요구사항별 메뉴 및 반응형 표시 | 5개 메뉴와 대응 섹션, 320·390·800·1024·1440px에서 표시 및 가로 넘침 없음 확인 |
| Streamlit AppTest | 패키지 미설치로 두 모듈 미실행 |
| 실제 LLM API 및 공개 웹서비스 | 미검증 |

검사 환경: Python 3.13.5, NumPy 2.3.5, pandas 2.2.3, scikit-learn 1.8.0, pytest 9.0.2. 개별 환경에서 재현하려면 설치 후 자동 검증 명령을 실행한다.

## 재현 방법

```bash
python -m pytest -q
python scripts/compare_python_js.py
python scripts/build_site_data.py
python scripts/generate_mock_protocol_trace.py
python scripts/release_check.py --strict
```

Playwright·Chromium 설치 환경의 오프라인 UI 검사: `python scripts/browser_offline_mock.py`.

`mock_llm_protocol.json`은 정상 도구 실행 및 사용자 제약 완화 시도 차단을 보여주는 모의 기록이다. 실제 API 응답이나 외부 인증 기록이 아니다.
