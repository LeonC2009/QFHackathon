# Quantum Carbon Hedging: Current State

Date: 2026-10-09

## 1. Purpose

This project demonstrates a data-to-quantum workflow for selecting a long/short energy-futures portfolio that balances carbon exposure, covariance risk, and trading constraints.

The project is a research and presentation prototype. It is not a trading system, an emissions compliance tool, or evidence that current quantum hardware outperforms classical optimization.

The strongest current claim is:

> A classical reference solver validates the formulation, while Qrisp and IQM Garnet demonstrate how the same constrained QUBO/Ising problem behaves in simulation and on real quantum hardware.

## 2. Active Data Universe

The active universe contains four prepared EIA energy futures:

- WTI crude oil: `wti`
- RBOB gasoline: `gasoline`
- Heating oil: `heating_oil`
- Natural gas: `natural_gas`

Hydro and wind are excluded from the active pipeline. The prepared files are under:

```text
project_data/data/
```

Important inputs include:

- `energy_futures.csv`: aligned historical prices.
- `energy_returns.csv`: daily percentage returns.
- `emissions.csv`: EIA carbon coefficients.
- `asset_metadata.csv`: instrument names and units.
- `raw/`: downloaded source workbooks.

The active model converts each asset into an approximate carbon exposure for an equal-$1,000 notional position. Price units are converted using the energy-content convention in `universe.py`.

## 3. End-to-End Architecture

```text
project_data/data/energy_futures.csv
project_data/data/energy_returns.csv
project_data/data/emissions.csv
                |
                v
          universe.py
                |
                v
      Universe: returns, covariance,
      position carbon, expected returns
                |
                v
             qubo.py
                |
                +--> exact feasible enumeration
                |
                +--> Ising fields and couplings
                |
                +--> Qrisp QAOA simulation
                |
                +--> Qiskit circuit for IQM Garnet
                |
                v
       results.py / iqm_result.json
                |
                v
          dashboard/
```

## 4. Mathematical Model

Each asset has two binary variables:

```text
x_i = 1 if asset i is long
y_i = 1 if asset i is short
```

The full bitstring is:

```text
v = [x_0, ..., x_(N-1), y_0, ..., y_(N-1)]
```

The signed position vector is:

```text
s = x - y
```

The QUBO objective combines:

- squared net carbon exposure,
- covariance risk,
- long-count penalty,
- short-count penalty,
- long/short overlap penalty,
- optional carbon and return tie-breakers.

The canonical form is:

```text
E(v) = v.T @ Q @ v + constant
```

`qubo_to_ising()` converts this using:

```text
v_i = (1 - Z_i) / 2
```

and returns:

```text
E = constant + sum(h_i Z_i) + sum(J_ij Z_i Z_j)
```

The code checks QUBO and Ising energies against the same bitstrings before quantum execution.

## 5. Borsuk-Ulam Role

The project uses Borsuk-Ulam as a symmetry motivation, not as a claim that every finite discrete portfolio must be exactly carbon neutral.

The discrete antipode is:

```text
A(x, y) = (y, x)
```

For the symmetric QUBO, swapping every long and short position gives equal energy. The explicit carbon penalty is what searches for low exposure. The theorem does not replace the optimizer and does not guarantee an exactly neutral portfolio in this finite asset set.

## 6. Solvers

### Exact classical reference

`qubo.brute_force()` enumerates feasible bitstrings for small instances. It is the trusted reference for the current 8-qubit model.

### Qrisp local simulation

`qaoa_solver.py` runs QAOA with Qrisp. For the active `N=4`, `K=2` case it uses:

- a seeded Dicke-state initialization,
- a portfolio mixer preserving the long and short cardinalities,
- QUBO cost evaluation,
- post-measurement feasibility checks.

The local constrained run has produced approximately 14.1% feasible samples in a benchmark run, although this varies with optimizer initialization and shot count.

### IQM Garnet

`run_on_quantum.py` translates the canonical Ising Hamiltonian to Qiskit and submits it to IQM Resonance. It uses:

- Qiskit `QAOAAnsatz`,
- an XX+YY mixer within each long/short block,
- a seeded initial state,
- local QAOA angles from `project_data/data/qaoa_angles.json`,
- Qiskit transpilation against the selected IQM backend.

The hardware mixer preserves the number of longs and shorts but does not fully prevent an asset from appearing in both blocks. The QUBO and decoder still enforce exclusivity when ranking results.

## 7. Verified Hardware Result

A 1,000-shot Garnet run completed successfully.

Best feasible portfolio:

```text
Long:  gasoline, natural_gas
Short: wti, heating_oil
```

The hardware result matched the exact classical optimum:

```text
QUBO energy: 1.979479
Net carbon: approximately 9238 kg CO2
```

The improved constrained hardware run produced approximately 4.1% feasible samples, compared with approximately 2.5% for the earlier unconstrained run.

The latest decoded artifacts are:

- `iqm_raw_results.json`: raw measurement counts. Ignored by Git.
- `iqm_result.json`: decoded result summary. Ignored by Git.

These files are local experiment outputs, not source inputs.

## 8. Scaling Benchmark

`scaling_benchmark.py` creates a reproducible size benchmark.

The four base assets are real prepared EIA inputs. Larger rows are deterministic stress expansions based on those assets. They are clearly labeled synthetic and must not be presented as additional market observations.

Current benchmark:

| Assets | Qubits | Feasible portfolios | Type |
|---:|---:|---:|---|
| 4 | 8 | 6 | real EIA base |
| 6 | 12 | 90 | synthetic stress |
| 8 | 16 | 420 | synthetic stress |
| 10 | 20 | 1,260 | synthetic stress |
| 12 | 24 | 18,480 | synthetic stress |

For `N` assets and `K` long plus `K` short positions, the number of non-overlapping portfolios is:

```text
choose(N, K) * choose(N - K, K)
```

The scaling benchmark is useful for presentation, but it is not a quantum advantage claim. A fair comparison needs a strong classical heuristic, wall-clock timing, solution quality, feasibility, and hardware overhead.

## 9. Presentation Dashboard

The dashboard consists of:

- `dashboard/index.html`: visual presentation surface.
- `dashboard/styles.css`: responsive visual system.
- `dashboard/app.js`: state rendering and controls.
- `dashboard_server.py`: local static server and API.

It displays:

- latest long/short portfolio,
- QUBO energy,
- net carbon exposure,
- hardware feasibility,
- asset carbon bars,
- QAOA pipeline stages,
- scaling runway,
- local QAOA and Resonance actions.

Start it with:

```bash
.venv/bin/python dashboard_server.py
```

Open:

```text
http://127.0.0.1:8765
```

The local button runs a 256-shot Qrisp experiment. The Garnet button asks for confirmation and submits 1,000 shots, consuming Resonance credits.

## 10. Cross-Platform Setup

Use a virtual environment. Do not depend on the system Python.

### macOS and Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r quantum/requirements.txt
python run_pipeline.py
```

Start the dashboard:

```bash
python dashboard_server.py
```

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r quantum\requirements.txt
python run_pipeline.py
```

Start the dashboard:

```powershell
python dashboard_server.py
```

### Windows Command Prompt

```bat
py -3 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r quantum\requirements.txt
python run_pipeline.py
```

## 11. Resonance Authentication

The official IQM Qiskit client documentation recommends installing the optional Qiskit adapter from `iqm-client[qiskit]`, setting `IQM_TOKEN` or passing a token to `IQMProvider`, selecting the quantum computer when needed, transpiling the circuit, and then calling `backend.run()`.

This repository accepts the project-friendly variable `RESONANCE_API_TOKEN` first and `IQM_TOKEN` as a compatibility fallback:

```python
token = os.environ.get("RESONANCE_API_TOKEN") or os.environ.get("IQM_TOKEN")
provider = IQMProvider(
    url,
    quantum_computer=backend_name,
    token=token,
)
```

The code defaults to:

```text
URL: https://resonance.iqm.tech
Backend: garnet
```

Override them when your account or organization supplies different values.

### macOS and Linux shell

Temporary for one terminal session:

```bash
export RESONANCE_API_TOKEN='paste-token-in-your-terminal'
export IQM_URL='https://resonance.iqm.tech'
export IQM_BACKEND='garnet'
```

Persistent for future zsh sessions:

```bash
printf '%s\n' 'export RESONANCE_API_TOKEN="paste-token-in-your-terminal"' >> ~/.zshrc
source ~/.zshrc
```

For bash, use `~/.bashrc` instead of `~/.zshrc`.

### Windows PowerShell

Temporary:

```powershell
$env:RESONANCE_API_TOKEN = "paste-token-in-your-terminal"
$env:IQM_URL = "https://resonance.iqm.tech"
$env:IQM_BACKEND = "garnet"
```

Persistent for the user account:

```powershell
[Environment]::SetEnvironmentVariable("RESONANCE_API_TOKEN", "paste-token-in-your-terminal", "User")
[Environment]::SetEnvironmentVariable("IQM_URL", "https://resonance.iqm.tech", "User")
[Environment]::SetEnvironmentVariable("IQM_BACKEND", "garnet", "User")
```

Open a new PowerShell window after setting persistent variables.

### Windows Command Prompt

Temporary:

```bat
set RESONANCE_API_TOKEN=paste-token-in-your-terminal
set IQM_URL=https://resonance.iqm.tech
set IQM_BACKEND=garnet
```

Never commit tokens, put them in Markdown, or send them through the dashboard source code. Regenerating a token invalidates the previous token according to the IQM documentation.

## 12. Safe Execution Order

Run these before spending hardware credits:

```bash
python -m py_compile *.py
python run_pipeline.py
python optimize_angles.py --reps 1 --maxiter 80
python run_on_quantum.py --dry-run --reps 1
```

Only after the dry run succeeds:

```bash
python run_on_quantum.py --shots 1000 --reps 1
```

The dry run authenticates, resolves Garnet, routes, and binds the circuit without submitting a job.

## 13. Known Limitations

- Four real assets are too small to demonstrate a practical quantum advantage.
- Larger benchmark rows are synthetic stress instances, not extra EIA market data.
- The hardware mixer preserves cardinality but not full per-asset exclusivity.
- The current model is not exactly carbon neutral; its selected result has approximately 9238 kg CO2 net exposure under the equal-$1,000 convention.
- QAOA parameters are optimized locally and then reused on hardware; hardware-aware optimization is not implemented.
- IQM results are noisy samples and should be compared against exact or best-known classical references.
- The dashboard hardware button submits a real job and consumes credits.

## 14. Recommended Next Work

1. Add automated unit tests for QUBO/Ising equality, antipodes, feasibility, and result decoding.
2. Add a classical MILP or simulated-annealing baseline for 12+ asset stress cases.
3. Implement a fully exclusivity-preserving mixer or a one-hot formulation.
4. Add repeated-shot confidence intervals instead of a single feasibility percentage.
5. Store experiment metadata such as timestamp, backend, calibration set, angle file, and shot count.
6. Compare local, simulated-noise, and Garnet results in one benchmark report.
