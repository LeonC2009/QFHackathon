# QFHackathon All-in-One

This folder is the separate launcher for the combined workflow. The original modular implementation remains in the repository root as the backup/reference version.

From this folder:

```bash
python -m venv .venv
source .venv/bin/activate                 # macOS/Linux
# .venv\Scripts\Activate.ps1             # Windows PowerShell
python -m pip install -r requirements.txt
python qfhackathon.py download --start 2018-01-01
python qfhackathon.py run --n 5 --k 2 --qaoa --shots 256
python qfhackathon.py hardware --dry-run
```

For a real Resonance run, set `RESONANCE_API_TOKEN`, `IQM_URL`, and `IQM_BACKEND` in the environment, then run:

```bash
python qfhackathon.py hardware --shots 1000
```

The launcher executes the combined source in `../qfhackathon_all_in_one.py`; no modular files need to be manually selected. Yahoo data is downloaded into the root project's `project_data/data/` directory so the existing dashboard and hardware adapter can use the same model.
