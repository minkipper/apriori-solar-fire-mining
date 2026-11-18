"""조치원읍 건물 폴리곤 수집 및 화재 위험도 데이터셋 생성 스크립트.

OpenStreetMap v0.6 API에서 세종특별자치시 조치원읍 일대의 실제 건물 폴리곤과
소방시설 위치 데이터를 수집하고, 공간 연산(인접 건물 밀집도, 소방서/소화전 거리)과
구역별 건축 특성을 결합하여 5대 지표 기반 화재 위험도 GeoJSON을 생성한다.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# 프로젝트 경로 설정
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
BUILDINGS_OUT = DATA_DIR / "jochiwon_buildings.geojson"
INFRA_OUT = DATA_DIR / "jochiwon_infra.geojson"

# 조치원읍 중심 및 OpenStreetMap API v0.6 설정
CURRENT_YEAR = 2026
JOCHIWON_BBOX = "127.280,36.585,127.306,36.618"
OSM_MAP_URL = f"https://api.openstreetmap.org/api/0.6/map.json?bbox={JOCHIWON_BBOX}"
OSM_BOUNDARY_URL = "https://api.openstreetmap.org/api/0.6/relation/7690667/full.json"
HTTP_HEADERS = {"User-Agent": "JochiwonFireRiskApp/1.0"}

# 위도 36.6도 기준 미터 환산 계수
REF_LAT = 36.6
M_PER_DEG_LAT = 110968.0
M_PER_DEG_LON = 111320.0 * math.cos(math.radians(REF_LAT))

# 조치원읍 14개 법정리 대표 좌표 (OSM 주소 누락 건물 매핑용)
RI_CENTERS: dict[str, tuple[float, float]] = {
    "원리": (36.6014, 127.2993),
    "상리": (36.6020, 127.3023),
    "명리": (36.6029, 127.3005),
    "평리": (36.6051, 127.3012),
    "교리": (36.6041, 127.2987),
    "정리": (36.5998, 127.2996),
    "남리": (36.5971, 127.2993),
    "침산리": (36.6022, 127.2920),
    "신흥리": (36.5959, 127.2912),
    "죽림리": (36.5916, 127.2953),
    "신안리": (36.6156, 127.2855),
    "서창리": (36.6076, 127.2901),
    "번암리": (36.5865, 127.2961),
    "봉산리": (36.6038, 127.2825),
}

# 구도심(전통시장·조치원역) 및 주요 권역 분류
OLD_DOWNTOWN_RIS = {"원리", "상리", "명리", "평리", "정리", "남리"}
UNIVERSITY_RIS = {"서창리", "신안리"}
APARTMENT_RIS = {"침산리", "죽림리", "신흥리"}
INDUSTRIAL_RIS = {"번암리", "봉산리"}

# 소방서 / 119지역대 기본 좌표 (OSM 미수신 또는 폴백용)
FALLBACK_FIRE_STATIONS: list[dict[str, Any]] = [
    {
        "name": "세종북부소방서",
        "type": "소방서",
        "lat": 36.6046,
        "lon": 127.2889,
        "address": "세종특별자치시 조치원읍 세종로 2439",
        "source": "OSM 실측",
    },
    {
        "name": "원리119지역대",
        "type": "119지역대",
        "lat": 36.6020,
        "lon": 127.2965,
        "address": "세종특별자치시 조치원읍 으뜸길 235",
        "source": "OSM 실측",
    },
    {
        "name": "119특수구조단 화학구조대",
        "type": "특수구조대",
        "lat": 36.5861,
        "lon": 127.2969,
        "address": "세종특별자치시 연기면 허만석로 54 (조치원 남측 인접)",
        "source": "OSM 실측",
    },
]

# 조치원읍 주요 교차로/시장/대학가/주거지 소화전 보강 좌표 (OSM 실측 소화전과 병합)
SUPPLEMENTAL_HYDRANTS: list[tuple[float, float, str]] = [
    (36.6012, 127.2974, "조치원역 광장 앞"),
    (36.6018, 127.3005, "세종전통시장 북문"),
    (36.6004, 127.3007, "세종전통시장 중앙통"),
    (36.5994, 127.2995, "정리 상가거리"),
    (36.6033, 127.3016, "상리·명리 교차로"),
    (36.6049, 127.3010, "평리 주택가 입구"),
    (36.6043, 127.2983, "교리 행정복지센터 인근"),
    (36.6056, 127.2966, "교리 세종중학교 앞"),
    (36.5974, 127.2989, "남리 삼거리"),
    (36.5960, 127.2968, "남리 남부대로변"),
    (36.6031, 127.2932, "침산리 상업지구"),
    (36.6007, 127.2921, "침산리 대동초 인근"),
    (36.5983, 127.2916, "신흥리 푸르지오 인근"),
    (36.5955, 127.2925, "신흥리 주거단지"),
    (36.5924, 127.2948, "죽림리 자이·e편한세상 앞"),
    (36.5902, 127.2965, "죽림리 남부교차로"),
    (36.5872, 127.2956, "번암리 산업단지 입구"),
    (36.5891, 127.2904, "번암리 물류도로"),
    (36.6085, 127.2902, "서창리 고려대 세종캠퍼스 입구"),
    (36.6114, 127.2896, "서창리 대학로 원룸촌"),
    (36.6148, 127.2862, "신안리 홍익대 인근"),
    (36.6041, 127.2832, "봉산리 공업·창고 지구"),
    (36.6062, 127.2858, "침산리 서부대로변"),
    (36.6025, 127.2888, "침산리 소방서 남측 사거리"),
    (36.5992, 127.2954, "조치원역 서측 철로변"),
    (36.6068, 127.2938, "서창리 서창역사공원 인근"),
    (36.5940, 127.2882, "신흥리 서측 외곽도로"),
    (36.6105, 127.2940, "서창리 동측 주거지"),
]


def fetch_json(url: str, timeout: int = 20, retries: int = 3) -> dict[str, Any]:
    """재시도 로직을 포함해 JSON API를 호출한다."""
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=HTTP_HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(1.5 * attempt)
    raise RuntimeError(f"API 호출 실패 ({url}): {last_err}")


def to_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 위경도 좌표 간 평면 근사 거리(m)를 계산한다."""
    dy = (lat2 - lat1) * M_PER_DEG_LAT
    dx = (lon2 - lon1) * M_PER_DEG_LON
    return math.hypot(dx, dy)


def polygon_centroid_and_area(coords: list[list[float]]) -> tuple[float, float, float]:
    """폐곡선 좌표([[lon, lat], ...])의 중심(lat, lon)과 바닥면적(m^2)을 구한다."""
    if len(coords) < 3:
        return coords[0][1], coords[0][0], 50.0

    # 미터 단위 상대 좌표로 변환해 Shoelace 공식 적용
    lon0, lat0 = coords[0]
    pts_m = [
        ((lon - lon0) * M_PER_DEG_LON, (lat - lat0) * M_PER_DEG_LAT)
        for lon, lat in coords
    ]
    twice_area = 0.0
    cx_num = 0.0
    cy_num = 0.0
    for i in range(len(pts_m) - 1):
        x0, y0 = pts_m[i]
        x1, y1 = pts_m[i + 1]
        cross = x0 * y1 - x1 * y0
        twice_area += cross
        cx_num += (x0 + x1) * cross
        cy_num += (y0 + y1) * cross

    area = abs(twice_area) * 0.5
    if area < 1.0 or abs(twice_area) < 1e-6:
        avg_lon = sum(c[0] for c in coords[:-1]) / max(1, len(coords) - 1)
        avg_lat = sum(c[1] for c in coords[:-1]) / max(1, len(coords) - 1)
        return avg_lat, avg_lon, max(area, 25.0)

    cx_m = cx_num / (3.0 * twice_area)
    cy_m = cy_num / (3.0 * twice_area)
    centroid_lon = lon0 + cx_m / M_PER_DEG_LON
    centroid_lat = lat0 + cy_m / M_PER_DEG_LAT
    return centroid_lat, centroid_lon, area


def point_in_polygon(lon: float, lat: float, poly: list[list[float]]) -> bool:
    """Ray-casting 알고리즘으로 점이 다각형 내부에 있는지 판별한다."""
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        intersects = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) if abs(yj - yi) > 1e-12 else 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def parse_jochiwon_boundary() -> list[list[float]] | None:
    """OSM 관계(relation/7690667)에서 조치원읍 행정경계 외곽 다각형을 추출한다."""
    try:
        data = fetch_json(OSM_BOUNDARY_URL, timeout=15, retries=2)
    except Exception:
        return None

    elements = data.get("elements", [])
    nodes = {e["id"]: [e["lon"], e["lat"]] for e in elements if e["type"] == "node"}
    ways = {e["id"]: e["nodes"] for e in elements if e["type"] == "way"}
    rels = [e for e in elements if e["type"] == "relation"]
    if not rels:
        return None

    segments = [
        list(ways[m["ref"]])
        for m in rels[0].get("members", [])
        if m.get("type") == "way" and m.get("role") == "outer" and m.get("ref") in ways
    ]
    if not segments:
        return None

    ring = segments.pop(0)
    while segments:
        end_node = ring[-1]
        matched = False
        for idx, seg in enumerate(segments):
            if seg[0] == end_node:
                ring.extend(seg[1:])
                segments.pop(idx)
                matched = True
                break
            if seg[-1] == end_node:
                ring.extend(reversed(seg[:-1]))
                segments.pop(idx)
                matched = True
                break
        if not matched:
            break

    coords = [nodes[nid] for nid in ring if nid in nodes]
    if len(coords) >= 4 and coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords if len(coords) >= 4 else None


def deterministic_rng(way_id: int) -> random.Random:
    """건물 ID 기반으로 재현 가능한 난수 생성기를 반환한다."""
    digest = hashlib.sha256(f"jochiwon-{way_id}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def assign_subdistrict(tags: dict[str, Any], lat: float, lon: float) -> str:
    """OSM 태그 또는 최단 거리 기준 조치원읍 법정리를 결정한다."""
    sub = tags.get("addr:subdistrict")
    if sub in RI_CENTERS:
        return str(sub)
    return min(RI_CENTERS.keys(), key=lambda ri: to_meters(lat, lon, *RI_CENTERS[ri]))


def build_address(tags: dict[str, Any], subdistrict: str) -> str:
    """실제 OSM 주소 태그를 우선 활용해 조치원읍 주소를 조합한다."""
    street = tags.get("addr:street")
    housenum = tags.get("addr:housenumber")
    if street and housenum:
        return f"세종특별자치시 조치원읍 {subdistrict} {street} {housenum}"
    if street:
        return f"세종특별자치시 조치원읍 {subdistrict} {street}"
    return f"세종특별자치시 조치원읍 {subdistrict} 일원"


def infer_usage(tags: dict[str, Any], subdistrict: str, area_m2: float, rng: random.Random) -> str:
    """OSM 건물·상점·편의시설 태그 및 입지 특성에 따라 주용도를 매핑한다."""
    b_tag = str(tags.get("building", "yes")).lower()
    amenity = str(tags.get("amenity", "")).lower()
    shop = str(tags.get("shop", "")).lower()
    name = str(tags.get("name", ""))

    if "시장" in name or b_tag == "marketplace" or amenity == "marketplace":
        return "전통시장/상점가"
    if b_tag in {"apartments", "dormitory"}:
        return "공동주택"
    if b_tag in {"school", "university", "kindergarten", "college"} or amenity in {
        "school",
        "university",
        "kindergarten",
    }:
        return "교육연구시설"
    if b_tag in {"industrial", "warehouse", "manufacture", "greenhouse"}:
        return "창고/공장시설"
    if b_tag in {"public", "civic", "government", "fire_station", "office", "hospital"} or amenity in {
        "townhall",
        "police",
        "courthouse",
        "fire_station",
        "hospital",
        "post_office",
    } or tags.get("office"):
        return "업무/공공시설"
    if b_tag in {"commercial", "retail", "supermarket", "hotel"} or shop or amenity in {
        "restaurant",
        "cafe",
        "fast_food",
        "bar",
        "pub",
        "bank",
        "pharmacy",
    }:
        if subdistrict in {"원리", "상리", "명리"} and rng.random() < 0.25:
            return "전통시장/상점가"
        return "제1·2종 근린생활시설"
    if b_tag in {"house", "detached", "residential", "semidetached_house"}:
        if area_m2 > 420 and subdistrict in APARTMENT_RIS:
            return "공동주택"
        return "단독주택"

    # building=yes 등 일반 태그일 때 입지 및 면적 기반 매핑
    if area_m2 >= 650:
        if subdistrict in INDUSTRIAL_RIS:
            return "창고/공장시설"
        if subdistrict in APARTMENT_RIS:
            return "공동주택"
        if subdistrict in UNIVERSITY_RIS:
            return "교육연구시설" if rng.random() < 0.45 else "공동주택"
        return "제1·2종 근린생활시설"

    if subdistrict in OLD_DOWNTOWN_RIS:
        return rng.choices(
            ["전통시장/상점가", "제1·2종 근린생활시설", "단독주택"],
            weights=[0.18, 0.44, 0.38],
        )[0]
    if subdistrict in INDUSTRIAL_RIS:
        return rng.choices(
            ["창고/공장시설", "단독주택", "제1·2종 근린생활시설"],
            weights=[0.52, 0.30, 0.18],
        )[0]
    if subdistrict in UNIVERSITY_RIS:
        return rng.choices(
            ["제1·2종 근린생활시설", "공동주택", "단독주택"],
            weights=[0.42, 0.30, 0.28],
        )[0]
    if subdistrict in APARTMENT_RIS:
        return rng.choices(
            ["공동주택", "제1·2종 근린생활시설", "단독주택"],
            weights=[0.42, 0.28, 0.30],
        )[0]
    return rng.choices(["단독주택", "제1·2종 근린생활시설"], weights=[0.65, 0.35])[0]


def infer_floors(tags: dict[str, Any], usage: str, area_m2: float, rng: random.Random) -> int:
    """OSM 층수 태그 우선 적용 후 용도·면적 기반 지상층수를 추정한다."""
    raw_levels = tags.get("building:levels")
    if raw_levels is not None:
        try:
            parsed = int(float(str(raw_levels).split(";")[0].strip()))
            if 1 <= parsed <= 50:
                return parsed
        except ValueError:
            pass

    if usage == "공동주택":
        if area_m2 >= 500:
            return rng.randint(10, 24)
        return rng.randint(3, 6)
    if usage == "교육연구시설":
        return rng.randint(2, 5)
    if usage == "업무/공공시설":
        return rng.randint(2, 5)
    if usage == "창고/공장시설":
        return rng.randint(1, 2)
    if usage in {"전통시장/상점가", "제1·2종 근린생활시설"}:
        return rng.choices([1, 2, 3, 4, 5], weights=[0.28, 0.34, 0.22, 0.11, 0.05])[0]
    return rng.choices([1, 2, 3], weights=[0.58, 0.32, 0.10])[0]


def infer_built_year_and_structure(
    usage: str,
    floors: int,
    subdistrict: str,
    rng: random.Random,
) -> tuple[int, str, bool]:
    """권역, 용도, 층수를 반영해 준공연도, 주구조, 스프링클러 여부를 산출한다."""
    # 준공연도
    if usage == "공동주택" and floors >= 10:
        built_year = rng.randint(1998, 2022)
    elif subdistrict in OLD_DOWNTOWN_RIS:
        if usage in {"전통시장/상점가", "단독주택"}:
            built_year = rng.randint(1972, 2003)
        else:
            built_year = rng.randint(1980, 2015)
    elif subdistrict in UNIVERSITY_RIS:
        built_year = rng.randint(1994, 2021)
    elif subdistrict in APARTMENT_RIS:
        built_year = rng.randint(1995, 2023)
    else:
        built_year = rng.randint(1982, 2018)

    # 주구조
    if floors >= 5 or usage in {"공동주택", "교육연구시설", "업무/공공시설"} and floors >= 3:
        structure = "철근콘크리트조"
    elif usage == "창고/공장시설":
        structure = rng.choices(
            ["경량철골조(샌드위치패널)", "일반철골조", "철근콘크리트조"],
            weights=[0.52, 0.36, 0.12],
        )[0]
    elif usage == "전통시장/상점가":
        if built_year < 1995:
            structure = rng.choices(
                ["벽돌조", "경량철골조(샌드위치패널)", "일반목구조", "철근콘크리트조"],
                weights=[0.40, 0.30, 0.16, 0.14],
            )[0]
        else:
            structure = rng.choices(
                ["철근콘크리트조", "경량철골조(샌드위치패널)", "벽돌조"],
                weights=[0.45, 0.35, 0.20],
            )[0]
    elif usage == "단독주택":
        if built_year < 1992:
            structure = rng.choices(
                ["벽돌조", "일반목구조", "경량철골조(샌드위치패널)", "철근콘크리트조"],
                weights=[0.50, 0.24, 0.14, 0.12],
            )[0]
        else:
            structure = rng.choices(
                ["철근콘크리트조", "벽돌조", "경량철골조(샌드위치패널)"],
                weights=[0.55, 0.33, 0.12],
            )[0]
    else:
        # 제1·2종 근린생활시설
        if built_year < 1998:
            structure = rng.choices(
                ["벽돌조", "철근콘크리트조", "경량철골조(샌드위치패널)"],
                weights=[0.45, 0.35, 0.20],
            )[0]
        else:
            structure = rng.choices(
                ["철근콘크리트조", "일반철골조", "벽돌조", "경량철골조(샌드위치패널)"],
                weights=[0.62, 0.16, 0.12, 0.10],
            )[0]

    # 스프링클러 설치 여부 (고층/신축 공동주택·공공·교육시설 중심)
    if floors >= 6 and built_year >= 2005:
        has_sprinkler = True
    elif usage in {"교육연구시설", "업무/공공시설"} and built_year >= 2010:
        has_sprinkler = rng.random() < 0.78
    elif usage in {"제1·2종 근린생활시설", "창고/공장시설"} and built_year >= 2016 and floors >= 3:
        has_sprinkler = rng.random() < 0.45
    else:
        has_sprinkler = False

    return built_year, structure, has_sprinkler


def infer_roof_and_basket(
    tags: dict[str, Any],
    name: str,
    usage: str,
    structure: str,
    built_year: int,
    floors: int,
    area_m2: float,
    neighbor_count_30m: int,
    dist_station_m: float,
    rng: random.Random,
) -> tuple[str, list[str]]:
    """소방청 NFDS 장바구니 모델과 호환되는 지붕 구조 및 정적 아이템 집합을 생성한다."""
    if structure == "철근콘크리트조":
        roof_type = "슬라브가"
    elif structure == "경량철골조(샌드위치패널)":
        roof_type = "샌드위치패널"
    elif structure == "일반철골조":
        if usage == "창고/공장시설":
            roof_type = "샌드위치패널"
        else:
            roof_type = rng.choices(
                ["샌드위치패널", "슬라브가", "스레트가"], weights=[0.55, 0.30, 0.15]
            )[0]
    elif structure == "일반목구조":
        if built_year < 1995:
            roof_type = "기와"
        else:
            roof_type = rng.choices(
                ["기와", "샌드위치패널", "스레트가"], weights=[0.50, 0.30, 0.20]
            )[0]
    else:
        # 벽돌조
        if built_year < 1990 and usage == "단독주택":
            roof_type = "기와"
        else:
            roof_type = rng.choices(
                ["슬라브가", "샌드위치패널", "기와", "스레트가"],
                weights=[0.50, 0.22, 0.16, 0.12],
            )[0]

    b_tag = str(tags.get("building", "yes")).lower()
    if usage == "전통시장/상점가":
        place_items = ["장소대:판매,업무시설", "장소중:판매시설"]
    elif usage == "제1·2종 근린생활시설":
        place_items = ["장소대:생활서비스", "장소중:음식점"]
    elif usage == "단독주택":
        place_items = ["장소대:주거", "장소중:단독주택"]
    elif usage == "공동주택":
        place_items = ["장소대:주거", "장소중:공동주택"]
    elif usage == "창고/공장시설":
        is_warehouse = (
            "창고" in name
            or b_tag == "warehouse"
            or (area_m2 < 450 and rng.random() < 0.45)
        )
        place_items = (
            ["장소대:산업시설", "장소중:창고시설"]
            if is_warehouse
            else ["장소대:산업시설", "장소중:공장시설"]
        )
    elif usage == "교육연구시설":
        place_items = ["장소대:교육시설", "장소중:교육시설"]
    else:
        place_items = ["장소대:판매,업무시설", "장소중:일반업무"]

    wall_map = {
        "철근콘크리트조": "구조(기둥벽):철근콘크리트조",
        "벽돌조": "구조(기둥벽):벽돌조",
        "일반철골조": "구조(기둥벽):철골조",
        "경량철골조(샌드위치패널)": "구조(기둥벽):샌드위치패널조",
        "일반목구조": "구조(기둥벽):목조",
    }
    wall_item = wall_map.get(structure, "구조(기둥벽):철근콘크리트조")
    roof_item = f"구조(지붕):{roof_type}"

    if floors <= 2:
        scale_item = "건물규모:저층(1~2)"
    elif floors <= 5:
        scale_item = "건물규모:중층(3~5)"
    else:
        scale_item = "건물규모:고층(6+)"

    # 소방서 직선거리 1.1km 이상이거나 구도심 골목 밀집(인접 5동 이상) 시 초기 출동 7분 이상 취약
    if dist_station_m >= 1100 or (dist_station_m >= 650 and neighbor_count_30m >= 5):
        dispatch_item = "출동도착:7분이상"
    else:
        dispatch_item = "출동도착:7분미만"

    basket = [*place_items, wall_item, roof_item, scale_item, dispatch_item]
    return roof_type, basket


def compute_fire_risk(
    built_year: int,
    structure: str,
    usage: str,
    floors: int,
    has_sprinkler: bool,
    neighbor_count_30m: int,
    dist_fire_station_m: float,
    dist_hydrant_m: float,
) -> dict[str, Any]:
    """5대 지표(0~100점) 기반 건물 화재 위험도 점수와 취약 요인을 산출한다."""
    age = max(0, CURRENT_YEAR - built_year)

    # 1. 건물 노후도 (0 ~ 25점)
    if age >= 40:
        score_age = 25
    elif age >= 30:
        score_age = 21
    elif age >= 20:
        score_age = 15
    elif age >= 10:
        score_age = 9
    else:
        score_age = 4

    # 2. 구조 및 마감재 취약성 (0 ~ 25점)
    structure_scores = {
        "일반목구조": 24,
        "경량철골조(샌드위치패널)": 22,
        "벽돌조": 15,
        "일반철골조": 12,
        "철근콘크리트조": 6,
    }
    score_structure = structure_scores.get(structure, 12)
    if has_sprinkler:
        score_structure = max(2, score_structure - 4)

    # 3. 용도 및 화기취급 위험도 (0 ~ 20점)
    usage_scores = {
        "전통시장/상점가": 19,
        "창고/공장시설": 17,
        "제1·2종 근린생활시설": 14,
        "단독주택": 10,
        "공동주택": 9,
        "교육연구시설": 7,
        "업무/공공시설": 6,
    }
    score_usage = usage_scores.get(usage, 10)
    if floors >= 10 and not has_sprinkler:
        score_usage = min(20, score_usage + 5)
    elif has_sprinkler:
        score_usage = max(3, score_usage - 3)

    # 4. 건물 밀집도 및 연소확대 위험 (0 ~ 15점)
    if neighbor_count_30m >= 8:
        score_spread = 15
    elif neighbor_count_30m >= 5:
        score_spread = 12
    elif neighbor_count_30m >= 3:
        score_spread = 8
    elif neighbor_count_30m >= 1:
        score_spread = 5
    else:
        score_spread = 2

    # 5. 소방서/소화전 접근 취약성 (0 ~ 15점)
    station_risk = min(8, round(dist_fire_station_m / 350.0))
    hydrant_risk = min(7, round(dist_hydrant_m / 65.0))
    score_access = min(15, station_risk + hydrant_risk)

    total = min(
        100,
        max(0, score_age + score_structure + score_usage + score_spread + score_access),
    )

    if total >= 75:
        grade = "위험(A)"
    elif total >= 60:
        grade = "경고(B)"
    elif total >= 45:
        grade = "주의(C)"
    elif total >= 30:
        grade = "보통(D)"
    else:
        grade = "안전(E)"

    # 핵심 위험 요인 산출 (기여 점수 높은 순 상위 3개)
    candidates: list[tuple[int, str]] = []
    if age >= 25:
        candidates.append((score_age, f"준공 {age}년 경과 노후화 (+{score_age}점)"))
    if structure in {"일반목구조", "경량철골조(샌드위치패널)", "벽돌조"}:
        candidates.append((score_structure, f"{structure} 구조 취약 (+{score_structure}점)"))
    if usage in {"전통시장/상점가", "창고/공장시설", "제1·2종 근린생활시설"}:
        candidates.append((score_usage, f"{usage} 화기·적재 위험 (+{score_usage}점)"))
    if neighbor_count_30m >= 4:
        candidates.append((score_spread, f"반경 30m 내 인접 건물 {neighbor_count_30m}동 밀집 (+{score_spread}점)"))
    if dist_hydrant_m > 120:
        candidates.append((score_access, f"최근접 소화전 {round(dist_hydrant_m)}m 이격 (+{score_access}점)"))
    elif dist_fire_station_m > 1200:
        candidates.append((score_access, f"소방거점 {round(dist_fire_station_m)}m 원거리 (+{score_access}점)"))
    if not has_sprinkler and (floors >= 3 or usage in {"전통시장/상점가", "창고/공장시설", "제1·2종 근린생활시설"}):
        candidates.append((8, "스프링클러 미설치"))

    candidates.sort(key=lambda item: item[0], reverse=True)
    factors = [text for _, text in candidates[:3]]
    if not factors:
        factors = ["양호한 내화·방재 여건"]

    return {
        "risk_score": total,
        "risk_grade": grade,
        "score_age": score_age,
        "score_structure": score_structure,
        "score_usage": score_usage,
        "score_spread": score_spread,
        "score_access": score_access,
        "risk_factors": factors,
    }


def compute_neighbor_counts(
    centroids: list[tuple[float, float]],
    radius_m: float = 30.0,
) -> list[int]:
    """공간 격자 인덱스를 사용해 각 건물 반경 30m 이내 인접 건물 수를 계산한다."""
    cell_deg_lat = radius_m / M_PER_DEG_LAT
    cell_deg_lon = radius_m / M_PER_DEG_LON
    grid: dict[tuple[int, int], list[int]] = {}

    for idx, (lat, lon) in enumerate(centroids):
        key = (int(lat / cell_deg_lat), int(lon / cell_deg_lon))
        grid.setdefault(key, []).append(idx)

    counts = [0] * len(centroids)
    for idx, (lat, lon) in enumerate(centroids):
        gx = int(lat / cell_deg_lat)
        gy = int(lon / cell_deg_lon)
        cnt = 0
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for other_idx in grid.get((gx + dx, gy + dy), []):
                    if other_idx == idx:
                        continue
                    o_lat, o_lon = centroids[other_idx]
                    if to_meters(lat, lon, o_lat, o_lon) <= radius_m:
                        cnt += 1
        counts[idx] = cnt
    return counts


def extract_osm_data() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[list[float]] | None]:
    """OSM API에서 건물, 소방서, 소화전, 조치원읍 행정경계를 추출한다."""
    osm_raw = fetch_json(OSM_MAP_URL, timeout=25, retries=3)
    elements = osm_raw.get("elements", [])
    nodes: dict[int, tuple[float, float]] = {
        e["id"]: (e["lat"], e["lon"]) for e in elements if e["type"] == "node"
    }

    boundary_poly = parse_jochiwon_boundary()

    # 소방서 추출 (중복 제거)
    fire_stations: list[dict[str, Any]] = []
    seen_station_names: set[str] = set()
    for e in elements:
        tags = e.get("tags", {})
        if tags.get("amenity") != "fire_station":
            continue
        name = tags.get("name:ko") or tags.get("name")
        if not name or name in seen_station_names:
            continue
        if e["type"] == "node":
            lat, lon = e["lat"], e["lon"]
        elif e["type"] == "way":
            pts = [nodes[nid] for nid in e.get("nodes", []) if nid in nodes]
            if not pts:
                continue
            lat = sum(p[0] for p in pts) / len(pts)
            lon = sum(p[1] for p in pts) / len(pts)
        else:
            continue

        seen_station_names.add(name)
        st_type = "소방서" if "소방서" in name else ("119지역대" if "지역대" in name else "특수구조대")
        street = tags.get("addr:street", "")
        hnum = tags.get("addr:housenumber", "")
        addr = f"세종특별자치시 조치원읍 {street} {hnum}".strip()
        fire_stations.append(
            {
                "name": name,
                "type": st_type,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "address": addr,
                "source": "OSM 실측",
            }
        )

    if len(fire_stations) < 3:
        existing = {s["name"] for s in fire_stations}
        for fb in FALLBACK_FIRE_STATIONS:
            if fb["name"] not in existing:
                fire_stations.append(fb)

    # 소화전 추출 (OSM 실측 + 조치원읍 주요 도로변 보강)
    hydrants: list[dict[str, Any]] = []
    for e in elements:
        tags = e.get("tags", {})
        if e["type"] == "node" and tags.get("emergency") == "fire_hydrant":
            hydrants.append(
                {
                    "name": tags.get("name") or "지상식 소화전 (OSM)",
                    "lat": round(e["lat"], 6),
                    "lon": round(e["lon"], 6),
                    "source": "OSM 실측",
                }
            )
    for h_lat, h_lon, label in SUPPLEMENTAL_HYDRANTS:
        if all(to_meters(h_lat, h_lon, ex["lat"], ex["lon"]) > 80 for ex in hydrants):
            hydrants.append(
                {
                    "name": f"소화전 ({label})",
                    "lat": h_lat,
                    "lon": h_lon,
                    "source": "주요 도로망 기준 배치",
                }
            )

    # 건물 폴리곤 추출
    buildings: list[dict[str, Any]] = []
    for e in elements:
        if e["type"] != "way":
            continue
        tags = e.get("tags", {})
        if "building" not in tags:
            continue
        pts = [nodes[nid] for nid in e.get("nodes", []) if nid in nodes]
        if len(pts) < 3:
            continue
        coords = [[round(lon, 7), round(lat, 7)] for lat, lon in pts]
        if coords[0] != coords[-1]:
            coords.append(coords[0])

        c_lat, c_lon, area_m2 = polygon_centroid_and_area(coords)
        if boundary_poly is not None and not point_in_polygon(c_lon, c_lat, boundary_poly):
            continue

        buildings.append(
            {
                "way_id": e["id"],
                "tags": tags,
                "coords": coords,
                "c_lat": c_lat,
                "c_lon": c_lon,
                "area_m2": area_m2,
            }
        )

    return buildings, fire_stations, hydrants, boundary_poly


def generate_fallback_buildings() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], None]:
    """네트워크 장애 시 조치원읍 14개 리 중심 격자 폴리곤 폴백 데이터를 생성한다."""
    rng = random.Random(20261118)
    buildings: list[dict[str, Any]] = []
    way_id = 9000000
    for ri_name, (base_lat, base_lon) in RI_CENTERS.items():
        cols, rows = (18, 14) if ri_name in OLD_DOWNTOWN_RIS else (14, 12)
        for r in range(rows):
            for c in range(cols):
                way_id += 1
                lat = base_lat + (r - rows / 2) * 0.00024 + rng.uniform(-0.00003, 0.00003)
                lon = base_lon + (c - cols / 2) * 0.00028 + rng.uniform(-0.00003, 0.00003)
                w_deg = rng.uniform(0.00010, 0.00020)
                h_deg = rng.uniform(0.00009, 0.00018)
                coords = [
                    [round(lon - w_deg / 2, 7), round(lat - h_deg / 2, 7)],
                    [round(lon + w_deg / 2, 7), round(lat - h_deg / 2, 7)],
                    [round(lon + w_deg / 2, 7), round(lat + h_deg / 2, 7)],
                    [round(lon - w_deg / 2, 7), round(lat + h_deg / 2, 7)],
                    [round(lon - w_deg / 2, 7), round(lat - h_deg / 2, 7)],
                ]
                c_lat, c_lon, area_m2 = polygon_centroid_and_area(coords)
                buildings.append(
                    {
                        "way_id": way_id,
                        "tags": {"building": "yes", "addr:subdistrict": ri_name},
                        "coords": coords,
                        "c_lat": c_lat,
                        "c_lon": c_lon,
                        "area_m2": area_m2,
                    }
                )

    hydrants = [
        {"name": f"소화전 ({label})", "lat": lat, "lon": lon, "source": "주요 도로망 기준 배치"}
        for lat, lon, label in SUPPLEMENTAL_HYDRANTS
    ]
    return buildings, FALLBACK_FIRE_STATIONS, hydrants, None


def build_datasets() -> None:
    """수집된 건물·인프라 데이터를 통합 가공해 GeoJSON 파일로 저장한다."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    data_mode = "OSM 실시간 수집"
    try:
        raw_buildings, fire_stations, hydrants, boundary_poly = extract_osm_data()
        if len(raw_buildings) < 100:
            raise RuntimeError("수집된 건물 수가 너무 적습니다.")
    except Exception as exc:
        print(f"[경고] OSM API 수집 실패로 폴백 데이터 생성기로 전환합니다: {exc}")
        raw_buildings, fire_stations, hydrants, boundary_poly = generate_fallback_buildings()
        data_mode = "오프라인 격자 폴백"

    centroids = [(b["c_lat"], b["c_lon"]) for b in raw_buildings]
    neighbor_counts = compute_neighbor_counts(centroids, radius_m=30.0)

    building_features: list[dict[str, Any]] = []
    for idx, b in enumerate(raw_buildings):
        tags = b["tags"]
        way_id = b["way_id"]
        c_lat = b["c_lat"]
        c_lon = b["c_lon"]
        area_m2 = round(b["area_m2"], 1)
        rng = deterministic_rng(way_id)

        subdistrict = assign_subdistrict(tags, c_lat, c_lon)
        address = build_address(tags, subdistrict)
        usage = infer_usage(tags, subdistrict, area_m2, rng)
        floors = infer_floors(tags, usage, area_m2, rng)
        built_year, structure, has_sprinkler = infer_built_year_and_structure(
            usage, floors, subdistrict, rng
        )
        total_area_m2 = round(area_m2 * floors, 1)

        # 건물명 결정
        raw_name = tags.get("name:ko") or tags.get("name")
        if raw_name:
            name = str(raw_name)
            has_real_name = True
        else:
            short_usage = usage.split("/")[0]
            name = f"{subdistrict} {short_usage} #{way_id % 10000:04d}"
            has_real_name = False

        # 소방서 / 소화전 최근접 거리 계산
        nearest_st = min(
            fire_stations,
            key=lambda st: to_meters(c_lat, c_lon, st["lat"], st["lon"]),
        )
        dist_station = round(
            to_meters(c_lat, c_lon, nearest_st["lat"], nearest_st["lon"]), 1
        )

        nearest_hyd = min(
            hydrants,
            key=lambda hyd: to_meters(c_lat, c_lon, hyd["lat"], hyd["lon"]),
        )
        dist_hydrant = round(
            to_meters(c_lat, c_lon, nearest_hyd["lat"], nearest_hyd["lon"]), 1
        )

        neighbor_cnt = neighbor_counts[idx]
        roof_type, static_basket = infer_roof_and_basket(
            tags=tags,
            name=name,
            usage=usage,
            structure=structure,
            built_year=built_year,
            floors=floors,
            area_m2=area_m2,
            neighbor_count_30m=neighbor_cnt,
            dist_station_m=dist_station,
            rng=rng,
        )
        risk = compute_fire_risk(
            built_year=built_year,
            structure=structure,
            usage=usage,
            floors=floors,
            has_sprinkler=has_sprinkler,
            neighbor_count_30m=neighbor_cnt,
            dist_fire_station_m=dist_station,
            dist_hydrant_m=dist_hydrant,
        )

        building_features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [b["coords"]]},
                "properties": {
                    "id": way_id,
                    "name": name,
                    "has_real_name": has_real_name,
                    "subdistrict": subdistrict,
                    "address": address,
                    "usage": usage,
                    "structure": structure,
                    "roof_type": roof_type,
                    "built_year": built_year,
                    "age": CURRENT_YEAR - built_year,
                    "floors": floors,
                    "footprint_area_m2": area_m2,
                    "total_area_m2": total_area_m2,
                    "has_sprinkler": has_sprinkler,
                    "neighbor_count_30m": neighbor_cnt,
                    "nearest_fire_station": nearest_st["name"],
                    "nearest_station_lat": nearest_st["lat"],
                    "nearest_station_lon": nearest_st["lon"],
                    "dist_fire_station_m": dist_station,
                    "nearest_hydrant_lat": nearest_hyd["lat"],
                    "nearest_hydrant_lon": nearest_hyd["lon"],
                    "dist_hydrant_m": dist_hydrant,
                    "centroid_lat": round(c_lat, 6),
                    "centroid_lon": round(c_lon, 6),
                    "osm_building_tag": tags.get("building", "yes"),
                    "static_basket": static_basket,
                    **risk,
                },
            }
        )

    buildings_geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "region": "세종특별자치시 조치원읍",
            "source_mode": data_mode,
            "building_count": len(building_features),
            "generated_year": CURRENT_YEAR,
            "note": "건물 형상·실제 건물명·일부 층수·소방서 위치는 OpenStreetMap 실측 기반이며, 건축물대장 미공개 속성(준공연도·주구조·스프링클러)은 조치원읍 구역 특성 기반 추정치가 포함되어 있습니다.",
        },
        "features": building_features,
    }

    infra_features: list[dict[str, Any]] = []
    for st in fire_stations:
        infra_features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [st["lon"], st["lat"]]},
                "properties": {
                    "kind": "fire_station",
                    "name": st["name"],
                    "station_type": st["type"],
                    "address": st["address"],
                    "source": st["source"],
                },
            }
        )
    for hyd in hydrants:
        infra_features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [hyd["lon"], hyd["lat"]]},
                "properties": {
                    "kind": "fire_hydrant",
                    "name": hyd["name"],
                    "source": hyd["source"],
                },
            }
        )
    if boundary_poly is not None:
        infra_features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [boundary_poly]},
                "properties": {
                    "kind": "boundary",
                    "name": "세종특별자치시 조치원읍 행정경계",
                },
            }
        )

    infra_geojson = {
        "type": "FeatureCollection",
        "features": infra_features,
    }

    BUILDINGS_OUT.write_text(
        json.dumps(buildings_geojson, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    INFRA_OUT.write_text(
        json.dumps(infra_geojson, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    print(
        f"생성 완료 ({data_mode}): 건물 {len(building_features)}동 -> {BUILDINGS_OUT}, "
        f"소방인프라 {len(infra_features)}건 -> {INFRA_OUT}"
    )


if __name__ == "__main__":
    build_datasets()
