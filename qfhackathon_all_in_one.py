"""Single-file Yahoo futures and QAOA workflow.

This is a convenience entry point; the existing modular files remain the
reference/backup implementation.

Examples:
    python qfhackathon_all_in_one.py download --start 2018-01-01
    python qfhackathon_all_in_one.py run --n 5 --k 2
    python qfhackathon_all_in_one.py run --n 5 --k 2 --qaoa --shots 256
    python qfhackathon_all_in_one.py hardware --dry-run
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "project_data" / "data"
TRADING_DAYS = 252
POSITION_NOTIONAL_USD = 1_000.0
FUTURES = {
    "CL=F": {"name": "WTI crude oil", "type": "oil", "mmbtu_per_unit": 5.8, "kg_co2_per_mmbtu": 73.15},
    "BZ=F": {"name": "Brent crude oil", "type": "oil", "mmbtu_per_unit": 5.8, "kg_co2_per_mmbtu": 73.15},
    "NG=F": {"name": "Natural gas", "type": "gas", "mmbtu_per_unit": 1.0, "kg_co2_per_mmbtu": 53.06},
    "RB=F": {"name": "RBOB gasoline", "type": "gasoline", "mmbtu_per_unit": 0.125, "kg_co2_per_mmbtu": 70.66},
    "HO=F": {"name": "Heating oil", "type": "heating_oil", "mmbtu_per_unit": 0.1385, "kg_co2_per_mmbtu": 73.15},
}


@dataclass
class Universe:
    tickers: list[str]
    types: list[str]
    carbon: np.ndarray
    mu: np.ndarray
    mu_raw: np.ndarray
    sigma: np.ndarray

    @property
    def n(self) -> int:
        return len(self.tickers)


def download_futures(start: str, end: str | None = None, data_dir: Path = DATA_DIR) -> None:
    import yfinance as yf

    tickers = list(FUTURES)
    raw = yf.download(
        tickers, start=start, end=end, auto_adjust=False,
        group_by="column", progress=False, threads=False,
    )
    if raw.empty:
        raise RuntimeError("Yahoo Finance returned no data")
    prices = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(prices, pd.DataFrame):
        prices = prices.to_frame()
    if list(prices.columns) == ["Close"]:
        prices.columns = [tickers[0]]
    prices = prices.rename_axis("date")
    prices = prices.dropna(axis=1, thresh=max(2, int(0.6 * len(prices))))
    prices = prices.ffill().dropna(how="any")
    selected = [ticker for ticker in prices.columns if ticker in FUTURES]
    prices = prices[selected]
    if len(selected) < 2:
        raise RuntimeError("Fewer than two futures had usable Yahoo price history")
    returns = prices.pct_change().dropna(how="any")
    metadata = pd.DataFrame.from_dict({ticker: FUTURES[ticker] for ticker in selected}, orient="index")
    metadata.index.name = "ticker"
    metadata["exp_return"] = returns.mean() * TRADING_DAYS
    metadata["vol"] = returns.std() * np.sqrt(TRADING_DAYS)
    metadata["sharpe"] = metadata["exp_return"] / metadata["vol"].replace(0, np.nan)
    metadata["carbon"] = (
        POSITION_NOTIONAL_USD / prices.mean()
        * metadata["mmbtu_per_unit"] * metadata["kg_co2_per_mmbtu"]
    )
    metadata["carbon_norm"] = metadata["carbon"] / metadata["carbon"].max()
    covariance = returns.cov() * TRADING_DAYS
    data_dir.mkdir(parents=True, exist_ok=True)
    prices.to_csv(data_dir / "yahoo_futures_prices.csv")
    returns.to_csv(data_dir / "yahoo_futures_returns.csv")
    metadata.round(8).to_csv(data_dir / "yahoo_futures_metadata.csv")
    covariance.round(8).to_csv(data_dir / "yahoo_futures_covariance.csv")
    print(f"Saved {len(selected)} futures and {len(returns)} daily observations to {data_dir}")


def load_universe(n: int, picks: list[str] | None = None, data_dir: Path = DATA_DIR) -> Universe:
    metadata = pd.read_csv(data_dir / "yahoo_futures_metadata.csv").set_index("ticker")
    returns = pd.read_csv(data_dir / "yahoo_futures_returns.csv", index_col="date")
    covariance = pd.read_csv(data_dir / "yahoo_futures_covariance.csv", index_col=0)
    available = [ticker for ticker in returns.columns if ticker in metadata.index and ticker in covariance.columns]
    selected = available[:n] if picks is None else list(picks)
    missing = sorted(set(selected) - set(available))
    if missing:
        raise ValueError(f"Unknown Yahoo futures or missing metadata: {missing}")
    if len(selected) < 2:
        raise ValueError("At least two futures are required")
    sub = returns[selected].dropna()
    mu_raw = sub.mean().to_numpy(float) * TRADING_DAYS
    scale = np.abs(mu_raw).max()
    sigma = sub.cov().to_numpy(float) * TRADING_DAYS
    return Universe(
        selected,
        metadata.loc[selected, "type"].tolist(),
        metadata.loc[selected, "carbon"].to_numpy(float),
        mu_raw / scale if scale > 0 else mu_raw,
        mu_raw,
        (sigma + sigma.T) / 2,
    )


def build_qubo(universe: Universe, k: int, cardinality_weight: float = 50.0, exclusivity_weight: float = 50.0):
    n = universe.n
    if not 0 < k <= n // 2:
        raise ValueError("k must be positive and no larger than floor(n / 2)")
    carbon = universe.carbon / max(float(np.mean(np.abs(universe.carbon))), 1e-12)
    covariance = universe.sigma / max(float(np.max(np.abs(universe.sigma))), 1e-12)
    position_map = np.hstack((np.eye(n), -np.eye(n)))
    q = np.outer(carbon @ position_map, carbon @ position_map)
    q += position_map.T @ covariance @ position_map
    constant = 0.0
    for start in (0, n):
        selector = np.zeros(2 * n)
        selector[start:start + n] = 1.0
        q += cardinality_weight * np.outer(selector, selector)
        q[start:start + n, start:start + n] -= 2 * cardinality_weight * k * np.eye(n)
        constant += cardinality_weight * k ** 2
    for index in range(n):
        q[index, n + index] += exclusivity_weight / 2
        q[n + index, index] += exclusivity_weight / 2
    return (q + q.T) / 2, constant


def energy(bits, q, constant=0.0):
    vector = np.asarray(tuple(bits), dtype=float)
    return float(vector @ q @ vector + constant)


def is_feasible(bits, n, k):
    values = np.asarray(tuple(bits), dtype=int)
    return values.size == 2 * n and int(values[:n].sum()) == k and int(values[n:].sum()) == k and not np.any(values[:n] & values[n:])


def exact(q, constant, n, k):
    candidates = []
    for index in range(1 << (2 * n)):
        bits = tuple((index >> shift) & 1 for shift in range(2 * n - 1, -1, -1))
        if is_feasible(bits, n, k):
            candidates.append((energy(bits, q, constant), bits))
    return min(candidates)


def decode(bits, universe):
    values = np.asarray(tuple(bits), dtype=int)
    longs = [universe.tickers[i] for i in range(universe.n) if values[i]]
    shorts = [universe.tickers[i] for i in range(universe.n) if values[universe.n + i]]
    return longs, shorts, float(universe.carbon @ (values[:universe.n] - values[universe.n:]))


def qubo_to_ising(q, constant=0.0):
    q = (np.asarray(q, dtype=float) + np.asarray(q, dtype=float).T) / 2
    ones = np.ones(q.shape[0])
    fields = -0.5 * q @ ones
    couplings = {
        (i, j): 0.5 * q[i, j]
        for i in range(q.shape[0])
        for j in range(i + 1, q.shape[0])
        if abs(q[i, j]) > 1e-12
    }
    ising_constant = constant + 0.25 * (ones @ q @ ones + np.trace(q))
    return fields, couplings, float(ising_constant)


def run_qaoa(q, constant, universe, k, p, steps, shots):
    from qrisp import QuantumArray, QuantumVariable, gphase, rz, rzz, x
    from qrisp.alg_primitives import dicke_state
    from qrisp.qaoa import QAOAProblem, portfolio_mixer
    fields, couplings, ising_constant = qubo_to_ising(q, constant)
    scale = max(float(np.max(np.abs(fields))), max((abs(value) for value in couplings.values()), default=0.0), 1.0)
    fields = fields / scale
    couplings = {key: value / scale for key, value in couplings.items()}

    def cost_operator(qv, gamma):
        qubits = [qv[0][i] for i in range(universe.n)] + [qv[1][i] for i in range(universe.n)]
        gphase(-gamma * ising_constant / scale, qubits[0])
        for index, field in enumerate(fields):
            if field:
                rz(2 * gamma * field, qubits[index])
        for (i, j), coupling in couplings.items():
            if coupling:
                rzz(2 * gamma * coupling, qubits[i], qubits[j])

    def normalize_key(key):
        if hasattr(key, "flatten"):
            return "".join(str(bit) for bit in key.flatten())
        return str(key).replace(" ", "")

    def classical_cost(counts):
        return sum(
            energy(tuple(int(bit) for bit in normalize_key(key)), q, constant) * value
            for key, value in counts.items()
        )

    def init(qarg):
        for i in range(k):
            x(qarg[0][i])
        for i in range(k):
            x(qarg[1][i])
        dicke_state(qarg[0], k)
        dicke_state(qarg[1], k)

    qarg = lambda: QuantumArray(QuantumVariable(universe.n), shape=(2,))
    result = QAOAProblem(cost_operator, portfolio_mixer(), classical_cost, init_function=init).run(
        qarg, depth=p, mes_kwargs={"shots": shots}, max_iter=max(steps, 2 * p + 2)
    )
    counts = {normalize_key(key): float(value) for key, value in result.items()}
    feasible = [(energy(tuple(int(bit) for bit in key), q, constant), key, value) for key, value in counts.items() if is_feasible(tuple(int(bit) for bit in key), universe.n, k)]
    best = min(feasible) if feasible else None
    print(f"QAOA completed: {len(counts)} states, feasible probability={sum(item[2] for item in feasible):.3f}")
    if best:
        print("Best sampled:", decode(tuple(int(bit) for bit in best[1]), universe), f"energy={best[0]:.6f}")


def run(args):
    universe = load_universe(args.n, args.picks)
    q, constant = build_qubo(universe, args.k)
    best_energy, best_bits = exact(q, constant, universe.n, args.k)
    print("Assets:", ", ".join(universe.tickers))
    print("Classical optimum:", decode(best_bits, universe), f"energy={best_energy:.6f}")
    if args.qaoa:
        run_qaoa(q, constant, universe, args.k, args.p, args.steps, args.shots)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    download = subparsers.add_parser("download")
    download.add_argument("--start", default="2018-01-01")
    download.add_argument("--end")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--n", type=int, default=5)
    run_parser.add_argument("--k", type=int, default=2)
    run_parser.add_argument("--p", type=int, default=1)
    run_parser.add_argument("--steps", type=int, default=10)
    run_parser.add_argument("--shots", type=int, default=256)
    run_parser.add_argument("--qaoa", action="store_true")
    run_parser.add_argument("--picks", nargs="*")
    hardware = subparsers.add_parser("hardware", help="delegate hardware submission to the maintained adapter")
    hardware.add_argument("--dry-run", action="store_true")
    hardware.add_argument("--shots", type=int, default=1000)
    hardware.add_argument("--reps", type=int, default=1)
    args = parser.parse_args()
    if args.command == "download":
        download_futures(args.start, args.end)
    elif args.command == "run":
        run(args)
    else:
        command = [sys.executable, "run_on_quantum.py", "--shots", str(args.shots), "--reps", str(args.reps)]
        if args.dry_run:
            command.append("--dry-run")
        subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
