"""Download a reproducible Yahoo Finance energy-futures dataset.

Usage:
    python project_data/download_yahoo_futures.py

Yahoo provides prices, but not the carbon metadata needed by this project.
The small catalog below keeps that metadata explicit and reviewable.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
TRADING_DAYS = 252
POSITION_NOTIONAL_USD = 1_000.0

# Carbon factors are kg CO2 per MMBtu. Contract units are the units quoted by
# Yahoo (barrels, gallons, or MMBtu), so carbon exposure is price-adjusted.
FUTURES = {
    "CL=F": {"name": "WTI crude oil", "type": "oil", "mmbtu_per_unit": 5.8, "kg_co2_per_mmbtu": 73.15},
    "BZ=F": {"name": "Brent crude oil", "type": "oil", "mmbtu_per_unit": 5.8, "kg_co2_per_mmbtu": 73.15},
    "NG=F": {"name": "Natural gas", "type": "gas", "mmbtu_per_unit": 1.0, "kg_co2_per_mmbtu": 53.06},
    "RB=F": {"name": "RBOB gasoline", "type": "gasoline", "mmbtu_per_unit": 0.125, "kg_co2_per_mmbtu": 70.66},
    "HO=F": {"name": "Heating oil", "type": "heating_oil", "mmbtu_per_unit": 0.1385, "kg_co2_per_mmbtu": 73.15},
}


def download(start: str, end: str, data_dir: Path = DATA_DIR) -> None:
    import yfinance as yf

    tickers = list(FUTURES)
    raw = yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=False,
        group_by="column",
        progress=False,
        threads=False,
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
    if prices.shape[1] < 2:
        raise RuntimeError("Fewer than two futures had usable Yahoo price history")

    selected = [ticker for ticker in prices.columns if ticker in FUTURES]
    prices = prices[selected]
    returns = prices.pct_change().dropna(how="any")
    annual_returns = returns.mean() * TRADING_DAYS
    annual_vol = returns.std() * np.sqrt(TRADING_DAYS)
    metadata = pd.DataFrame.from_dict({ticker: FUTURES[ticker] for ticker in selected}, orient="index")
    metadata.index.name = "ticker"
    metadata["exp_return"] = annual_returns
    metadata["vol"] = annual_vol
    metadata["sharpe"] = metadata["exp_return"] / metadata["vol"].replace(0, np.nan)
    metadata["carbon"] = (
        POSITION_NOTIONAL_USD / prices.mean()
        * metadata["mmbtu_per_unit"]
        * metadata["kg_co2_per_mmbtu"]
    )
    metadata["carbon_norm"] = metadata["carbon"] / metadata["carbon"].max()
    covariance = returns.cov() * TRADING_DAYS

    data_dir.mkdir(parents=True, exist_ok=True)
    prices.to_csv(data_dir / "yahoo_futures_prices.csv")
    returns.to_csv(data_dir / "yahoo_futures_returns.csv")
    metadata.round(8).to_csv(data_dir / "yahoo_futures_metadata.csv")
    covariance.round(8).to_csv(data_dir / "yahoo_futures_covariance.csv")
    print(f"Saved {len(selected)} futures and {len(returns)} daily observations to {data_dir}")
    print(metadata[["name", "type", "carbon", "exp_return", "vol"]].round(4).to_string())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    download(args.start, args.end, args.data_dir)


if __name__ == "__main__":
    main()