"""Serve the loop dashboard. Standard library only.

    python -m ui.server [--port 8080]

GET /             -> ui/index.html
GET /api/results  -> runs/results.jsonl as a JSON array
GET /api/receipt  -> most recent runs/*/receipt.json
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core import config  # noqa: E402

UI_DIR = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(UI_DIR), **kw)

    def _json(self, obj) -> None:
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/results"):
            p = config.RUNS_DIR / "results.jsonl"
            rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
            return self._json(rows)
        if self.path.startswith("/api/receipt"):
            receipts = sorted(config.RUNS_DIR.glob("*/receipt.json"), key=lambda q: q.stat().st_mtime)
            return self._json(json.loads(receipts[-1].read_text()) if receipts else {})
        if self.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def log_message(self, *args) -> None:
        pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    print(f"ratchet dashboard at http://{args.host}:{args.port}")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
