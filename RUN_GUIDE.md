# ALD-OPTIX — MacBook 실행 및 배포

## 1. ZIP 준비

프로젝트 ZIP을 풀면 `ALD_OPTIX` 폴더가 나옵니다. **그 안에서 `app.py`가 바로 보여야** 합니다. Finder에서 폴더를 터미널로 드래그하면 경로를 정확히 입력할 수 있습니다.

```bash
cd ~/Downloads/ALD_OPTIX
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-dev.txt
python scripts/release_check.py --strict
python -m streamlit run app.py
```

MacBook에 Node.js가 없다면 [nodejs.org](https://nodejs.org/)에서 설치한 뒤 `node --version`을 확인하세요. `release_check.py --strict`는 Node.js·Streamlit이 누락된 검증을 성공으로 처리하지 않습니다.

## 2. 앱 동작 확인

Streamlit 화면(보통 `http://localhost:8501`)에서 다음을 직접 확인합니다.

- Recipe Studio: 목표 두께 10 nm, 시간 최소화 → 추정 시간 약 25.05분·`.md` 보고서 다운로드
- 최대 온도 150°C: 측정 후보 없음으로 추천 거부
- AI Workflow: 구조화 입력, 최대 200°C, 시간 최소화 → 근거·레시피·검증 기록·로그 다운로드
- GPC 최대화 → 1.410 Å/cycle 후보
- 요청문 또는 실행 모드 변경 시 이전 워크플로 결과 자동 제거
- 미지원 화학계(`Al2O3 10nm, 새로운 산화제를 쓰자`) → 중단

`docs/mock_llm_protocol.json`은 **오프라인 모의 LLM 기록**이라서 실제 LLM API 실행 기록이 아닙니다.

## 3. 선택형 실제 AI API 확인

실시간 OpenAI API 이용 권한과 과금 한도가 필요합니다. 먼저 **웹앱 기본 기능이 작동하는지** 확인한 후, 필요할 때만 본인 터미널에 `OPENAI_API_KEY`를 설정하고 다음을 사용하세요.

```bash
python scripts/llm_live_smoke.py --confirm-live
```

`private_logs/`는 Git 저장소에서 제외되어야 합니다. 비밀키·접근 코드·원시 민감 로그를 대화창이나 공개 GitHub에 올리지 마세요. 실시간 호출이 실패하면 오류 기록을 확인합니다.

## 4. 공개 배포

1. GitHub 저장소의 **루트**에 `app.py`, `core.py`, `agent.py`, `exports.py`, `requirements.txt`, `.github/`, `site/` 등이 있도록 업로드합니다. `.venv` 및 비밀 설정은 업로드하지 않습니다.
2. GitHub Actions 탭에서 **전체 테스트와 Streamlit AppTest가 PASS**인지 확인합니다.
3. [Streamlit Community Cloud](https://share.streamlit.io/)에서 GitHub 저장소 → Main file `app.py` 선택 후 배포합니다. 실제 공개 URL로 Recipe Studio·AI Workflow·보고서 다운로드를 확인합니다.
4. [Cloudflare Pages](https://dash.cloudflare.com/)에 같은 GitHub 저장소를 연결합니다. Framework preset `None`, Build command 공백, Output directory `site`입니다.
5. Cloudflare 배포 후 GitHub의 `site/config.js`에 **실제 Streamlit 공개 HTTPS URL**을 입력하고 commit하여 재배포합니다.
6. 시크릿 창·휴대폰에서 홈페이지 → Streamlit 이동 및 입력·거부·다운로드 동작을 다시 확인합니다.

학습용 ALD 실측 데이터 기반 의사결정 지원이며 실제 제조 공정 승인은 아닙니다.
