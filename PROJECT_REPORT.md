# Quantum Carbon-Hedging Project Report

Date: 2026-10-09

## Security

A Resonance credential was pasted into chat. Treat it as exposed and revoke or rotate it in the Resonance dashboard before using it.

The code reads credentials only from environment variables:

```bash
RESONANCE_API_TOKEN
IQM_TOKEN
IQM_URL
IQM_BACKEND
```

The credential is not stored in this repository.

## Implemented Workflow

The active workflow is:

```text
EIA energy data
    -> daily returns and covariance
    -> equal-$1,000 carbon exposure
    -> long/short constrained QUBO
    -> exact Ising conversion
    -> antipodal Borsuk-Ulam symmetry check
    -> Qrisp QAOA
    -> optional IQM Garnet submission
```

The active universe contains four EIA energy futures:

- WTI crude oil
- Natural gas
- RBOB gasoline
- Heating oil

Hydro and wind are excluded from the active optimization pipeline.

## Active Components

- `universe.py`: loads EIA returns and emissions metadata and calculates position-level carbon exposure.
- `qubo.py`: canonical QUBO, feasibility, antipode, brute-force, and Ising conversion helpers.
- `run_pipeline.py`: complete local workflow and model export.
- `qaoa_solver.py`: Qrisp QAOA adapter.
- `run_on_quantum.py`: Qiskit-to-IQM Resonance/Garnet adapter.
- `quantum/requirements.txt`: Qrisp, Qiskit, IQM, NumPy, SciPy, and Matplotlib dependencies.
- `README.md`: setup and usage instructions.
- `archive/`: superseded PennyLane, synthetic-data, Colab, and exploratory files.

## Verification

The local `.venv` was created and dependencies were installed successfully.

The following checks passed:

```text
Python compilation: passed
Borsuk-Ulam antipodal pair check: passed
QUBO/Ising energy consistency: passed
Qrisp QAOA execution: passed
Offline IQM Hamiltonian translation: passed
IQM model size: 8 qubits
IQM Pauli terms: 36
Credential guard without token: passed
```

The local Qrisp pipeline was executed with:

```bash
.venv/bin/python run_pipeline.py \
  --n 4 \
  --k 2 \
  --qaoa \
  --p 1 \
  --steps 6 \
  --shots 256
```

No IQM hardware job was submitted, so no Resonance credits were consumed.

### Latest IQM Connectivity Test

The authenticated, metadata-only Resonance test was run from the repository
environment using `RESONANCE_API_TOKEN`. It successfully authenticated and
resolved the Garnet backend:

```text
IQM Resonance authentication and Garnet backend lookup: OK
Backend: garnet
No circuit submitted
```

This result was printed by the terminal test and is recorded here. No
measurement counts were generated because submitting a circuit was intentionally
not performed.

### IQM Garnet Hardware Run

The first hardware submission was completed successfully with:

```bash
.venv/bin/python run_on_quantum.py --shots 1000
```

The raw counts were saved locally to `iqm_raw_results.json` (ignored by Git).
The counts were decoded using the canonical QUBO and feasibility rules:

```text
Total decoded shots: 1000
Distinct bitstrings: 238
Feasible shots: 25 (2.5%)
```

Best feasible hardware sample:

```text
Probability: approximately 0.2%
Energy: 1.979479
Long: gasoline, natural_gas
Short: wti, heating_oil
Net carbon: approximately 9238.30 kg CO2
```

This matches the exact classical optimum. The low feasible-shot rate indicates
that the current fixed-angle, unconstrained QAOA circuit needs improvement
before using hardware results as a reliable optimizer. The next hardware-stage
improvements are angle optimization, a constraint-preserving mixer or stronger
penalties, and automatic count decoding in `run_on_quantum.py`.

## Current Classical Result

The current exact classical optimum is:

```text
Long:  gasoline, natural_gas
Short: wti, heating_oil
```

The antipodal portfolio is also verified:

```text
Long:  wti, heating_oil
Short: gasoline, natural_gas
```

The QUBO and Ising representations produce matching energies for the same bitstrings.

## Modeling Interpretation

The objective combines:

- carbon exposure,
- covariance risk,
- exactly two long positions,
- exactly two short positions,
- no asset being both long and short.

The current best portfolio is not exactly carbon neutral. Its net exposure is approximately `9238 kg CO2` under the equal-$1,000 position convention.

This is expected from the current weighted objective. Borsuk-Ulam symmetry motivates the long/short swap operation and verifies equal energy for the symmetric model; it does not guarantee exact carbon neutrality in a finite discrete asset universe.

If exact or near-exact neutrality is required, the model should next use one or more of:

1. A larger carbon-balance penalty.
2. An explicit carbon-exposure tolerance constraint.
3. Unequal position weights.
4. More eligible energy contracts.

## Running Locally

Install dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r quantum/requirements.txt
```

Run the classical pipeline:

```bash
.venv/bin/python run_pipeline.py
```

Run local Qrisp QAOA:

```bash
.venv/bin/python run_pipeline.py --qaoa --p 1 --steps 10 --shots 512
```

The pipeline writes the canonical model to:

```text
aayush-ai-response/data/optimization_model.json
```

## Running On IQM Garnet

After rotating the exposed credential, set the new values directly in a local terminal:

```bash
export IQM_TOKEN='new-token'
export IQM_URL='https://resonance.iqm.tech'
export IQM_BACKEND='garnet'
```

If the Resonance dashboard provides a different API endpoint under `resonance.ibm.tech`, use that exact API endpoint in `IQM_URL`.

Generate the latest model:

```bash
.venv/bin/python run_pipeline.py
```

Start with a small hardware validation job:

```bash
.venv/bin/python run_on_quantum.py --shots 100
```

Then increase the shot count only after the small job is validated:

```bash
.venv/bin/python run_on_quantum.py --shots 1000
```

## Remaining Engineering Work

Before treating the hardware result as a complete experiment:

- Optimize QAOA angles instead of using fixed trial angles.
- Decode IQM measurement counts into feasible portfolios.
- Rerank hardware samples using the canonical QUBO energy.
- Report the best feasible portfolio and carbon exposure.
- Compare local Qrisp, exact classical enumeration, and IQM results.
- Add automated tests for QUBO/Ising equivalence and antipode symmetry.