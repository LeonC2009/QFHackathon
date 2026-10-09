# QFHackathon All-in-One

This folder is a separate, self-contained combined workflow. The original modular implementation remains in the repository root as the backup/reference version.

From this folder:

```bash
python -m venv .venv
source .venv/bin/activate                 # macOS/Linux
# .venv\Scripts\Activate.ps1             # Windows PowerShell
python -m pip install -r requirements.txt
python qfhackathon.py download --start 2018-01-01
python qfhackathon.py run --n 5 --k 2 --qaoa --shots 256
```

Yahoo data is downloaded into this folder's `data/` directory. No root project files are needed for download, exact solving, or local QAOA. Use the original root setup for the IQM Resonance/Garnet hardware adapter.
