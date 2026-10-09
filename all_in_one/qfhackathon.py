"""Run the combined workflow from the dedicated all_in_one folder."""

from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
runpy.run_path(str(ROOT / "qfhackathon_all_in_one.py"), run_name="__main__")
