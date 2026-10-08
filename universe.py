"""
Step 2 - load assets.csv / cov.csv and pick the N assets that go into the QUBO.
(This is the asset-selection logic that used to live at the top of matrix.py.)
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent


@dataclass
class Universe:
    tickers: list      # length N
    types: list        # energy type per ticker
    carbon: np.ndarray # normalised carbon intensity in [0, 1]
    mu: np.ndarray     # annualised expected return, scaled to [-1, 1]
    mu_raw: np.ndarray # annualised expected return, unscaled
    sigma: np.ndarray  # annualised covariance matrix (N x N)

    @property
    def n(self):
        return len(self.tickers)


def load_universe(n=6, picks=None, data_dir=HERE):
    """
    n      number of candidate assets (the QUBO uses 2n qubits).
    picks  optional explicit ticker list, e.g. ["XOM", "BTU", "EQT", "FSLR", "CEG", "BEP"].
    """
    data_dir = Path(data_dir)
    assets = pd.read_csv(data_dir / "assets.csv", index_col="ticker")
    cov = pd.read_csv(data_dir / "cov.csv", index_col=0)

    if picks is None:
        # best Sharpe within each energy type, topped up with the best leftovers
        best = assets.sort_values("sharpe", ascending=False).groupby("type").head(1)
        rest = assets.drop(best.index).sort_values("sharpe", ascending=False)
        picks = (list(best.index) + list(rest.index))[:n]
    else:
        picks = list(picks)

    sub = assets.loc[picks]
    sigma = cov.loc[picks, picks].to_numpy(float)
    sigma = (sigma + sigma.T) / 2

    mu_raw = sub["exp_return"].to_numpy(float)
    scale = np.abs(mu_raw).max()
    return Universe(
        tickers=picks,
        types=sub["type"].tolist(),
        carbon=sub["carbon_norm"].to_numpy(float),
        mu=mu_raw / scale if scale > 0 else mu_raw,
        mu_raw=mu_raw,
        sigma=sigma,
    )
