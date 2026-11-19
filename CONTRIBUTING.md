# 협업 가이드 (Git 처음 쓰는 팀원용)

> 한 줄 요약: **`main`은 건드리지 않는다. 내 브랜치에서 작업하고 PR을 연다. 머지는 팀장이 한다.**

AI 에이전트(종류 무관)를 쓴다면, 에이전트가 [AGENTS.md](AGENTS.md)를 읽고 이 규칙을 대신 지켜 줍니다. 아래는 직접 할 때의 순서입니다.

---

## 비유로 이해하기

- `main` = 팀 공용 **최종 보고서 원본**. 아무나 고치면 안 됩니다.
- 브랜치 = 원본을 복사한 **내 작업용 사본**. 마음껏 고쳐도 원본은 안전합니다.
- PR(Pull Request) = "제 사본 내용을 원본에 반영해 주세요"라는 **결재 요청서**.
- 머지(Merge) = 팀장이 결재해서 원본에 반영하는 것.

---

## 처음 한 번만

```bash
git clone https://github.com/minkipper/apriori-solar-fire-mining.git
cd apriori-solar-fire-mining
```

## 작업할 때마다 (6단계)

**1. 최신 `main` 받기**
```bash
git checkout main
git pull origin main
```

**2. 내 브랜치 만들기** (이름 규칙: `종류/짧은-설명`)
```bash
git checkout -b feat/pcy-bitmap
```
종류: `feat`(기능) `fix`(버그) `docs`(문서) `data`(데이터) `research`(조사) `refactor`(정리) `chore`(설정)

**3. 작업하고 상태 확인**
```bash
git status
```

**4. 커밋** (형식: `종류: 요약`, 한국어 가능)
```bash
git add 바꾼파일
git commit -m "feat: PCY 해시 버킷 구현"
```

**5. 내 브랜치로 푸시**
```bash
git push -u origin feat/pcy-bitmap
```

**6. GitHub에서 PR 열기**
- 저장소 페이지에 뜨는 **Compare & pull request** 버튼 클릭
- base: `main` ← compare: 내 브랜치 확인
- 템플릿 채우고, Reviewers에 팀장(`minkipper`) 지정
- 머지는 팀장이 합니다. 기다리면 됩니다.

---

## 데이터 올릴 때

- `data/raw/<출처>/`에 넣습니다. 예: 소방청 → `data/raw/nfa/`
- 파일 이름은 영어로 짓습니다. 예: `nfa_fire_stats_2024.csv`
- [data/README.md](data/README.md)의 데이터 목록에 한 줄을 추가합니다.
- 자세한 규칙은 [data/README.md](data/README.md)를 보세요.

---

## 하지 말 것

- `main`에서 바로 커밋·푸시
- 내 PR을 직접 머지
- `git push --force`
- 다른 사람 브랜치 삭제
- API 키, `.env` 파일 커밋

## 막혔을 때

- 충돌(conflict)이 났다 → 아무것도 지우지 말고 팀 채팅에 공유
- 실수로 `main`에 커밋했다 → 푸시하지 말고 팀장에게 알리기
- 뭐가 뭔지 모르겠다 → `git status` 결과를 캡처해서 공유
