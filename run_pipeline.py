"""Run data -> QUBO -> Ising -> exact check -> Qrisp QAOA."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from borsuk_ulam import borsuk_ulam_circle
from qaoa_solver import run_qaoa
from qubo import (
    antipode,
    brute_force,
    decode,
    is_feasible,
    ising_energy,
    qubo_energy,
    qubo_to_ising,
    build_qubo,
)
from universe import load_universe


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=4)
    parser.add_argument("--k", type=int, default=2)
    parser.add_argument("--p", type=int, default=1)
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--shots", type=int, default=512)
    parser.add_argument("--cardinality-weight", type=float, default=50.0)
    parser.add_argument("--exclusivity-weight", type=float, default=50.0)
    parser.add_argument("--qaoa", action="store_true")
    parser.add_argument("--picks", nargs="*")
    parser.add_argument("--data-source", choices=("eia", "yahoo"), default="eia")
    args = parser.parse_args()

    universe = load_universe(n=args.n, picks=args.picks, data_source=args.data_source)
    if 2 * args.k > universe.n:
        parser.error("--k requires at least 2*k candidate assets")
    print("Energy universe:", ", ".join(universe.tickers))

    symmetric_q, symmetric_constant = build_qubo(
        universe,
        args.k,
        cardinality_weight=args.cardinality_weight,
        exclusivity_weight=args.exclusivity_weight,
    )
    symmetric_best = brute_force(
        symmetric_q, symmetric_constant, universe.n, args.k, top=1
    )[0]
    symmetric_energy, symmetric_bits = symmetric_best
    mirrored_bits = antipode(symmetric_bits)
    pair_exists = (
        is_feasible(mirrored_bits, universe.n, args.k)
        and np.isclose(
            qubo_energy(mirrored_bits, symmetric_q, symmetric_constant),
            symmetric_energy,
        )
    )
    print(f"Borsuk-Ulam-inspired antipodal pair exists: {pair_exists}")
    print("  pair:", decode(symmetric_bits, universe), "<->", decode(mirrored_bits, universe))

    q, constant = build_qubo(
        universe,
        args.k,
        cardinality_weight=args.cardinality_weight,
        exclusivity_weight=args.exclusivity_weight,
        tau=0.3,
        lam=0.5,
    )
    fields, couplings, ising_constant = qubo_to_ising(q, constant)
    model_path = Path("project_data/data/optimization_model.json")
    model_path.write_text(
        json.dumps(
            {
                "assets": universe.tickers,
                "data_source": args.data_source,
                "variable_order": [f"x_{asset}" for asset in universe.tickers]
                + [f"y_{asset}" for asset in universe.tickers],
                "carbon_exposure": universe.carbon.tolist(),
                "covariance": universe.sigma.tolist(),
                "qubo_matrix": q.tolist(),
                "qubo_constant": constant,
                "long_count": args.k,
                "short_count": args.k,
                "cardinality_weight": args.cardinality_weight,
                "exclusivity_weight": args.exclusivity_weight,
                "ising_fields": fields.tolist(),
                "ising_couplings": {f"{i},{j}": value for (i, j), value in couplings.items()},
                "ising_constant": ising_constant,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Saved canonical model: {model_path}")
    classical_best = brute_force(q, constant, universe.n, args.k, top=1)[0]
    energy, bits = classical_best
    print("Ising/QUBO consistency:", np.isclose(ising_energy(bits, fields, couplings, ising_constant), energy))
    print("Classical optimum:", decode(bits, universe), f"energy={energy:.6f}")

    if args.qaoa:
        counts, _ = run_qaoa(
            q,
            constant,
            p=args.p,
            steps=args.steps,
            shots=args.shots,
            asset_count=universe.n,
            long_count=args.k,
            short_count=args.k,
        )
        feasible_probability = sum(
            probability
            for bitstring, probability in counts.items()
            if is_feasible(tuple(int(bit) for bit in bitstring), universe.n, args.k)
        )
        feasible_samples = [
            (qubo_energy(tuple(int(bit) for bit in bitstring), q, constant), bitstring, probability)
            for bitstring, probability in counts.items()
            if is_feasible(tuple(int(bit) for bit in bitstring), universe.n, args.k)
        ]
        best_result = None
        if feasible_samples:
            best_energy, best_bitstring, best_probability = min(feasible_samples)
            longs, shorts, net_carbon = decode(tuple(int(bit) for bit in best_bitstring), universe)
            best_result = {
                "long": longs,
                "short": shorts,
                "net_carbon": net_carbon,
                "energy": best_energy,
                "probability": best_probability,
            }
        Path("local_qaoa_result.json").write_text(
            json.dumps({
                "best_feasible": best_result,
                "feasible_probability": feasible_probability,
                "total_shots": args.shots,
                "distinct_bitstrings": len(counts),
                "data_source": args.data_source,
            }, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Qrisp feasible probability: {feasible_probability:.3f}")
        ranked = sorted(
            (
                qubo_energy(tuple(int(bit) for bit in bitstring), q, constant),
                bitstring,
                count,
            )
            for bitstring, count in counts.items()
        )
        print("Qrisp samples:")
        for energy, bitstring, probability in ranked[:5]:
            sample_bits = tuple(int(bit) for bit in bitstring)
            print(
            f"  probability={probability:.3f} E={energy:.6f} "
                f"feasible={is_feasible(sample_bits, universe.n, args.k)} "
                f"{decode(sample_bits, universe)}"
            )

    clean, dirty = universe.carbon.min(), universe.carbon.max()
    theta, weights = borsuk_ulam_circle(c_clean=clean / dirty, c_dirty=1.0)
    print(f"Continuous B-U check: theta={theta:.6f}, weights={weights}")


if __name__ == "__main__":
    main()
