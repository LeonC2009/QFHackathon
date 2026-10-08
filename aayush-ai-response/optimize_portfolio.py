#!/usr/bin/env python3
"""Build and benchmark the carbon-hedging QUBO from the prepared data."""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd


DATA_DIR = Path("data")
ASSETS = ["wti", "natural_gas", "gasoline", "heating_oil"]
POSITION_NOTIONAL_USD = 1_000.0
LONG_COUNT = 2
SHORT_COUNT = 2

# The QUBO weights are applied after scaling risk to the same rough magnitude
# as carbon exposure. This keeps the two terms numerically comparable.
CARBON_WEIGHT = 1.0
RISK_WEIGHT = 1.0
EXCLUSIVITY_WEIGHT = 10_000.0
CARDINALITY_WEIGHT = 10_000.0

# MMBtu per physical price unit. These are energy-content conventions used to
# turn equal-dollar positions into comparable combustion-carbon exposures.
MMBTU_PER_UNIT = {
    "wti": 5.8,            # per barrel
    "natural_gas": 1.0,    # per MMBtu
    "gasoline": 0.125,     # per gallon
    "heating_oil": 0.1385, # per gallon
}


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    prices = pd.read_csv(DATA_DIR / "energy_futures.csv", parse_dates=["date"])
    returns = pd.read_csv(DATA_DIR / "energy_returns.csv", parse_dates=["date"])
    emissions = pd.read_csv(DATA_DIR / "emissions.csv").set_index("asset")

    return_prices = {
        asset: next(column for column in prices if column.startswith(f"{asset}_"))
        for asset in ASSETS
    }
    prices = prices[["date", *return_prices.values()]].rename(
        columns={column: asset for asset, column in return_prices.items()}
    )
    returns = returns[["date", *ASSETS]].set_index("date")
    prices = prices.set_index("date")
    emissions = emissions.loc[ASSETS]

    if prices.empty or returns.empty:
        raise ValueError("The prepared futures and returns files must not be empty.")

    return prices, returns.join(emissions[["kg_co2_per_mmbtu"]], how="cross")


def carbon_exposure(prices: pd.DataFrame, emissions: pd.DataFrame) -> np.ndarray:
    """Return kg CO2 per $1,000 notional position for each asset."""
    mean_prices = prices[ASSETS].mean()
    factors = emissions["kg_co2_per_mmbtu"]
    return np.array([
        POSITION_NOTIONAL_USD
        / mean_prices[asset]
        * MMBTU_PER_UNIT[asset]
        * factors[asset]
        for asset in ASSETS
    ])


def build_qubo(
    covariance: np.ndarray,
    carbon: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Build Q and constant so objective(bits) = bits.T @ Q @ bits + constant."""
    asset_count = len(ASSETS)
    variable_count = 2 * asset_count
    q = np.zeros((variable_count, variable_count), dtype=float)
    constant = 0.0

    # s_i = x_i - y_i, represented by the signed-position matrix B.
    position_map = np.hstack((np.eye(asset_count), -np.eye(asset_count)))
    carbon_vector = carbon @ position_map
    q += CARBON_WEIGHT * np.outer(carbon_vector, carbon_vector)

    risk_matrix = position_map.T @ covariance @ position_map
    q += RISK_WEIGHT * risk_matrix

    for offset, target in ((0, LONG_COUNT), (asset_count, SHORT_COUNT)):
        cardinality_vector = np.zeros(variable_count)
        cardinality_vector[offset:offset + asset_count] = 1.0
        q += CARDINALITY_WEIGHT * np.outer(cardinality_vector, cardinality_vector)
        q[offset:offset + asset_count, offset:offset + asset_count] -= (
            2 * CARDINALITY_WEIGHT * target
            * np.eye(asset_count)
        )
        constant += CARDINALITY_WEIGHT * target**2

    for asset_index in range(asset_count):
        long_index = asset_index
        short_index = asset_count + asset_index
        q[long_index, short_index] += EXCLUSIVITY_WEIGHT / 2
        q[short_index, long_index] += EXCLUSIVITY_WEIGHT / 2

    return q, constant


def objective(bits: np.ndarray, q: np.ndarray, constant: float) -> float:
    return float(bits @ q @ bits + constant)


def decode(bits: np.ndarray) -> dict[str, object]:
    asset_count = len(ASSETS)
    longs = [asset for asset, bit in zip(ASSETS, bits[:asset_count]) if bit]
    shorts = [asset for asset, bit in zip(ASSETS, bits[asset_count:]) if bit]
    return {"long": longs, "short": shorts}


def main() -> None:
    prices, returns_with_emissions = load_inputs()
    emissions = pd.read_csv(DATA_DIR / "emissions.csv").set_index("asset").loc[ASSETS]
    returns = returns_with_emissions[ASSETS]
    covariance = returns.cov().to_numpy()
    carbon = carbon_exposure(prices, emissions)
    carbon_scale = float(np.mean(carbon))
    risk_scale = float(np.max(covariance))
    if carbon_scale <= 0 or risk_scale <= 0:
        raise ValueError("Carbon and covariance scales must be positive.")

    q, constant = build_qubo(
        covariance / risk_scale,
        carbon / carbon_scale,
    )

    candidates = []
    for bits_tuple in itertools.product((0, 1), repeat=2 * len(ASSETS)):
        bits = np.array(bits_tuple, dtype=float)
        decoded = decode(bits)
        signed = bits[:len(ASSETS)] - bits[len(ASSETS):]
        candidates.append(
            {
                "bits": [int(bit) for bit in bits],
                "objective": objective(bits, q, constant),
                "carbon_exposure": float(signed @ carbon),
                "financial_risk": float(signed @ covariance @ signed),
                **decoded,
            }
        )

    best = min(candidates, key=lambda result: result["objective"])
    ising_fields = (q.sum(axis=1) / 2).tolist()
    ising_couplings = {
        f"{i},{j}": float(q[i, j] / 2)
        for i in range(len(q))
        for j in range(i + 1, len(q))
        if q[i, j] != 0
    }

    output = {
        "assets": ASSETS,
        "variable_order": [f"x_{asset}" for asset in ASSETS]
        + [f"y_{asset}" for asset in ASSETS],
        "position_notional_usd": POSITION_NOTIONAL_USD,
        "mmbtu_per_unit": MMBTU_PER_UNIT,
        "carbon_exposure_kg_per_position": carbon.tolist(),
        "objective_carbon_scale_kg": carbon_scale,
        "objective_risk_scale": risk_scale,
        "covariance": covariance.tolist(),
        "qubo_matrix": q.tolist(),
        "qubo_constant": constant,
        "ising_fields": ising_fields,
        "ising_couplings": ising_couplings,
        "exact_classical_optimum": best,
    }
    (DATA_DIR / "optimization_model.json").write_text(
        json.dumps(output, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Exact classical optimum")
    print(json.dumps(best, indent=2))
    print(f"Carbon exposure coefficients (kg CO2/position): {carbon}")
    print("Saved: data/optimization_model.json")


if __name__ == "__main__":
    main()