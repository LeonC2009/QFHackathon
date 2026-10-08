"""Step 4 - QAOA on the Ising Hamiltonian (PennyLane)."""
import numpy as np


def run_qaoa(h, J, const, p=3, steps=120, lr=0.05, seed=0, verbose=True):
    """Returns (probabilities over all 2^n bitstrings, energy history)."""
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
            for i in range(n):
                qml.RZ(2 * gamma * hs[i], wires=i)
            for (i, j), Jij in Js.items():
                qml.IsingZZ(2 * gamma * Jij, wires=[i, j])
            for i in range(n):
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
        if verbose and s % 20 == 0:
            print(f"  step {s:3d}  <E> = {history[-1]:8.4f}")

    return np.array(probs(params)), history
