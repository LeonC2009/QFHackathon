"""Standalone Yahoo futures and local QAOA workflow for the all_in_one folder."""
from __future__ import annotations

import argparse
import itertools
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
TRADING_DAYS = 252
FUTURES = {
    "CL=F": ("WTI crude oil", "oil", 5.8, 73.15),
    "BZ=F": ("Brent crude oil", "oil", 5.8, 73.15),
    "NG=F": ("Natural gas", "gas", 1.0, 53.06),
    "RB=F": ("RBOB gasoline", "gasoline", 0.125, 70.66),
    "HO=F": ("Heating oil", "heating_oil", 0.1385, 73.15),
}


@dataclass
class Universe:
    tickers: list[str]
    types: list[str]
    carbon: np.ndarray
    sigma: np.ndarray


def download(start, end=None):
    import yfinance as yf

    tickers = list(FUTURES)
    raw = yf.download(tickers, start=start, end=end, auto_adjust=False, group_by="column", progress=False, threads=False)
    if raw.empty:
        raise RuntimeError("Yahoo Finance returned no data")
    prices = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(prices, pd.DataFrame):
        prices = prices.to_frame()
    if list(prices.columns) == ["Close"]:
        prices.columns = [tickers[0]]
    prices = prices.ffill().dropna(how="any")
    selected = [ticker for ticker in prices.columns if ticker in FUTURES]
    if len(selected) < 2:
        raise RuntimeError("Fewer than two futures had usable price history")
    prices = prices[selected]
    returns = prices.pct_change().dropna(how="any")
    metadata = pd.DataFrame.from_dict(
        {ticker: {"name": FUTURES[ticker][0], "type": FUTURES[ticker][1], "mmbtu_per_unit": FUTURES[ticker][2], "kg_co2_per_mmbtu": FUTURES[ticker][3]} for ticker in selected},
        orient="index",
    )
    metadata.index.name = "ticker"
    metadata["exp_return"] = returns.mean() * TRADING_DAYS
    metadata["vol"] = returns.std() * np.sqrt(TRADING_DAYS)
    metadata["carbon"] = 1000.0 / prices.mean() * metadata["mmbtu_per_unit"] * metadata["kg_co2_per_mmbtu"]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    prices.to_csv(DATA_DIR / "prices.csv")
    returns.to_csv(DATA_DIR / "returns.csv")
    metadata.to_csv(DATA_DIR / "metadata.csv")
    returns.cov().mul(TRADING_DAYS).to_csv(DATA_DIR / "covariance.csv")
    print(f"Saved {len(selected)} futures and {len(returns)} observations to {DATA_DIR}")


def load(n):
    metadata = pd.read_csv(DATA_DIR / "metadata.csv").set_index("ticker")
    returns = pd.read_csv(DATA_DIR / "returns.csv", index_col=0)
    tickers = [ticker for ticker in returns.columns if ticker in metadata.index][:n]
    if len(tickers) < 2:
        raise RuntimeError("Download the dataset first or choose at least two futures")
    return Universe(tickers, metadata.loc[tickers, "type"].tolist(), metadata.loc[tickers, "carbon"].to_numpy(float), returns[tickers].cov().to_numpy(float) * TRADING_DAYS)


def build_qubo(u, k):
    n = len(u.tickers)
    if not 0 < k <= n // 2:
        raise ValueError("k must be between 1 and floor(n/2)")
    carbon = u.carbon / np.mean(np.abs(u.carbon))
    sigma = u.sigma / max(np.max(np.abs(u.sigma)), 1e-12)
    mapping = np.hstack((np.eye(n), -np.eye(n)))
    q = np.outer(carbon @ mapping, carbon @ mapping) + mapping.T @ sigma @ mapping
    constant = 0.0
    for start in (0, n):
        selector = np.zeros(2 * n)
        selector[start:start + n] = 1
        q += 50 * np.outer(selector, selector)
        q[start:start + n, start:start + n] -= 100 * k * np.eye(n)
        constant += 50 * k * k
    for i in range(n):
        q[i, n + i] += 25
        q[n + i, i] += 25
    return (q + q.T) / 2, constant


def energy(bits, q, constant):
    values = np.asarray(bits, dtype=float)
    return float(values @ q @ values + constant)


def feasible(bits, n, k):
    values = np.asarray(bits, dtype=int)
    return values.size == 2 * n and values[:n].sum() == k and values[n:].sum() == k and not np.any(values[:n] & values[n:])


def exact(q, constant, n, k):
    candidates = []
    for index in range(1 << (2 * n)):
        bits = tuple((index >> shift) & 1 for shift in range(2 * n - 1, -1, -1))
        if feasible(bits, n, k):
            candidates.append((energy(bits, q, constant), bits))
    return min(candidates)


def describe(bits, u):
    values = np.asarray(bits, dtype=int)
    longs = [u.tickers[i] for i in range(u.n) if values[i]]
    shorts = [u.tickers[i] for i in range(u.n) if values[u.n + i]]
    net = float(u.carbon @ (values[:u.n] - values[u.n:]))
    return f"long={longs} short={shorts} net_carbon={net:.2f}"


@property
def _n(u):
    return len(u.tickers)
Universe.n = _n


def run_qaoa(q, constant, u, k, shots, steps):
    from qrisp import QuantumArray, QuantumVariable, gphase, rz, rzz, x
    from qrisp.alg_primitives import dicke_state
    from qrisp.qaoa import QAOAProblem, portfolio_mixer

    scale = max(float(np.max(np.abs(q))), 1.0)

    def cost_operator(qarg, gamma):
        qubits = [qarg[0][i] for i in range(u.n)] + [qarg[1][i] for i in range(u.n)]
        gphase(-gamma * constant / scale, qubits[0])
        for i in range(2 * u.n):
            if q[i, i]:
                rz(2 * gamma * q[i, i] / scale, qubits[i])
        for i in range(2 * u.n):
            for j in range(i + 1, 2 * u.n):
                if q[i, j]:
                    rzz(2 * gamma * q[i, j] / scale, qubits[i], qubits[j])

    def key(value):
        return "".join(str(bit) for bit in value.flatten()) if hasattr(value, "flatten") else str(value).replace(" ", "")

    def classical_cost(counts):
        return sum(energy(tuple(int(bit) for bit in key(name)), q, constant) * count for name, count in counts.items())

    def initialize(qarg):
        for i in range(k):
            x(qarg[0][i])
            x(qarg[1][i])
        dicke_state(qarg[0], k)
        dicke_state(qarg[1], k)

    result = QAOAProblem(cost_operator, portfolio_mixer(), classical_cost, init_function=initialize).run(
        lambda: QuantumArray(QuantumVariable(u.n), shape=(2,)), depth=1, mes_kwargs={"shots": shots}, max_iter=max(steps, 4)
    )
    counts = {key(name): float(count) for name, count in result.items()}
    valid = [(energy(tuple(map(int, name)), q, constant), name, count) for name, count in counts.items() if feasible(tuple(map(int, name)), u.n, k)]
    print(f"QAOA states={len(counts)} feasible_probability={sum(item[2] for item in valid):.3f}")
    if valid:
        best = min(valid)
        print("Best sampled:", describe(tuple(map(int, best[1])), u), f"energy={best[0]:.6f}")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    download_parser = sub.add_parser("download")
    download_parser.add_argument("--start", default="2018-01-01")
    download_parser.add_argument("--end")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--n", type=int, default=5)
    run_parser.add_argument("--k", type=int, default=2)
    run_parser.add_argument("--qaoa", action="store_true")
    run_parser.add_argument("--shots", type=int, default=256)
    run_parser.add_argument("--steps", type=int, default=10)
    args = parser.parse_args()
    if args.command == "download":
        download(args.start, args.end)
        return
    u = load(args.n)
    q, constant = build_qubo(u, args.k)
    best_energy, best_bits = exact(q, constant, u.n, args.k)
    print("Assets:", ", ".join(u.tickers))
    print("Classical optimum:", describe(best_bits, u), f"energy={best_energy:.6f}")
    if args.qaoa:
        run_qaoa(q, constant, u, args.k, args.shots, args.steps)


if __name__ == "__main__":
    main()
