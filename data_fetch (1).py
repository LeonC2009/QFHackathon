"""
Step 1 - download prices and build assets.csv / cov.csv.

    pip install yfinance pandas numpy
    python data_fetch.py            # writes assets.csv and cov.csv next to this file

(Renamed from data-fetch.py: a hyphen makes a module un-importable in Python.)
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent

YEARS = 3
TRADING_DAYS = 252

# Lifecycle carbon intensity by generation type, gCO2e/kWh.
# Source: IPCC AR5 WG3 Annex III (Schlomer et al. 2014), median values.
CARBON_BY_TYPE = {
    "coal": 820, "oil": 650, "gas": 490, "biomass": 230,
    "solar": 48, "hydro": 24, "nuclear": 12, "wind": 11,
}

# ticker -> dominant energy type (simplification: most companies have a mix).
UNIVERSE = {
    "BTU": "coal", "CNR": "coal",
    "XOM": "oil", "CVX": "oil", "COP": "oil", "OXY": "oil",
    "EQT": "gas", "AR": "gas", "EXE": "gas",
    "ENPH": "solar", "FSLR": "solar", "RUN": "solar",
    "VWDRY": "wind", "DNNGY": "wind", "CWEN": "wind",
    "BEP": "hydro",
    "CEG": "nuclear", "CCJ": "nuclear", "OKLO": "nuclear",
    "DRX.L": "biomass",
}


def main(out_dir=HERE):
    import yfinance as yf  # imported here so the rest of the pipeline works without it

    out_dir = Path(out_dir)
    tickers = list(UNIVERSE)
    prices = yf.download(tickers, period=f"{YEARS}y", interval="1d",
                         auto_adjust=True, progress=False)["Close"]
    prices = prices.dropna(axis=1, thresh=int(0.6 * len(prices)))

    missing = sorted(set(tickers) - set(prices.columns))
    if missing:
        print(f"WARNING: no usable data for {missing}")

    returns = prices.ffill().pct_change().dropna(how="any")

    assets = pd.DataFrame({
        "type": pd.Series(UNIVERSE).reindex(returns.columns),
        "exp_return": returns.mean() * TRADING_DAYS,
        "vol": returns.std() * np.sqrt(TRADING_DAYS),
    })
    assets["sharpe"] = assets["exp_return"] / assets["vol"]
    assets["carbon"] = assets["type"].map(CARBON_BY_TYPE)
    assets["carbon_norm"] = assets["carbon"] / assets["carbon"].max()
    assets.index.name = "ticker"

    cov = returns.cov() * TRADING_DAYS

    assets.round(4).to_csv(out_dir / "assets.csv")
    cov.round(6).to_csv(out_dir / "cov.csv")

    print(assets.round(3).sort_values("carbon").to_string())
    print(f"\n{len(assets)} assets, {len(returns)} daily observations")
    print(f"({returns.index[0].date()} to {returns.index[-1].date()})")


if __name__ == "__main__":
    main()
