from pathlib import Path

import pandas as pd

from universe import load_universe


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "project_data" / "data"


def test_yahoo_artifacts_have_matching_assets():
    metadata = pd.read_csv(DATA_DIR / "yahoo_futures_metadata.csv")
    returns = pd.read_csv(DATA_DIR / "yahoo_futures_returns.csv", index_col="date")
    covariance = pd.read_csv(DATA_DIR / "yahoo_futures_covariance.csv", index_col=0)

    tickers = metadata["ticker"].tolist()
    assert len(tickers) >= 2
    assert returns.columns.tolist() == tickers
    assert covariance.index.tolist() == tickers
    assert covariance.columns.tolist() == tickers
    assert metadata["carbon"].gt(0).all()


def test_yahoo_loader_returns_valid_universe():
    universe = load_universe(n=5, data_source="yahoo")

    assert universe.n == 5
    assert universe.sigma.shape == (5, 5)
    assert universe.carbon.shape == (5,)
    assert universe.mu.shape == (5,)
    assert universe.types == ["oil", "oil", "heating_oil", "gas", "gasoline"]