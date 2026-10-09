"""
Smoke test for the Qiskit Aer environment.

1. Prints versions.
2. Runs a Bell circuit on AerSimulator (is Aer installed and working?).
3. Checks that antipodal_qaoa.ising_to_pauli_terms() gives a Qiskit Hamiltonian whose energy on
   basis states, evaluated THROUGH Aer, equals the QUBO energy - i.e. qubit ordering is right.
   A deliberately reversed Hamiltonian must fail, proving the test can catch scrambling.
4. Prints a statevector memory table so you can pick N (qubits = 2N).

Run from the repo folder (needs antipodal_qaoa.py next to it):
    python check_aer.py                 # random 6-qubit test problem
    python check_aer.py --q Q.npy       # also test on your real Q (<= 20 qubits)
"""

import argparse
import sys

import numpy as np

try:
    import qiskit
    import qiskit_aer
    from qiskit import QuantumCircuit, transpile
    from qiskit.quantum_info import SparsePauliOp, Statevector
    from qiskit_aer import AerSimulator
except ImportError as e:
    sys.exit(f"Qiskit/Aer not importable ({e}).\nRun:  python setup_env.py   (or: pip install -r requirements.txt)")

from antipodal_qaoa import qubo_to_ising, qubo_energy, ising_to_pauli_terms

FAILS = []


def report(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        FAILS.append(name)


def bell_test(sim):
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    counts = sim.run(transpile(qc, sim), shots=1000).result().get_counts()
    report("Bell circuit on AerSimulator", set(counts) <= {"00", "11"} and len(counts) == 2, f"counts={counts}")


def aer_energy(sim, bits, op, const):
    """Energy of a computational basis state, evaluated through Aer's statevector."""
    n = len(bits)
    qc = QuantumCircuit(n)
    for q, b in enumerate(bits):  # bits[q] = value of qubit q
        if b:
            qc.x(q)
    qc.save_statevector()
    sv = Statevector(sim.run(transpile(qc, sim)).result().get_statevector())
    return float(np.real(sv.expectation_value(op))) + const


def ordering_test(sim, Q, label, trials=10, seed=0):
    n = Q.shape[0]
    Qs = (Q + Q.T) / 2
    h, J, const = qubo_to_ising(Qs)
    terms = ising_to_pauli_terms(h, J)
    good = SparsePauliOp.from_list(terms)
    bad = SparsePauliOp.from_list([(lab[::-1], c) for lab, c in terms])  # reversed qubit order
    rng = np.random.default_rng(seed)
    worst_good, worst_bad = 0.0, 0.0
    for _ in range(trials):
        bits = tuple(int(b) for b in rng.integers(0, 2, n))
        ref = qubo_energy(bits, Q)
        worst_good = max(worst_good, abs(aer_energy(sim, bits, good, const) - ref))
        worst_bad = max(worst_bad, abs(aer_energy(sim, bits, bad, const) - ref))
    report(f"Ising ordering via Aer ({label}, {n} qubits)", worst_good < 1e-8, f"max err {worst_good:.2e}")
    report(f"Reversed ordering is detected ({label})", worst_bad > 1e-6, f"max err {worst_bad:.2e}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--q", default=None, help="optional path to your Q.npy (<= 20 qubits)")
    args = ap.parse_args()

    print(f"qiskit {qiskit.__version__} | qiskit-aer {qiskit_aer.__version__} | numpy {np.__version__}")
    sim = AerSimulator(method="statevector")

    bell_test(sim)

    rng = np.random.default_rng(1)
    ordering_test(sim, rng.normal(size=(6, 6)), "random")
    if args.q:
        Q = np.load(args.q)
        if Q.shape[0] <= 20:
            ordering_test(sim, Q, args.q)
        else:
            print(f"Skipping {args.q}: {Q.shape[0]} qubits is too many for this quick test.")

    print("\nStatevector memory (complex128) for 2N qubits:")
    for N in (6, 8, 10, 12, 14):
        q = 2 * N
        mb = 16 * 2 ** q / 2 ** 20
        print(f"  N={N:2d} contracts -> {q:2d} qubits -> {mb:10.1f} MB" + ("   (comfortable)" if mb < 1024 else "   (heavy)"))

    if FAILS:
        sys.exit(f"\n{len(FAILS)} check(s) failed: {FAILS}")
    print("\nAll checks passed - Aer environment is ready.")


if __name__ == "__main__":
    main()
