#!/usr/bin/env python3
"""Run a small Qrisp QAOA experiment for the exported portfolio QUBO."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from qrisp import QuantumVariable, gphase, rz, rzz
from qrisp.qaoa import QAOAProblem, RX_mixer


MODEL_PATH = Path("data/optimization_model.json")
DEPTH = 1
SHOTS = 256
MAX_ITER = 10


def load_model() -> tuple[np.ndarray, list[str], dict[str, object]]:
    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    return (
        np.array(model["qubo_matrix"], dtype=float),
        model["variable_order"],
        model,
    )


def make_cost_operator(q: np.ndarray):
    """Create the QUBO phase separator, equivalent to its Ising form."""
    def cost_operator(qv, gamma):
        gamma = gamma / np.sqrt(np.linalg.norm(q))
        gphase(-gamma / 4 * (np.sum(q) + np.trace(q)), qv[0])

        for i in range(len(q)):
            rz(-gamma / 2 * (np.sum(q[i]) + np.sum(q[:, i])), qv[i])
            for j in range(i + 1, len(q)):
                if q[i, j] != 0:
                    rzz(gamma / 2 * q[i, j], qv[i], qv[j])

    return cost_operator


def make_classical_cost(q: np.ndarray):
    def classical_cost(counts):
        return sum(
            float(np.array(list(bitstring), dtype=int) @ q @ np.array(list(bitstring), dtype=int))
            * count
            for bitstring, count in counts.items()
        )

    return classical_cost


def main() -> None:
    q, variable_order, model = load_model()
    problem = QAOAProblem(
        cost_operator=make_cost_operator(q),
        mixer=RX_mixer,
        cl_cost_function=make_classical_cost(q),
    )
    counts = problem.run(
        QuantumVariable(len(q)),
        depth=DEPTH,
        mes_kwargs={"shots": SHOTS},
        max_iter=MAX_ITER,
    )

    ranked = sorted(
        ((float(np.array(list(bitstring), dtype=int) @ q @ np.array(list(bitstring), dtype=int)), bitstring, probability)
         for bitstring, probability in counts.items()),
        key=lambda result: result[0],
    )
    best_cost, best_bitstring, best_probability = ranked[0]
    best_bits = np.array(list(best_bitstring), dtype=float)
    asset_count = len(variable_order) // 2
    signed = best_bits[:asset_count] - best_bits[asset_count:]
    carbon = np.array(model["carbon_exposure_kg_per_position"])
    covariance = np.array(model["covariance"])
    result = {
        "depth": DEPTH,
        "shots": SHOTS,
        "max_iter": MAX_ITER,
        "variable_order": variable_order,
        "best_bitstring": best_bitstring,
        "best_qubo_cost": best_cost,
        "best_objective": best_cost + model["qubo_constant"],
        "carbon_exposure": float(signed @ carbon),
        "financial_risk": float(signed @ covariance @ signed),
        "long": [asset[2:] for asset, bit in zip(variable_order[:asset_count], best_bits[:asset_count]) if bit],
        "short": [asset[2:] for asset, bit in zip(variable_order[asset_count:], best_bits[asset_count:]) if bit],
        "best_probability": best_probability,
        "exact_classical_optimum": model["exact_classical_optimum"],
    }
    Path("data/qaoa_result.json").write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()