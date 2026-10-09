"""Decode and rank QAOA measurement results against the canonical model."""

from __future__ import annotations

from typing import Mapping

import numpy as np

from qubo import is_feasible


def rank_measurements(
    counts: Mapping[str, int | float],
    model: dict,
    long_count: int = 2,
    short_count: int | None = None,
    reverse_bitstrings: bool = True,
) -> list[dict[str, object]]:
    """Decode Qiskit bitstrings and rank feasible samples by QUBO energy."""
    assets = list(model["assets"])
    asset_count = len(assets)
    short_count = long_count if short_count is None else short_count
    q = np.asarray(model["qubo_matrix"], dtype=float)
    constant = float(model["qubo_constant"])
    carbon = np.asarray(model["carbon_exposure"], dtype=float)
    total = float(sum(float(value) for value in counts.values()))
    if total <= 0:
        raise ValueError("Measurement counts must contain a positive total")

    ranked = []
    for raw_bitstring, raw_count in counts.items():
        bitstring = str(raw_bitstring).replace(" ", "")
        if len(bitstring) != 2 * asset_count or set(bitstring) - {"0", "1"}:
            continue
        # Qiskit displays the highest-index qubit first; the model uses q0 first.
        ordered_bits = bitstring[::-1] if reverse_bitstrings else bitstring
        bits = np.fromiter((int(bit) for bit in ordered_bits), dtype=int)
        energy = float(bits @ q @ bits + constant)
        feasible = is_feasible(bits, asset_count, long_count) and (
            int(bits[asset_count:].sum()) == short_count
        )
        signed = bits[:asset_count] - bits[asset_count:]
        ranked.append(
            {
                "bitstring": bitstring,
                "probability": float(raw_count) / total,
                "count": float(raw_count),
                "energy": energy,
                "feasible": feasible,
                "long": [asset for asset, bit in zip(assets, bits[:asset_count]) if bit],
                "short": [asset for asset, bit in zip(assets, bits[asset_count:]) if bit],
                "net_carbon": float(carbon @ signed),
            }
        )
    return sorted(ranked, key=lambda item: (not item["feasible"], item["energy"]))


def summarize_measurements(
    counts: Mapping[str, int | float],
    model: dict,
    long_count: int = 2,
    short_count: int | None = None,
    reverse_bitstrings: bool = True,
) -> dict[str, object]:
    ranked = rank_measurements(
        counts,
        model,
        long_count,
        short_count,
        reverse_bitstrings,
    )
    total = sum(item["count"] for item in ranked)
    feasible = [item for item in ranked if item["feasible"]]
    return {
        "total_shots": int(total) if total.is_integer() else total,
        "distinct_bitstrings": len(ranked),
        "feasible_shots": sum(item["count"] for item in feasible),
        "feasible_probability": sum(item["probability"] for item in feasible),
        "best_feasible": feasible[0] if feasible else None,
        "top_feasible": feasible[:10],
        "top_measured": sorted(ranked, key=lambda item: item["count"], reverse=True)[:10],
    }
