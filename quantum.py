"""
Build the asset DataFrame for the carbon-aware portfolio prototype.

    pip install yfinance pandas numpy
    python build_energy_dataframe.py

Outputs (in the working directory):
    assets.csv  - one row per ticker: energy type, carbon intensity, expected return, vol, sharpe
    cov.csv     - annualised covariance matrix of returns
"""
import numpy as np
import pandas as pd
import yfinance as yf

# ------------------------------------------------------------------ config
YEARS = 3
TRADING_DAYS = 252

# Lifecycle carbon intensity by generation type, gCO2e/kWh.
# Source: IPCC AR5 WG3 Annex III (Schlomer et al. 2014), median values.
# Cross-check / alternatives: NREL LCA Harmonization, Our World in Data "carbon intensity of electricity".
CARBON_BY_TYPE = {
    "coal": 820, "oil": 650, "gas": 490, "biomass": 230,
    "solar": 48, "hydro": 24, "nuclear": 12, "wind": 11,
}

# ticker -> dominant energy type. This is a simplification: most companies have a mix.
# Verify each ticker still trades (mergers/delistings happen) before relying on it.
UNIVERSE = {
    # coal
    "BTU": "coal",      # Peabody Energy
    "CNR": "coal",      # Core Natural Resources (Arch + CONSOL merger)
    # oil
    "XOM": "oil", "CVX": "oil", "COP": "oil", "OXY": "oil",
    # gas
    "EQT": "gas", "AR": "gas", "EXE": "gas",       # Expand Energy (ex-Chesapeake)
    # solar
    "ENPH": "solar", "FSLR": "solar", "RUN": "solar",
    # wind (Vestas and Orsted trade as US OTC ADRs)
    "VWDRY": "wind", "DNNGY": "wind", "CWEN": "wind",
    # hydro
    "BEP": "hydro",     # Brookfield Renewable Partners
    # nuclear
    "CEG": "nuclear",   # Constellation Energy
    "CCJ": "nuclear",   # Cameco (uranium fuel, not generation)
    "OKLO": "nuclear",  # pre-revenue; short history
    # biomass
    "DRX.L": "biomass", # Drax Group (London)
}


def main():
    tickers = list(UNIVERSE)

    # ---------------------------------------------------------- prices
    prices = yf.download(tickers, period=f"{YEARS}y", interval="1d",auto_adjust=True, progress=False,)["Close"]

    # drop tickers that failed to download or have almost no history
    prices = prices.dropna(axis=1, thresh=int(0.6 * len(prices)))
    missing = sorted(set(tickers) - set(prices.columns))
    if missing:
        print(f"WARNING: no usable data for {missing}")

    # different exchanges have different holidays: forward-fill gaps, then compute returns
    returns = prices.ffill().pct_change().dropna(how="any")

    # ---------------------------------------------------------- assets DataFrame
    assets = pd.DataFrame({
        "type": pd.Series(UNIVERSE).reindex(returns.columns),
        "exp_return": returns.mean() * TRADING_DAYS,            # annualised mean return
        "vol": returns.std() * np.sqrt(TRADING_DAYS),           # annualised volatility
    })
    assets["sharpe"] = assets["exp_return"] / assets["vol"]     # risk-free rate ignored
    assets["carbon"] = assets["type"].map(CARBON_BY_TYPE)       # gCO2e/kWh
    assets["carbon_norm"] = assets["carbon"] / assets["carbon"].max()
    assets.index.name = "ticker"

    cov = returns.cov() * TRADING_DAYS

    assets.round(4).to_csv("assets.csv")
    cov.round(6).to_csv("cov.csv")

    print(assets.round(3).sort_values("carbon").to_string())
    print(f"\n{len(assets)} assets, {len(returns)} daily observations")
    print(f"({returns.index[0].date()} to {returns.index[-1].date()})")


if __name__ == "__main__":
    main()