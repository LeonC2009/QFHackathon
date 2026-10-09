# QFHackathon All-in-One

This folder is a separate, self-contained combined workflow. The original modular implementation remains in the repository root as the backup/reference version.

From this folder:

```bash
python -m venv .venv
source .venv/bin/activate                 # macOS/Linux
# .venv\Scripts\Activate.ps1             # Windows PowerShell
python -m pip install -r requirements.txt
python qfhackathon.py download --start 2018-01-01
python qfhackathon.py classical --n 5 --k 2
python qfhackathon.py local --n 5 --k 2 --shots 256
```

Show more detailed logs with `--verbose` before the command. The CLI prints timestamped stages and animated spinners while downloading, enumerating, optimizing, or submitting.

For Resonance, the original root adapter is used because it owns the IQM model/transpilation path:

```bash
export RESONANCE_API_TOKEN='your-token'
python qfhackathon.py resonance --dry-run
python qfhackathon.py resonance --shots 1000
```

Yahoo data is downloaded into this folder's `data/` directory. The classical and local commands are self-contained; Resonance additionally requires the original root project to be present one directory above.
