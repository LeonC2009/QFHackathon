#!/usr/bin/env python3
"""
Download and prepare the energy-futures + emissions dataset
for the Quantum Topological Carbon Hedging project.

Sources:
- U.S. Energy Information Administration (EIA)
- NYMEX Contract 1 daily futures series
- EIA carbon-dioxide emission coefficients

Assets:
    WTI crude oil
    Natural gas
    RBOB gasoline
    No. 2 heating oil

Research period:
    2015-01-01 through 2024-04-05

The script:
1. Downloads the four EIA futures XLS files.
2. Downloads EIA's official CO2 coefficient XLSX.
3. Extracts and cleans the daily Contract 1 price series.
4. Aligns all four assets on common trading dates.
5. Calculates daily percentage returns.
6. Creates a clean emissions table.
7. Saves everything under ./data/

Install:
    python3.12 -m venv .venv
    source .venv/bin/activate
    pip install pandas requests openpyxl xlrd

Run:
    python download_data.py
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
import requests


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"

START_DATE = "2015-01-01"
END_DATE = "2024-04-05"

TIMEOUT = 60

# These are the exact EIA XLS endpoints linked by the current EIA pages.
# EIA states that NYMEX futures data are not available after April 5, 2024.
FUTURES = {
    "wti": {
        "url": "https://www.eia.gov/dnav/pet/hist_xls/RCLC1d.xls",
        "raw_file": "wti_contract1.xls",
        "price_column": "wti_price_usd_per_bbl",
    },
    "gasoline": {
        "url": (
            "https://www.eia.gov/dnav/pet/hist_xls/"
            "EER_EPMRR_PE1_Y35NY_DPGd.xls"
        ),
        "raw_file": "gasoline_contract1.xls",
        "price_column": "gasoline_price_usd_per_gallon",
    },
    "heating_oil": {
        "url": (
            "https://www.eia.gov/dnav/pet/hist_xls/"
            "EER_EPD2F_PE1_Y35NY_DPGd.xls"
        ),
        "raw_file": "heating_oil_contract1.xls",
        "price_column": "heating_oil_price_usd_per_gallon",
    },
    "natural_gas": {
        "url": "https://www.eia.gov/dnav/ng/hist_xls/RNGC1d.xls",
        "raw_file": "natural_gas_contract1.xls",
        "price_column": "natural_gas_price_usd_per_mmbtu",
    },
}

EMISSIONS_URL = (
    "https://www.eia.gov/environment/emissions/xls/co2_vol_mass.xlsx"
)
EMISSIONS_RAW_FILE = "eia_co2_vol_mass.xlsx"


# EIA's current published CO2 factors.
#
# Units:
#   kg CO2 / MMBtu
#
# Natural gas, finished motor gasoline and distillate/home-heating fuel
# are directly listed on EIA's emissions page.
#
# Crude oil is listed in EIA's February 2026 STEO CO2 methodology as
# 74.47 kg CO2/MMBtu.
#
# These are fuel combustion factors, not life-cycle emissions factors.
EMISSION_FACTORS = {
    "wti": {
        "fuel": "crude oil",
        "kg_co2_per_mmbtu": 74.47,
        "source_note": "EIA STEO CO2 emission factor, February 2026",
    },
    "natural_gas": {
        "fuel": "natural gas",
        "kg_co2_per_mmbtu": 52.91,
        "source_note": "EIA Carbon Dioxide Emissions Coefficients",
    },
    "gasoline": {
        "fuel": "finished motor gasoline",
        "kg_co2_per_mmbtu": 70.66,
        "source_note": "EIA Carbon Dioxide Emissions Coefficients",
    },
    "heating_oil": {
        "fuel": "diesel and home heating fuel (distillate fuel oil)",
        "kg_co2_per_mmbtu": 74.14,
        "source_note": "EIA Carbon Dioxide Emissions Coefficients",
    },
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def download_bytes(url: str) -> bytes:
    """Download a file and return its bytes."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Macintosh; Intel Mac OS X) "
            "EnergyFuturesResearch/1.0"
        )
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=TIMEOUT,
    )
    response.raise_for_status()

    if not response.content:
        raise RuntimeError(f"Downloaded an empty file: {url}")

    return response.content


def save_bytes(data: bytes, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


# ---------------------------------------------------------------------------
# EIA XLS parser
# ---------------------------------------------------------------------------

def find_date_column(raw: pd.DataFrame) -> int:
    """Find the column containing the largest number of valid dates."""
    best_column = None
    best_count = 0

    for column in raw.columns:
        parsed = pd.to_datetime(raw[column], format="mixed", errors="coerce")
        count = parsed.between(
            pd.Timestamp(START_DATE),
            pd.Timestamp(END_DATE),
        ).sum()

        if count > best_count:
            best_column = column
            best_count = count

    if best_column is None:
        raise ValueError("Could not identify a date column in the EIA XLS file.")

    return best_column


def clean_futures_xls(
    content: bytes,
    output_column: str,
) -> pd.DataFrame:
    """
    Read one EIA historical XLS file and return:

        date | asset_price

    The parser does not assume a fixed metadata-row count.
    """
    workbook = pd.ExcelFile(BytesIO(content))
    sheets = []

    for sheet_name in workbook.sheet_names:
        sheet = pd.read_excel(workbook, sheet_name=sheet_name, header=None)
        sheet = sheet.dropna(axis=1, how="all")
        date_count = max(
            (
                pd.to_datetime(column, format="mixed", errors="coerce")
                .between(pd.Timestamp(START_DATE), pd.Timestamp(END_DATE))
                .sum()
                for _, column in sheet.items()
            ),
            default=0,
        )
        sheets.append((date_count, sheet))

    _, raw = max(sheets, key=lambda item: item[0])
    date_column = find_date_column(raw)

    # Find the first non-date column containing numeric observations.
    price_column = None

    for column in raw.columns:
        if column == date_column:
            continue

        numeric = pd.to_numeric(
            raw[column],
            errors="coerce",
        )

        if numeric.notna().sum() >= 20:
            price_column = column
            break

    if price_column is None:
        raise ValueError(
            "Could not identify the price column in the EIA XLS file."
        )

    clean = pd.DataFrame(
        {
            "date": pd.to_datetime(
                raw[date_column],
                format="mixed",
                errors="coerce",
            ),
            output_column: pd.to_numeric(
                raw[price_column],
                errors="coerce",
            ),
        }
    )

    clean = clean.dropna(subset=["date", output_column])

    clean = clean[
        (clean["date"] >= pd.Timestamp(START_DATE))
        & (clean["date"] <= pd.Timestamp(END_DATE))
    ]

    clean = (
        clean
        .drop_duplicates(subset=["date"])
        .sort_values("date")
        .reset_index(drop=True)
    )

    if clean.empty:
        raise ValueError(
            f"No observations found between {START_DATE} and {END_DATE}."
        )

    return clean


# ---------------------------------------------------------------------------
# Emissions XLSX parser
# ---------------------------------------------------------------------------

def download_emissions_workbook() -> Path:
    """Download EIA's official CO2 coefficients workbook."""
    print("Downloading EIA emissions workbook...")
    content = download_bytes(EMISSIONS_URL)

    path = RAW_DIR / EMISSIONS_RAW_FILE
    save_bytes(content, path)

    print(f"  saved: {path}")
    return path


def build_emissions_table(workbook_path: Path) -> pd.DataFrame:
    """
    Create the compact emissions.csv used by the optimization.

    We retain the original EIA workbook in data/raw/ as an audit source.
    """
    rows = []

    for asset, info in EMISSION_FACTORS.items():
        rows.append(
            {
                "asset": asset,
                "fuel": info["fuel"],
                "kg_co2_per_mmbtu": info["kg_co2_per_mmbtu"],
                "source_note": info["source_note"],
            }
        )

    emissions = pd.DataFrame(rows)

    # Store the source workbook name for traceability.
    emissions["source_workbook"] = workbook_path.name

    return emissions


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("ENERGY FUTURES DATASET BUILDER")
    print("=" * 72)
    print(f"Period: {START_DATE} -> {END_DATE}")
    print("Source: U.S. Energy Information Administration (EIA)")
    print()

    # ---------------------------------------------------------------
    # 1. Download and clean futures
    # ---------------------------------------------------------------

    cleaned = {}

    for asset, config in FUTURES.items():
        print(f"Downloading {asset} futures...")

        content = download_bytes(config["url"])

        raw_path = RAW_DIR / config["raw_file"]
        save_bytes(content, raw_path)

        df = clean_futures_xls(
            content,
            config["price_column"],
        )

        output_path = DATA_DIR / f"{asset}.csv"
        df.to_csv(output_path, index=False)

        cleaned[asset] = df

        print(f"  raw:     {raw_path}")
        print(f"  cleaned: {output_path}")
        print(f"  rows:    {len(df):,}")
        print(
            f"  dates:   "
            f"{df['date'].min().date()} -> "
            f"{df['date'].max().date()}"
        )
        print()

    # ---------------------------------------------------------------
    # 2. Align all futures on common dates
    # ---------------------------------------------------------------

    print("Combining futures on common dates...")

    combined = None

    for df in cleaned.values():
        if combined is None:
            combined = df.copy()
        else:
            combined = combined.merge(
                df,
                on="date",
                how="inner",
            )

    if combined is None or combined.empty:
        raise RuntimeError("No common dates found across futures datasets.")

    combined = combined.sort_values("date").reset_index(drop=True)

    combined_path = DATA_DIR / "energy_futures.csv"
    combined.to_csv(combined_path, index=False)

    print(f"  saved: {combined_path}")
    print(f"  common trading days: {len(combined):,}")
    print()

    # ---------------------------------------------------------------
    # 3. Calculate returns
    # ---------------------------------------------------------------

    print("Calculating daily returns...")

    returns = combined[["date"]].copy()

    for asset, config in FUTURES.items():
        returns[asset] = combined[config["price_column"]].pct_change()

    returns = returns.dropna().reset_index(drop=True)

    returns_path = DATA_DIR / "energy_returns.csv"
    returns.to_csv(returns_path, index=False)

    print(f"  saved: {returns_path}")
    print(f"  rows:  {len(returns):,}")
    print()

    # ---------------------------------------------------------------
    # 4. Download emissions workbook
    # ---------------------------------------------------------------

    emissions_workbook = download_emissions_workbook()

    # ---------------------------------------------------------------
    # 5. Build compact emissions table
    # ---------------------------------------------------------------

    emissions = build_emissions_table(emissions_workbook)

    emissions_path = DATA_DIR / "emissions.csv"
    emissions.to_csv(emissions_path, index=False)

    print(f"Saved emissions table: {emissions_path}")
    print()

    # ---------------------------------------------------------------
    # 6. Build a machine-readable asset metadata file
    # ---------------------------------------------------------------

    metadata = pd.DataFrame(
        [
            {
                "asset": "wti",
                "instrument": "Cushing, OK Crude Oil Future Contract 1",
                "unit": "USD/barrel",
                "carbon_unit": "kg CO2/MMBtu",
            },
            {
                "asset": "natural_gas",
                "instrument": "Natural Gas Future Contract 1",
                "unit": "USD/MMBtu",
                "carbon_unit": "kg CO2/MMBtu",
            },
            {
                "asset": "gasoline",
                "instrument": (
                    "New York Harbor Reformulated RBOB Regular "
                    "Gasoline Future Contract 1"
                ),
                "unit": "USD/gallon",
                "carbon_unit": "kg CO2/MMBtu",
            },
            {
                "asset": "heating_oil",
                "instrument": (
                    "New York Harbor No. 2 Heating Oil "
                    "Future Contract 1"
                ),
                "unit": "USD/gallon",
                "carbon_unit": "kg CO2/MMBtu",
            },
        ]
    )

    metadata_path = DATA_DIR / "asset_metadata.csv"
    metadata.to_csv(metadata_path, index=False)

    # ---------------------------------------------------------------
    # 7. Summary
    # ---------------------------------------------------------------

    print("=" * 72)
    print("DATASET READY")
    print("=" * 72)

    print("\nCreated:")
    for path in sorted(DATA_DIR.rglob("*")):
        if path.is_file():
            print(f"  {path}")

    print("\nAssets:")
    print("  WTI Crude")
    print("  Natural Gas")
    print("  RBOB Gasoline")
    print("  Heating Oil")

    print("\nNext step:")
    print(
        "Use energy_returns.csv + emissions.csv to build the "
        "carbon-risk Ising Hamiltonian."
    )


if __name__ == "__main__":
    main()
