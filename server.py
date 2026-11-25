"""조치원읍 및 전국 브이월드(V-World) 연동 건물 화재 위험도 평가 지도 웹 서버.

- 정적 HTML/CSS/JS 및 GeoJSON 파일을 UTF-8과 CORS 헤더로 서빙
- 서버 측 .env의 VWORLD_API_KEY를 안전하게 프록시하여 전국 건물(GIS건물통합정보), 장소/주소 검색, 공식 배경지도 타일 제공
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import vworld_service  # noqa: E402

ALLOWED_WMTS_LAYERS = {
    "Base": "png",
    "white": "png",
    "midnight": "png",
    "Hybrid": "png",
    "Satellite": "jpeg",
}


class JochiwonRequestHandler(SimpleHTTPRequestHandler):
    """GeoJSON MIME 타입, UTF-8 인코딩 및 브이월드 백엔드 프록시 엔드포인트를 지원하는 핸들러."""

    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".geojson": "application/geo+json; charset=utf-8",
    }

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if not getattr(self, "_custom_cache", False):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/api/vworld/status":
            key, domain = vworld_service.load_vworld_config()
            self._send_json({"configured": bool(key), "domain": domain})
            return

        if path == "/api/vworld/search":
            q = (qs.get("q", [""])[0] or "").strip()
            if not q:
                self._send_json({"items": []})
                return
            try:
                items = vworld_service.search_vworld_places(q, size=8)
                self._send_json({"items": items})
            except Exception as exc:
                self._send_json({"error": str(exc), "items": []}, status=502)
            return

        if path == "/api/vworld/buildings":
            raw_bbox = (qs.get("bbox", [""])[0] or "").strip()
            try:
                parts = [float(x) for x in raw_bbox.split(",")]
                if len(parts) != 4:
                    raise ValueError("bbox는 minLon,minLat,maxLon,maxLat 형식이어야 합니다.")
                min_lon, min_lat, max_lon, max_lat = parts
                if max_lon <= min_lon or max_lat <= min_lat:
                    raise ValueError("유효하지 않은 bbox 범위입니다.")
                if (max_lon - min_lon) > 0.065 or (max_lat - min_lat) > 0.055:
                    self._send_json(
                        {"error": "조회 영역이 너무 넓습니다. 지도를 조금 더 확대(줌 16 이상)해 주세요."},
                        status=400,
                    )
                    return
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return

            try:
                result = vworld_service.get_viewport_dataset(min_lon, min_lat, max_lon, max_lat)
                self._send_json(result)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=502)
            return

        if path.startswith("/api/vworld/wmts/"):
            # /api/vworld/wmts/{layer}/{z}/{y}/{x}
            segs = path.strip("/").split("/")
            if len(segs) == 7:
                _, _, _, layer, z_s, y_s, x_s = segs
                x_clean = x_s.split(".")[0]
                if layer in ALLOWED_WMTS_LAYERS and z_s.isdigit() and y_s.isdigit() and x_clean.isdigit():
                    key, _ = vworld_service.load_vworld_config()
                    if not key:
                        self.send_error(503, "VWORLD_API_KEY not configured")
                        return
                    ext = ALLOWED_WMTS_LAYERS[layer]
                    tile_url = f"https://api.vworld.kr/req/wmts/1.0.0/{key}/{layer}/{z_s}/{y_s}/{x_clean}.{ext}"
                    try:
                        req = urllib.request.Request(tile_url, headers={"User-Agent": "FireRiskMapVWorld/1.0"})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            data = resp.read()
                            ctype = resp.headers.get("Content-Type") or f"image/{ext}"
                        self._custom_cache = True
                        self.send_response(200)
                        self.send_header("Content-Type", ctype)
                        self.send_header("Content-Length", str(len(data)))
                        self.send_header("Cache-Control", "public, max-age=86400")
                        self.end_headers()
                        self.wfile.write(data)
                        return
                    except urllib.error.HTTPError as exc:
                        self.send_error(exc.code, "Tile upstream error")
                        return
                    except Exception:
                        self.send_error(502, "Tile fetch failed")
                        return

        super().do_GET()


def main() -> None:
    parser = argparse.ArgumentParser(description="조치원읍 및 전국 브이월드 화재 위험도 지도 웹 서버")
    parser.add_argument("--host", default="127.0.0.1", help="바인딩 호스트 (기본: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="포트 번호 (기본: 8000)")
    args = parser.parse_args()

    key, _ = vworld_service.load_vworld_config()
    vworld_state = "활성화됨 (.env 키 감지)" if key else "미설정"

    handler = partial(JochiwonRequestHandler, directory=str(ROOT_DIR))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"🔥 화재 위험도 지도 서버 실행 중: http://{args.host}:{args.port} (브이월드 API: {vworld_state})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
