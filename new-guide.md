# QFHackathon: Implementation Guide (Demo to Benchmark)

*Based on the repository state of 2026-10-09. Every step is written so a teammate can pick it up cold.*

## 0. Goal and ground rules

**Goal.** Turn the current 4-asset demo into a credible, reproducible benchmark of a carbon-constrained long/short portfolio problem, with honest classical, random, simulated-quantum and real-hardware comparisons. We are not trying to prove quantum advantage. We are trying to show exactly where today's hardware stands and what would have to be true for it to matter.

**Ground rules**

1. Baselines before quantum claims. No quantum number goes on a slide without a random and a classical number next to it.
2. Every result is reproducible: seed, git hash, data window, and parameters are stored with it.
3. Real data is labeled real; synthetic is labeled synthetic and kept out of headline claims.
4. Tests before refactors. The QUBO/Ising equivalence test is the safety net for everything below.
5. No tokens in code, Markdown, chat, or dashboard source. Rotate the Resonance token that was pasted into chat before doing anything else.

**Phase overview**

| Phase | What | Output | Effort |
| --- | --- | --- | --- |
| 0 | Housekeeping | branch, tests folder, token rotated, wording fixed | S |
| 1 | Test suite for the existing model | green pytest on current code | S |
| 2 | One-qubit-per-asset spin model | `qubo_spin.py` + exact solver | M |
| 3 | Hamming-weight-preserving circuits | `circuits.py`, feasibility by construction | M |
| 4 | Data expansion + rolling windows | 8 to 12 real instruments, \~100 instances | M |
| 5 | Benchmark harness | `bench/` with all solvers and metrics | L |
| 6 | Quantum improvements | CVaR, warm start, INTERP, mitigation, hybrid | M |
| 7 | Borsuk-Ulam decision | one honest paragraph or a symmetry-breaking feature | S |
| 8 | Hardware campaign | cached Garnet results with metadata | M |
| 9 | Dashboard and slides | replay-only dashboard, 7-slide story | M |
| 10 | Definition of done | checklist | S |

Effort: S is under half a day, M is about a day, L is 1 to 2 days. Phases 2 and 3 can be done in parallel with phase 4 by different people.

---

## Phase 0. Housekeeping

1. **Rotate the Resonance token** in the Resonance dashboard. Regenerating invalidates the old one. Set the new one only through environment variables.
2. Create a branch: `git checkout -b benchmark-v2`. Keep `main` demo-able until the new work is merged.
3. Create folders: `tests/`, `bench/`, `results/`, `docs/`. Add `results/raw/` to `.gitignore` if raw counts are large, but commit the small summary JSON files the dashboard reads.
4. Add `pytest` to `quantum/requirements.txt`.
5. **Fix the wording now** so it does not get forgotten. In `dashboard/index.html` change the kicker 'Carbon-neutral pair discovery' and the hero headline to 'carbon-aware hedge' language, and show net exposure next to gross exposure everywhere. The current best portfolio has 9,238 kg net exposure, which is not neutral.
6. Add a `results/metadata.py` helper now; every later phase uses it:

```python
# results/metadata.py
import json, subprocess, time, platform

def run_metadata(**extra):
    try:
        git = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    except Exception:
        git = 'unknown'
    return {'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'), 'git': git,
            'python': platform.python_version(), **extra}

def save(path, payload, **meta):
    with open(path, 'w') as f:
        json.dump({'meta': run_metadata(**meta), 'data': payload}, f, indent=2)
```

---

## Phase 1. Tests for what already exists

Create `tests/test_qubo.py`. These lock in the behavior you already verified by hand, so later refactors cannot silently break it.

```python
import numpy as np, itertools
from universe import load_universe
from qubo import (build_qubo, qubo_energy, qubo_to_ising, ising_energy,
                  antipode, is_feasible, brute_force)

def test_qubo_matches_ising_on_random_bitstrings():
    u = load_universe(n=4)
    q, c = build_qubo(u, 2, tau=0.3, lam=0.5)
    h, J, ic = qubo_to_ising(q, c)
    rng = np.random.default_rng(0)
    for _ in range(200):
        bits = rng.integers(0, 2, 8)
        assert np.isclose(qubo_energy(bits, q, c), ising_energy(bits, h, J, ic))

def test_antipode_is_involution_and_preserves_symmetric_energy():
    u = load_universe(n=4)
    q, c = build_qubo(u, 2)  # tau=lam=0 gives the symmetric model
    for bits in itertools.product([0, 1], repeat=8):
        assert antipode(antipode(bits)) == tuple(bits)
        assert np.isclose(qubo_energy(bits, q, c), qubo_energy(antipode(bits), q, c))

def test_feasible_count_is_six():
    n = 4
    feas = [b for b in itertools.product([0, 1], repeat=2 * n) if is_feasible(b, n, 2)]
    assert len(feas) == 6

def test_brute_force_returns_known_optimum():
    u = load_universe(n=4)
    q, c = build_qubo(u, 2, tau=0.3, lam=0.5)
    e, bits = brute_force(q, c, 4, 2, top=1)[0]
    assert np.isclose(e, 1.979479, atol=1e-4)
```

Run `pytest -q`. If the last test fails, your local data differs from the committed result; investigate before going further. Also add a decoder test for `results.py` using a small hand-made counts dictionary, including the Qiskit little-endian bit order (the rightmost character is qubit 0).

---

## Phase 2. One-qubit-per-asset spin model

### Why

The current model uses a long bit and a short bit per asset. That costs 2N qubits, needs an exclusivity penalty, and lets the hardware sample assets that are both long and short. Instead, let every asset in the chosen universe be either long (+1) or short (-1): one qubit per asset, no exclusivity term, half the qubits.

### Math

Let `s_i = +1` for long and `-1` for short, with K longs, so `sum(s) = 2K - n` (call it D). Objective:

```
E(s) = alpha * (c.s / c_scale)^2 + beta * (s' Sigma s / sigma_scale) + gamma * (sum(s) - D)^2
```

- `c` is carbon per equal-notional position, `Sigma` is the covariance matrix.
- `gamma > 0` is only needed if you do NOT use a Hamming-weight-preserving mixer. With the mixer in Phase 3, set `gamma = 0`.
- Write the quadratic form as `s' M s`. Since `s_i^2 = 1`, it equals `trace(M) + 2 * sum_{i<j} M_ij s_i s_j`. So `J_ij = 2 * M_ij`, and the constant is `trace(M)`.
- Qiskit's Z has eigenvalue +1 on bit 0 and -1 on bit 1. If bit 1 means long (s = +1), then `s = -Z`. Linear terms flip sign, quadratic terms do not.

### Implementation: `qubo_spin.py`

```python
import itertools
import numpy as np

def build_spin_model(c, sigma, K, alpha=1.0, beta=1.0, gamma=0.0):
    n = len(c)
    c = np.asarray(c, float) / max(np.mean(np.abs(c)), 1e-12)
    S = np.asarray(sigma, float) / max(np.max(np.abs(sigma)), 1e-12)
    D = 2 * K - n
    M = alpha * np.outer(c, c) + beta * S + gamma * np.ones((n, n))
    h = -2.0 * gamma * D * np.ones(n)          # coefficient of s_i
    J = np.triu(2.0 * M, 1)                    # coefficient of s_i s_j, i<j
    const = float(np.trace(M) + gamma * D ** 2)
    return {'h': h, 'J': J, 'const': const, 'n': n, 'K': K}

def energy(s, m):
    s = np.asarray(s, float)
    return float(m['const'] + m['h'] @ s + s @ m['J'] @ s)

def bits_to_s(bits):          # bit 1 = long
    return 2 * np.asarray(bits, float) - 1

def exact(m, top=5):
    n, K = m['n'], m['K']
    out = []
    for longs in itertools.combinations(range(n), K):
        s = -np.ones(n)
        s[list(longs)] = 1
        out.append((energy(s, m), longs))
    out.sort(key=lambda t: t[0])
    return out[:top]

def to_pauli_z(m):
    # returns (h_z, J_z, const) for E = const + sum h_z Z_i + sum J_z Z_i Z_j with s = -Z
    return -m['h'], m['J'], m['const']
```

Exact enumeration is `C(n, K)` evaluations, so it stays instant to about n = 26. That makes it your ground truth for every instance you benchmark.

### Tests (`tests/test_spin.py`)

1. For random `s`, `energy(s, m)` equals the direct formula with the three terms computed separately.
2. For `n = 2K` and `gamma = 0`, `energy(s) == energy(-s)` (the long/short symmetry).
3. `to_pauli_z` energy on a bitstring equals `energy(bits_to_s(bits))`.

### Design decision: do you allow 'none'?

My quick check of all 81 long/short/none combinations of the 4 current assets found a two-asset hedge (long heating oil, short gasoline) with roughly 353 kg net exposure and far lower variance than the forced 2+2 portfolio. Forcing every asset into a leg is a restriction. Pick one and write it in the docs:

- **A. Select then split.** Stage 1 chooses the traded subset classically or with a second small QAOA. Stage 2 is the spin model on that subset. Simple, defensible.
- **B. Report both.** Keep fixed-K as the headline benchmark (clean, comparable) and add one slide showing the free-cardinality classical optimum to prove you understand the limitation. I recommend this one.

Also report **net and gross exposure** and a **neutrality ratio** `|net| / gross` in every result file.

---

## Phase 3. Hamming-weight-preserving circuits

Use an XY mixer so the circuit only ever visits states with exactly K longs. Feasibility then holds by construction on a perfect machine, and only noise creates invalid shots.

### Building blocks (`circuits.py`)

```python
import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit.library import PauliEvolutionGate
from qiskit.quantum_info import SparsePauliOp

def cost_operator(h_z, J_z, n):
    terms = [('Z', [i], h_z[i]) for i in range(n) if abs(h_z[i]) > 1e-12]
    terms += [('ZZ', [i, j], J_z[i, j]) for i in range(n)
              for j in range(i + 1, n) if abs(J_z[i, j]) > 1e-12]
    return SparsePauliOp.from_sparse_list(terms, num_qubits=n)

def xy_layers(n):
    even = [(i, i + 1) for i in range(0, n - 1, 2)]
    odd = [(i, i + 1) for i in range(1, n - 1, 2)]
    return even, odd

XY = SparsePauliOp(['XX', 'YY'], [1.0, 1.0])

def qaoa_circuit(h_z, J_z, n, K, gammas, betas, init_longs=None, measure=True):
    cost = cost_operator(h_z, J_z, n)
    qc = QuantumCircuit(n)
    for i in (init_longs if init_longs is not None else range(K)):
        qc.x(i)                       # bit 1 = long
    even, odd = xy_layers(n)
    for g, b in zip(gammas, betas):
        qc.append(PauliEvolutionGate(cost, time=g), range(n))
        for layer in (even, odd):
            for i, j in layer:
                qc.append(PauliEvolutionGate(XY, time=b), [i, j])
    if measure:
        qc.measure_all()
    return qc
```

Notes:

- XX and YY on the same pair commute, so each pair gate is exact. Even and odd layers do not commute with each other, so the order matters (this is a Trotterized ring/path mixer, which is standard).
- A linear chain maps naturally onto the hardware lattice, so routing overhead stays low. A complete-graph mixer is more expressive but much deeper.
- Initial state: `|1..10..0>` is a valid Hamming-weight-K state. Warm starts (Phase 6) replace it with a classical solution.

### Verification (`tests/test_circuits.py`)

```python
from qiskit.quantum_info import Statevector

def test_weight_preserved():
    n, K = 6, 3
    h = np.zeros(n); J = np.triu(np.random.default_rng(1).normal(size=(n, n)), 1)
    qc = qaoa_circuit(h, J, n, K, [0.4, 0.2], [0.7, 0.3], measure=False)
    probs = Statevector(qc).probabilities_dict()
    assert all(k.count('1') == K for k, p in probs.items() if p > 1e-9)
```

Also check the bit-order convention once: pick a state with a known long set, run it through your decoder, and assert the long set comes out right. Qiskit strings are little-endian (rightmost character is qubit 0). Most 'the hardware found a weird answer' bugs live here.

### Hardware sizing (do before spending credits)

Transpile against the Garnet backend and print depth and two-qubit gate count for n = 6, 8, 10 at p = 1, 2. If depth is large, expect the signal to drown in noise; plan hardware runs at p = 1 and n up to about 10, and use simulation for larger n. Keep the existing `--dry-run` flow in `run_on_quantum.py`.

Also keep the Qrisp path: reuse the same Ising `(h_z, J_z)` in `qaoa_solver.py`, and keep its cardinality-preserving mixer. Qrisp is your fast local simulator; Qiskit is your hardware path.

---

## Phase 4. Data expansion and rolling windows

### 4a. More real instruments

The synthetic stress rows are the weakest part of the story. Replace them with real series.

1. **Open `project_data/download_data.py`.** The files are named `*_contract1.xls`, so the URL pattern probably encodes the contract number. Test whether contracts 2 to 4 download with the same pattern. I have not verified the EIA URLs; confirm them in the file and in a browser.
2. **Be aware of the carbon-diversity trap.** Different contract months of the same fuel share one emissions coefficient, so they differ only through price level and covariance. That is useful (many near-ties make the landscape hard) but it will not give the carbon term much to balance. Say so in the docs.
3. **Add other fuels for real carbon diversity.** EIA publishes free spot-price series for items such as Brent, jet fuel, ULSD, propane, and Gulf Coast gasoline, and the emissions workbook you already download (`eia_co2_vol_mass.xlsx`) has coefficients for fuels such as propane, jet fuel, and residual oil. Check each coefficient and unit in the workbook yourself, and extend `MMBTU_PER_UNIT` in `universe.py` with a comment citing the conversion. Label spot series as spot, not futures.
4. Target 8 to 12 real instruments. Add an `asset_type` column (future or spot) to `asset_metadata.csv`.

### 4b. Rolling windows (real statistics instead of one anecdote)

Refactor `load_universe` to accept a date window:

```python
def load_universe(n=4, picks=None, data_dir=None, start=None, end=None):
    ...
    returns = returns.loc[start:end]      # after index_col='date' parsing
    prices = prices.loc[start:end]
```

Then generate instances:

```python
# bench/instances.py
import pandas as pd
from universe import load_universe

def rolling_instances(assets, lookback_days=252, step='M', first='2016-01-01'):
    ends = pd.date_range(first, '2024-04-05', freq='ME')
    for end in ends:
        start = end - pd.Timedelta(days=int(lookback_days * 1.45))
        u = load_universe(picks=assets, start=str(start.date()), end=str(end.date()))
        yield {'end': str(end.date()), 'universe': u}
```

This yields about 100 real instances per asset subset. Also generate instances over random asset subsets of size n = 4, 6, 8, 10, 12 drawn from your real pool (not synthetic copies). Use `freq='M'` if your pandas is older than 2.2.

### 4c. Data card

Write `docs/DATA.md`: source URLs, date range (EIA futures end 2024-04-05), unit conversions, emissions coefficients and their sources, the equal-$1,000 notional convention, and known limitations (continuous contract roll effects, spot vs futures, stationary-covariance assumption).

---

## Phase 5. Benchmark harness

### Layout

```
bench/
  instances.py        # real instances (Phase 4)
  solvers.py          # exact, annealing, tabu, random, qaoa_sim, qaoa_hw
  metrics.py          # gap, success probability, TTS, bootstrap CIs
  run_benchmark.py    # loops instances x solvers x seeds, writes results/
  analyze.py          # tables and plots, writes results/benchmark_summary.json
```

### Common result schema

Every solver returns the same dict so analysis is trivial:

```python
{'solver': 'sa', 'instance': '2019-03-31', 'n': 8, 'K': 4, 'seed': 3,
 'best_energy': ..., 'opt_energy': ..., 'samples': [(energy, count), ...],
 'feasible_rate': 1.0, 'wall_seconds': ..., 'shots_or_steps': ...}
```

### Solvers

- **exact**: `qubo_spin.exact`. Ground truth.
- **random\_feasible**: uniform random K-subsets. This is the fair 'no intelligence' baseline once feasibility is guaranteed by construction.
- **random\_raw**: uniform random bitstrings, feasibility rate `C(n,K)/2^n`. This is the baseline the Garnet feasibility rate must be compared against.
- **simulated annealing** with swap moves that preserve cardinality:

```python
def anneal(m, steps=20000, T0=1.0, T1=0.01, seed=0):
    rng = np.random.default_rng(seed)
    n, K = m['n'], m['K']
    s = -np.ones(n); s[rng.choice(n, K, replace=False)] = 1
    E = energy(s, m); best = (E, s.copy())
    for t in range(steps):
        T = T0 * (T1 / T0) ** (t / steps)
        i = rng.choice(np.flatnonzero(s == 1)); j = rng.choice(np.flatnonzero(s == -1))
        s2 = s.copy(); s2[i], s2[j] = -1, 1
        E2 = energy(s2, m)
        if E2 < E or rng.random() < np.exp((E - E2) / T):
            s, E = s2, E2
            if E < best[0]: best = (E, s.copy())
    return best
```

Scale `T0` and `T1` to the spread of energies on the instance (for example, the standard deviation of random-portfolio energies), not fixed numbers. Add a **tabu search** or greedy-swap local search as a second classical baseline.

- **qaoa\_sim**: your Qiskit circuit on `Statevector` or Aer for exact probabilities, optimizing angles with COBYLA from several starts, p = 1, 2, 3.
- **qaoa\_noisy**: Aer with a noise model. Check `iqm.qiskit_iqm` for fake backends that approximate Garnet; if none fits, build a depolarizing plus readout-error model using published fidelities.
- **qaoa\_hw**: Garnet, cached, only for a few instances (Phase 8).

### Metrics (`metrics.py`)

```python
import numpy as np

def gap(e_found, e_opt, e_random_mean):
    # 0 = optimal, 1 = no better than random
    return (e_found - e_opt) / max(e_random_mean - e_opt, 1e-12)

def p_opt(samples, e_opt, tol=1e-9):
    tot = sum(c for _, c in samples)
    return sum(c for e, c in samples if e <= e_opt + tol) / tot

def tts99(p, shots_per_run):
    if p <= 0: return np.inf
    if p >= 1: return shots_per_run
    return shots_per_run * np.log(0.01) / np.log(1 - p)

def bootstrap_ci(x, f=np.mean, B=2000, seed=0):
    rng = np.random.default_rng(seed); x = np.asarray(x)
    stats = [f(rng.choice(x, len(x))) for _ in range(B)]
    return np.percentile(stats, [2.5, 97.5])
```

Report per solver and per n: median gap, probability of finding the optimum, probability of beating the random-feasible median, TTS99, and wall-clock, each with a bootstrap CI **over instances**. For hardware, also report feasible-shot rate against `random_raw`, and the same metrics after Hamming-weight post-selection.

### Experiment matrix

| Axis | Values |
| --- | --- |
| n assets | 4, 6, 8, 10, 12 (qaoa\_sim up to about 16) |
| instances per n | 30 to 100 rolling windows |
| QAOA depth p | 1, 2, 3 |
| shots (sim) | 4096 |
| seeds | 5 per stochastic solver |

Run the whole matrix with one command (`python -m bench.run_benchmark --config bench/config.yaml`) and make it resumable by skipping instance/solver/seed combinations already in `results/`.

**Expect and plan for this outcome:** classical methods win on time and quality at every size. That is fine. The result table and the honest framing is the deliverable.

---

## Phase 6. Quantum-side improvements

Add one at a time, and re-run the same benchmark subset after each so you can report what each change bought you.

1. **CVaR objective.** Optimize the mean energy of the best `alpha` fraction of samples (alpha around 0.1 to 0.25) instead of the plain mean. It usually raises the probability of sampling good states.

```python
def cvar(energies, probs, alpha=0.2):
    order = np.argsort(energies); acc = 0.0; tot = 0.0
    for k in order:
        take = min(probs[k], alpha - acc)
        tot += take * energies[k]; acc += take
        if acc >= alpha - 1e-12: break
    return tot / alpha
```

2. **Parameter transfer and INTERP.** Optimize angles on a few training instances and reuse them on the rest; this cuts optimizer cost and removes the 'locally tuned angles' criticism. Initialize depth p+1 from a good depth p solution:

```python
def interp(x):                      # x: angles at depth p -> angles at depth p+1
    p = len(x); new = np.zeros(p + 1)
    for i in range(p + 1):
        a = x[i - 1] if i > 0 else 0.0
        b = x[i] if i < p else 0.0
        new[i] = (i * a + (p - i) * b) / p
    return new
```

3. **Warm start.** Run SA (or a greedy swap search), then pass its solution as `init_longs`. Be transparent that this makes the result partly classical, and always show the cold-start result too.
4. **Readout-error mitigation.** For n up to about 10, calibrate with the 2^n basis states (or a tensored per-qubit confusion matrix) and invert it, clipping negatives. Report raw, Hamming-weight post-selected, and mitigated numbers side by side.
5. **Hybrid finish with a fair control.** Take the top samples from QAOA and run a 1-swap local search from each. The control that makes this honest is the same local search started from random portfolios with the same total number of evaluations. If QAOA starts do not beat random starts, say so.

---

## Phase 7. Borsuk-Ulam: pick one honest option

Right now the antipode check is true by construction, because any quadratic form is even under `s -> -s`. Choose:

- **Option A: drop it** from the core claims and keep one slide of motivation.
- **Option B: use it as symmetry breaking.** When `n = 2K` and there are no odd terms, `s` and `-s` have equal energy, so fix `s_0 = +1`. That removes one qubit and halves the search space. Write a test proving the optimal energy is unchanged, and report the saving in qubits and depth.
- **Option C: continuous relaxation story.** With fractional weights, an exactly carbon-balanced hedge exists whenever positive and negative carbon exposures can be mixed (an intermediate-value argument). Integer long/short selection is where hardness enters. Only claim the discrete problem is hard in the weights; do not claim the theorem proves your portfolio exists.

Recommended: B plus one sentence from C. Never write 'Borsuk-Ulam proves'.

---

## Phase 8. Hardware campaign

Decide the budget first (shots and jobs available on Resonance). A sensible plan:

1. Choose 3 instances at each of n = 6, 8, 10, from your rolling set, covering one easy, one medium, one hard case by classical gap spread.
2. For each: dry-run (authenticates, routes, binds, no submission), then 2,000 shots at p = 1 with angles from simulation. Optionally repeat once to estimate run-to-run variation.
3. Save raw counts and a metadata record each time (backend, calibration timestamp if exposed, transpiled depth, two-qubit gate count, angle file, shots, git hash, instance id) with `results/metadata.save`.
4. Decode with the existing `results.py`, adapted to the new one-qubit encoding, then run the same metrics as every other solver.
5. Compare to: random\_raw, random\_feasible, qaoa\_sim (ideal), qaoa\_noisy, SA.

Never resubmit to get a nicer result. If a job is bad, report it and record why. The presentation shows cached results only.

---

## Phase 9. Dashboard and slides

### Dashboard changes

1. Read from `results/benchmark_summary.json` instead of hard-coded values.
2. Add a **Reality check** panel: bars for random, SA, QAOA sim, QAOA noisy, Garnet, showing probability of optimum and feasibility, with CIs.
3. Show **net vs gross exposure** and neutrality ratio.
4. Scaling plot using real windows; label any synthetic point 'synthetic'.
5. Replace the Garnet submit button with **Replay cached Garnet run**. Gate any real submission behind an environment flag such as `ALLOW_HARDWARE=1` plus a confirmation, so nobody triggers it on stage.
6. Fix the inconsistency between the dashboard (231 distinct states) and the report (238); both should be generated from the same result file.

### Slide story (7 slides)

1. Problem: carbon-aware long/short hedging; feasible set grows combinatorially.
2. Pipeline: EIA data to spin model to QAOA to hardware, with verified equivalence tests.
3. Encoding: one qubit per asset, feasibility by construction.
4. Benchmark design: instances, baselines, metrics.
5. Results: one chart with random, SA, sim, noisy, Garnet.
6. Honest limits and what we learned (classical wins at this scale, why).
7. Roadmap: what hardware quality and problem size would change the picture.

### Claims ledger

| Say | Do not say |
| --- | --- |
| End-to-end validated pipeline on real data and real hardware | Quantum advantage |
| Garnet beats uniform random sampling by X (with CI) | Garnet solved the problem better than classical |
| Net exposure reduced by X% vs gross | Carbon-neutral portfolio |
| Symmetry halves the search space | Borsuk-Ulam proves our hedge exists |
| Classical methods solve all tested sizes instantly | Our scaling shows a crossover |

### Questions to rehearse

- *Why use a quantum computer if classical solves it in microseconds?* Because this is a benchmark of where hardware stands; we state the crossover conditions rather than claim one.
- *Is the hardware doing better than random?* Show the numbers and CI against random\_raw and random\_feasible.
- *Why equal weights?* Simplicity for a binary encoding; weighted extension is the roadmap.
- *Is the covariance stable?* No; that is why we use rolling windows and report spread.
- *Why not mitigate errors?* We did, and report raw and mitigated side by side.

---

## Phase 10. Definition of done

- [ ] Token rotated; no secrets in the repo (`git log -p | grep -i token` returns nothing sensitive)
- [ ] `pytest -q` green, including the spin model, circuit weight and decoder tests
- [ ] `docs/DATA.md` written; real vs synthetic clearly labeled
- [ ] At least 8 real instruments and about 100 rolling instances per size
- [ ] Benchmark runs from one command and is resumable; summary JSON committed
- [ ] Exact, random (two kinds), SA, tabu, qaoa\_sim, qaoa\_noisy implemented
- [ ] Hardware results cached with full metadata for at least 6 instances
- [ ] Dashboard reads summary JSON; replay only; wording fixed
- [ ] README updated with the new quick start and the claims ledger
- [ ] Slides rehearsed, including the questions above

### Suggested order if time gets tight

Phases 0 to 3, then 5 on the existing 4 assets, then 4, then 8, then 9. Phase 6 items can be dropped individually; CVaR and the hybrid-with-control are the two worth keeping.
