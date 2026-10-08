"""
Build the QUBO cost matrix Q only (no solving).

Goal: maximise expected return, minimise carbon footprint.
Variables: z = [x_0..x_{N-1}, y_0..y_{N-1}]   (x_i = long asset i, y_i = short asset i)
Cost: E(z) = z^T Q z   (lower is better)
"""
import json
import numpy as np
import pandas as pd

# ------------------------------------------------------------------ load + pick 10
assets = pd.read_csv("assets.csv", index_col="ticker")

N = 10
# Best Sharpe within each energy type, topped up with the best leftovers.
# Or hand-pick:  picks = ["XOM", "BTU", "EQT", "FSLR", "CWEN", "BEP", "CEG", "ENPH", "CVX", "DNNGY"]
best_per_type = assets.sort_values("sharpe", ascending=False).groupby("type").head(1)
leftovers = assets.drop(best_per_type.index).sort_values("sharpe", ascending=False)
picks = (list(best_per_type.index) + list(leftovers.index))[:N]

sub = assets.loc[picks]
mu = sub["exp_return"].to_numpy()
c = sub["carbon_norm"].to_numpy()
mu_n = mu / np.abs(mu).max()          # scale return to about [-1, 1] so it is comparable to carbon [0, 1]
print(sub[["type", "exp_return", "carbon"]].round(3), "\n")

# ------------------------------------------------------------------ parameters
K = 3                  # number of longs = number of shorts
w = 1.0 / K            # equal weight per position
lam_carbon = 1.0       # carbon vs return trade-off: higher -> cleaner portfolio, lower return
lam_card = 5.0         # penalty: exactly K longs and K shorts
lam_excl = 5.0         # penalty: never long and short the same asset
# lam_card / lam_excl must be larger than the biggest gain the objective can get from breaking
# a constraint, otherwise the optimiser will cheat. Tune lam_carbon to move along the return/carbon trade-off.


def add_square(Q, a, b, lam):
    """Add lam * (a.z - b)^2 to Q (constant dropped; z^2 = z so linear terms sit on the diagonal)."""
    Q += lam * np.outer(a, a)
    Q[np.diag_indices_from(Q)] += -2 * lam * b * a


# ------------------------------------------------------------------ build Q
Q = np.zeros((2 * N, 2 * N))
diag = np.diag_indices(2 * N)

# 1) maximise profit  ->  minimise -(mu.x - mu.y) * w
#    long earns mu_i; short earns -mu_i
Q[diag] += -w * np.concatenate([mu_n, -mu_n])

# 2) minimise carbon footprint  ->  minimise lam * (c.x - c.y) * w
#    long adds carbon c_i; short of a dirty asset removes it (net exposure falls)
Q[diag] += lam_carbon * w * np.concatenate([c, -c])

# 3) constraints
is_long = np.concatenate([np.ones(N), np.zeros(N)])
add_square(Q, is_long, K, lam_card)        # exactly K longs
add_square(Q, 1 - is_long, K, lam_card)    # exactly K shorts
for i in range(N):
    Q[i, N + i] += lam_excl                # not both long and short

Q = (Q + Q.T) / 2                           # symmetric form (same energies)

# ------------------------------------------------------------------ save
labels = [f"long_{t}" for t in picks] + [f"short_{t}" for t in picks]
np.save("Q.npy", Q)
with open("qubit_labels.json", "w") as f:
    json.dump(labels, f)

print(f"Q shape: {Q.shape}  (qubit i <-> labels[i])")
print("Saved Q.npy and qubit_labels.json")