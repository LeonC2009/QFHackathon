"""Submit the canonical Ising Hamiltonian to IQM Resonance/Garnet.

Set RESONANCE_API_TOKEN in the shell. IQM_TOKEN remains supported as a fallback.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from qiskit import QuantumCircuit, transpile
from qiskit.circuit.library import QAOAAnsatz
from qiskit.quantum_info import SparsePauliOp
from iqm.qiskit_iqm import IQMProvider

from results.decoder import summarize_measurements


DEFAULT_MODEL = Path("project_data/data/optimization_model.json")
DEFAULT_ANGLES = Path("project_data/data/qaoa_angles.json")


def load_hamiltonian(model_path: Path) -> tuple[SparsePauliOp, dict]:
    model = json.loads(model_path.read_text(encoding="utf-8"))
    fields = model["ising_fields"]
    couplings = {
        tuple(int(index) for index in key.split(",")): value
        for key, value in model["ising_couplings"].items()
    }
    width = len(fields)
    terms = []
    for index, coefficient in enumerate(fields):
        if coefficient:
            pauli = ["I"] * width
            pauli[width - 1 - index] = "Z"
            terms.append(("".join(pauli), coefficient))
    for (i, j), coefficient in couplings.items():
        if coefficient:
            pauli = ["I"] * width
            pauli[width - 1 - i] = "Z"
            pauli[width - 1 - j] = "Z"
            terms.append(("".join(pauli), coefficient))
    return SparsePauliOp.from_list(terms), model


def build_constraint_mixer(width: int, asset_count: int, long_count: int, short_count: int):
    """Build block-local XX+YY terms that preserve long/short cardinality."""
    terms = []
    for start, count in ((0, long_count), (asset_count, short_count)):
        for offset in range(asset_count):
            i = start + offset
            j = start + ((offset + 1) % asset_count)
            if i == j:
                continue
            for pauli in ("X", "Y"):
                word = ["I"] * width
                word[width - 1 - i] = pauli
                word[width - 1 - j] = pauli
                terms.append(("".join(word), 0.5))
    return SparsePauliOp.from_list(terms).simplify()


def build_constraint_initial_state(width: int, asset_count: int, long_count: int, short_count: int):
    initial = QuantumCircuit(width)
    for index in range(long_count):
        initial.x(index)
    for index in range(short_count):
        initial.x(asset_count + index)
    return initial


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--shots", type=int, default=1000)
    parser.add_argument("--angles", type=Path, default=DEFAULT_ANGLES)
    parser.add_argument("--dry-run", action="store_true", help="route and bind the circuit without submitting it")
    args = parser.parse_args()

    token = os.environ.get("RESONANCE_API_TOKEN") or os.environ.get("IQM_TOKEN")
    if not token:
        raise SystemExit("Set RESONANCE_API_TOKEN in the shell before using IQM Resonance")
    url = os.environ.get("IQM_URL", "https://resonance.iqm.tech")
    backend_name = os.environ.get("IQM_BACKEND", "garnet")

    hamiltonian, model = load_hamiltonian(args.model)
    scale = max(float(max(abs(value) for value in hamiltonian.coeffs)), 1.0)
    hamiltonian = hamiltonian * (1.0 / scale)
    asset_count = len(model["assets"])
    long_count = int(model.get("long_count", 2))
    short_count = int(model.get("short_count", long_count))
    provider = IQMProvider(url, quantum_computer=backend_name, token=token)
    backend = provider.get_backend(backend_name)
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
    circuit.measure_all()
    transpiled = transpile(circuit, backend=backend, optimization_level=3)
    if args.angles.exists():
        angle_data = json.loads(args.angles.read_text(encoding="utf-8"))
        if int(angle_data["reps"]) != args.reps:
            raise SystemExit(f"Angle file reps={angle_data['reps']} does not match --reps={args.reps}")
        angles = [float(value) for value in angle_data["angles"]]
    else:
        angles = [0.5] * len(transpiled.parameters)
    if len(angles) != len(transpiled.parameters):
        raise SystemExit("The angle count does not match the transpiled QAOA circuit")
    bound = transpiled.assign_parameters(dict(zip(transpiled.parameters, angles)))

    if args.dry_run:
        print(f"IQM dry run OK: {backend.name}, {len(model['assets']) * 2} qubits, {len(angles)} angles bound")
        return

    print(f"Submitting {len(model['assets']) * 2} qubits to {backend.name}...")
    result = backend.run(bound, shots=args.shots).result()
    counts = result.get_counts()
    Path("iqm_raw_results.json").write_text(json.dumps(counts, indent=2) + "\n", encoding="utf-8")
    summary = summarize_measurements(
        counts,
        model,
        long_count=long_count,
        short_count=short_count,
    )
    Path("iqm_result.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("Saved IQM counts to iqm_raw_results.json")
    print("Saved decoded IQM result to iqm_result.json")
    if summary["best_feasible"] is None:
        print("No feasible portfolio was measured")
    else:
        best = summary["best_feasible"]
        print(
            f"Best feasible portfolio: long={best['long']} short={best['short']} "
            f"energy={best['energy']:.6f} probability={best['probability']:.3f}"
        )
        print(f"Feasible probability: {summary['feasible_probability']:.3f}")


if __name__ == "__main__":
    main()
