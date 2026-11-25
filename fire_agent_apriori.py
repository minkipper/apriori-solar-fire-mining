#!/usr/bin/env python3
"""대화형 화재 위험 진단 AI 에이전트 — [A-Priori 단독 k=2 버전]

사용자의 일상적인 자연어 질문을 받아:
1. Upstage Solar가 질문에서 조건(장소, 피해 기준, 상황 등)을 파악
2. 115,237건 실제 데이터에서 표준 A-Priori(교재 §6.2, k=2) 알고리즘으로 2-항목 위험 쌍(L2) 및 피해 위험도(배수) 계산
3. Solar가 결과를 종합하여 일상 언어로 친절하게 답변 + 맞춤형 예방 체크리스트 제공

실행:
  python fire_agent_apriori.py
"""
import csv
import gzip
import json
import os
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime
from itertools import combinations

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GZ = os.path.join(HERE, "data", "소방청_화재현황_20231231.csv.gz")
DEFAULT_CSV = os.path.join(HERE, "data", "소방청_화재현황_20231231.csv")
DATA_PATH = DEFAULT_GZ if os.path.exists(DEFAULT_GZ) else DEFAULT_CSV
SOLAR_URL = "https://api.upstage.ai/v1/chat/completions"


# ───────────────────────── 환경설정 및 유틸 ─────────────────────────
def load_env(path=os.path.join(HERE, ".env")):
    env = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def to_float(s):
    try:
        return float((s or "").replace(",", "").strip())
    except ValueError:
        return None


def parse_dt(s):
    try:
        return datetime.strptime((s or "").strip()[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        return None


# ───────────────────────── 데이터 로딩 & 장바구니 ─────────────────────────
SKIP_VALUES = {"", "미상", "해당없음", "기타", "N"}


def build_basket(r):
    items = set()

    def add(prefix, val):
        v = (val or "").strip()
        if v not in SKIP_VALUES:
            items.add(f"{prefix}:{v}")

    add("장소대", r.get("장소대분류"))
    add("장소중", r.get("장소중분류"))
    add("장소소", r.get("장소소분류"))
    add("발화요인", r.get("발화요인대분류"))
    add("발화열원", r.get("발화열원"))
    add("최초착화물", r.get("최초착화물대분류"))
    add("연소확대물", r.get("연소확대물대분류"))
    add("구조", r.get("건물구조조"))
    add("지붕", r.get("건물구조즙"))

    floor = to_float(r.get("발화층"))
    if floor is not None:
        if floor < 0:
            items.add("발화층:지하")
        elif floor <= 1:
            items.add("발화층:1층")
        elif floor <= 3:
            items.add("발화층:2~3층")
        else:
            items.add("발화층:4층이상")

    dt = parse_dt(r.get("접수일시"))
    if dt:
        items.add("시간대:" + ("심야(00-06)" if dt.hour < 6 else "주간(06-18)" if dt.hour < 18 else "야간(18-24)"))
        items.add("계절:" + ("겨울" if dt.month in (12, 1, 2) else "봄" if dt.month <= 5 else "여름" if dt.month <= 8 else "가을"))
        arr = parse_dt(r.get("도착일시"))
        if arr and arr >= dt:
            mins = (arr - dt).total_seconds() / 60
            items.add("출동도착:" + ("7분이상" if mins >= 7 else "7분미만"))

    hum = to_float(r.get("습도"))
    if hum is not None and hum > 0:
        items.add("습도:" + ("건조(<30)" if hum < 30 else "보통(30-60)" if hum < 60 else "습함(60+)"))

    dist = to_float(r.get("소방서거리(km)"))
    if dist is not None and dist > 0:
        items.add("소방서거리:" + ("5km이상" if dist >= 5 else "5km미만"))
    return items


# ───────────────────────── 표준 A-Priori 알고리즘 (k=2) ─────────────────────────
def apriori_k2(baskets, min_count):
    """표준 A-Priori 알고리즘 (교재 §6.2, k=2): Pass 1 (L1) -> Pass 2 (C2 -> L2)."""
    t0 = time.perf_counter()

    # [Pass 1] C1 카운트 -> 최소 지지도 이상인 빈발 1-아이템 L1 추출
    c1 = Counter()
    for b in baskets:
        c1.update(b)
    l1 = sorted(i for i, c in c1.items() if c >= min_count)
    frequent = {(i,): c1[i] for i in l1}

    # [Pass 2] 단조성 가지치기: L1에 속한 아이템 쌍으로만 후보 C2 생성 후 카운트 -> L2 추출
    cand2 = set(combinations(l1, 2))
    l1set = set(l1)
    c2 = Counter()
    for b in baskets:
        fb = [i for i in b if i in l1set]
        if len(fb) < 2:
            continue
        for p in combinations(fb, 2):
            if p in cand2:
                c2[p] += 1
    l2 = {p: c for p, c in c2.items() if c >= min_count}
    frequent.update(l2)

    stats = {
        "algorithm": "A-Priori",
        "max_k": 2,
        "c1_items": len(c1),
        "l1_frequent_items": len(l1),
        "c2_candidates": len(cand2),
        "l2_frequent_pairs": len(l2),
        "seconds": round(time.perf_counter() - t0, 3),
    }
    return frequent, stats


def count_pairs(baskets, pairs):
    """추출된 빈발 2-항목 쌍(L2)이 전체 장바구니에서 몇 번 등장하는지 카운트."""
    relevant = {i for p in pairs for i in p}
    counts = Counter()
    for b in baskets:
        fb = [i for i in b if i in relevant]
        if len(fb) < 2:
            continue
        for p in combinations(fb, 2):
            if p in pairs:
                counts[p] += 1
    return counts


class FireDataset:
    """소방청 화재현황 데이터를 로드하고 A-Priori(k=2)로 위험 쌍을 조회하는 데이터셋."""

    def __init__(self, data_path=DATA_PATH):
        print(f"⏳ 115,237건 소방청 화재 데이터 로딩 중... ({os.path.basename(data_path)})")
        t0 = time.perf_counter()
        self.rows = []
        opener = gzip.open(data_path, "rt", encoding="cp949", errors="replace", newline="") if data_path.endswith(".gz") else open(data_path, encoding="cp949", errors="replace", newline="")
        with opener as f:
            for r in csv.DictReader(f):
                basket = build_basket(r)
                if basket:
                    self.rows.append({
                        "basket": basket,
                        "prop": to_float(r.get("재산피해소계(천원)")) or 0,
                        "cas": to_float(r.get("인명피해(명)소계")) or 0,
                        "place_l": r.get("장소대분류") or "",
                        "place_m": r.get("장소중분류") or "",
                        "place_s": r.get("장소소분류") or "",
                    })
        props = sorted(r["prop"] for r in self.rows)
        self.p95 = props[int(len(props) * 0.95)] if props else 0
        print(f"✅ 데이터 로딩 완료! 총 {len(self.rows):,}건 (소요 시간: {time.perf_counter()-t0:.2f}초)")

    def query_patterns(self, place_keyword="", target="property", top_k=10, max_item_support=0.85):
        # 1. 장소 필터링
        filtered = []
        for r in self.rows:
            if place_keyword:
                if not (place_keyword in r["place_l"] or place_keyword in r["place_m"] or place_keyword in r["place_s"]):
                    continue
            filtered.append(r)

        n = len(filtered)
        if n < 30:
            return None, f"'{place_keyword}' 관련 데이터가 너무 적습니다 ({n}건)."

        # 2. 큰 피해 기준 플래그
        if target == "casualty":
            heavy_flags = [r["cas"] > 0 for r in filtered]
            target_desc = "인명피해(사망/부상) 발생 화재"
        else:
            heavy_flags = [r["prop"] >= self.p95 for r in filtered]
            target_desc = f"재산피해 상위 5% (>= {self.p95:,.0f}천원) 화재"

        n_heavy = sum(heavy_flags)
        if n_heavy < 5:
            return None, f"해당 장소에서 {target_desc} 사례가 {n_heavy}건으로 너무 적습니다."

        # 3. 장바구니 정수 인코딩 (지지도 85% 초과의 너무 흔한 단일 아이템 제외)
        raw_baskets = [r["basket"] for r in filtered]
        item_count = Counter(i for b in raw_baskets for i in b)
        vocab = sorted(i for i, c in item_count.items() if c / n <= max_item_support)
        idx = {name: k for k, name in enumerate(vocab)}
        baskets = [tuple(sorted(idx[i] for i in b if i in idx)) for b in raw_baskets]
        heavy_baskets = [b for b, f in zip(baskets, heavy_flags) if f]

        # 4. A-Priori 알고리즘 실행 (k=2: L1 -> C2 -> L2)
        min_heavy_count = max(3, int(n_heavy * 0.03))
        freq, stats = apriori_k2(heavy_baskets, min_heavy_count)
        freq_pairs = {s: cnt for s, cnt in freq.items() if len(s) == 2}
        if not freq_pairs:
            min_heavy_count = max(2, int(n_heavy * 0.01))
            freq, stats = apriori_k2(heavy_baskets, min_heavy_count)
            freq_pairs = {s: cnt for s, cnt in freq.items() if len(s) == 2}

        # 5. 전체 집합에서 해당 빈발 2-항목 쌍 출현 빈도 측정 (향상도/배수 계산)
        c_total = count_pairs(baskets, set(freq_pairs))

        n_rest = n - n_heavy
        results = []
        for pair, ch in freq_pairs.items():
            crest = c_total[pair] - ch
            sup_h = ch / n_heavy
            sup_r = (crest + 0.5) / n_rest
            ratio = sup_h / sup_r
            results.append({
                "items": [vocab[i] for i in pair],
                "count_heavy": ch,
                "sup_heavy": sup_h,
                "sup_rest": sup_r,
                "ratio": ratio,
            })

        results.sort(key=lambda x: (-x["ratio"], -x["count_heavy"]))
        return {
            "algo": "apriori",
            "place": place_keyword or "전체",
            "total_count": n,
            "heavy_count": n_heavy,
            "target_desc": target_desc,
            "stats": stats,
            "top_combos": results[:top_k],
        }, None


# ───────────────────────── Upstage Solar API 연동 ─────────────────────────
def call_solar(api_key, model, messages, temperature=0.3):
    body = json.dumps({
        "model": model,
        "temperature": temperature,
        "messages": messages,
    }).encode("utf-8")
    req = urllib.request.Request(
        SOLAR_URL, data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def parse_user_intent(user_msg, api_key, model):
    system = (
        "당신은 사용자의 일상 언어 질문에서 화재 데이터 분석 조건을 추출하는 어시스턴트입니다.\n"
        "반드시 JSON 형식으로만 응답하세요.\n"
        "형식: {\"place\": \"장소 키워드(예: 음식점, 아파트, 공장, 주택, 차량, 병원 등. 특정 장소가 없으면 빈문자열)\", "
        "\"target\": \"property 또는 casualty (사망, 부상, 인명피해 관련 질문이면 casualty, 그 외엔 property)\"}"
    )
    res = call_solar(api_key, model, [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ], temperature=0.0)
    try:
        clean = res.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.endswith("```"):
            clean = clean[:-3]
        return json.loads(clean.strip())
    except Exception:
        return {"place": "", "target": "property"}


def generate_agent_response(user_msg, query_result, api_key, model):
    system = (
        "당신은 115,237건의 실제 소방청 화재 통계(A-Priori k=2 알고리즘 결과)를 기반으로 답변하는 전문 화재 안전 AI 에이전트입니다.\n"
        "사용자가 일상적인 대화체로 질문하면 친절하고 신뢰감 있게 설명하세요.\n\n"
        "답변 작성 지침:\n"
        "1. 실제 통계 수치(배수, 건수 등)를 명확히 인용하여 근거를 제시할 것.\n"
        "2. '전기요인 + 전기' 같은 뻔한 동어반복은 제외하고, 실제로 주의해야 할 복합 위험 조건(예: 특정 건축자재, 시간대, 확산물질 등)을 중심으로 풀어서 설명할 것.\n"
        "3. 사용자가 바로 실천할 수 있는 '구체적인 맞춤형 예방 체크리스트 3~4가지'를 체크박스([ ]) 형태로 제공할 것.\n"
        "4. 데이터에 없는 허구의 수치를 지어내지 말 것."
    )
    s = query_result["stats"]
    user_prompt = (
        f"[사용자 질문]: {user_msg}\n\n"
        f"[A-Priori (k=2) 알고리즘 분석 결과]:\n"
        f"- 분석 대상: {query_result['place']} 관련 화재 총 {query_result['total_count']:,}건 중 {query_result['target_desc']} {query_result['heavy_count']:,}건\n"
        f"- 가지치기 통계: L1 빈발 아이템 {s['l1_frequent_items']}개 → C2 후보쌍 {s['c2_candidates']:,}개 → L2 빈발쌍 {s['l2_frequent_pairs']:,}개\n"
        f"- 위험 증폭 2-항목 쌍 (큰 피해 화재에서 유독 자주 발생하는 쌍 상위):\n"
    )
    for i, r in enumerate(query_result["top_combos"], 1):
        user_prompt += f"  {i}. {' + '.join(r['items'])} (큰피해 발생 비율 {r['sup_heavy']:.1%}, 평소 대비 {r['ratio']:.1f}배 위험, {r['count_heavy']}건)\n"

    user_prompt += "\n위 통계 결과를 바탕으로 사용자의 질문에 친절하고 전문적으로 답변해 주세요."

    return call_solar(api_key, model, [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ], temperature=0.3)


# ───────────────────────── 대화 루프 실행 ─────────────────────────
def main():
    env = load_env()
    api_key = env.get("UPSTAGE_API_KEY", "")
    model = env.get("UPSTAGE_MODEL", "solar-pro4")

    if not api_key or api_key.startswith("여기에"):
        print("❌ .env 파일에 UPSTAGE_API_KEY가 올바르게 설정되지 않았습니다.")
        sys.exit(1)

    print("=" * 65)
    print("🔥 소방청 빅데이터 기반 일상 대화형 화재 위험 진단 AI 에이전트")
    print("   (A-Priori 단독 k=2 알고리즘 + Upstage Solar-pro4 결합)")
    print("=" * 65)

    dataset = FireDataset(DATA_PATH)

    print("\n💡 이제 궁금한 점을 편하게 일상 언어로 질문해 보세요! (종료: 'q' 또는 'exit')")
    print("   예시 1) 고깃집이나 음식점에서는 어떤 상황일 때 불이 크게 나?")
    print("   예시 2) 오래된 원룸이나 다세대주택에서 사람이 다치는 화재는 왜 생겨?")
    print("   예시 3) 공장에서 재산피해가 엄청 커지는 위험한 조건 조합이 뭐야?")
    print("-" * 65)

    while True:
        try:
            user_input = input("\n🗣️  질문: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n종료합니다.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("q", "exit", "quit", "종료"):
            print("에이전트를 종료합니다. 안전한 하루 보내세요! 🚒")
            break

        print("🤖 [Solar] 질문 분석 중...", end="\r", flush=True)
        intent = parse_user_intent(user_input, api_key, model)
        place = intent.get("place", "")
        target = intent.get("target", "property")

        print(f"📊 [A-Priori k=2] 11만건 데이터 검색 중 (장소: '{place or '전체'}', 기준: {target})...", end="\r", flush=True)
        res, err = dataset.query_patterns(place_keyword=place, target=target, top_k=8)

        if err:
            print(f"\n⚠️  {err}")
            continue

        s = res["stats"]
        print(
            f"📌 [A-Priori (k=2) 완료] L1={s['l1_frequent_items']}개 | "
            f"C2 후보: {s['c2_candidates']:,}개 → L2={s['l2_frequent_pairs']:,}개 ({s['seconds']:.3f}초)"
        )
        print("✍️  [Solar] 전문 화재 안전 답변 및 맞춤 점검표 작성 중...   ", end="\r", flush=True)
        reply = generate_agent_response(user_input, res, api_key, model)

        print("\n" + "=" * 65)
        print(reply)
        print("=" * 65)


if __name__ == "__main__":
    main()
