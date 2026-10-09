"""Qrisp QAOA adapter for the canonical QUBO model."""

from __future__ import annotations

import numpy as np

from qubo import qubo_to_ising


def run_qaoa(q, constant=0.0, p=1, steps=10, shots=512, verbose=True):
    """Run Qrisp QAOA and return ``(counts, history)``."""
    from qrisp import QuantumVariable, gphase, rz, rzz
    from qrisp.qaoa import QAOAProblem, RX_mixer

    fields, couplings, ising_constant = qubo_to_ising(q, constant)
    scale = max(
        float(np.max(np.abs(fields))),
        max((abs(value) for value in couplings.values()), default=0.0),
        1.0,
    )
    scaled_fields = fields / scale
    scaled_couplings = {key: value / scale for key, value in couplings.items()}

    def cost_operator(qv, gamma):
        gphase(-gamma * ising_constant / scale, qv[0])
        for index, field in enumerate(scaled_fields):
            if field:
                rz(2 * gamma * field, qv[index])
        for (i, j), coupling in scaled_couplings.items():
            if coupling:
                rzz(2 * gamma * coupling, qv[i], qv[j])

    def classical_cost(counts):
        total = 0.0
        for bitstring, count in counts.items():
            bits = np.fromiter((int(bit) for bit in str(bitstring)), dtype=float)
            total += float(bits @ q @ bits + constant) * count
        return total

    problem = QAOAProblem(
        cost_operator=cost_operator,
        mixer=RX_mixer,
        cl_cost_function=classical_cost,
    )
    result = problem.run(
        QuantumVariable(len(fields)),
        depth=p,
        mes_kwargs={"shots": shots},
        max_iter=max(steps, 2 * p + 2),
    )
    counts = {str(bitstring): float(probability) for bitstring, probability in result.items()}
    if verbose:
        print(f"Qrisp QAOA completed: {len(counts)} bitstrings, {shots} shots")
    return counts, [float(classical_cost(counts)) / max(sum(counts.values()), 1.0)]
