"""Local presentation dashboard for the carbon-hedging pipeline."""

from __future__ import annotations

import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DASHBOARD = ROOT / "dashboard"
MODEL_PATH = ROOT / "aayush-ai-response" / "data" / "optimization_model.json"
RESULT_PATH = ROOT / "iqm_result.json"
LOCAL_RESULT_PATH = ROOT / "local_qaoa_result.json"
ANGLES_PATH = ROOT / "aayush-ai-response" / "data" / "qaoa_angles.json"


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def state() -> dict:
    model = read_json(MODEL_PATH, {})
    result = read_json(RESULT_PATH, {})
    angles = read_json(ANGLES_PATH, {})
    assets = []
    for index, asset in enumerate(model.get("assets", [])):
        assets.append(
            {
                "asset": asset,
                "carbon": model.get("carbon_exposure", [])[index],
            }
        )
    return {
        "model": {
            "assets": model.get("assets", []),
            "long_count": model.get("long_count", 2),
            "short_count": model.get("short_count", 2),
            "cardinality_weight": model.get("cardinality_weight"),
            "exclusivity_weight": model.get("exclusivity_weight"),
            "assets_detail": assets,
        },
        "result": result,
        "source": "IQM GARNET / 1,000 SHOTS",
        "angles": angles,
    }


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
        if urlparse(self.path).path != "/api/run-local":
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        try:
            process = subprocess.run(
                [
                    sys.executable,
                    "run_pipeline.py",
                    "--n",
                    "4",
                    "--k",
                    "2",
                    "--qaoa",
                    "--p",
                    "1",
                    "--steps",
                    "20",
                    "--shots",
                    "256",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            output = process.stdout + process.stderr
            response_state = state()
            response_state["result"] = read_json(LOCAL_RESULT_PATH, {})
            response_state["source"] = "LOCAL QAOA / 256 SHOTS"
            self._send(
                200 if process.returncode == 0 else 500,
                json.dumps({"ok": process.returncode == 0, "output": output, "state": response_state}).encode(),
                "application/json",
            )
        except subprocess.TimeoutExpired:
            self._send(504, json.dumps({"ok": False, "output": "Local simulation timed out"}).encode(), "application/json")

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    port = 8765
    print(f"Dashboard running at http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler).serve_forever()
