# 📌 프로젝트 진행상황 기록 (PROJECT_STATUS)

> **목적:** 대화가 길어지거나 새 세션으로 넘어가더라도 로컬·GitHub 상태, 주차별 산출물, 핵심 수치, 사용자 선호 규칙을 즉시 이어서 파악할 수 있도록 정리한 기준 문서입니다.  
> **최종 기록 일시:** 2026-11-25  
> **프로젝트:** 2026-2 빅데이터개론 — `A-Priori · PCY + Upstage Solar + 조치원읍 화재 위험도 지도`

---

## 1. 로컬 폴더 및 Git 환경 구분

1. **통합 프로젝트 루트 (지도 웹 시스템 + Week 11 A-Priori / PCY 파이프라인)**
   - 경로: `c:\Users\minki\OneDrive\Desktop\프로젝트\빅데이터개론 프로젝트`
   - 체크아웃 브랜치: `테스트3` (최근 커밋 `cbf3ff0`: `Add Jochiwon-eup interactive fire risk map with PCY hybrid scoring`)
   - 주요 구성:
     - **지도 웹 시스템:** `index.html`, `server.py`, `scripts/build_jochiwon_data.py`, `scripts/mine_pcy_rules.py`, `static/`, `data/jochiwon_*`
     - **Week 11 A-Priori / PCY 단독 파이프라인(바탕화면 폴더에서 통합 완료):** `fire_apriori.py`, `fire_pcy.py`, `fire_pipeline.py`, `out/`(`benchmark.json`, `report*.md`, `stats_*.json`)
     - **대화형 Solar 에이전트 (`k=2` 통일):** `fire_agent.py`(`k=2` 통합, 기본 PCY / `--algo apriori`), `fire_agent_apriori.py`(A-Priori 단독 `k=2`), `fire_agent_pcy.py`(PCY `k=2`) — 모두 `.csv.gz` 자동 로드(`DATA_PATH`) 적용
     - **공통 설정 및 문서·산출물:** `.env`, `.env.example`, `프로젝트_기획서_및_10주차_발표대본.md`, `Week10_팀_중간보고서.pdf`
   - 기존 바탕화면 폴더(`C:\Users\minki\OneDrive\Desktop\빅데이터개론 프로젝트`)는 2026-11-24에 안 겹치는 파일 및 신버전 `fire_agent.py`를 이 루트로 이관하고 중복 파일(`data/소방청_화재현황_20231231.csv`, 구버전 `README.md`/`.gitignore`) 정리 후 삭제 완료.
2. **Git 실행 및 인증 환경**
   - Windows PowerShell에는 `git`이 설치되어 있지 않으며, **WSL Ubuntu (`/usr/bin/git`) + SSH 키 (`~/.ssh/id_ed25519`)**로 GitHub 인증이 설정되어 있음.
   - 원격 저장소: `git@github.com:minkipper/apriori-solar-fire-mining.git` (`https://github.com/minkipper/apriori-solar-fire-mining`)
   - 참고: 다른 과목/실습 저장소 `minkipper/introduction_to_bigdata`도 별도로 존재하므로 혼동하지 말 것.

---

## 2. GitHub 원격 저장소 및 브랜치/PR 현황

### 원격 브랜치 상태
- **`main`** (최신 커밋 `ffeba87`, 2026-11-23):
  - `week10/README.md` (1주차 중간 보고서) 반영 완료
  - 기존 파일: `README.md`, `fire_agent.py`, `docs/fire-agent-review.md`, `data/소방청_화재현황_20231231.csv.gz`, `소방청_연간화재통계_20241231.csv`
- **`테스트3`** (원격 `cbf3ff0`, 2026-11-18):
  - 1차 조치원읍 지도 + A-Priori/PCY(max_k=3, 236규칙) 버전이 푸시되어 있음.
  - **로컬 작업 폴더 미푸시 변경사항(6개 파일)**: `PCY 단독 (k=2)` 전환 + 지도 가독성 개선 변경분이 아직 커밋·푸시되지 않고 로컬에 남아 있음:
    - `scripts/mine_pcy_rules.py`
    - `data/jochiwon_pcy_rules.json`
    - `index.html`
    - `static/style.css`
    - `static/app.js`
    - `README.md`
- **`테스트`** (`a458811`): 초기 데모(`fire_agent.py`) 및 PR #2/#3 기록
- **`docs/team-git-rules`** (`b6ae279`, **PR #1 Open**): `@Seccond`가 작성한 협업 규칙(`CONTRIBUTING.md`, `AGENTS.md`, `data/README.md`, `.github/pull_request_template.md`, `data/raw/nfa/nfa_fire_stats_2024.csv`). 아직 `main`에 머지되지 않음.
- **`research/data-survey`** (`2731f06`): `@Seccond`의 1차 데이터 출처 조사(`docs/research/01-data.md`)
- **`HiddenTroll_SurveyResult`** (`783e3cb`): `@HiddenTroller`의 `소방청_연간화재통계_20241231.csv` 업로드

---

## 3. 주차별 작업 내역 및 핵심 검증 수치

### Week 10 (실제 작업 11/03 - 11/06) — 보고서 작성 및 `main` 반영 완료 (`week10/README.md`)
- 주제 확정 (`README.md`) 및 팀 협업 규칙(`docs/team-git-rules`) · 데이터 출처 조사(`docs/research/01-data.md`) 진행
- 원천 데이터 확보: `소방청_화재현황_20231231.csv.gz` (115,237건) 및 `소방청_연간화재통계_20241231.csv`
- 초기 대화형 데모(`테스트` 브랜치 `fire_agent.py`) 구현 및 리뷰(`docs/fire-agent-review.md`):
  1. 실제 코드에 A-Priori/PCY 가지치기 없이 `combinations` 전수 집계만 구현된 점 확인
  2. `main()`이 `.csv.gz` 대신 압축 해제된 `.csv`를 강제 호출하는 실행 경로 오류 및 `.env.example` 미비 확인

### Week 11 (실제 작업 11/10 - 11/16) — A-Priori · PCY 직접 구현 (프로젝트 루트로 통합 완료)
- A-Priori(§6.2) 및 PCY(§6.3.1 해시 버킷·비트맵) 직접 구현 (`fire_apriori.py`, `fire_pcy.py`, `fire_pipeline.py`) 및 115,237건 벤치마크 완료 (`out/benchmark.json`, `out/report_*.md`)
- **참고:** 아직 Week 11 보고서는 작성 전임.

### Week 12 (실제 작업 11/17 - 11/23) — 조치원읍 지도 시스템 + PCY 단독(k=2) (현재 폴더)
1. **조치원읍 건물 공간 데이터 및 위험도 모델 구축 (`scripts/build_jochiwon_data.py`)**
   - OpenStreetMap v0.6 API (`bbox=127.280,36.585,127.306,36.618`, `relation/7690667` 행정경계) 기반 실제 건물 **3,322동** + 소방 인프라 **39건**(소방거점 3곳: 세종북부소방서·원리119지역대·119특수구조단 화학구조대, 소화전 35곳, 행정경계 1건) 생성 (`data/jochiwon_buildings.geojson`, `data/jochiwon_infra.geojson`)
   - *The Discard* 복원(연속 물리·공간 점수 0-70점) + PCY 통계 시너지(0-30점) + 실시간 기상/시간대/계절 결합
2. **PCY 단독 (`k=2`) 경량화 (`scripts/mine_pcy_rules.py` → `data/jochiwon_pcy_rules.json`)**
   - `apriori` 및 `k>=3` 후보 생성을 제거하고 PCY 단독 `max_k=2`, `n_buckets=32,771`로 축소
   - 건축물 화재 **75,798건**(대형 재산피해 상위 5% `>= 37,266천원`: 4,963건, 인명피해: 4,182건) 대상: `L1=37개`, 전체 666쌍 중 **C2 후보 393쌍 (41.0% 절감, 0.503초)**, 최종 `k=2` 복합 위험 쌍 **140개** 추출
   - 매칭률: 주간·봄·보통습도 2,341/3,322동(최대 4.75배), 심야·겨울·건조 2,923/3,322동(최대 7.09배)
3. **지도 가독성 개선 (로컬 적용 완료, 미푸시)**
   - 기본 배경지도 `Carto Voyager` 적용, 등급별 차등 투명도(Smart Opacity) + 투명도 슬라이더(20-95%), 줌 레벨(zoom >= 16) 연동 소화전/외곽선 클러터 제어, 14개 법정리 지명 라벨 추가
4. **브이월드(V-World) 공식 API 연동 및 전국 실시간 확장 (2026-11-25 완료)**
   - `.env`에 `VWORLD_API_KEY` 등록 및 백엔드 프록시(`server.py` + `scripts/vworld_service.py`) 구축 완료
   - 국토교통부 `도로명주소건물(LT_C_SPBD)` + `GIS건물통합정보(LT_C_BLDGINFO)` 결합으로 조치원읍 기본 데이터셋 재구축(기존 OSM 누락 구역이던 **세종여고·신안리·신대리 외곽 건물 공백 해결** 및 실제 사용승인일·주구조·주용도·층수 반영)
   - 지도 좌측 **전국 실시간 브이월드 탐색**(전국 장소·주소 검색, 이동 시 화면 `bbox` 건물·119안전센터 자동 로딩, 브이월드 공식 한글·위성 하이브리드 배경지도) 추가 완료

---

## 4. 사용자 선호 및 협업 주의사항 (반드시 준수)

- **원격 푸시 전 확인:** GitHub 저장소·브랜치 대상 및 반영 내용을 사용자에게 먼저 확인받고 푸시할 것.
- **문서 작성 규칙:**
  - 취소선(`~~`)을 사용하지 말 것 — 삭제할 내용은 그냥 지울 것.
  - 마크다운에서 범위 표기 시 물결표(`~`) 두 개가 같은 줄에 들어가지 않도록 하이픈(`-`)을 사용할 것 (GitHub 자동 취소선 방지).
- **협업 규칙 (`docs/team-git-rules`의 `AGENTS.md` / `CONTRIBUTING.md`):**
  - 팀원 작업 시 `main` 직접 커밋·푸시 금지, `종류/짧은-설명` 브랜치 + PR, 데이터는 `data/raw/<출처>/`에 영문 소문자 파일명 권장, API 키·`.env` 커밋 금지.

---

## 5. 다음 할 일 (Next Actions)

- [ ] 현재 로컬 `테스트3` 브랜치의 수정본(PCY `k=2` + 지도 가독성 개선 6개 파일)을 원격 `테스트3`에 푸시할지 사용자 확인 후 반영
- [ ] **Week 11 보고서** (`week11/README.md` 등) 및 **Week 12 보고서** 작성 여부 결정
- [ ] (선택) 위성 지도에서 확인된 누락 건물 보완 (OSM 타일 확장 vs 브이월드/건축물대장 공공데이터 결합)
- [ ] (선택) `docs/team-git-rules` PR #1 머지 여부 결정
