"""
Run the whole thing:  data -> universe -> QUBO -> Ising -> (brute force | QAOA) -> report

    python data_fetch.py                        # once, needs internet + yfinance
    python run_pipeline.py                      # classical reference only
    python run_pipeline.py --qaoa               # also run QAOA (needs pennylane)
    python run_pipeline.py --n 8 --k 2 --qaoa   # 16 qubits (slower)
"""
import argparse

import numpy as np

from borsuk_ulam import borsuk_ulam_circle
from qaoa_solver import run_qaoa
from qubo import (antipode, brute_force, build_qubo, decode, is_feasible,
                  ising_energy, qubo_energy, qubo_to_ising)
from universe import load_universe

#argument parsing and making everything work together
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6, help="candidate assets (qubits = 2n)")
    ap.add_argument("--k", type=int, default=2, help="longs = shorts = k")
    ap.add_argument("--picks", nargs="*", help="explicit tickers instead of auto-pick")
    ap.add_argument("--tau", type=float, default=0.3, help="odd carbon tilt")
    ap.add_argument("--lam", type=float, default=0.5, help="odd return reward")
    ap.add_argument("--qaoa", action="store_true", help="run QAOA via PennyLane")
    ap.add_argument("--p", type=int, default=3, help="QAOA layers")
    ap.add_argument("--steps", type=int, default=120, help="QAOA optimiser steps")
    ap.add_argument("--data-dir", default=None)
    args = ap.parse_args()

    kw = {"data_dir": args.data_dir} if args.data_dir else {}
    u = load_universe(n=args.n, picks=args.picks, **kw)
    N, K = u.n, args.k
    assert 2 * K <= N, "need at least 2K assets (K longs + K disjoint shorts)"

    print("Universe:")
    for t, ty, c, m in zip(u.tickers, u.types, u.carbon, u.mu_raw):
        print(f"  {t:6s} {ty:8s} carbon_norm={c:.3f}  exp_return={m:+.3f}")

    # --- symmetric (pure antipodal) problem: ground states should come in pairs
    Q0, off0 = build_qubo(u, K=K, tau=0.0, lam=0.0)
    e0, v0 = brute_force(Q0, off0, N, K)[0]
    print(f"\nSymmetric problem, brute-force ground energy: {e0:.4f}")
    print("  antipode has same energy:",
          np.isclose(qubo_energy(antipode(v0, N), Q0, off0), e0),
          "->", decode(antipode(v0, N), u))

    # --- break the symmetry with the odd terms
    Q, off = build_qubo(u, K=K, tau=args.tau, lam=args.lam)
    h, J, const = qubo_to_ising(Q, off)
    ranked = brute_force(Q, off, N, K)
    e_opt, v_opt = ranked[0]
    print("\nIsing/QUBO consistency:", np.isclose(ising_energy(v_opt, h, J, const), e_opt))
    L, S, nc = decode(v_opt, u)
    print(f"Classical optimum  E={e_opt:.4f}  long={L}  short={S}  net_carbon={nc:+.3f}")

    # --- QAOA
    if args.qaoa:
        print(f"\nQAOA on {2 * N} qubits ...")
        pr, _ = run_qaoa(h, J, const, p=args.p, steps=args.steps)
        print("\nTop sampled bitstrings:")
        for idx in np.argsort(pr)[::-1][:5]:
            bits = tuple(int(b) for b in format(idx, f"0{2 * N}b"))
            L, S, nc = decode(bits, u)
            print(f"  p={pr[idx]:.3f} E={qubo_energy(bits, Q, off):8.3f} "
                  f"feasible={is_feasible(bits, N, K)} long={L} short={S} net_carbon={nc:+.3f}")
        opt_idx = int("".join(map(str, v_opt)), 2)
        print(f"\nP(optimal bitstring) = {pr[opt_idx]:.3f}  (uniform: {1 / 2 ** (2 * N):.5f})")

    # --- continuous Borsuk-Ulam demo on the cleanest vs dirtiest candidate
    clean, dirty = u.carbon.min(), u.carbon.max()
    t, w = borsuk_ulam_circle(c_clean=clean / dirty, c_dirty=1.0)
    ic, id_ = u.tickers[int(np.argmin(u.carbon))], u.tickers[int(np.argmax(u.carbon))]
    print(f"\nContinuous B-U demo ({ic} vs {id_}): theta*={t:.4f}, weights = {w[0]:+.3f}:{w[1]:+.3f}")


if __name__ == "__main__":
    main()
