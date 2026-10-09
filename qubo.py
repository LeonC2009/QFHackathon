"""Canonical carbon-hedging QUBO and Ising conversion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from universe import Universe


@dataclass(frozen=True)
class QuboModel:
    matrix: np.ndarray
    constant: float
    carbon_scale: float
    risk_scale: float
    long_count: int
    short_count: int


def build_qubo(
    universe: Universe,
    K: int,
    carbon_weight: float = 1.0,
    risk_weight: float = 1.0,
    cardinality_weight: float = 50.0,
    exclusivity_weight: float = 50.0,
    tau: float = 0.0,
    lam: float = 0.0,
) -> tuple[np.ndarray, float]:
    """Build ``E(v) = v.T @ Q @ v + constant`` for v=[longs, shorts].

    The squared carbon term and covariance term are even under swapping the
    long and short halves. ``tau`` and ``lam`` are optional odd tie-breakers.
    """
    n = universe.n
    if not 0 < K <= n // 2:
        raise ValueError("K must be positive and no larger than floor(n / 2)")

    carbon = np.asarray(universe.carbon, dtype=float)
    covariance = np.asarray(universe.sigma, dtype=float)
    carbon_scale = max(float(np.mean(np.abs(carbon))), 1e-12)
    risk_scale = max(float(np.max(np.abs(covariance))), 1e-12)
    carbon = carbon / carbon_scale
    covariance = covariance / risk_scale

    position_map = np.hstack((np.eye(n), -np.eye(n)))
    q = np.zeros((2 * n, 2 * n), dtype=float)
    constant = 0.0

    signed_carbon = carbon @ position_map
    q += carbon_weight * np.outer(signed_carbon, signed_carbon)
    q += risk_weight * position_map.T @ covariance @ position_map

    for start, target in ((0, K), (n, K)):
        selector = np.zeros(2 * n)
        selector[start:start + n] = 1.0
        q += cardinality_weight * np.outer(selector, selector)
        q[start:start + n, start:start + n] -= 2 * cardinality_weight * target * np.eye(n)
        constant += cardinality_weight * target**2

    for i in range(n):
        q[i, n + i] += exclusivity_weight / 2
        q[n + i, i] += exclusivity_weight / 2

    odd = tau * carbon - lam * universe.mu
    q[np.arange(2 * n), np.arange(2 * n)] += np.concatenate((odd, -odd))
    return (q + q.T) / 2, constant


def qubo_energy(bits: Iterable[float], q: np.ndarray, constant: float = 0.0) -> float:
    vector = np.asarray(tuple(bits), dtype=float)
    return float(vector @ q @ vector + constant)


def qubo_to_ising(q: np.ndarray, constant: float = 0.0):
    """Return h, sparse J, and the exact Ising constant for v=(1-Z)/2."""
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


def ising_energy(bits, fields, couplings, constant):
    z = 1.0 - 2.0 * np.asarray(bits, dtype=float)
    return float(constant + fields @ z + sum(value * z[i] * z[j] for (i, j), value in couplings.items()))


def antipode(bits: Iterable[float]) -> tuple[int, ...]:
    values = tuple(int(bit) for bit in bits)
    if len(values) % 2:
        raise ValueError("The long/short bitstring must have even length")
    half = len(values) // 2
    return values[half:] + values[:half]


def is_feasible(bits: Iterable[float], asset_count: int, K: int) -> bool:
    values = np.asarray(tuple(bits), dtype=int)
    return (
        values.size == 2 * asset_count
        and int(values[:asset_count].sum()) == K
        and int(values[asset_count:].sum()) == K
        and not np.any(values[:asset_count] & values[asset_count:])
    )


def brute_force(q: np.ndarray, constant: float, asset_count: int, K: int, top: int = 10):
    """Return the best feasible bitstrings, using chunks to cap memory."""
    n = 2 * asset_count
    candidates = []
    for index in range(1 << n):
        bits = tuple((index >> shift) & 1 for shift in range(n - 1, -1, -1))
        if is_feasible(bits, asset_count, K):
            candidates.append((qubo_energy(bits, q, constant), bits))
    return sorted(candidates, key=lambda item: item[0])[:top]


def decode(bits: Iterable[float], universe: Universe):
    values = np.asarray(tuple(bits), dtype=int)
    n = universe.n
    longs = [universe.tickers[i] for i in range(n) if values[i]]
    shorts = [universe.tickers[i] for i in range(n) if values[n + i]]
    net_carbon = float(universe.carbon @ (values[:n] - values[n:]))
    return longs, shorts, net_carbon
