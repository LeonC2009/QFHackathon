"""
Create a virtual environment with Qiskit + Aer and verify it works.

Usage (any OS, from the repo folder):
    python setup_env.py                # creates .venv-aer, installs requirements.txt, runs check_aer.py
    python setup_env.py --venv myenv   # custom folder name
    python setup_env.py --recreate     # delete and rebuild the environment

Afterwards activate it:
    Windows (PowerShell):  .venv-aer\\Scripts\\Activate.ps1
    Windows (cmd):         .venv-aer\\Scripts\\activate.bat
    macOS / Linux:         source .venv-aer/bin/activate
"""

import argparse
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(cmd):
    print("\n$", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--venv", default=".venv-aer", help="environment folder name (default .venv-aer)")
    ap.add_argument("--recreate", action="store_true", help="delete and rebuild the environment")
    ap.add_argument("--skip-check", action="store_true", help="skip running check_aer.py at the end")
    args = ap.parse_args()

    if sys.version_info < (3, 10):
        print(f"WARNING: Python {sys.version_info.major}.{sys.version_info.minor} detected; "
              "recent Qiskit/Aer releases generally need 3.10+. Use a newer Python if install fails.")

    venv_dir = HERE / args.venv
    if args.recreate and venv_dir.exists():
        print(f"Removing {venv_dir} ...")
        shutil.rmtree(venv_dir)
    if not venv_dir.exists():
        print(f"Creating virtual environment in {venv_dir} ...")
        venv.EnvBuilder(with_pip=True).create(venv_dir)
    else:
        print(f"Re-using existing environment in {venv_dir}")

    py = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run([py, "-m", "pip", "install", "--upgrade", "pip"])
    run([py, "-m", "pip", "install", "-r", HERE / "requirements.txt"])

    if not args.skip_check:
        run([py, HERE / "check_aer.py"])

    print("\nEnvironment ready. Activate it with:")
    print(f"  Windows (PowerShell): {args.venv}\\Scripts\\Activate.ps1")
    print(f"  macOS / Linux:        source {args.venv}/bin/activate")


if __name__ == "__main__":
    main()
