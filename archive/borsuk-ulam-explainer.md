# How Borsuk-Ulam Appears in the Carbon-Hedging Project

This note explains the role of Borsuk-Ulam in the project in plain language, while separating the mathematical theorem from the finite portfolio optimization code. The short version is that the project uses antipodal symmetry as an idea and performs two concrete checks inspired by it. The theorem itself does not guarantee that the optimizer will find an exactly carbon-neutral portfolio.

## The theorem, in the version relevant here

The Borsuk-Ulam theorem says that for a continuous function from an \(n\)-dimensional sphere to \(n\)-dimensional real space, some point on the sphere has the same function value as its antipodal point. Antipodal points are opposite points: if one point is \(w\), the other is \(-w\).

The small example in this project uses the circle \(S^1\), which is the set of two-dimensional vectors of length one. It maps each point on the circle to one real number: its weighted carbon exposure. The theorem then says there is a point whose exposure is the same as the exposure at the opposite point.

For this particular linear exposure function, that shared value must be zero. Reversing a vector reverses the sign of its exposure, so the only value equal to its own negative is zero. This conclusion depends on the continuous circle and the linear exposure function; it does not automatically carry over to a finite list of all-or-nothing portfolio choices.

## The continuous circle demo

The function `borsuk_ulam_circle()` in [`borsuk_ulam.py`](../borsuk_ulam.py) constructs a circle point

`w(t) = (cos(t), sin(t))`

and assigns it the scalar exposure

`f(t) = c_clean * cos(t) + c_dirty * sin(t)`.

Here `c_clean` and `c_dirty` are two carbon coefficients. In the pipeline, they are taken from the minimum and maximum carbon exposure values in the loaded asset universe, with the larger value normalized to 1. The circle coordinates are continuous weights: they can be fractional and negative. They should not be read as binary decisions to buy or short actual assets.

The point opposite `w(t)` is `w(t + pi)`, which equals `-w(t)`. Because the exposure is linear,

`f(t + pi) = -f(t)`.

The code defines `g(t) = f(t) - f(t + pi)`. Therefore `g(t) = 2*f(t)`. At a root of `g`, the two antipodal exposures are equal; because they are negatives of one another, both are zero. The implementation looks for that root by bisection on the interval from 0 to pi. For the positive carbon coefficients used here, the endpoint values have opposite signs, so the interval brackets a root.

This is a numerical demonstration of the continuous, two-coordinate case, not a portfolio optimizer. It returns a circle angle and a pair of continuous weights. The pipeline prints these at the end as a separate check; it does not feed those weights into the QUBO or use them to select the portfolio.

## How the portfolio is encoded

The actual optimization is in [`qubo.py`](../qubo.py). For `n` assets, it uses `2n` binary variables:

`v = [x_1, ..., x_n, y_1, ..., y_n]`

where `x_i = 1` means asset `i` is long and `y_i = 1` means asset `i` is short. The net position in asset `i` is `x_i - y_i`. In matrix form, the code writes this as

`net = position_map @ v`, where `position_map = [I, -I]`.

The QUBO objective combines squared net carbon exposure, portfolio covariance risk, penalties for not choosing exactly `K` long and `K` short positions, and a penalty for putting the same asset on both sides. Its energy has the form `v.T @ Q @ v + constant`; the solver searches for binary strings with low energy. Feasibility is also checked explicitly by `is_feasible()`.

The word “canonical” in the project refers to the main model representation used by the pipeline: this binary objective is converted exactly into an Ising model for QAOA, with a fixed order of long variables followed by short variables. It is not a special form of the Borsuk-Ulam theorem.

## The discrete antipodal symmetry check

For a portfolio bitstring, the code's `antipode()` swaps the two halves:

`[longs, shorts] -> [shorts, longs]`.

This reverses every net position, so net carbon changes sign. But the carbon contribution to the QUBO is the *square* of net carbon exposure, so its energy is unchanged. The covariance term is quadratic in the net positions, so it too is unchanged when all net positions reverse. The exact-cardinality penalties treat long and short sides equally, and the same-asset exclusivity penalty is unchanged by swapping sides. Thus, when the optional tie-breakers are off, the full QUBO energy is invariant under this swap.

`run_pipeline.py` checks this directly. It builds a symmetric model using the default `tau=0` and `lam=0`, finds a best feasible bitstring by brute force, swaps its long and short halves, then checks that the swapped string is feasible and has the same energy. Since both sides contain exactly `K` positions, the swapped string remains feasible. This is a finite, exact symmetry check for the model and input data; it is not an application of the continuous theorem that proves neutrality.

The distinction matters: the antipodal pair can have exposures `+C` and `-C` for a nonzero `C`. Equal QUBO energy does not mean either portfolio is carbon-neutral. The carbon-squared term encourages low exposure, but its symmetry alone only says the two opposite exposures cost the same.

## Why the production QUBO adds tie-breakers

After the symmetric check, the pipeline builds the model it writes to `optimization_model.json` with `tau=0.3` and `lam=0.5`. In `build_qubo()`, the optional diagonal term is based on

`odd = tau * carbon - lam * mu`.

It is added with one sign to the long variables and the opposite sign to the short variables. Swapping longs and shorts therefore reverses this contribution. These terms break the exact degeneracy between a portfolio and its long/short-swapped partner and can favor one of them based on carbon and expected return. Consequently, the saved, tie-broken model is not generally antipodally symmetric, even though the separate symmetric model used for the check is.

This is why the pipeline deliberately checks symmetry before adding the tie-breakers. The check demonstrates a property of the symmetric base objective; it does not claim that the final tie-broken QUBO still has equal energies for antipodal portfolios.

## What is and is not being claimed

The project uses the Borsuk-Ulam idea in two limited ways. First, it contains a continuous circle demo where a scalar linear carbon exposure is guaranteed to vanish somewhere, and the code numerically finds that point. Second, it uses a long/short swap as a discrete analogue of taking an antipode and verifies that the symmetric base QUBO assigns equal energy to a feasible pair.

Neither check proves that one of the discrete portfolios is exactly carbon-neutral. The continuous point may use arbitrary real-valued weights, while the QUBO portfolios use binary inclusion decisions. The discrete symmetry gives equal-and-opposite carbon exposures, not necessarily zero exposure. In the actual portfolio search, neutrality is encouraged by minimizing squared carbon exposure alongside risk and constraint penalties; the result must be assessed from its decoded net carbon value.

The broader theorem is useful motivation for thinking about opposite points and sign reversal. The actual optimization guarantee comes from the objective, constraints, and solver behavior—not from Borsuk-Ulam.
