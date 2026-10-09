# Quantum Topological Carbon Hedging

This repository builds a long/short carbon-hedging portfolio from four EIA energy futures: WTI crude oil, natural gas, RBOB gasoline, and heating oil. Hydro and wind are excluded from the active pipeline.

## Active workflow

```text
EIA prices + emissions -> returns/covariance -> constrained QUBO
-> Ising -> Borsuk-inspired antipode check -> Qrisp QAOA
-> IQM Garnet -> decoded portfolio result
```

The Borsuk-Ulam theorem motivates the long/short swap symmetry. It does not prove that a finite discrete portfolio is exactly carbon neutral; the QUBO carbon-balance term is what drives the search.

## Local pipeline

```bash
python3 -m pip install -r quantum/requirements.txt
python3 run_pipeline.py
python3 run_pipeline.py --qaoa --p 1 --steps 20 --shots 512
python3 optimize_angles.py --reps 1 --maxiter 80
```

The pipeline reads prepared EIA files under `aayush-ai-response/data/` and writes the canonical model to `aayush-ai-response/data/optimization_model.json`.

## IQM Garnet

Set the token in your shell. It is never stored in source control:

```bash
export RESONANCE_API_TOKEN='token-from-resonance-dashboard'
export IQM_URL='https://resonance.iqm.tech'
export IQM_BACKEND='garnet'
```

Validate routing without spending credits:

```bash
python3 run_on_quantum.py --dry-run --reps 1
```

Submit a hardware run only when ready:

```bash
python3 run_on_quantum.py --shots 1000 --reps 1
```

The runner saves raw counts to `iqm_raw_results.json` and decoded results to `iqm_result.json`.

## Presentation dashboard

Start the local dashboard:

```bash
python3 dashboard_server.py
```

Then open <http://127.0.0.1:8765>. The dashboard reads the current model and hardware result, visualizes the portfolio and feasibility rate, and can run a local Qrisp simulation with the **Run local QAOA** button.

## Layout

- `dashboard/`: presentation frontend.
- `dashboard_server.py`: local static server and local-QAOA API.
- `run_pipeline.py`: canonical end-to-end workflow.
- `universe.py`: EIA data and position-level emissions loader.
- `qubo.py`: QUBO, Ising, feasibility, and antipode helpers.
- `qaoa_solver.py`: Qrisp simulator adapter.
- `optimize_angles.py`: local QAOA angle optimization.
- `results.py`: shared hardware measurement decoder.
- `run_on_quantum.py`: IQM Resonance/Garnet adapter.
- `aayush-ai-response/data/`: prepared inputs and generated model artifacts.
- `archive/`: superseded scripts and reference material.
