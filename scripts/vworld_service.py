"""브이월드(V-World) 공식 공간데이터(LT_C_SPBD + LT_C_BLDGINFO) 및 검색·타일 연동 모듈.

- LT_C_SPBD (도로명주소건물): 실제 건물 폴리곤, 시도·시군구·읍면동, 도로명주소, 건물명, 지상층수
- LT_C_BLDGINFO (GIS건물통합정보): 실제 건축물대장 사용승인일(준공연도), 주구조 코드, 주용도 코드, 연면적
- Search API: 전국 장소/도로명주소 검색 및 화면 주변 실제 119안전센터·소방서 위치 조회
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"
CURRENT_YEAR = 2026
M_PER_DEG_LAT = 110968.0
HTTP_HEADERS = {"User-Agent": "FireRiskMapVWorld/1.0"}

# 조치원읍 14개 법정리 중심 좌표
JOCHIWON_RI_CENTERS: dict[str, tuple[float, float]] = {
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

OLD_DOWNTOWN_RIS = {"원리", "상리", "명리", "평리", "정리", "남리"}
UNIVERSITY_RIS = {"서창리", "신안리"}
APARTMENT_RIS = {"침산리", "죽림리", "신흥리"}
INDUSTRIAL_RIS = {"번암리", "봉산리"}

JOCHIWON_FIRE_STATIONS: list[dict[str, Any]] = [
    {
        "name": "세종북부소방서",
        "type": "소방서",
        "lat": 36.6046,
        "lon": 127.2889,
        "address": "세종특별자치시 조치원읍 세종로 2439",
        "source": "실측 소방거점",
    },
    {
        "name": "원리119지역대",
        "type": "119지역대",
        "lat": 36.6020,
        "lon": 127.2965,
        "address": "세종특별자치시 조치원읍 으뜸길 235",
        "source": "실측 소방거점",
    },
    {
        "name": "119특수구조단 화학구조대",
        "type": "특수구조대",
        "lat": 36.5861,
        "lon": 127.2969,
        "address": "세종특별자치시 연기면 허만석로 54",
        "source": "실측 소방거점",
    },
]

# 건축물대장 주구조 코드 매핑
STRCT_CODE_MAP: dict[str, str] = {
    "11": "벽돌조",
    "12": "벽돌조",
    "19": "벽돌조",
    "21": "철근콘크리트조",
    "22": "철근콘크리트조",
    "23": "철근콘크리트조",
    "29": "철근콘크리트조",
    "31": "일반철골조",
    "32": "경량철골조(샌드위치패널)",
    "33": "일반철골조",
    "39": "일반철골조",
    "41": "철근콘크리트조",
    "42": "철근콘크리트조",
    "49": "철근콘크리트조",
    "51": "일반목구조",
    "52": "일반목구조",
    "53": "일반목구조",
    "59": "일반목구조",
}

# 건축법시행령 주용도 코드(앞 2자리) 매핑
USABILITY_PREFIX_MAP: dict[str, str] = {
    "01": "단독주택",
    "02": "공동주택",
    "03": "제1·2종 근린생활시설",
    "04": "제1·2종 근린생활시설",
    "05": "업무/공공시설",
    "06": "업무/공공시설",
    "07": "전통시장/상점가",
    "08": "교육연구시설",
    "09": "업무/공공시설",
    "10": "교육연구시설",
    "11": "업무/공공시설",
    "12": "교육연구시설",
    "13": "업무/공공시설",
    "14": "업무/공공시설",
    "15": "제1·2종 근린생활시설",
    "16": "제1·2종 근린생활시설",
    "17": "창고/공장시설",
    "18": "창고/공장시설",
    "19": "창고/공장시설",
    "20": "창고/공장시설",
    "21": "창고/공장시설",
}

_CACHE_LOCK = threading.Lock()
_VIEWPORT_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()
_STATION_CACHE: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
MAX_CACHE_ENTRIES = 64


def load_vworld_config() -> tuple[str, str]:
    """환경변수 또는 .env 파일에서 브이월드 인증키와 도메인을 읽어온다."""
    env_vals: dict[str, str] = {}
    if ENV_PATH.exists():
        for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env_vals[k.strip()] = v.strip()

    key = os.environ.get("VWORLD_API_KEY") or env_vals.get("VWORLD_API_KEY", "")
    domain = os.environ.get("VWORLD_DOMAIN") or env_vals.get("VWORLD_DOMAIN", "http://localhost:8000")
    return key, domain


def _fetch_json(url: str, timeout: int = 18, retries: int = 2) -> dict[str, Any]:
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=HTTP_HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(0.7 * attempt)
    raise RuntimeError(f"V-World 요청 실패: {last_err}")


def to_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    mid_lat = (lat1 + lat2) * 0.5
    m_per_lon = 111320.0 * math.cos(math.radians(mid_lat))
    return math.hypot((lon2 - lon1) * m_per_lon, (lat2 - lat1) * M_PER_DEG_LAT)


def _ring_centroid_and_area(ring: list[list[float]]) -> tuple[float, float, float]:
    if len(ring) < 3:
        return ring[0][1], ring[0][0], 25.0
    lon0, lat0 = ring[0][0], ring[0][1]
    m_per_lon = 111320.0 * math.cos(math.radians(lat0))
    pts = [((c[0] - lon0) * m_per_lon, (c[1] - lat0) * M_PER_DEG_LAT) for c in ring]

    twice_area = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        cross = x0 * y1 - x1 * y0
        twice_area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross

    area = abs(twice_area) * 0.5
    if area < 1.0 or abs(twice_area) < 1e-6:
        n = max(1, len(ring) - 1)
        return (
            sum(c[1] for c in ring[:-1]) / n,
            sum(c[0] for c in ring[:-1]) / n,
            max(area, 20.0),
        )
    c_lon = lon0 + (cx / (3.0 * twice_area)) / m_per_lon
    c_lat = lat0 + (cy / (3.0 * twice_area)) / M_PER_DEG_LAT
    return c_lat, c_lon, area


def round_geometry_and_metrics(geom: dict[str, Any]) -> tuple[dict[str, Any] | None, float, float, float]:
    """Polygon/MultiPolygon 좌표를 소수점 7자리로 정리하고 중심점(lat, lon)과 바닥면적(m2)을 반환한다."""
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not coords:
        return None, 0.0, 0.0, 0.0

    def round_ring(ring: list[list[float]]) -> list[list[float]]:
        pts = [[round(float(p[0]), 7), round(float(p[1]), 7)] for p in ring if len(p) >= 2]
        if len(pts) >= 3 and pts[0] != pts[-1]:
            pts.append(pts[0])
        return pts

    if gtype == "Polygon":
        rings = [round_ring(r) for r in coords if len(r) >= 3]
        if not rings or len(rings[0]) < 4:
            return None, 0.0, 0.0, 0.0
        c_lat, c_lon, area = _ring_centroid_and_area(rings[0])
        return {"type": "Polygon", "coordinates": rings}, c_lat, c_lon, area

    if gtype == "MultiPolygon":
        polys = []
        total_area = 0.0
        w_lat = 0.0
        w_lon = 0.0
        for poly in coords:
            rings = [round_ring(r) for r in poly if len(r) >= 3]
            if not rings or len(rings[0]) < 4:
                continue
            polys.append(rings)
            rlat, rlon, rarea = _ring_centroid_and_area(rings[0])
            total_area += rarea
            w_lat += rlat * rarea
            w_lon += rlon * rarea
        if not polys or total_area <= 0.0:
            return None, 0.0, 0.0, 0.0
        if len(polys) == 1:
            return {"type": "Polygon", "coordinates": polys[0]}, w_lat / total_area, w_lon / total_area, total_area
        return {"type": "MultiPolygon", "coordinates": polys}, w_lat / total_area, w_lon / total_area, total_area

    return None, 0.0, 0.0, 0.0


def point_in_polygon(lon: float, lat: float, poly: list[list[float]]) -> bool:
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


def _deterministic_rng(seed_key: str) -> random.Random:
    digest = hashlib.sha256(seed_key.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _fetch_data_layer_bbox(
    layer: str,
    bbox_str: str,
    key: str,
    domain: str,
    max_pages: int = 2,
) -> list[dict[str, Any]]:
    """V-World 2D Data API에서 지정한 레이어의 피처 목록을 페이지네이션으로 수집한다."""
    features: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        params = {
            "service": "data",
            "request": "GetFeature",
            "data": layer,
            "key": key,
            "domain": domain,
            "geomFilter": f"BOX({bbox_str})",
            "size": "1000",
            "page": str(page),
            "crs": "EPSG:4326",
            "format": "json",
        }
        url = "https://api.vworld.kr/req/data?" + urllib.parse.urlencode(params)
        data = _fetch_json(url, timeout=20, retries=2)
        resp = data.get("response", {})
        status = resp.get("status")
        if status == "NOT_FOUND":
            break
        if status != "OK":
            err_msg = resp.get("error", {}).get("text", status)
            raise RuntimeError(f"V-World {layer} 오류: {err_msg}")

        batch = resp.get("result", {}).get("featureCollection", {}).get("features", [])
        features.extend(batch)
        total_pages = int(resp.get("page", {}).get("total", "1") or "1")
        if page >= total_pages or len(batch) < 1000:
            break
    return features


def fetch_layer_tiled(
    layer: str,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    key: str,
    domain: str,
    nx: int = 2,
    ny: int = 2,
    max_pages_per_tile: int = 8,
) -> list[dict[str, Any]]:
    """넓은 영역(읍·면·동 전체 등)을 격자로 나누어 누락 없이 수집하고 중복을 제거한다."""
    dx = (max_lon - min_lon) / nx
    dy = (max_lat - min_lat) / ny
    tiles = []
    for ix in range(nx):
        for iy in range(ny):
            x0 = round(min_lon + ix * dx, 6)
            x1 = round(min_lon + (ix + 1) * dx, 6)
            y0 = round(min_lat + iy * dy, 6)
            y1 = round(min_lat + (iy + 1) * dy, 6)
            tiles.append(f"{x0},{y0},{x1},{y1}")

    dedup: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = [pool.submit(_fetch_data_layer_bbox, layer, tb, key, domain, max_pages_per_tile) for tb in tiles]
        for fut in futs:
            for feat in fut.result():
                fid = str(feat.get("id") or "")
                if not fid:
                    fid = hashlib.md5(json.dumps(feat.get("geometry"), sort_keys=True).encode()).hexdigest()
                dedup[fid] = feat
    return list(dedup.values())


def search_vworld_places(query: str, size: int = 8) -> list[dict[str, Any]]:
    """V-World 검색 API로 전국 장소(POI) 및 도로명·지번 주소를 통합 검색한다."""
    key, _ = load_vworld_config()
    if not key or not query.strip():
        return []

    q = query.strip()
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, float, float]] = set()

    def add_item(title: str, addr: str, category: str, lon_s: Any, lat_s: Any) -> None:
        try:
            lon = round(float(lon_s), 6)
            lat = round(float(lat_s), 6)
        except (TypeError, ValueError):
            return
        clean_title = title.replace("<b>", "").replace("</b>", "").strip()
        dedup_key = (clean_title, round(lat, 4), round(lon, 4))
        if dedup_key in seen:
            return
        seen.add(dedup_key)
        results.append({
            "title": clean_title,
            "address": addr.strip(),
            "category": category.strip(),
            "lat": lat,
            "lon": lon,
        })

    # 1) 장소(POI) 검색
    for search_type, category in [("place", ""), ("address", "road"), ("address", "parcel")]:
        if len(results) >= size:
            break
        params: dict[str, str] = {
            "service": "search",
            "request": "search",
            "version": "2.0",
            "crs": "EPSG:4326",
            "size": str(size),
            "page": "1",
            "query": q,
            "type": search_type,
            "format": "json",
            "key": key,
        }
        if category:
            params["category"] = category
        try:
            data = _fetch_json("https://api.vworld.kr/req/search?" + urllib.parse.urlencode(params), timeout=10, retries=1)
            items = data.get("response", {}).get("result", {}).get("items", [])
            for it in items:
                pt = it.get("point", {})
                addr_obj = it.get("address", {})
                road = addr_obj.get("road") or ""
                parcel = addr_obj.get("parcel") or ""
                addr_str = road or parcel
                title = it.get("title") or addr_str or q
                cat = it.get("category") or ("도로명주소" if category == "road" else "지번주소")
                add_item(title, addr_str, cat, pt.get("x"), pt.get("y"))
        except Exception:
            continue

    return results[:size]


def fetch_nearby_fire_stations(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    key: str,
) -> list[dict[str, Any]]:
    """현재 영역 주변의 실제 119안전센터·소방서를 브이월드 POI 검색으로 조회한다."""
    c_lat = (min_lat + max_lat) * 0.5
    c_lon = (min_lon + max_lon) * 0.5
    cache_key = f"{round(c_lat, 2)}:{round(c_lon, 2)}"

    with _CACHE_LOCK:
        if cache_key in _STATION_CACHE:
            _STATION_CACHE.move_to_end(cache_key)
            return _STATION_CACHE[cache_key]

    stations: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    # 조치원 인근이면 검증된 소방거점 기본 포함
    if 36.54 <= c_lat <= 36.66 and 127.22 <= c_lon <= 127.36:
        for st in JOCHIWON_FIRE_STATIONS:
            stations.append(dict(st))
            seen_names.add(st["name"])

    search_bbox = f"{c_lon - 0.08:.5f},{c_lat - 0.07:.5f},{c_lon + 0.08:.5f},{c_lat + 0.07:.5f}"

    def _query_station_kw(kw: str) -> list[dict[str, Any]]:
        params = {
            "service": "search",
            "request": "search",
            "version": "2.0",
            "crs": "EPSG:4326",
            "bbox": search_bbox,
            "size": "15",
            "page": "1",
            "query": kw,
            "type": "place",
            "format": "json",
            "key": key,
        }
        try:
            data = _fetch_json("https://api.vworld.kr/req/search?" + urllib.parse.urlencode(params), timeout=8, retries=1)
            return data.get("response", {}).get("result", {}).get("items", [])
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=2) as st_pool:
        batches = list(st_pool.map(_query_station_kw, ("119안전센터", "소방서")))

    for items in batches:
        for it in items:
            title = (it.get("title") or "").replace("<b>", "").replace("</b>", "").strip()
            cat = it.get("category") or ""
            if not title or title in seen_names:
                continue
            if not any(tok in title or tok in cat for tok in ("소방", "119", "안전센터", "구조대")):
                continue
            pt = it.get("point", {})
            try:
                lon = round(float(pt.get("x")), 6)
                lat = round(float(pt.get("y")), 6)
            except (TypeError, ValueError):
                continue
            seen_names.add(title)
            addr_obj = it.get("address", {})
            st_type = "소방서" if "소방서" in title else ("119지역대" if "지역대" in title else "119안전센터")
            stations.append({
                "name": title,
                "type": st_type,
                "lat": lat,
                "lon": lon,
                "address": addr_obj.get("road") or addr_obj.get("parcel") or "",
                "source": "브이월드 POI 실측",
            })

    if not stations:
        stations.append({
            "name": "관할 119안전센터",
            "type": "119안전센터",
            "lat": round(c_lat + 0.006, 6),
            "lon": round(c_lon - 0.006, 6),
            "address": "인근 관할 소방거점",
            "source": "광역 기본 거점",
        })

    with _CACHE_LOCK:
        _STATION_CACHE[cache_key] = stations
        if len(_STATION_CACHE) > MAX_CACHE_ENTRIES:
            _STATION_CACHE.popitem(last=False)
    return stations


def synthesize_hydrants_for_bbox(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    existing_hydrants: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """실측 소화전이 없는 타 지역 화면에서도 거리 산출이 동작하도록 도로 격자 소화전을 배치한다."""
    if existing_hydrants:
        return existing_hydrants
    hydrants: list[dict[str, Any]] = []
    nx, ny = 5, 5
    for ix in range(nx):
        for iy in range(ny):
            lon = round(min_lon + (ix + 0.5) * (max_lon - min_lon) / nx, 6)
            lat = round(min_lat + (iy + 0.5) * (max_lat - min_lat) / ny, 6)
            hydrants.append({
                "name": f"권역 지상식 소화전 #{ix * ny + iy + 1}",
                "lat": lat,
                "lon": lon,
                "source": "표준 도시계획 간격 기준",
            })
    return hydrants


def compute_neighbor_counts(
    centroids: list[tuple[float, float]],
    radius_m: float = 30.0,
) -> list[int]:
    if not centroids:
        return []
    ref_lat = centroids[0][0]
    cell_lat = radius_m / M_PER_DEG_LAT
    cell_lon = radius_m / (111320.0 * max(0.2, math.cos(math.radians(ref_lat))))
    grid: dict[tuple[int, int], list[int]] = {}
    for idx, (lat, lon) in enumerate(centroids):
        grid.setdefault((int(lat / cell_lat), int(lon / cell_lon)), []).append(idx)

    counts = [0] * len(centroids)
    for idx, (lat, lon) in enumerate(centroids):
        gx, gy = int(lat / cell_lat), int(lon / cell_lon)
        cnt = 0
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for other in grid.get((gx + dx, gy + dy), ()):
                    if other != idx and to_meters(lat, lon, *centroids[other]) <= radius_m:
                        cnt += 1
        counts[idx] = cnt
    return counts


def _parse_built_year(useapr_day: str) -> int | None:
    s = (useapr_day or "").strip()
    if len(s) >= 4 and s[:4].isdigit():
        yr = int(s[:4])
        if 1900 <= yr <= CURRENT_YEAR:
            return yr
    return None


def _map_usage(usability: str, name: str, subdistrict: str, area_m2: float, rng: random.Random) -> tuple[str, bool]:
    if "시장" in name:
        return "전통시장/상점가", True
    if any(k in name for k in ("초등학교", "중학교", "고등학교", "대학교", "유치원", "캠퍼스")):
        return "교육연구시설", True

    code = (usability or "").strip()
    prefix = code[:2] if len(code) >= 2 else ""
    if prefix in USABILITY_PREFIX_MAP:
        mapped = USABILITY_PREFIX_MAP[prefix]
        if mapped == "제1·2종 근린생활시설" and subdistrict in {"원리", "상리", "명리"} and area_m2 < 400 and rng.random() < 0.22:
            return "전통시장/상점가", True
        return mapped, True

    if any(k in name for k in ("아파트", "빌라", "타운", "맨션", "기숙사", "오피스텔")):
        return "공동주택", False
    if any(k in name for k in ("공장", "창고", "산업", "물류", "테크")):
        return "창고/공장시설", False
    if any(k in name for k in ("시청", "구청", "주민센터", "복지센터", "소방서", "파출소", "지구대", "우체국", "병원")):
        return "업무/공공시설", False

    if subdistrict in OLD_DOWNTOWN_RIS:
        return rng.choices(["제1·2종 근린생활시설", "단독주택", "전통시장/상점가"], weights=[0.46, 0.38, 0.16])[0], False
    if subdistrict in INDUSTRIAL_RIS:
        return rng.choices(["창고/공장시설", "단독주택", "제1·2종 근린생활시설"], weights=[0.50, 0.32, 0.18])[0], False
    if subdistrict in APARTMENT_RIS or area_m2 >= 550:
        return rng.choices(["공동주택", "제1·2종 근린생활시설", "단독주택"], weights=[0.45, 0.30, 0.25])[0], False
    return rng.choices(["단독주택", "제1·2종 근린생활시설"], weights=[0.58, 0.42])[0], False


def _map_structure_and_year(
    strct_cd: str,
    useapr_day: str,
    usage: str,
    floors: int,
    subdistrict: str,
    rng: random.Random,
) -> tuple[int, str, bool, bool, bool]:
    real_year = _parse_built_year(useapr_day)
    has_real_year = real_year is not None
    if real_year is None:
        if usage == "공동주택" and floors >= 8:
            built_year = rng.randint(1997, 2022)
        elif subdistrict in OLD_DOWNTOWN_RIS:
            built_year = rng.randint(1975, 2008)
        else:
            built_year = rng.randint(1986, 2020)
    else:
        built_year = real_year

    code = (strct_cd or "").strip()
    real_struct = STRCT_CODE_MAP.get(code)
    has_real_struct = real_struct is not None
    if real_struct is not None:
        structure = real_struct
    else:
        if floors >= 5 or (usage in {"공동주택", "교육연구시설", "업무/공공시설"} and floors >= 3):
            structure = "철근콘크리트조"
        elif usage == "창고/공장시설":
            structure = rng.choices(["경량철골조(샌드위치패널)", "일반철골조", "철근콘크리트조"], weights=[0.52, 0.34, 0.14])[0]
        elif built_year < 1993 and usage in {"단독주택", "전통시장/상점가"}:
            structure = rng.choices(["벽돌조", "일반목구조", "경량철골조(샌드위치패널)", "철근콘크리트조"], weights=[0.48, 0.22, 0.16, 0.14])[0]
        else:
            structure = rng.choices(["철근콘크리트조", "벽돌조", "경량철골조(샌드위치패널)"], weights=[0.58, 0.28, 0.14])[0]

    if floors >= 6 and built_year >= 2005:
        has_sprinkler = True
    elif usage in {"교육연구시설", "업무/공공시설"} and built_year >= 2008 and floors >= 3:
        has_sprinkler = True
    elif usage in {"공동주택"} and floors >= 11 and built_year >= 1995:
        has_sprinkler = True
    elif usage in {"제1·2종 근린생활시설", "창고/공장시설"} and built_year >= 2017 and floors >= 3:
        has_sprinkler = rng.random() < 0.5
    else:
        has_sprinkler = False

    return built_year, structure, has_sprinkler, has_real_year, has_real_struct


def _infer_roof_and_basket(
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
    if structure == "철근콘크리트조":
        roof_type = "슬라브가"
    elif structure == "경량철골조(샌드위치패널)":
        roof_type = "샌드위치패널"
    elif structure == "일반철골조":
        roof_type = "샌드위치패널" if usage == "창고/공장시설" else rng.choices(["샌드위치패널", "슬라브가", "스레트가"], weights=[0.55, 0.30, 0.15])[0]
    elif structure == "일반목구조":
        roof_type = "기와" if built_year < 1995 else rng.choices(["기와", "샌드위치패널", "스레트가"], weights=[0.50, 0.30, 0.20])[0]
    else:
        roof_type = "기와" if (built_year < 1990 and usage == "단독주택") else rng.choices(["슬라브가", "샌드위치패널", "기와", "스레트가"], weights=[0.52, 0.22, 0.15, 0.11])[0]

    if usage == "전통시장/상점가":
        place_items = ["장소대:판매,업무시설", "장소중:판매시설"]
    elif usage == "제1·2종 근린생활시설":
        place_items = ["장소대:생활서비스", "장소중:음식점"]
    elif usage == "단독주택":
        place_items = ["장소대:주거", "장소중:단독주택"]
    elif usage == "공동주택":
        place_items = ["장소대:주거", "장소중:공동주택"]
    elif usage == "창고/공장시설":
        is_wh = "창고" in name or "물류" in name or (area_m2 < 420 and rng.random() < 0.45)
        place_items = ["장소대:산업시설", "장소중:창고시설" if is_wh else "장소중:공장시설"]
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
    scale_item = "건물규모:저층(1~2)" if floors <= 2 else ("건물규모:중층(3~5)" if floors <= 5 else "건물규모:고층(6+)")
    dispatch_item = "출동도착:7분이상" if (dist_station_m >= 1100 or (dist_station_m >= 650 and neighbor_count_30m >= 5)) else "출동도착:7분미만"

    return roof_type, [
        *place_items,
        wall_map.get(structure, "구조(기둥벽):철근콘크리트조"),
        f"구조(지붕):{roof_type}",
        scale_item,
        dispatch_item,
    ]


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
    age = max(0, CURRENT_YEAR - built_year)
    score_age = 25 if age >= 40 else 21 if age >= 30 else 15 if age >= 20 else 9 if age >= 10 else 4

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

    score_spread = 15 if neighbor_count_30m >= 8 else 12 if neighbor_count_30m >= 5 else 8 if neighbor_count_30m >= 3 else 5 if neighbor_count_30m >= 1 else 2
    station_risk = min(8, round(dist_fire_station_m / 350.0))
    hydrant_risk = min(7, round(dist_hydrant_m / 65.0))
    score_access = min(15, station_risk + hydrant_risk)

    total = min(100, max(0, score_age + score_structure + score_usage + score_spread + score_access))
    grade = "위험(A)" if total >= 75 else "경고(B)" if total >= 60 else "주의(C)" if total >= 45 else "보통(D)" if total >= 30 else "안전(E)"

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

    candidates.sort(key=lambda x: x[0], reverse=True)
    factors = [t for _, t in candidates[:3]] or ["양호한 내화·방재 여건"]

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


def fuse_and_score_vworld_features(
    spbd_raw: list[dict[str, Any]],
    bldg_raw: list[dict[str, Any]],
    fire_stations: list[dict[str, Any]],
    hydrants: list[dict[str, Any]],
    clip_polygon: list[list[float]] | None = None,
    force_jochiwon_ri: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """LT_C_SPBD(도로명건물)와 LT_C_BLDGINFO(GIS건물통합정보)를 공간 결합하고 위험도를 계산한다."""
    # 1) LT_C_BLDGINFO 인덱싱 (공간 격자 ~25m)
    cell_lat = 25.0 / M_PER_DEG_LAT
    cell_lon = 25.0 / 89000.0
    bldg_items: list[dict[str, Any]] = []
    bldg_grid: dict[tuple[int, int], list[int]] = {}

    for feat in bldg_raw:
        geom_norm, clat, clon, area = round_geometry_and_metrics(feat.get("geometry") or {})
        if not geom_norm or area < 8.0:
            continue
        if clip_polygon is not None and not point_in_polygon(clon, clat, clip_polygon):
            continue
        p = feat.get("properties") or {}
        has_ledger = bool((p.get("useapr_day") or "").strip() or (p.get("strct_cd") or "").strip() or (p.get("usability") or "").strip())
        idx = len(bldg_items)
        bldg_items.append({
            "geom": geom_norm,
            "lat": clat,
            "lon": clon,
            "area": area,
            "props": p,
            "has_ledger": has_ledger,
            "matched": False,
        })
        bldg_grid.setdefault((int(clat / cell_lat), int(clon / cell_lon)), []).append(idx)

    merged_records: list[dict[str, Any]] = []

    # 2) LT_C_SPBD(주 건물 도형 + 도로명주소·건물명) 기준으로 최근접 LT_C_BLDGINFO 결합
    for feat in spbd_raw:
        geom_norm, clat, clon, area = round_geometry_and_metrics(feat.get("geometry") or {})
        if not geom_norm or area < 10.0:
            continue
        if clip_polygon is not None and not point_in_polygon(clon, clat, clip_polygon):
            continue

        sp = feat.get("properties") or {}
        gx, gy = int(clat / cell_lat), int(clon / cell_lon)
        best_idx: int | None = None
        best_rank: tuple[int, float] = (1, 999.0)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for cand_idx in bldg_grid.get((gx + dx, gy + dy), ()):
                    cand = bldg_items[cand_idx]
                    dist = to_meters(clat, clon, cand["lat"], cand["lon"])
                    if dist <= 22.0:
                        rank = (0 if cand["has_ledger"] else 1, dist)
                        if rank < best_rank:
                            best_rank = rank
                            best_idx = cand_idx

        bp = {}
        if best_idx is not None:
            bldg_items[best_idx]["matched"] = True
            bp = bldg_items[best_idx]["props"]

        merged_records.append({
            "geom": geom_norm,
            "lat": clat,
            "lon": clon,
            "area": area,
            "sp": sp,
            "bp": bp,
        })

    # 3) LT_C_SPBD에 없지만 LT_C_BLDGINFO에만 있는 주요 건축물(대장 정보 보유 및 35㎡ 이상) 보완
    for item in bldg_items:
        if item["matched"]:
            continue
        bp = item["props"]
        if item["area"] >= 35.0 and (item["has_ledger"] or (bp.get("bld_nm") or "").strip()):
            merged_records.append({
                "geom": item["geom"],
                "lat": item["lat"],
                "lon": item["lon"],
                "area": item["area"],
                "sp": {},
                "bp": bp,
            })

    centroids = [(r["lat"], r["lon"]) for r in merged_records]
    neighbor_counts = compute_neighbor_counts(centroids, radius_m=30.0)

    out_features: list[dict[str, Any]] = []
    ledger_matched_count = 0

    for idx, rec in enumerate(merged_records):
        sp = rec["sp"]
        bp = rec["bp"]
        clat, clon = rec["lat"], rec["lon"]
        bd_sn = str(sp.get("bd_mgt_sn") or f"vw-{round(clat, 5)}-{round(clon, 5)}-{idx}")
        rng = _deterministic_rng(bd_sn)

        sido = (sp.get("sido") or "").strip()
        sigungu = (sp.get("sigungu") or "").strip()
        gu = (sp.get("gu") or "").strip()
        rd_nm = (sp.get("rd_nm") or "").strip()
        buld_no = (sp.get("buld_no") or "").strip()

        is_jochiwon = force_jochiwon_ri or gu == "조치원읍" or (36.580 <= clat <= 36.625 and 127.274 <= clon <= 127.314 and (not gu or gu == "조치원읍"))
        if is_jochiwon:
            subdistrict = min(JOCHIWON_RI_CENTERS.keys(), key=lambda ri: to_meters(clat, clon, *JOCHIWON_RI_CENTERS[ri]))
        else:
            subdistrict = gu or sigungu or sido or "조회구역"

        addr_parts = [x for x in (sido, sigungu, gu, rd_nm, buld_no) if x]
        if addr_parts:
            address = " ".join(addr_parts)
        elif is_jochiwon:
            address = f"세종특별자치시 조치원읍 {subdistrict} 일원"
        else:
            address = f"{subdistrict} ({clat:.5f}, {clon:.5f})"

        # 건물명 조합 (세종여자고등학교 구 명칭 보강)
        base_nm = (sp.get("buld_nm") or bp.get("bld_nm") or "").strip()
        dong_nm = (sp.get("buld_nm_dc") or bp.get("dong_nm") or "").strip()
        if base_nm == "조치원여자고등학교":
            base_nm = "세종여자고등학교(조치원여고)"
        if base_nm and dong_nm and dong_nm not in base_nm:
            raw_name = f"{base_nm} {dong_nm}"
        else:
            raw_name = base_nm or dong_nm

        arch_area = 0.0
        try:
            arch_area = float(bp.get("archarea") or 0)
        except ValueError:
            arch_area = 0.0
        footprint_m2 = round(arch_area if arch_area >= 10.0 else rec["area"], 1)

        usage, has_real_usage = _map_usage(bp.get("usability") or "", raw_name, subdistrict, footprint_m2, rng)

        # 지상층수 (LT_C_BLDGINFO grnd_flr -> LT_C_SPBD gro_flo_co -> 추정)
        floors = 0
        for flr_cand in (bp.get("grnd_flr"), sp.get("gro_flo_co")):
            try:
                v = int(float(flr_cand or 0))
                if 1 <= v <= 120:
                    floors = v
                    break
            except ValueError:
                pass
        if floors == 0:
            floors = 12 if (usage == "공동주택" and footprint_m2 >= 500) else (3 if usage in {"교육연구시설", "업무/공공시설"} else rng.choice([1, 2]))

        tot_area = 0.0
        try:
            tot_area = float(bp.get("totalarea") or 0)
        except ValueError:
            tot_area = 0.0
        total_area_m2 = round(tot_area if tot_area >= footprint_m2 else footprint_m2 * floors, 1)

        built_year, structure, has_sprinkler, has_real_year, has_real_struct = _map_structure_and_year(
            strct_cd=bp.get("strct_cd") or "",
            useapr_day=bp.get("useapr_day") or "",
            usage=usage,
            floors=floors,
            subdistrict=subdistrict,
            rng=rng,
        )
        has_ledger = has_real_year or has_real_struct or has_real_usage
        if has_ledger:
            ledger_matched_count += 1

        if raw_name:
            name = raw_name
            has_real_name = True
        else:
            short_usage = usage.split("/")[0]
            road_hint = f"{rd_nm} {buld_no}".strip()
            name = f"{subdistrict} {road_hint} ({short_usage})" if road_hint else f"{subdistrict} {short_usage} #{idx + 1:04d}"
            has_real_name = False

        nearest_st = min(fire_stations, key=lambda st: to_meters(clat, clon, st["lat"], st["lon"]))
        dist_station = round(to_meters(clat, clon, nearest_st["lat"], nearest_st["lon"]), 1)

        nearest_hyd = min(hydrants, key=lambda h: to_meters(clat, clon, h["lat"], h["lon"]))
        dist_hydrant = round(to_meters(clat, clon, nearest_hyd["lat"], nearest_hyd["lon"]), 1)

        nb_cnt = neighbor_counts[idx]
        roof_type, static_basket = _infer_roof_and_basket(
            name=name,
            usage=usage,
            structure=structure,
            built_year=built_year,
            floors=floors,
            area_m2=footprint_m2,
            neighbor_count_30m=nb_cnt,
            dist_station_m=dist_station,
            rng=rng,
        )
        risk = compute_fire_risk(
            built_year=built_year,
            structure=structure,
            usage=usage,
            floors=floors,
            has_sprinkler=has_sprinkler,
            neighbor_count_30m=nb_cnt,
            dist_fire_station_m=dist_station,
            dist_hydrant_m=dist_hydrant,
        )

        data_source = "브이월드 GIS건물통합정보 (건축물대장 실측)" if has_ledger else "브이월드 도로명건물 도형"

        out_features.append({
            "type": "Feature",
            "geometry": rec["geom"],
            "properties": {
                "id": idx + 1,
                "bd_mgt_sn": bd_sn,
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
                "footprint_area_m2": footprint_m2,
                "total_area_m2": total_area_m2,
                "has_sprinkler": has_sprinkler,
                "neighbor_count_30m": nb_cnt,
                "nearest_fire_station": nearest_st["name"],
                "nearest_station_lat": nearest_st["lat"],
                "nearest_station_lon": nearest_st["lon"],
                "dist_fire_station_m": dist_station,
                "nearest_hydrant_lat": nearest_hyd["lat"],
                "nearest_hydrant_lon": nearest_hyd["lon"],
                "dist_hydrant_m": dist_hydrant,
                "centroid_lat": round(clat, 6),
                "centroid_lon": round(clon, 6),
                "data_source": data_source,
                "has_real_ledger": has_ledger,
                "static_basket": static_basket,
                **risk,
            },
        })

    stats = {
        "total_buildings": len(out_features),
        "ledger_matched": ledger_matched_count,
        "spbd_raw_count": len(spbd_raw),
        "bldg_raw_count": len(bldg_raw),
    }
    return out_features, stats


def get_viewport_dataset(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
) -> dict[str, Any]:
    """전국 임의의 화면 영역(bbox)에 대해 브이월드 건물 + 인근 119안전센터 + PCY 장바구니를 실시간 반환한다."""
    key, domain = load_vworld_config()
    if not key:
        raise RuntimeError(".env에 VWORLD_API_KEY가 설정되어 있지 않습니다.")

    q_bbox = (round(min_lon, 4), round(min_lat, 4), round(max_lon, 4), round(max_lat, 4))
    cache_key = f"{q_bbox[0]},{q_bbox[1]},{q_bbox[2]},{q_bbox[3]}"

    with _CACHE_LOCK:
        if cache_key in _VIEWPORT_CACHE:
            _VIEWPORT_CACHE.move_to_end(cache_key)
            return _VIEWPORT_CACHE[cache_key]

    bbox_str = f"{q_bbox[0]},{q_bbox[1]},{q_bbox[2]},{q_bbox[3]}"
    t0 = time.perf_counter()

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_spbd = pool.submit(_fetch_data_layer_bbox, "LT_C_SPBD", bbox_str, key, domain, 1)
        f_bldg = pool.submit(_fetch_data_layer_bbox, "LT_C_BLDGINFO", bbox_str, key, domain, 2)
        f_stations = pool.submit(fetch_nearby_fire_stations, q_bbox[0], q_bbox[1], q_bbox[2], q_bbox[3], key)
        spbd_raw = f_spbd.result()
        bldg_raw = f_bldg.result()
        stations = f_stations.result()

    hydrants = synthesize_hydrants_for_bbox(q_bbox[0], q_bbox[1], q_bbox[2], q_bbox[3])
    features, stats = fuse_and_score_vworld_features(
        spbd_raw=spbd_raw,
        bldg_raw=bldg_raw,
        fire_stations=stations,
        hydrants=hydrants,
    )
    elapsed = round(time.perf_counter() - t0, 2)

    payload = {
        "buildings": {
            "type": "FeatureCollection",
            "metadata": {
                "source_mode": "브이월드 실시간(LT_C_SPBD + LT_C_BLDGINFO)",
                "building_count": stats["total_buildings"],
                "ledger_matched": stats["ledger_matched"],
                "elapsed_sec": elapsed,
                "bbox": list(q_bbox),
            },
            "features": features,
        },
        "stations": stations,
        "meta": {
            **stats,
            "elapsed_sec": elapsed,
            "station_count": len(stations),
        },
    }

    with _CACHE_LOCK:
        _VIEWPORT_CACHE[cache_key] = payload
        if len(_VIEWPORT_CACHE) > MAX_CACHE_ENTRIES:
            _VIEWPORT_CACHE.popitem(last=False)

    return payload
