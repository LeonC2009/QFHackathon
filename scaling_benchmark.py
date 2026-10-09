"""Benchmark how the carbon-hedging QUBO scales with portfolio size.

The four base assets are real EIA inputs. Larger rows are deterministic stress
instances made by perturbing those observed assets; they are not extra market
data and must be labeled as synthetic scaling benchmarks.
"""

from __future__ import annotations

import argparse
import json
import time
from math import comb
from pathlib import Path

import numpy as np

from qubo import brute_force, build_qubo, qubo_to_ising
from universe import Universe, load_universe


DEFAULT_OUTPUT = Path("project_data/data/scaling_benchmark.json")


def expand_universe(base: Universe, asset_count: int) -> Universe:
    if asset_count <= base.n:
        indexes = list(range(asset_count))
        return Universe(
            tickers=[base.tickers[index] for index in indexes],
            types=[base.types[index] for index in indexes],
            carbon=base.carbon[indexes].copy(),
            mu=base.mu[indexes].copy(),
            mu_raw=base.mu_raw[indexes].copy(),
            sigma=base.sigma[np.ix_(indexes, indexes)].copy(),
        )

    rng = np.random.default_rng(20261009 + asset_count)
    repeats = int(np.ceil(asset_count / base.n))
    tickers = []
    types = []
    carbon = []
    mu = []
    mu_raw = []
    for repeat in range(repeats):
        for index in range(base.n):
            if len(tickers) == asset_count:
                break
            suffix = "" if repeat == 0 else f"_stress{repeat + 1}"
            tickers.append(f"{base.tickers[index]}{suffix}")
            types.append(base.types[index])
            carbon.append(base.carbon[index] * (1 + rng.normal(0, 0.025)))
            mu.append(base.mu[index] + rng.normal(0, 0.01))
            mu_raw.append(base.mu_raw[index] + rng.normal(0, 0.002))

    base_indexes = np.arange(asset_count) % base.n
    sigma = base.sigma[np.ix_(base_indexes, base_indexes)].copy()
    sigma *= rng.uniform(0.96, 1.04, size=(asset_count, asset_count))
    sigma = (sigma + sigma.T) / 2
    sigma[np.diag_indices(asset_count)] = np.maximum(np.diag(sigma), 1e-8)
    return Universe(tickers, types, np.array(carbon), np.array(mu), np.array(mu_raw), sigma)


def benchmark(base: Universe, asset_counts: list[int], exact_limit: int) -> list[dict[str, object]]:
    rows = []
    for asset_count in asset_counts:
        universe = expand_universe(base, asset_count)
        long_count = max(2, asset_count // 4)
        feasible_states = comb(asset_count, long_count) * comb(asset_count - long_count, long_count)
        start = time.perf_counter()
        q, constant = build_qubo(
            universe,
            long_count,
            cardinality_weight=50.0,
            exclusivity_weight=50.0,
            tau=0.3,
            lam=0.5,
        )
        qubo_seconds = time.perf_counter() - start
        _, couplings, _ = qubo_to_ising(q, constant)
        row: dict[str, object] = {
            "asset_count": asset_count,
            "qubits": 2 * asset_count,
            "long_count": long_count,
            "feasible_portfolios": feasible_states,
            "qubo_seconds": round(qubo_seconds, 6),
            "ising_terms": asset_count * 2 + len(couplings),
            "benchmark_kind": "real_base_assets" if asset_count <= base.n else "synthetic_stress_expansion",
        }
        if asset_count <= exact_limit:
            exact_start = time.perf_counter()
            energy, bits = brute_force(q, constant, asset_count, long_count, top=1)[0]
            row.update(
                {
                    "exact_energy": energy,
                    "exact_seconds": round(time.perf_counter() - exact_start, 6),
                    "exact_bitstring": "".join(str(bit) for bit in bits),
                }
            )
        else:
            row["exact_energy"] = None
            row["exact_seconds"] = None
            row["note"] = "Use MILP, simulated annealing, or hybrid QAOA for this size."
        rows.append(row)
        print(
            f"N={asset_count:2d} assets | qubits={2 * asset_count:2d} | "
            f"feasible portfolios={feasible_states:,} | kind={row['benchmark_kind']}"
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", type=int, default=[4, 6, 8, 10, 12, 16, 20])
    parser.add_argument("--exact-limit", type=int, default=8)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    base = load_universe(n=4)
    rows = benchmark(base, args.sizes, args.exact_limit)
    payload = {
        "base_assets": base.tickers,
        "base_data_source": "prepared EIA data",
        "synthetic_expansion_warning": "Rows larger than the base universe are deterministic stress instances, not additional market observations.",
        "results": rows,
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Saved scaling benchmark to {args.output}")


if __name__ == "__main__":
    main()
