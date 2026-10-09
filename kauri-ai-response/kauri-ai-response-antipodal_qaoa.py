"""
Antipodal carbon hedge on energy futures: load QUBO -> Ising -> QAOA (PennyLane).

Inputs (written by matrix.py, same folder by default):
    Q.npy              (2N x 2N) QUBO matrix, E(v) = v^T Q v
    qubit_labels.json  2N labels, qubit i <-> labels[i]: first N are "long_<contract>",
                       last N are "short_<contract>" (same contract order)

Binary variables: v = [x_0..x_{N-1}, y_0..y_{N-1}]
    x_i = 1 -> long contract i        y_i = 1 -> short contract i
Net exposure: w = x - y.   Antipodal map A(x, y) = (y, x)  <=>  w -> -w.

Run:  pip install pennylane numpy
      python antipodal_qaoa.py                       # defaults: Q.npy, qubit_labels.json
      python antipodal_qaoa.py --p 2 --steps 80      # lighter QAOA
      python antipodal_qaoa.py --no-qaoa             # brute force + antipodal check only

NOTE: Q.npy has no constant term (matrix.py drops it), so energies here are
relative; only the ordering / differences between bitstrings matter.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

# Optional: CO2 emission factors (kg CO2 / MMBtu, approx. EPA) used ONLY for the
# net-carbon readout when a label matches one of these names. Add your contracts here.
EMISSION_FACTORS = {
    "Brent": 74.5, "WTI": 74.5, "HeatOil": 74.0,
    "TTF Gas": 53.1, "HH Gas": 53.1, "API2 Coal": 93.3,
}


# --------------------------------------------------------------------------
# 1. Load Q and labels
# --------------------------------------------------------------------------
def load_problem(q_path, labels_path):
    Q = np.load(q_path)
    with open(labels_path) as f:
        labels = json.load(f)

    n = Q.shape[0]
    if Q.ndim != 2 or Q.shape[0] != Q.shape[1]:
        raise ValueError(f"Q must be square, got shape {Q.shape}")
    if len(labels) != n:
        raise ValueError(f"{len(labels)} labels but Q is {n}x{n}")
    if n % 2:
        raise ValueError(f"Q has odd size {n}; expected 2N (N longs + N shorts)")

    N = n // 2
    longs, shorts = labels[:N], labels[N:]
    if not all(s.startswith("long_") for s in longs) or not all(s.startswith("short_") for s in shorts):
        raise ValueError("labels must be N 'long_<name>' followed by N 'short_<name>'")
    names = [s[len("long_"):] for s in longs]
    if names != [s[len("short_"):] for s in shorts]:
        raise ValueError("long_ and short_ labels must list the same contracts in the same order")

    Q = (Q + Q.T) / 2  # same energies, symmetric form
    return Q, names, N


def qubo_energy(v, Q):
    v = np.asarray(v, float)
    return float(v @ Q @ v)


def brute_force(Q, top=10, chunk_bits=16):
    """Exact ranking over all 2^n bitstrings, vectorised in chunks (fine up to ~22 qubits)."""
    n = Q.shape[0]
    total = 1 << n
    size = 1 << min(n, chunk_bits)
    shifts = np.arange(n - 1, -1, -1)  # bit 0 of the string = most significant (matches PennyLane)
    best = []
    for start in range(0, total, size):
        idx = np.arange(start, min(start + size, total))
        V = ((idx[:, None] >> shifts) & 1).astype(float)
        E = np.einsum("ij,jk,ik->i", V, Q, V)
        k = min(top, len(E))
        sel = np.argpartition(E, k - 1)[:k]
        best += [(float(E[s]), tuple(int(b) for b in V[s])) for s in sel]
    best.sort(key=lambda t: t[0])
    return best[:top]


# --------------------------------------------------------------------------
# 2. QUBO -> Ising (v_i = (1 - z_i)/2):  E = const + sum h_i Z_i + sum_{i<j} J_ij Z_i Z_j
# --------------------------------------------------------------------------
def qubo_to_ising(Q):
    n = Q.shape[0]
    ones = np.ones(n)
    h = -0.5 * Q @ ones
    J = {(i, j): 0.5 * Q[i, j] for i in range(n) for j in range(i + 1, n) if abs(Q[i, j]) > 1e-12}
    const = 0.25 * (ones @ Q @ ones + np.trace(Q))
    return h, J, const


def ising_energy(bits, h, J, const):
    z = 1 - 2 * np.asarray(bits, float)
    return const + h @ z + sum(Jij * z[i] * z[j] for (i, j), Jij in J.items())


# --------------------------------------------------------------------------
# 3. Decode / report helpers
# --------------------------------------------------------------------------
def decode(bits, names):
    N = len(names)
    x, y = np.array(bits[:N]), np.array(bits[N:])
    longs = [names[i] for i in range(N) if x[i]]
    shorts = [names[i] for i in range(N) if y[i]]
    overlap = [names[i] for i in range(N) if x[i] and y[i]]
    net_carbon = None
    if all(nm in EMISSION_FACTORS for nm in names):
        ef = np.array([EMISSION_FACTORS[nm] for nm in names])
        net_carbon = float((ef / ef.max()) @ (x - y))
    return longs, shorts, overlap, net_carbon


def antipode(bits):
    """Antipodal map on the discrete problem: swap long <-> short."""
    N = len(bits) // 2
    return tuple(bits[N:]) + tuple(bits[:N])


def describe(bits, names, Q):
    L, S, ov, nc = decode(bits, names)
    carbon = f" net_carbon={nc:+.3f}" if nc is not None else ""
    flag = "" if (len(L) == len(S) and not ov) else "  [constraint violated]"
    return f"E={qubo_energy(bits, Q):8.3f} long={L} short={S}{carbon}{flag}"


# --------------------------------------------------------------------------
# 4. QAOA in PennyLane
# --------------------------------------------------------------------------
def run_qaoa(h, J, const, p=3, steps=120, lr=0.05, seed=0):
    import pennylane as qml
    from pennylane import numpy as pnp

    n = len(h)
    scale = max(np.abs(h).max(), max(abs(v) for v in J.values()))  # keeps angles O(1)
    hs = h / scale
    Js = {k: v / scale for k, v in J.items()}

    dev = qml.device("default.qubit", wires=n)
    ops = [qml.PauliZ(i) for i in range(n)] + [qml.PauliZ(i) @ qml.PauliZ(j) for (i, j) in Js]
    coeffs = [float(c) for c in hs] + [float(c) for c in Js.values()]
    H = qml.dot(coeffs, ops)

    def ansatz(params):
        for i in range(n):
            qml.Hadamard(wires=i)
        for layer in range(p):
            gamma, beta = params[0][layer], params[1][layer]
            for i in range(n):  # e^{-i gamma h_i Z_i}
                qml.RZ(2 * gamma * hs[i], wires=i)
            for (i, j), Jij in Js.items():  # e^{-i gamma J_ij Z_i Z_j}
                qml.IsingZZ(2 * gamma * Jij, wires=[i, j])
            for i in range(n):  # mixer e^{-i beta X_i}
                qml.RX(2 * beta, wires=i)

    @qml.qnode(dev, diff_method="backprop")
    def cost(params):
        ansatz(params)
        return qml.expval(H)

    @qml.qnode(dev)
    def probs(params):
        ansatz(params)
        return qml.probs(wires=range(n))

    rng = np.random.default_rng(seed)
    init = np.stack([np.linspace(0.1, 0.6, p), np.linspace(0.6, 0.1, p)])
    params = pnp.array(init + rng.normal(0, 0.02, init.shape), requires_grad=True)
    opt = qml.AdamOptimizer(stepsize=lr)

    history = []
    for s in range(steps):
        params, c = opt.step_and_cost(cost, params)
        history.append(float(c) * scale + const)
        if s % 20 == 0:
            print(f"  step {s:3d} <E> = {history[-1]:8.4f}")
    return np.array(probs(params)), history


# --------------------------------------------------------------------------
# 5. Main
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--q", default="Q.npy")
    ap.add_argument("--labels", default="qubit_labels.json")
    ap.add_argument("--p", type=int, default=3, help="QAOA layers")
    ap.add_argument("--steps", type=int, default=120, help="optimiser steps")
    ap.add_argument("--no-qaoa", action="store_true", help="skip QAOA (brute force only)")
    ap.add_argument("--garnet", action="store_true",
                    help="sample the QAOA circuit on IQM Garnet (needs IQM_TOKEN; see garnet_qaoa.py)")
    ap.add_argument("--shots", type=int, default=4000, help="shots on Garnet")
    args = ap.parse_args()

    for path in (args.q, args.labels):
        if not Path(path).exists():
            sys.exit(f"Missing {path}. Run matrix.py first (or pass --q / --labels).")

    Q, names, N = load_problem(args.q, args.labels)
    n = 2 * N
    print(f"Loaded Q {Q.shape} for {N} contracts: {names}")

    # --- exact solution + antipodal symmetry diagnostic
    ranked = brute_force(Q, top=5)
    e0, v0 = ranked[0]
    print("\nBrute-force top 5:")
    for e, v in ranked:
        print(" ", describe(v, names, Q))
    sym = np.isclose(qubo_energy(antipode(v0), Q), e0)
    print(f"\nAntipode of the optimum has the same energy? {sym}")
    if not sym:
        print("  -> Q contains odd (linear return/carbon) terms that break the long<->short symmetry.")

    # --- Ising consistency check
    h, J, const = qubo_to_ising(Q)
    print("Ising/QUBO consistency check:", np.isclose(ising_energy(v0, h, J, const), e0))

    if args.no_qaoa:
        return
    if n > 16:
        print(f"\nWARNING: {n} qubits - statevector QAOA will be slow and memory hungry; "
              "consider --p 1 --steps 40 or --no-qaoa.")

    print(f"\nQAOA on {n} qubits (p={args.p}, steps={args.steps}) ...")
    if args.garnet:
        from garnet_qaoa import run_qaoa_garnet
        pr, hist = run_qaoa_garnet(h, J, const, p=args.p, steps=args.steps, shots=args.shots)
    else:
        pr, hist = run_qaoa(h, J, const, p=args.p, steps=args.steps)
    print("\nTop sampled bitstrings:")
    for idx in np.argsort(pr)[::-1][:5]:
        bits = tuple(int(b) for b in format(idx, f"0{n}b"))
        print(f"  p={pr[idx]:.3f} {describe(bits, names, Q)}")
    opt_idx = int("".join(map(str, v0)), 2)
    print(f"\nP(optimal bitstring) = {pr[opt_idx]:.3f} (uniform would be {1 / 2 ** n:.6f})")


if __name__ == "__main__":
    main()
