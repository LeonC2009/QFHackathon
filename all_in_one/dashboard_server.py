"""Serve the standalone dashboard and run only this folder's workflow."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DASHBOARD = ROOT / "dashboard"
DATA_DIR = ROOT / "data"
RESULT_PATH = DATA_DIR / "dashboard_result.json"


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def state() -> dict:
    with (DATA_DIR / "metadata.csv").open(newline="", encoding="utf-8") as metadata_file:
        metadata = list(csv.DictReader(metadata_file))
    result = read_json(RESULT_PATH, {})
    asset_details = [
        {"asset": row["ticker"], "carbon": float(row["carbon"])}
        for row in metadata
    ]
    assets = [asset["asset"] for asset in asset_details]
    return {
        "model": {
            "assets": assets,
            "data_source": "yahoo",
            "long_count": 2,
            "short_count": 2,
            "assets_detail": asset_details,
        },
        "result": result,
        "source": result.get("source", "YAHOO / STANDALONE DATASET"),
        "scaling": [{
            "asset_count": len(assets),
            "qubits": len(assets) * 2,
            "search_space": 2 ** (len(assets) * 2),
            "feasible_portfolios": (
                _combination_count(len(assets), 2) *
                _combination_count(len(assets) - 2, 2)
            ),
            "benchmark_kind": "real_base_assets",
        }],
    }


def _combination_count(n: int, k: int) -> int:
    if k < 0 or k > n:
        return 0
    result = 1
    for value in range(1, k + 1):
        result = result * (n - value + 1) // value
    return result


class DashboardHandler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/state":
            self._send(200, json.dumps(state()).encode(), "application/json")
            return
        if path == "/":
            path = "/index.html"
        requested = (DASHBOARD / path.lstrip("/")).resolve()
        if DASHBOARD not in requested.parents or not requested.is_file():
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }.get(requested.suffix, "application/octet-stream")
        self._send(200, requested.read_bytes(), content_type)

    def do_POST(self) -> None:
        endpoint = urlparse(self.path).path
        if endpoint == "/api/run-local":
            command = [
                sys.executable, str(ROOT / "qfhackathon.py"), "local",
                "--n", "5", "--k", "2", "--shots", "256", "--steps", "20",
            ]
        elif endpoint == "/api/run-resonance":
            command = [
                sys.executable, str(ROOT / "qfhackathon.py"), "resonance",
                "--shots", "1000", "--reps", "1", "--n", "5", "--k", "2",
            ]
        else:
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return

        try:
            process = subprocess.run(
                command, cwd=ROOT, capture_output=True, text=True,
                timeout=300, check=False,
            )
            output = process.stdout + process.stderr
            payload = {
                "ok": process.returncode == 0,
                "output": output,
                "state": state() if process.returncode == 0 else None,
            }
            self._send(
                200 if process.returncode == 0 else 500,
                json.dumps(payload).encode(),
                "application/json",
            )
        except subprocess.TimeoutExpired:
            self._send(
                504,
                json.dumps({"ok": False, "output": "Simulation timed out"}).encode(),
                "application/json",
            )
        except OSError as error:
            self._send(
                500,
                json.dumps({"ok": False, "output": str(error)}).encode(),
                "application/json",
            )

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    port = 8765
    print(f"Standalone dashboard running at http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler).serve_forever()
