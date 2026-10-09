"""Submit the canonical Ising Hamiltonian to IQM Resonance/Garnet.

Set IQM_TOKEN in the shell. The token is never stored in the repository.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from qiskit import transpile
from qiskit.circuit.library import QAOAAnsatz
from qiskit.quantum_info import SparsePauliOp
from iqm.qiskit_iqm import IQMProvider


DEFAULT_MODEL = Path("aayush-ai-response/data/optimization_model.json")


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--shots", type=int, default=1000)
    args = parser.parse_args()

    token = os.environ.get("IQM_TOKEN")
    if not token:
        raise SystemExit("Set IQM_TOKEN in the shell before submitting to IQM Resonance")
    url = os.environ.get("IQM_URL", "https://resonance.iqm.tech")
    backend_name = os.environ.get("IQM_BACKEND", "garnet")

    hamiltonian, model = load_hamiltonian(args.model)
    provider = IQMProvider(url, token=token)
    backend = provider.get_backend(backend_name)
    circuit = QAOAAnsatz(cost_operator=hamiltonian, reps=args.reps)
    circuit.measure_all()
    transpiled = transpile(circuit, backend=backend, optimization_level=3)
    angles = [0.5] * len(transpiled.parameters)
    bound = transpiled.assign_parameters(dict(zip(transpiled.parameters, angles)))

    print(f"Submitting {len(model['assets']) * 2} qubits to {backend.name}...")
    result = backend.run(bound, shots=args.shots).result()
    counts = result.get_counts()
    Path("iqm_raw_results.json").write_text(json.dumps(counts, indent=2) + "\n", encoding="utf-8")
    print("Saved IQM counts to iqm_raw_results.json")


if __name__ == "__main__":
    main()
