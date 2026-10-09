# Quantum Topological Carbon Hedging

This repository builds a long/short carbon-hedging portfolio from four EIA energy futures: WTI crude oil, natural gas, RBOB gasoline, and heating oil. Hydro and wind assets are excluded from the active pipeline.

The active path is:

```text
EIA prices + emissions -> daily returns/covariance -> constrained QUBO
-> exact Ising conversion -> Borsuk-inspired antipode check -> Qrisp QAOA
-> optional IQM Resonance/Garnet submission
```

The Borsuk-Ulam theorem motivates the long/short swap symmetry. It does not prove that a finite discrete portfolio is exactly carbon neutral. The carbon balance penalty in the QUBO is the mechanism that searches for a low-exposure portfolio.

## Run locally

```bash
python3 -m pip install -r quantum/requirements.txt
python3 run_pipeline.py
python3 run_pipeline.py --qaoa --p 1 --steps 10 --shots 512
```

The pipeline reads prepared EIA files under `aayush-ai-response/data/` and writes the canonical model to `aayush-ai-response/data/optimization_model.json`.

## Run on IQM Garnet

The IQM script uses Qiskit as the circuit/Hamiltonian bridge to IQM Resonance. It submits the same Ising fields and couplings produced by the pipeline; it does not use PennyLane.

```bash
export IQM_TOKEN='token-from-resonance-dashboard'
export IQM_URL='https://resonance.iqm.tech'
export IQM_BACKEND='garnet'
python3 run_on_quantum.py --shots 1000
```

The token is never stored in source control. Start with small shot counts while validating the circuit; IQM Resonance credits are consumed by hardware jobs.

## Layout

- `run_pipeline.py`: canonical end-to-end workflow.
- `universe.py`: EIA data and emissions loader; rejects non-energy inputs.
- `qubo.py`: QUBO, Ising conversion, feasibility, and antipode helpers.
- `qaoa_solver.py`: Qrisp simulator adapter.
- `run_on_quantum.py`: IQM Resonance/Garnet adapter.
- `aayush-ai-response/data/`: prepared EIA inputs and generated model output.
- `archive/`: superseded scripts, notebook exports, and reference material.
