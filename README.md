# Quantum Topological Carbon Hedging

A research and presentation prototype that turns energy-futures data into a constrained long/short QUBO, converts it to an Ising Hamiltonian, evaluates it classically and with Qrisp, and can submit the same model to IQM Resonance/Garnet. The default source is EIA; a reproducible Yahoo Finance futures source is also available for larger experiments.

Hydro and wind are excluded from the active universe. The current real-data universe is WTI crude oil, natural gas, RBOB gasoline, and heating oil.

## Quick Start

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r quantum/requirements.txt
python run_pipeline.py
```

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r quantum\requirements.txt
python run_pipeline.py
```

Run local Qrisp:

```bash
python run_pipeline.py --qaoa --p 1 --steps 20 --shots 512
```

## Single-file workflow

For presentations or quick experiments, [qfhackathon_all_in_one.py](qfhackathon_all_in_one.py) combines the Yahoo downloader, data loader, QUBO, exact solver, and local QAOA into one command-line file. The existing modular setup remains unchanged and is the backup/reference implementation.

```bash
python qfhackathon_all_in_one.py download --start 2018-01-01
python qfhackathon_all_in_one.py run --n 5 --k 2 --qaoa --shots 256
```

The hardware command intentionally delegates to the maintained Resonance adapter so the credential and transpilation path stays in one reviewed place:

```bash
python qfhackathon_all_in_one.py hardware --dry-run
python qfhackathon_all_in_one.py hardware --shots 1000
```

For a separately runnable copy of this combined workflow, use the [all_in_one/](all_in_one/) folder. It includes its own `requirements.txt`, README, and launcher; the original separated implementation remains in the repository root.

The standalone folder also includes its own dashboard. From inside `all_in_one/`, run `python dashboard_server.py` and open <http://127.0.0.1:8765>; its UI and run controls use only files and data inside that folder.

Download Yahoo Finance futures and run the classical pipeline:

```bash
python project_data/download_yahoo_futures.py --start 2018-01-01
python run_pipeline.py --data-source yahoo --n 4 --k 2
```

Yahoo supplies prices only. The downloader stores explicit contract metadata and estimates carbon exposure per `$1,000` position using fuel-specific emissions factors. The Yahoo source currently covers WTI, Brent, natural gas, gasoline, and heating oil; add reviewed contracts in [project_data/download_yahoo_futures.py](project_data/download_yahoo_futures.py). EIA remains the default and should remain the headline source when real EIA emissions data is required.

Optimize hardware angles and validate without submitting:

```bash
python optimize_angles.py --reps 1 --maxiter 80
python run_on_quantum.py --dry-run --reps 1
```

## IQM Resonance/Garnet

The official IQM Qiskit adapter documentation recommends `iqm-client[qiskit]`, a token passed to `IQMProvider`, a selected quantum computer, Qiskit transpilation, and `backend.run()`.

Set credentials in the environment, never in source files:

macOS/Linux:

```bash
export RESONANCE_API_TOKEN='paste-token-in-your-terminal'
export IQM_URL='https://resonance.iqm.tech'
export IQM_BACKEND='garnet'
```

Windows PowerShell:

```powershell
$env:RESONANCE_API_TOKEN = "paste-token-in-your-terminal"
$env:IQM_URL = "https://resonance.iqm.tech"
$env:IQM_BACKEND = "garnet"
```

Windows Command Prompt:

```bat
set RESONANCE_API_TOKEN=paste-token-in-your-terminal
set IQM_URL=https://resonance.iqm.tech
set IQM_BACKEND=garnet
```

Test routing without using credits:

```bash
python run_on_quantum.py --dry-run --reps 1
```

Submit a real 1,000-shot job only after the dry run succeeds:

```bash
python run_on_quantum.py --shots 1000 --reps 1
```

The code accepts `RESONANCE_API_TOKEN` first and `IQM_TOKEN` as a compatibility fallback. Regenerating an IQM token invalidates the previous token. Never commit or paste a real token into Markdown, source code, or chat.

## Presentation Dashboard

```bash
python dashboard_server.py
```

Open <http://127.0.0.1:8765>.

The dashboard visualizes the latest decoded portfolio, carbon exposure, feasibility, QUBO score, asset emissions, scaling benchmark, and local QAOA results. The separate **Submit to Garnet** control asks for confirmation before consuming Resonance credits.

## Project Map

- `universe.py`: loads EIA or generated Yahoo returns, covariance, expected returns, and position carbon exposure.
- `qubo.py`: builds the constrained QUBO, converts to Ising, checks feasibility, and evaluates antipodes.
- `run_pipeline.py`: canonical data-to-QAOA workflow and model export.
- `qaoa_solver.py`: Qrisp simulator with a cardinality-preserving portfolio mixer.
- `optimize_angles.py`: local Qiskit angle optimization for hardware runs.
- `run_on_quantum.py`: Qiskit/IQM Resonance/Garnet submission path.
- `results.py`: shared hardware count decoder and feasible-portfolio ranking.
- `scaling_benchmark.py`: real-base plus clearly labeled synthetic stress-size benchmark.
- `dashboard/`: presentation frontend.
- `dashboard_server.py`: local dashboard server and execution API.
- `project_data/`: generic project data, prepared EIA files, generated Yahoo futures artifacts, model, and angle artifacts.
- `project_data/download_yahoo_futures.py`: reproducibly downloads Yahoo futures and builds returns, covariance, and carbon metadata.
- `PROJECT_STATE.md`: detailed architecture, results, setup, platform notes, and limitations.
- `archive/`: superseded scripts and reference material.

## Current Reference Result

The best validated portfolio is:

```text
Long:  gasoline, natural_gas
Short: wti, heating_oil
```

The current hardware workflow finds the same portfolio as exact classical enumeration, but hardware feasibility remains lower than local simulation. See [PROJECT_STATE.md](PROJECT_STATE.md) for the detailed state and next work.

## Tests

Run the offline regression tests with:

```bash
python -m pytest -q
```
