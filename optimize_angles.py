"""Optimize QAOA angles locally before an IQM hardware submission."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from qiskit.circuit.library import QAOAAnsatz
from qiskit.quantum_info import Statevector
from scipy.optimize import minimize

from run_on_quantum import (
    build_constraint_initial_state,
    build_constraint_mixer,
    load_hamiltonian,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=Path("project_data/data/optimization_model.json"))
    parser.add_argument("--output", type=Path, default=Path("project_data/data/qaoa_angles.json"))
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--maxiter", type=int, default=80)
    args = parser.parse_args()

    hamiltonian, model = load_hamiltonian(args.model)
    scale = max(float(np.max(np.abs(hamiltonian.coeffs))), 1.0)
    hamiltonian = hamiltonian * (1.0 / scale)
    asset_count = len(model["assets"])
    long_count = int(model.get("long_count", 2))
    short_count = int(model.get("short_count", long_count))
    circuit = QAOAAnsatz(
        cost_operator=hamiltonian,
        mixer_operator=build_constraint_mixer(
            len(model["ising_fields"]), asset_count, long_count, short_count
        ),
        initial_state=build_constraint_initial_state(
            len(model["ising_fields"]), asset_count, long_count, short_count
        ),
        reps=args.reps,
    )
    parameters = list(circuit.parameters)

    def energy(values: np.ndarray) -> float:
        bound = circuit.assign_parameters(dict(zip(parameters, values)))
        return float(np.real(Statevector.from_instruction(bound).expectation_value(hamiltonian)))

    initial = np.tile([0.5, 0.5], args.reps)
    optimized = minimize(
        energy,
        initial,
        method="COBYLA",
        options={"maxiter": args.maxiter, "rhobeg": 0.5, "tol": 1e-4},
    )
    result = {
        "reps": args.reps,
        "parameters": [str(parameter) for parameter in parameters],
        "angles": [float(value) for value in optimized.x],
        "scaled_energy": float(optimized.fun),
        "hamiltonian_scale": scale,
        "success": bool(optimized.success),
        "iterations": int(optimized.nfev),
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
