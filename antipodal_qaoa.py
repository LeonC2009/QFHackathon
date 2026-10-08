"""
Antipodal carbon hedge: QUBO -> Ising -> QAOA in PennyLane.

Binary variables (2N of them):  v = [x_0..x_{N-1}, y_0..y_{N-1}]
    x_i = 1 -> long asset i      y_i = 1 -> short asset i
Net exposure vector:  w = x - y   (in {-1, 0, 1}^N)

The antipodal map is A(x, y) = (y, x)  <=>  w -> -w.
  * "even" terms (carbon balance, covariance, cardinality, exclusivity) are
    invariant under A  -> ground states come in antipodal pairs.
  * "odd" terms (tilt / carry) are the only thing that breaks the symmetry.

Run:  pip install pennylane numpy   then   python antipodal_qaoa.py
NOTE: emission factors are approximate EPA values; prices/vols/correlations
are SYNTHETIC / illustrative, not real market data.
"""
import itertools
import numpy as np

# --------------------------------------------------------------------------
# 1. Universe: pure fossil-energy futures (synthetic market data)
# --------------------------------------------------------------------------
ASSETS = ["Brent", "WTI", "HeatOil", "TTF Gas", "HH Gas", "API2 Coal"]
# CO2 emission factors, kg CO2 per MMBtu burned (approx. EPA values)
EF = np.array([74.5, 74.5, 74.0, 53.1, 53.1, 93.3])
CARBON = EF / EF.max()          # normalised to [0, 1]
# NOTE: real contracts need notional conversion (bbl / MWh / tonne -> MMBtu -> CO2)
# synthetic expected carry per asset (for the optional odd term)
MU = np.array([0.02, 0.02, 0.01, 0.03, 0.02, -0.01])
N = len(ASSETS)
K = 2  # longs == shorts == K

# synthetic covariance: annualised vols x a block correlation structure
#                Brent  WTI  HeatOil TTF   HH   Coal
VOL = np.array([0.30, 0.32, 0.30, 0.55, 0.50, 0.40])
CORR = np.array([
    [1.00, 0.95, 0.85, 0.45, 0.35, 0.40],
    [0.95, 1.00, 0.83, 0.43, 0.40, 0.38],
    [0.85, 0.83, 1.00, 0.42, 0.33, 0.37],
    [0.45, 0.43, 0.42, 1.00, 0.40, 0.70],
    [0.35, 0.40, 0.33, 0.40, 1.00, 0.30],
    [0.40, 0.38, 0.37, 0.70, 0.30, 1.00],
])
SIGMA = np.outer(VOL, VOL) * CORR
assert np.linalg.eigvalsh(SIGMA).min() > 0, "covariance must be PSD"


# --------------------------------------------------------------------------
# 2. QUBO   E(v) = v^T Q v + offset      (linear terms live on the diagonal)
# --------------------------------------------------------------------------
def build_qubo(A=10.0, B=1.0, P_card=4.0, P_excl=4.0, tau=0.0, lam=0.0):
    """
    A      carbon balance      A * (c.x - c.y)^2
    B      covariance          B * w^T Sigma w         (market-direction risk)
    P_card cardinality         P * [(sum x - K)^2 + (sum y - K)^2]
    P_excl exclusivity         P * sum_i x_i y_i       (no long+short same asset)
    tau    odd carbon tilt     tau * c.w   (prefers long lower-carbon fuel / short higher-carbon fuel)
    lam    odd carry reward    -lam * mu.w
    """
    n = 2 * N
    D = np.hstack([np.eye(N), -np.eye(N)])  # w = D v
    Q = np.zeros((n, n))
    offset = 0.0

    # even: carbon balance + covariance
    Q += A * D.T @ np.outer(CARBON, CARBON) @ D
    Q += B * D.T @ SIGMA @ D

    # even: cardinality  P (1.s - K)^2 = P (s s^T) - 2PK s + PK^2   (v^2 = v)
    for block in (slice(0, N), slice(N, n)):
        Q[block, block] += P_card * np.ones((N, N))
        Q[np.arange(block.start, block.stop), np.arange(block.start, block.stop)] += -2 * P_card * K
        offset += P_card * K**2

    # even: exclusivity
    for i in range(N):
        Q[i, N + i] += P_excl / 2
        Q[N + i, i] += P_excl / 2

    # odd: tilt / carry (linear in w -> linear in v -> diagonal)
    g = tau * CARBON - lam * MU
    Q[np.arange(n), np.arange(n)] += np.concatenate([g, -g])

    return Q, offset


def qubo_energy(v, Q, offset):
    v = np.asarray(v, float)
    return float(v @ Q @ v + offset)


def brute_force(Q, offset):
    n = Q.shape[0]
    best = []
    for bits in itertools.product([0, 1], repeat=n):
        best.append((qubo_energy(bits, Q, offset), bits))
    best.sort(key=lambda t: t[0])
    return best


# --------------------------------------------------------------------------
# 3. QUBO -> Ising   (v_i = (1 - z_i)/2,  z_i = <Z_i> in {+1,-1})
#    E = const + sum_i h_i Z_i + sum_{i<j} J_ij Z_i Z_j
# --------------------------------------------------------------------------
def qubo_to_ising(Q, offset):
    Qs = (Q + Q.T) / 2
    n = Q.shape[0]
    ones = np.ones(n)
    h = -0.5 * Qs @ ones
    J = {(i, j): 0.5 * Qs[i, j] for i in range(n) for j in range(i + 1, n) if abs(Qs[i, j]) > 1e-12}
    const = offset + 0.25 * (ones @ Qs @ ones + np.trace(Qs))
    return h, J, const


def ising_energy(bits, h, J, const):
    z = 1 - 2 * np.asarray(bits, float)
    return const + h @ z + sum(Jij * z[i] * z[j] for (i, j), Jij in J.items())


# --------------------------------------------------------------------------
# 4. Decode / report helpers
# --------------------------------------------------------------------------
def decode(bits):
    x, y = np.array(bits[:N]), np.array(bits[N:])
    longs = [ASSETS[i] for i in range(N) if x[i]]
    shorts = [ASSETS[i] for i in range(N) if y[i]]
    net_carbon = float(CARBON @ (x - y))
    return longs, shorts, net_carbon


def antipode(bits):
    """Borsuk-Ulam style antipodal map on the discrete problem: swap long <-> short."""
    return tuple(bits[N:]) + tuple(bits[:N])


# --------------------------------------------------------------------------
# 5. QAOA in PennyLane
# --------------------------------------------------------------------------
def run_qaoa(h, J, const, Q, offset, p=3, steps=120, lr=0.05, seed=0):
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
            for i in range(n):                               # e^{-i gamma h_i Z_i}
                qml.RZ(2 * gamma * hs[i], wires=i)
            for (i, j), Jij in Js.items():                   # e^{-i gamma J_ij Z_i Z_j}
                qml.IsingZZ(2 * gamma * Jij, wires=[i, j])
            for i in range(n):                               # mixer e^{-i beta X_i}
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
            print(f"  step {s:3d}   <E> = {history[-1]:8.4f}")

    pr = np.array(probs(params))
    return pr, history


# --------------------------------------------------------------------------
# 6. Continuous Borsuk-Ulam sanity demo on S^1 (placeholder for the BU module)
#    f(w) = c . w for w = (cos t, sin t) over a (gas, coal) pair.
#    g(t) = f(t) - f(t + pi) is ODD, so it changes sign -> a root exists
#    -> f(w) = f(-w) -> (for linear f) net carbon exposure 0.
# --------------------------------------------------------------------------
def borsuk_ulam_circle(c_clean=53.1 / 93.3, c_dirty=1.0, tol=1e-10):  # gas vs coal
    f = lambda t: c_clean * np.cos(t) + c_dirty * np.sin(t)
    g = lambda t: f(t) - f(t + np.pi)
    lo, hi = 0.0, np.pi  # g(0) and g(pi) have opposite signs since g(t+pi) = -g(t)
    while hi - lo > tol:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if np.sign(g(mid)) == np.sign(g(lo)) else (lo, mid)
    t = (lo + hi) / 2
    return t, np.array([np.cos(t), np.sin(t)])  # weight ratio gas:coal that nets to zero


# --------------------------------------------------------------------------
if __name__ == "__main__":
    # --- symmetric (pure antipodal) problem
    Q, off = build_qubo(tau=0.0, lam=0.0)
    ranked = brute_force(Q, off)
    e0, v0 = ranked[0]
    print("Brute-force ground energy:", round(e0, 4))
    print("  antipode has same energy? ",
          np.isclose(qubo_energy(antipode(v0), Q, off), e0), "->", decode(antipode(v0)))

    # --- break the symmetry with a small odd tilt, then solve with QAOA
    Q, off = build_qubo(tau=0.3, lam=0.5)
    h, J, const = qubo_to_ising(Q, off)
    ranked = brute_force(Q, off)
    e_opt, v_opt = ranked[0]
    print("\nIsing/QUBO consistency check:",
          np.isclose(ising_energy(v_opt, h, J, const), e_opt))
    print("Optimum:", decode(v_opt), "E =", round(e_opt, 4))

    print(f"\nQAOA on {2 * N} qubits ...")
    pr, hist = run_qaoa(h, J, const, Q, off, p=3, steps=120)

    top = np.argsort(pr)[::-1][:5]
    print("\nTop sampled bitstrings:")
    for idx in top:
        bits = tuple(int(b) for b in format(idx, f"0{2 * N}b"))
        L, S, nc = decode(bits)
        print(f"  p={pr[idx]:.3f}  E={qubo_energy(bits, Q, off):7.3f}  long={L} short={S} net_carbon={nc:+.3f}")
    opt_idx = int("".join(map(str, v_opt)), 2)
    print(f"\nP(optimal bitstring) = {pr[opt_idx]:.3f}   (uniform would be {1 / 2 ** (2 * N):.4f})")

    t, w = borsuk_ulam_circle()
    print(f"\nContinuous B-U demo: theta*={t:.4f}, weights gas:coal = {w[0]:+.3f}:{w[1]:+.3f}")
