"""소방청 115,237건 화재 데이터 기반 PCY 단독 (k=2) 복합 위험 규칙 추출 스크립트.

기존 빅데이터개론 프로젝트의 PCY(Park-Chen-Yu) 해시 비트맵 알고리즘만 사용하여
k=2 (2-항목 빈발 쌍 L2) 복합 화재 위험 규칙(data/jochiwon_pcy_rules.json)을 생성한다.
"""

from __future__ import annotations

import csv
import gzip
import json
import os
import time
from collections import Counter
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RULES_OUT = DATA_DIR / "jochiwon_pcy_rules.json"

# 기존 빅데이터개론 프로젝트의 소방청 화재현황 원본 데이터 경로
NFDS_GZ_PATH = Path(r"C:\Users\minki\OneDrive\Desktop\빅데이터개론 프로젝트\data\소방청_화재현황_20231231.csv.gz")
NFDS_CSV_PATH = Path(r"C:\Users\minki\OneDrive\Desktop\빅데이터개론 프로젝트\data\소방청_화재현황_20231231.csv")

SKIP_VALUES = {"", "미상", "해당없음", "기타", "N"}

# 조치원읍 지도 건물 및 환경 시뮬레이터와 1:1 매핑 가능한 아이템 집합
TARGET_USAGES = (
    "단독주택",
    "공동주택",
    "음식점",
    "판매시설",
    "일반업무",
    "공장시설",
    "창고시설",
    "교육시설",
)

ROOF_NORMALIZE = {
    "슬라브가": "슬라브가",
    "샌드위치패널": "샌드위치패널",
    "스레트가": "스레트가",
    "와가": "기와",
    "한식기와": "기와",
    "시멘트기와": "기와",
}

MATCHABLE_ITEMS: set[str] = {
    # 장소대 / 장소중
    "장소대:주거",
    "장소대:생활서비스",
    "장소대:판매,업무시설",
    "장소대:산업시설",
    "장소대:교육시설",
    *(f"장소중:{u}" for u in TARGET_USAGES),
    # 건물 구조(기둥벽 / 지붕)
    "구조(기둥벽):철근콘크리트조",
    "구조(기둥벽):벽돌조",
    "구조(기둥벽):철골조",
    "구조(기둥벽):샌드위치패널조",
    "구조(기둥벽):목조",
    "구조(지붕):슬라브가",
    "구조(지붕):샌드위치패널",
    "구조(지붕):스레트가",
    "구조(지붕):기와",
    # 건물 규모 / 출동 도착
    "건물규모:저층(1~2)",
    "건물규모:중층(3~5)",
    "건물규모:고층(6+)",
    "출동도착:7분이상",
    "출동도착:7분미만",
    # 실시간 환경 조건 (시간대 / 계절 / 습도)
    "시간대:심야(00-06)",
    "시간대:주간(06-18)",
    "시간대:야간(18-24)",
    "계절:봄",
    "계절:여름",
    "계절:가을",
    "계절:겨울",
    "습도:건조(<30)",
    "습도:보통(30-60)",
    "습도:습함(60+)",
}


def to_float(val: str | None) -> float | None:
    try:
        return float((val or "").replace(",", "").strip())
    except ValueError:
        return None


def parse_dt(val: str | None) -> datetime | None:
    try:
        return datetime.strptime((val or "").strip()[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def resolve_nfds_path() -> Path:
    env_override = os.environ.get("NFDS_CSV_PATH")
    if env_override and Path(env_override).exists():
        return Path(env_override)
    candidates = [
        DATA_DIR / "소방청_화재현황_20231231.csv.gz",
        DATA_DIR / "소방청_화재현황_20231231.csv",
        NFDS_GZ_PATH,
        NFDS_CSV_PATH,
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        f"소방청 화재현황 원본 파일을 찾을 수 없습니다: {candidates[0]} 또는 {NFDS_GZ_PATH}"
    )


def build_pre_fire_basket(row: dict[str, str]) -> set[str]:
    """CSV 한 행에서 지도 건물·환경과 매칭 가능한 사전 관측 아이템 장바구니를 생성한다."""
    items: set[str] = set()

    place_l = (row.get("장소대분류") or "").strip()
    place_m = (row.get("장소중분류") or "").strip()
    if place_l == "교육시설" and place_m in {"학교", "연구,학원"}:
        place_m = "교육시설"
    if place_l:
        candidate = f"장소대:{place_l}"
        if candidate in MATCHABLE_ITEMS:
            items.add(candidate)
    if place_m:
        candidate = f"장소중:{place_m}"
        if candidate in MATCHABLE_ITEMS:
            items.add(candidate)

    wall = (row.get("건물구조조") or "").strip()
    if wall:
        candidate = f"구조(기둥벽):{wall}"
        if candidate in MATCHABLE_ITEMS:
            items.add(candidate)

    roof_raw = (row.get("건물구조즙") or "").strip()
    roof_norm = ROOF_NORMALIZE.get(roof_raw)
    if roof_norm:
        items.add(f"구조(지붕):{roof_norm}")

    height = to_float(row.get("건물층수(지상)"))
    if height is not None and height >= 1:
        items.add(
            "건물규모:"
            + ("저층(1~2)" if height <= 2 else "중층(3~5)" if height <= 5 else "고층(6+)")
        )

    dt = parse_dt(row.get("접수일시"))
    if dt:
        items.add(
            "시간대:"
            + ("심야(00-06)" if dt.hour < 6 else "주간(06-18)" if dt.hour < 18 else "야간(18-24)")
        )
        items.add(
            "계절:"
            + (
                "겨울"
                if dt.month in (12, 1, 2)
                else "봄"
                if dt.month <= 5
                else "여름"
                if dt.month <= 8
                else "가을"
            )
        )
        arr = parse_dt(row.get("도착일시"))
        if arr and arr >= dt:
            mins = (arr - dt).total_seconds() / 60.0
            items.add("출동도착:" + ("7분이상" if mins >= 7.0 else "7분미만"))

    hum = to_float(row.get("습도"))
    if hum is not None and hum > 0:
        items.add(
            "습도:"
            + ("건조(<30)" if hum < 30 else "보통(30-60)" if hum < 60 else "습함(60+)")
        )

    return items


# ───────────────────── PCY 단독 알고리즘 (k=2, 해시 버킷 + 비트맵 가지치기) ─────────────────────
def pair_hash(a: int, b: int, n_buckets: int) -> int:
    return (a * 10007 + b) % n_buckets


def pcy(
    baskets: list[tuple[int, ...]],
    min_count: int,
    n_buckets: int = 32_771,
) -> tuple[dict[tuple[int, ...], int], dict[str, Any]]:
    """PCY (Park-Chen-Yu) 단독 k=2 마이닝 (Pass 1 해시·비트맵 -> Pass 2 L2)."""
    t0 = time.perf_counter()

    # [Pass 1] 단일 아이템 C1 카운트 + 모든 2-쌍을 해시 버킷에 누적
    c1: Counter[int] = Counter()
    bucket = [0] * n_buckets
    for b in baskets:
        c1.update(b)
        for a, c in combinations(b, 2):
            bucket[pair_hash(a, c, n_buckets)] += 1

    l1 = sorted(i for i, c in c1.items() if c >= min_count)
    frequent: dict[tuple[int, ...], int] = {(i,): c1[i] for i in l1}

    # 비트맵 생성 후 (a in L1 and c in L1 and bitmap[h(a,c)] == 1) 인 2-쌍만 C2 후보로 채택
    bitmap = [c >= min_count for c in bucket]
    naive_c2_pairs = len(l1) * (len(l1) - 1) // 2
    cand2 = {(a, c) for a, c in combinations(l1, 2) if bitmap[pair_hash(a, c, n_buckets)]}

    # [Pass 2] 가지치기된 C2 후보만 카운트하여 빈발 2-항목 쌍 L2 확정 (k=2)
    l1set = set(l1)
    c2: Counter[tuple[int, int]] = Counter()
    for b in baskets:
        fb = [i for i in b if i in l1set]
        for p in combinations(fb, 2):
            if p in cand2:
                c2[p] += 1
    l2 = {p: c for p, c in c2.items() if c >= min_count}
    frequent.update(l2)

    c2_reduction = round(1.0 - (len(cand2) / naive_c2_pairs), 4) if naive_c2_pairs else 0.0
    stats: dict[str, Any] = {
        "algorithm": "PCY",
        "max_k": 2,
        "n_buckets": n_buckets,
        "c1_items": len(c1),
        "l1_frequent_items": len(l1),
        "naive_c2_pairs": naive_c2_pairs,
        "bitmap_frequent_buckets": sum(bitmap),
        "c2_candidates": len(cand2),
        "l2_frequent_pairs": len(l2),
        "c2_reduction": c2_reduction,
        "seconds": round(time.perf_counter() - t0, 3),
    }
    return frequent, stats


def build_checklist(items: list[str], top_cause: str, top_spread: str, primary_target: str) -> str:
    """Solar 감사 기준(실질 복합 위험 패턴)을 반영한 현장 예방 점검 가이드를 생성한다."""
    tips: list[str] = []
    joined = " ".join(items)
    if "심야(00-06)" in joined:
        tips.append("심야 무인·취침 시간대 조기 감지용 단독경보형감지기·속보설비 점검")
    if "샌드위치패널" in joined or "목조" in joined or "철골조" in joined:
        tips.append("가연성 외벽·지붕 및 무내화 철골 구간 방화구획 확인")
    if "출동도착:7분이상" in joined:
        tips.append("초기 골든타임 지연 대비 자체 소화전·비상소화장치 가동 점검")
    if "건조(<30)" in joined or "겨울" in joined or "봄" in joined:
        tips.append("건조기 난방·전열기구 과부하 및 주변 가연물 이격 조치")
    if "전기적 요인" in top_cause:
        tips.append("노후 분전반·문어발 배선 및 누전차단기 집중 진단")
    elif "부주의" in top_cause:
        tips.append("조리·화기 취급 부주의 및 흡연·용접 화원 관리 강화")
    if top_spread and top_spread != "미상":
        tips.append(f"주요 연소확대물({top_spread}) 적재 분산 필요")
    if not tips:
        tips.append(f"{primary_target} 예방을 위한 정기 소방안전점검 권장")
    return " · ".join(tips[:2])


def is_valid_composite_rule(items: tuple[str, ...]) -> bool:
    """동어반복(장소대+장소중 동시 포함)을 배제하고 k=2 건물·환경 복합 쌍만 허용한다."""
    if len(items) != 2:
        return False
    has_place_l = any(i.startswith("장소대:") for i in items)
    has_place_m = any(i.startswith("장소중:") for i in items)
    if has_place_l and has_place_m:
        return False
    has_building_attr = any(i.startswith(("장소대:", "장소중:", "구조(", "건물규모:")) for i in items)
    return has_building_attr


def mine_rules() -> None:
    nfds_path = resolve_nfds_path()
    print(f"[1/4] 소방청 데이터 로딩 중: {nfds_path}")
    opener = (
        gzip.open(nfds_path, "rt", encoding="cp949", errors="replace", newline="")
        if nfds_path.suffix == ".gz"
        else open(nfds_path, encoding="cp949", errors="replace", newline="")
    )

    all_props: list[float] = []
    building_records: list[dict[str, Any]] = []
    n_total_fires = 0

    with opener as f:
        for row in csv.DictReader(f):
            n_total_fires += 1
            prop_val = to_float(row.get("재산피해소계(천원)")) or 0.0
            all_props.append(prop_val)

            place_l = (row.get("장소대분류") or "").strip()
            place_m = (row.get("장소중분류") or "").strip()
            if place_l in {"자동차,철도차량", "임야", ""} or place_m == "야외":
                continue

            basket = build_pre_fire_basket(row)
            if len(basket) < 2:
                continue

            cas_val = to_float(row.get("인명피해(명)소계")) or 0.0
            cause = (row.get("발화요인대분류") or "").strip()
            spread = (row.get("연소확대물대분류") or "").strip()
            building_records.append(
                {
                    "basket": basket,
                    "prop": prop_val,
                    "cas": cas_val,
                    "place_m": place_m,
                    "cause": "" if cause in SKIP_VALUES else cause,
                    "spread": "" if spread in SKIP_VALUES else spread,
                }
            )

    all_props.sort()
    p95_prop = all_props[int(len(all_props) * 0.95)] if all_props else 0.0
    n_building = len(building_records)
    flags_prop = [r["prop"] >= p95_prop and p95_prop > 0 for r in building_records]
    flags_cas = [r["cas"] > 0 for r in building_records]
    n_heavy_prop = sum(flags_prop)
    n_heavy_cas = sum(flags_cas)

    print(
        f"      전체 {n_total_fires:,}건 중 건축물 화재 {n_building:,}건 "
        f"(대형 재산피해 >= {p95_prop:,.0f}천원: {n_heavy_prop:,}건, 인명피해: {n_heavy_cas:,}건)"
    )

    # 정수 인코딩 (전체 어휘)
    item_counts = Counter(i for r in building_records for i in r["basket"])
    vocab = sorted(i for i, c in item_counts.items() if c / n_building <= 0.85)
    idx_map = {name: k for k, name in enumerate(vocab)}

    encoded_baskets = [
        tuple(sorted(idx_map[i] for i in r["basket"] if i in idx_map))
        for r in building_records
    ]

    # [2/4] PCY 단독 (k=2) 실행 및 비트맵 가지치기 지표 기록 (전체 건축물 화재, min_support=1.0%)
    print("[2/4] PCY 단독 알고리즘 (k=2) 실행 ...")
    bench_min_count = max(2, int(n_building * 0.01))
    _, stats_p = pcy(encoded_baskets, bench_min_count, n_buckets=32_771)
    print(
        f"      L1={stats_p['l1_frequent_items']}개 -> 전체 쌍 {stats_p['naive_c2_pairs']:,} vs "
        f"PCY 비트맵 후 C2={stats_p['c2_candidates']:,} "
        f"(절감 {stats_p['c2_reduction']:.1%}), L2={stats_p['l2_frequent_pairs']:,}쌍"
    )

    # [3/4] 전체 및 용도별 PCY k=2 마이닝으로 후보 쌍 수집
    print("[3/4] 전체 및 용도별 k=2 복합 위험 쌍 PCY 마이닝 ...")
    candidate_itemsets: set[tuple[int, ...]] = set()

    heavy_prop_baskets = [b for b, f in zip(encoded_baskets, flags_prop) if f]
    heavy_cas_baskets = [b for b, f in zip(encoded_baskets, flags_cas) if f]

    freq_gp, _ = pcy(heavy_prop_baskets, max(15, int(n_heavy_prop * 0.005)))
    freq_gc, _ = pcy(heavy_cas_baskets, max(15, int(n_heavy_cas * 0.005)))
    candidate_itemsets.update(s for s in freq_gp if len(s) == 2)
    candidate_itemsets.update(s for s in freq_gc if len(s) == 2)

    # 조치원읍 8개 용도별 조건부 PCY (k=2) 마이닝 (희소 용도의 정밀 패턴 확보)
    for usage in TARGET_USAGES:
        usage_item = f"장소중:{usage}"
        if usage_item not in idx_map:
            continue
        u_idx = idx_map[usage_item]
        sub_prop = [b for b, f in zip(encoded_baskets, flags_prop) if f and u_idx in b]
        sub_cas = [b for b, f in zip(encoded_baskets, flags_cas) if f and u_idx in b]
        if len(sub_prop) >= 10:
            fp_u, _ = pcy(sub_prop, max(5, int(len(sub_prop) * 0.03)))
            candidate_itemsets.update(s for s in fp_u if len(s) == 2 and u_idx in s)
        if len(sub_cas) >= 10:
            fc_u, _ = pcy(sub_cas, max(5, int(len(sub_cas) * 0.03)))
            candidate_itemsets.update(s for s in fc_u if len(s) == 2 and u_idx in s)

    # 동어반복 및 무의미한 조합 제거 (len(s) == 2)
    valid_cands = {
        s
        for s in candidate_itemsets
        if is_valid_composite_rule(tuple(vocab[i] for i in s))
    }
    print(f"      유효 k=2 후보 쌍 {len(valid_cands):,}개 통계 검증 중 ...")

    # 전체 75,798건 기준 정밀 통계(재산/인명 건수, 배수, 주요 발화요인/연소확대물) 산출
    relevant_ids = {i for s in valid_cands for i in s}

    total_cnt: Counter[tuple[int, ...]] = Counter()
    prop_cnt: Counter[tuple[int, ...]] = Counter()
    cas_cnt: Counter[tuple[int, ...]] = Counter()
    cause_cnt: dict[tuple[int, ...], Counter[str]] = {}
    spread_cnt: dict[tuple[int, ...], Counter[str]] = {}

    for rec, b, is_p, is_c in zip(building_records, encoded_baskets, flags_prop, flags_cas):
        fb = [i for i in b if i in relevant_ids]
        if len(fb) < 2:
            continue
        c_val = rec["cause"]
        sp_val = rec["spread"]
        for comb in combinations(fb, 2):
            if comb in valid_cands:
                total_cnt[comb] += 1
                if is_p:
                    prop_cnt[comb] += 1
                if is_c:
                    cas_cnt[comb] += 1
                if c_val:
                    cause_cnt.setdefault(comb, Counter())[c_val] += 1
                if sp_val:
                    spread_cnt.setdefault(comb, Counter())[sp_val] += 1

    n_rest_prop = n_building - n_heavy_prop
    n_rest_cas = n_building - n_heavy_cas

    scored_rules: list[dict[str, Any]] = []
    for comb in valid_cands:
        tot = total_cnt[comb]
        cp = prop_cnt[comb]
        cc = cas_cnt[comb]
        if tot < 15 or max(cp, cc) < 5:
            continue

        sup_p = cp / n_heavy_prop
        sup_rp = (tot - cp + 0.5) / n_rest_prop
        ratio_prop = sup_p / sup_rp

        sup_c = cc / n_heavy_cas
        sup_rc = (tot - cc + 0.5) / n_rest_cas
        ratio_cas = sup_c / sup_rc

        max_ratio = max(ratio_prop, ratio_cas)
        if max_ratio < 1.15:
            continue

        items = [vocab[i] for i in comb]
        primary_target = "대형 재산피해" if ratio_prop >= ratio_cas else "인명피해"

        top_cause_str = "미상"
        if comb in cause_cnt and cause_cnt[comb]:
            cname, cnum = cause_cnt[comb].most_common(1)[0]
            top_cause_str = f"{cname} ({round(cnum / tot * 100)}%)"

        top_spread_str = "미상"
        if comb in spread_cnt and spread_cnt[comb]:
            sname, snum = spread_cnt[comb].most_common(1)[0]
            top_spread_str = f"{sname} ({round(snum / tot * 100)}%)"

        audit_label = "실질 복합 위험 패턴" if max_ratio >= 2.0 else "주의 복합 위험 패턴"
        checklist = build_checklist(items, top_cause_str, top_spread_str, primary_target)

        scored_rules.append(
            {
                "items": items,
                "k": len(items),
                "total_fires": tot,
                "count_prop": cp,
                "sup_prop": round(sup_p, 4),
                "ratio_prop": round(ratio_prop, 2),
                "count_cas": cc,
                "sup_cas": round(sup_c, 4),
                "ratio_cas": round(ratio_cas, 2),
                "max_ratio": round(max_ratio, 2),
                "primary_target": primary_target,
                "top_cause": top_cause_str,
                "top_spread": top_spread_str,
                "audit_label": audit_label,
                "checklist": checklist,
            }
        )

    # 용도별 균형 확보 + 전체 상위 고위험 규칙 병합 (중복 제거)
    selected_map: dict[tuple[str, ...], dict[str, Any]] = {}
    for usage in TARGET_USAGES:
        u_tag = f"장소중:{usage}"
        u_rules = [r for r in scored_rules if u_tag in r["items"]]
        u_prop = sorted(u_rules, key=lambda r: (-r["ratio_prop"], -r["count_prop"]))[:16]
        u_cas = sorted(u_rules, key=lambda r: (-r["ratio_cas"], -r["count_cas"]))[:12]
        for r in u_prop + u_cas:
            selected_map[tuple(r["items"])] = r

    global_top = sorted(scored_rules, key=lambda r: (-r["max_ratio"], -r["total_fires"]))[:80]
    for r in global_top:
        selected_map[tuple(r["items"])] = r

    final_rules = sorted(
        selected_map.values(),
        key=lambda r: (-r["max_ratio"], -max(r["count_prop"], r["count_cas"])),
    )

    output = {
        "metadata": {
            "algorithm": "PCY",
            "max_k": 2,
            "source_dataset": nfds_path.name,
            "n_total_fires": n_total_fires,
            "n_building_fires": n_building,
            "p95_property_damage_krw": round(p95_prop),
            "n_heavy_property": n_heavy_prop,
            "n_casualty": n_heavy_cas,
            "vocab_size": len(vocab),
            "benchmark": {
                "min_support": 0.01,
                "min_count": bench_min_count,
                "n_buckets": stats_p["n_buckets"],
                "naive_c2_pairs": stats_p["naive_c2_pairs"],
                "c2_reduction": stats_p["c2_reduction"],
                "pcy": stats_p,
            },
            "rule_count": len(final_rules),
        },
        "rules": final_rules,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RULES_OUT.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[4/4] 저장 완료: {RULES_OUT} (최종 규칙 {len(final_rules)}개)")


if __name__ == "__main__":
    mine_rules()
