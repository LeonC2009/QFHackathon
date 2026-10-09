"""Load the prepared EIA energy returns and emissions metadata."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = HERE / "project_data" / "data"
POSITION_NOTIONAL_USD = 1_000.0
MMBTU_PER_UNIT = {
    "wti": 5.8,
    "natural_gas": 1.0,
    "gasoline": 0.125,
    "heating_oil": 0.1385,
}


@dataclass
class Universe:
    tickers: list      # length N
    types: list        # energy type per ticker
    carbon: np.ndarray # kg CO2 per $1,000 notional position
    mu: np.ndarray     # annualised expected return, scaled to [-1, 1]
    mu_raw: np.ndarray # annualised expected return, unscaled
    sigma: np.ndarray  # annualised covariance matrix (N x N)

    @property
    def n(self):
        return len(self.tickers)


def load_universe(n=4, picks=None, data_dir=None, data_source="eia"):
    """
    n      number of candidate assets (the QUBO uses 2n qubits).
    picks  optional explicit ticker list, e.g. ["XOM", "BTU", "EQT", "FSLR", "CEG", "BEP"].
    """
    data_dir = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    if data_source == "yahoo":
        return _load_yahoo_universe(n, picks, data_dir)
    if data_source != "eia":
        raise ValueError(f"Unknown data source: {data_source}")
    prices = pd.read_csv(data_dir / "energy_futures.csv")
    prices = prices.set_index("date")
    returns = pd.read_csv(data_dir / "energy_returns.csv", index_col="date")
    emissions = pd.read_csv(data_dir / "emissions.csv").set_index("asset")
    available = [asset for asset in returns.columns if asset in emissions.index]
    if not available:
        raise ValueError("No compatible energy/emissions assets were found")

    if picks is None:
        picks = available[:n]
    else:
        picks = list(picks)
    if not set(picks).issubset(available):
        missing = sorted(set(picks) - set(available))
        raise ValueError(f"Unknown or non-energy assets requested: {missing}")
    if len(picks) < 2:
        raise ValueError("At least two energy assets are required")
    price_columns = {
        asset: next(column for column in prices if column.startswith(f"{asset}_price_"))
        for asset in picks
    }

    sub = returns[picks].dropna()
    sigma = sub.cov().to_numpy(float) * 252.0
    sigma = (sigma + sigma.T) / 2

    mu_raw = sub.mean().to_numpy(float) * 252.0
    scale = np.abs(mu_raw).max()
    return Universe(
        tickers=picks,
        types=emissions.loc[picks, "fuel"].tolist(),
        carbon=np.array([
            POSITION_NOTIONAL_USD
            / prices[price_columns[asset]].mean()
            * MMBTU_PER_UNIT[asset]
            * emissions.loc[asset, "kg_co2_per_mmbtu"]
            for asset in picks
        ]),
        mu=mu_raw / scale if scale > 0 else mu_raw,
        mu_raw=mu_raw,
        sigma=sigma,
    )


def _load_yahoo_universe(n, picks, data_dir):
    metadata = pd.read_csv(data_dir / "yahoo_futures_metadata.csv").set_index("ticker")
    covariance = pd.read_csv(data_dir / "yahoo_futures_covariance.csv", index_col=0)
    returns = pd.read_csv(data_dir / "yahoo_futures_returns.csv", index_col="date")
    available = [ticker for ticker in returns.columns if ticker in metadata.index and ticker in covariance.columns]
    if picks is None:
        picks = available[:n]
    else:
        picks = list(picks)
    missing = sorted(set(picks) - set(available))
    if missing:
        raise ValueError(f"Unknown Yahoo futures or missing metadata: {missing}")
    if len(picks) < 2:
        raise ValueError("At least two Yahoo futures are required")
    sub = returns[picks].dropna()
    mu_raw = sub.mean().to_numpy(float) * 252.0
    sigma = sub.cov().to_numpy(float) * 252.0
    sigma = (sigma + sigma.T) / 2
    return Universe(
        tickers=picks,
        types=metadata.loc[picks, "type"].tolist(),
        carbon=metadata.loc[picks, "carbon"].to_numpy(float),
        mu=mu_raw / np.abs(mu_raw).max() if np.abs(mu_raw).max() > 0 else mu_raw,
        mu_raw=mu_raw,
        sigma=sigma,
    )
