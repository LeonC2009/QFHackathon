"""Qrisp QAOA adapter for the canonical QUBO model."""

from __future__ import annotations

import numpy as np

from qubo import qubo_to_ising


def run_qaoa(
    q,
    constant=0.0,
    p=1,
    steps=10,
    shots=512,
    asset_count=None,
    long_count=None,
    short_count=None,
    verbose=True,
):
    """Run Qrisp QAOA and return ``(counts, history)``."""
    from qrisp import QuantumArray, QuantumVariable, gphase, rz, rzz, x
    from qrisp.alg_primitives import dicke_state
    from qrisp.qaoa import QAOAProblem, RX_mixer, portfolio_mixer

    constrained = (
        asset_count is not None
        and long_count is not None
        and short_count is not None
        and asset_count == 2 * long_count
        and long_count == short_count
    )

    fields, couplings, ising_constant = qubo_to_ising(q, constant)
    scale = max(
        float(np.max(np.abs(fields))),
        max((abs(value) for value in couplings.values()), default=0.0),
        1.0,
    )
    scaled_fields = fields / scale
    scaled_couplings = {key: value / scale for key, value in couplings.items()}

    def cost_operator(qv, gamma):
        qubits = (
            [qv[0][index] for index in range(asset_count)]
            + [qv[1][index] for index in range(asset_count)]
            if constrained
            else qv
        )
        gphase(-gamma * ising_constant / scale, qubits[0])
        for index, field in enumerate(scaled_fields):
            if field:
                rz(2 * gamma * field, qubits[index])
        for (i, j), coupling in scaled_couplings.items():
            if coupling:
                rzz(2 * gamma * coupling, qubits[i], qubits[j])

    def classical_cost(counts):
        total = 0.0
        for bitstring, count in counts.items():
            if hasattr(bitstring, "flatten"):
                bitstring = "".join(str(bit) for bit in bitstring.flatten())
            bits = np.fromiter((int(bit) for bit in str(bitstring)), dtype=float)
            total += float(bits @ q @ bits + constant) * count
        return total

    if constrained:
        def make_qarg():
            return QuantumArray(QuantumVariable(asset_count), shape=(2,))

        def init_function(qarg):
            for index in range(long_count):
                x(qarg[0][index])
            for index in range(short_count):
                x(qarg[1][index])
            dicke_state(qarg[0], long_count)
            dicke_state(qarg[1], short_count)

        qarg = make_qarg
        mixer = portfolio_mixer()
        init = init_function
    else:
        qarg = QuantumVariable(len(fields))
        mixer = RX_mixer
        init = None

    problem = QAOAProblem(
        cost_operator=cost_operator,
        mixer=mixer,
        cl_cost_function=classical_cost,
        init_function=init,
    )
    result = problem.run(
        qarg,
        depth=p,
        mes_kwargs={"shots": shots},
        max_iter=max(steps, 2 * p + 2),
    )
    counts = {}
    for bitstring, probability in result.items():
        if hasattr(bitstring, "flatten"):
            bitstring = "".join(str(bit) for bit in bitstring.flatten())
        counts[str(bitstring)] = float(probability)
    if verbose:
        print(f"Qrisp QAOA completed: {len(counts)} bitstrings, {shots} shots")
    return counts, [float(classical_cost(counts)) / max(sum(counts.values()), 1.0)]
