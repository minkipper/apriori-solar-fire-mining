"""조치원읍 건물 화재 위험도 평가 지도 웹 서버.

정적 HTML/CSS/JS 및 GeoJSON 파일을 UTF-8과 CORS 헤더로 서빙한다.
"""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent


class JochiwonRequestHandler(SimpleHTTPRequestHandler):
    """GeoJSON MIME 타입, UTF-8 인코딩 및 CORS 헤더를 지원하는 핸들러."""

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
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description="조치원읍 화재 위험도 지도 웹 서버")
    parser.add_argument("--host", default="127.0.0.1", help="바인딩 호스트 (기본: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="포트 번호 (기본: 8000)")
    args = parser.parse_args()

    handler = partial(JochiwonRequestHandler, directory=str(ROOT_DIR))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"조치원읍 화재 위험도 지도 서버 실행 중: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
