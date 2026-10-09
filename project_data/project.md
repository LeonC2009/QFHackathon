Absolutely. Here is a **self-contained Markdown handoff document** you can paste into another ChatGPT conversation. It explains the project, the mathematical formulation, the dataset, what has already been decided, what we are currently implementing, and what the next chat should do.

````markdown
# Quantum Topological Carbon Hedging for Energy Futures

## 1. Project overview

I am building a quantum optimization project called:

**Quantum Topological Carbon Hedging for Energy Futures**

The basic idea is to use **quantum optimization (QAOA)** to construct a portfolio of energy futures that:

1. minimizes financial risk,
2. has approximately zero net carbon exposure,
3. uses real historical futures data,
4. uses a binary **QUBO / Ising formulation**,
5. is solved using **Qrisp**.

The project originally considered pairing low-carbon renewable energy futures such as wind/hydro against high-carbon fossil fuel futures. We have decided **not to use wind or hydro** because obtaining clean, free, comparable historical futures data for them is difficult.

Instead, the project uses several real fossil/energy futures with **different carbon intensities**.

The core concept therefore remains the same:

> Construct a long/short energy-futures portfolio whose carbon exposure approximately cancels out while its financial risk is minimized.

---

# 2. Important conceptual correction

The project originally used the **Borsuk-Ulam theorem** as part of its motivation.

The rough original idea was:

> For every carbon exposure vector, there should be an opposite vector that cancels it.

However, this should **not** be presented as a mathematical proof that an exact carbon-neutral portfolio must exist in our finite discrete asset universe.

Instead:

- Borsuk-Ulam is the **topological/mathematical inspiration** for looking for opposite/cancelling exposure configurations.
- The actual optimization problem is what determines whether a near-zero carbon hedge exists.
- The explicit **carbon exposure penalty in the QUBO** is what pushes the solution toward carbon neutrality.

So the project should not claim:

> "Borsuk-Ulam proves our portfolio has a carbon-neutral hedge."

It should say something closer to:

> "The Borsuk-Ulam theorem motivates the search for opposing exposure configurations, while the actual carbon-neutral hedge is obtained computationally through the QUBO/Ising optimization."

---

# 3. Dataset

## Data source

We are using the:

**U.S. Energy Information Administration (EIA)**

because it provides:

- official government data,
- free access,
- actual energy futures,
- long historical records,
- relatively easy downloadable XLS files.

The chosen research period is:

**2015-01-01 → 2024-04-05**

The end date is important because EIA's historical NYMEX futures data is available through April 5, 2024.

---

# 4. Futures being used

We are currently using four energy futures:

| Asset | Futures series | Approximate unit |
|---|---|---|
| WTI Crude Oil | NYMEX Contract 1 | USD/barrel |
| Natural Gas | NYMEX Contract 1 | USD/MMBtu |
| RBOB Gasoline | NYMEX Contract 1 | USD/gallon |
| No. 2 Heating Oil | NYMEX Contract 1 | USD/gallon |

These are all real energy futures.

The important point is that they do **not** have identical carbon intensities.

That gives us something to optimize.

---

# 5. Why these assets?

We need assets that have:

- real futures prices,
- historical data,
- different carbon intensities,
- enough price variation to calculate financial risk,
- a relationship to energy/carbon exposure.

For example:

- Natural gas has a lower direct CO₂ emissions factor per unit of energy than petroleum-derived fuels.
- Gasoline, diesel/heating oil, etc. have higher emissions factors.
- This creates different carbon exposures.

The optimizer can therefore combine long and short positions in these assets to make the weighted carbon exposure approach zero.

---

# 6. Carbon intensity data

We are using EIA emissions coefficients.

The relevant EIA carbon dioxide coefficients include approximately:

```text
Natural gas:
52.91 kg CO2 / MMBtu

Finished motor gasoline:
70.66 kg CO2 / MMBtu

Distillate fuel / home heating fuel:
74.14 kg CO2 / MMBtu
````

There is an important distinction between:

* the physical futures price unit,
* the energy content,
* and the carbon-emissions unit.

We should **not casually assign the same emissions coefficient to crude oil just because it is a petroleum product**.

The final implementation should clearly document where every carbon coefficient comes from and how the futures price units are converted into comparable carbon exposure.

Do not silently assume that:

```text
74.14 kg CO2/MMBtu
```

is the emissions factor for crude oil.

---

# 7. Current data-processing pipeline

The Python script being built should automatically:

1. download the EIA futures data,
2. save the raw XLS files,
3. clean the spreadsheets,
4. extract dates and prices,
5. restrict the data to:

```text
2015-01-01
through
2024-04-05
```

6. align the four futures on common trading dates,
7. calculate daily returns,
8. create the emissions metadata,
9. save everything as CSV files.

The intended directory structure is:

```text
data/
├── raw/
│   ├── wti_contract1.xls
│   ├── natural_gas_contract1.xls
│   ├── gasoline_contract1.xls
│   ├── heating_oil_contract1.xls
│   └── eia_co2_vol_mass.xlsx
│
├── wti.csv
├── natural_gas.csv
├── gasoline.csv
├── heating_oil.csv
├── energy_futures.csv
├── energy_returns.csv
├── emissions.csv
└── asset_metadata.csv
```

---

# 8. Current Python environment

The computer is a Mac.

Project location:

```text
/Users/eyus00/Developer/thon/
```

The virtual environment is:

```text
.venv
```

It is activated with:

```bash
source .venv/bin/activate
```

Required packages:

```bash
pip install pandas requests openpyxl xlrd
```

The script is:

```text
download_data.py
```

Run it with:

```bash
python download_data.py
```

---

# 9. Current data-download problem

The script successfully downloaded the WTI EIA XLS file but initially failed while trying to detect the `"Date"` header.

The original parser assumed the spreadsheet would contain a literal `"Date"` header.

That assumption is unreliable because EIA's XLS spreadsheets contain metadata/header formatting that varies from the simple structure we expected.

The parser is therefore being changed to detect the date column based on actual parseable datetime values rather than requiring a literal `"Date"` header.

The new approach is:

```python
for each column:
    try to parse values as dates

choose the column containing the most valid dates
```

Then:

```python
for the remaining columns:
    try to parse values as numbers

choose the appropriate numeric price column
```

This makes the downloader much more robust against EIA spreadsheet formatting.

---

# 10. What `energy_futures.csv` should represent

The combined futures dataset should look conceptually like:

```text
date,wti,natural_gas,gasoline,heating_oil
2015-01-02,...
2015-01-05,...
2015-01-06,...
...
```

The exact number of rows depends on the common trading dates available across all four datasets.

All assets need to be aligned by date.

---

# 11. Returns

The optimization should use returns to estimate financial risk.

For each asset:

$$
r_{i,t}
=
\frac{P_{i,t}-P_{i,t-1}}{P_{i,t-1}}
$$

or equivalently:

$$
r_{i,t}
=
\frac{P_{i,t}}{P_{i,t-1}}-1
$$

where:

* \(P_{i,t}\) = price of asset \(i\) on day \(t\)
* \(r_{i,t}\) = daily return.

The resulting dataset should be:

```text
date,wti,natural_gas,gasoline,heating_oil
```

but with the values representing daily returns rather than prices.

---

# 12. Financial risk

The main financial-risk measure is based on the covariance matrix.

From the daily return matrix we calculate:

$$
\Sigma
$$

where:

$$
\Sigma_{ij}
=
\operatorname{Cov}(r_i,r_j)
$$

This captures how the futures move relative to each other.

For a portfolio vector \(s\), portfolio variance is:

$$
s^T\Sigma s
$$

This becomes the financial-risk component of the optimization.

---

# 13. Long/short variables

We use binary variables.

For each asset \(i\):

$$
x_i \in \{0,1\}
$$

means:

```text
x_i = 1 → long asset i
x_i = 0 → not long asset i
```

and:

$$
y_i \in \{0,1\}
$$

means:

```text
y_i = 1 → short asset i
y_i = 0 → not short asset i
```

Therefore each asset has two binary decisions.

For four assets:

```text
x_wti
x_gas
x_gasoline
x_heating_oil

y_wti
y_gas
y_gasoline
y_heating_oil
```

There are therefore 8 binary variables in the basic formulation.

---

# 14. Net position

Define:

$$
s_i=x_i-y_i
$$

So:

```text
s_i = +1 → long
s_i = -1 → short
s_i = 0  → not selected
```

This is useful because the portfolio can be represented as a signed vector:

$$
s=(s_1,s_2,\dots,s_n)
$$

---

# 15. Exclusivity constraint

We do not want the same asset to be simultaneously long and short.

Therefore:

$$
x_i y_i = 0
$$

for every asset.

The QUBO can enforce this using:

$$
\lambda_E \sum_i x_i y_i
$$

where:

$$
\lambda_E > 0
$$

is a penalty coefficient.

If both \(x_i=1\) and \(y_i=1\), the objective receives a penalty.

---

# 16. Carbon exposure

Each asset receives a carbon-intensity coefficient:

$$
c_i
$$

Collect these into:

$$
c=(c_1,c_2,\dots,c_n)
$$

The portfolio's net carbon exposure is:

$$
C=s^Tc
$$

or:

$$
C=\sum_i c_i s_i
$$

If the portfolio has equal long and short notional weighting, a carbon-neutral portfolio would satisfy approximately:

$$
C=0
$$

---

# 17. Carbon-neutrality penalty

We don't necessarily require a hard equality constraint.

Instead, we square the carbon exposure:

$$
C^2=(c^Ts)^2
$$

and add it to the objective:

$$
\lambda_C(c^Ts)^2
$$

where:

$$
\lambda_C>0
$$

is the carbon penalty strength.

This means:

* large carbon imbalance → large penalty
* small carbon imbalance → small penalty
* zero carbon imbalance → zero penalty

This is the main mechanism that pushes the solution toward carbon neutrality.

---

# 18. Financial risk term

The financial risk term is:

$$
\lambda_R s^T\Sigma s
$$

where:

* \(s\) = long/short portfolio vector,
* \(\Sigma\) = return covariance matrix,
* \(\lambda_R\) = risk weight.

We want this term to be small.

---

# 19. Optional expected-return term

If we want the optimizer to prefer potentially profitable positions, we can calculate:

$$
\mu_i = E[r_i]
$$

and define:

$$
\mu=(\mu_1,\dots,\mu_n)
$$

Then:

$$
-\lambda_P\mu^Ts
$$

can be included.

The minus sign is important because the optimization minimizes the objective.

A positive expected return therefore decreases the objective.

However, this should be used carefully because historical average returns can be noisy.

The simplest first version can omit expected return and focus on:

```text
carbon neutrality
+
financial risk
```

---

# 20. Position/cardinality constraint

We may want exactly \(K\) long positions and \(K\) short positions.

For example:

$$
K=2
$$

Then:

$$
\sum_i x_i=K
$$

and:

$$
\sum_i y_i=K
$$

can be enforced using squared penalties:

$$
\lambda_K
\left(
\sum_i x_i-K
\right)^2
$$

and:

$$
\lambda_K
\left(
\sum_i y_i-K
\right)^2
$$

Together:

$$
\lambda_K
\left(\sum_i x_i-K\right)^2
+
\lambda_K
\left(\sum_i y_i-K\right)^2
$$

This keeps the portfolio from simply selecting every asset.

---

# 21. Full QUBO objective

The main objective is approximately:

$$
\boxed{
H(x,y)
=
\lambda_C(c^Ts)^2
+
\lambda_Rs^T\Sigma s
-
\lambda_P\mu^Ts
+
\lambda_K
\left(\sum_i x_i-K\right)^2
+
\lambda_K
\left(\sum_i y_i-K\right)^2
+
\lambda_E\sum_i x_iy_i
}
$$

where:

$$
s_i=x_i-y_i
$$

and:

$$
x_i,y_i\in\{0,1\}
$$

This is the central optimization problem.

---

# 22. What the optimizer is actually trying to do

In simple language:

> Pick a set of energy futures to go long and short so that the carbon emissions associated with the long positions are approximately cancelled by the carbon exposure of the short positions, while also keeping the portfolio financially low-risk.

For example, conceptually:

```text
LONG:
Natural Gas
Gasoline

SHORT:
Heating Oil
WTI
```

The optimizer would calculate whether this combination:

* cancels carbon exposure,
* has acceptable financial risk,
* satisfies the required number of long/short positions.

The actual final combination should come from the optimization rather than being manually chosen.

---

# 23. Why this is a hedging problem

The project is NOT simply:

> "Find the greenest energy portfolio."

Instead, it is:

> "Find a long/short portfolio whose carbon exposure is hedged."

This distinction matters.

We are not simply minimizing:

$$
c^Ts
$$

because that could lead to trivial or undesirable solutions.

We are minimizing:

$$
(c^Ts)^2
$$

while simultaneously considering:

$$
s^T\Sigma s
$$

and portfolio constraints.

So carbon neutrality is one objective among several.

---

# 24. QUBO → Ising conversion

The user specifically wants an **Ising/QUBO formulation**, not just a generic classical QUBO solver.

For a binary variable:

$$
x_i\in\{0,1\}
$$

we use the standard transformation:

$$
x_i=\frac{1+z_i}{2}
$$

where:

$$
z_i\in\{-1,+1\}
$$

Similarly:

$$
y_i=\frac{1+w_i}{2}
$$

where:

$$
w_i\in\{-1,+1\}
$$

This converts the binary QUBO into an Ising Hamiltonian.

---

# 25. Why Ising?

Quantum algorithms such as **QAOA** naturally work with Hamiltonians composed of Pauli operators.

The classical QUBO:

$$
Q(x)
$$

can be transformed into an Ising Hamiltonian:

$$
H_C
=
\sum_i h_i Z_i
+
\sum_{i<j}J_{ij}Z_iZ_j
+
\text{constant}
$$

where:

* \(Z_i\) is a Pauli-Z operator,
* \(h_i\) are local fields,
* \(J_{ij}\) are pairwise couplings.

The constant can normally be ignored because it does not change which state minimizes the Hamiltonian.

---

# 26. QAOA

We want to solve the Ising problem using:

**QAOA — Quantum Approximate Optimization Algorithm**

The basic structure is:

$$
|\psi(\boldsymbol{\gamma},\boldsymbol{\beta})\rangle
=
U_B(\boldsymbol{\beta})
U_C(\boldsymbol{\gamma})
|+\rangle^{\otimes n}
$$

where:

$$
U_C(\gamma)
=
e^{-i\gamma H_C}
$$

is the cost Hamiltonian unitary, and:

$$
U_B(\beta)
=
e^{-i\beta H_B}
$$

is the mixer unitary.

The optimizer changes:

$$
\gamma,\beta
$$

to minimize the expected cost:

$$
\langle H_C\rangle
$$

---

# 27. Qrisp

The implementation should use:

**Qrisp**

rather than PennyLane.

Qrisp provides tools for:

* quantum circuits,
* quantum variables,
* Hamiltonians,
* QAOA,
* Ising-style cost Hamiltonians.

The important requirement is:

> Use Qrisp's actual Ising/QAOA functionality rather than simply using a generic classical QUBO solver.

There is a generic QUBO solver in Qrisp, but that is **not the main approach desired for this project**.

The point of the project is to demonstrate the QUBO → Ising → QAOA pipeline.

---

# 28. Desired Qrisp pipeline

Conceptually:

```text
EIA futures data
        ↓
clean prices
        ↓
daily returns
        ↓
covariance matrix Σ
        ↓
carbon coefficients c
        ↓
construct QUBO
        ↓
convert QUBO → Ising Hamiltonian
        ↓
construct Qrisp cost Hamiltonian
        ↓
QAOA
        ↓
measure candidate bitstrings
        ↓
decode long/short positions
        ↓
evaluate carbon exposure + financial risk
```

---

# 29. Number of qubits

With 4 assets and two binary variables per asset:

```text
4 x 2 = 8 binary variables
```

Therefore the basic problem uses:

$$
8\text{ qubits}
$$

if each binary variable is mapped to one qubit.

This is intentionally small.

The project is not trying to claim that an 8-qubit simulation is commercially useful.

Instead, it demonstrates the methodology:

```text
real financial data
→ optimization model
→ QUBO
→ Ising Hamiltonian
→ QAOA
→ portfolio
```

---

# 30. Classical benchmark

We should also solve the same optimization classically.

This is important because otherwise we cannot tell whether QAOA found a good solution.

For a small 8-variable problem, we can enumerate all possible bitstrings:

$$
2^8=256
$$

possibilities.

This is trivial computationally.

The classical benchmark can therefore:

1. enumerate all 256 configurations,
2. calculate their objective values,
3. find the global optimum,
4. compare QAOA's best result with it.

This is actually a very useful part of the project.

---

# 31. QAOA evaluation

After running QAOA, we should decode the measured bitstring.

Example:

```text
x = [1,0,1,0]
y = [0,1,0,1]
```

This means:

```text
LONG:
WTI
Gasoline

SHORT:
Natural Gas
Heating Oil
```

depending on the asset ordering.

Then calculate:

### Carbon exposure

$$
C=c^Ts
$$

### Carbon imbalance

$$
|C|
$$

### Financial risk

$$
R=s^T\Sigma s
$$

### Objective

$$
H(x,y)
$$

Then compare the QAOA result with the exact classical optimum.

---

# 32. Important issue: units

This is one of the most important technical parts of the project.

The four futures have different price units:

```text
WTI:
USD/barrel

Natural Gas:
USD/MMBtu

Gasoline:
USD/gallon

Heating Oil:
USD/gallon
```

Carbon intensity is generally expressed on an energy basis such as:

```text
kg CO2/MMBtu
```

Therefore we should **not simply put the raw carbon coefficients into the vector c without thinking about units**.

We need to define what one "position" represents.

A simple academic formulation can normalize each asset's carbon exposure to a consistent notional.

For example:

```text
one position = fixed monetary notional
```

or:

```text
one position = fixed energy notional
```

The chosen convention must be explicitly stated.

Do not mix:

```text
kg CO2/MMBtu
```

with:

```text
USD/barrel
```

without a conversion/normalization step.

---

# 33. Recommended normalization approach

For a clean demonstration, define each position as an equal notional exposure.

For example:

```text
$1,000 notional per selected long/short position
```

Then determine the corresponding underlying quantity for each futures contract.

The carbon exposure of each position can then be normalized into a common unit.

The exact method should be carefully documented and should not be invented casually.

If exact contract specifications are used, verify them from an authoritative source.

---

# 34. What the project is NOT doing

The project is NOT:

* predicting oil prices,
* predicting climate change,
* building a trading bot,
* claiming guaranteed profits,
* proving that carbon-neutral portfolios always exist,
* proving Borsuk-Ulam directly gives a trading strategy,
* claiming QAOA is already better than classical optimization,
* using renewable-energy futures anymore,
* simply minimizing the carbon footprint of a portfolio.

It is an **optimization demonstration**.

---

# 35. Main research question

A good formulation of the research question is:

> **Can a QUBO/Ising formulation solved using QAOA identify a low-risk long/short energy-futures portfolio with approximately neutral carbon exposure?**

Possible secondary questions:

1. How close to zero can the carbon exposure become?
2. How does adding the carbon penalty change the portfolio?
3. How does QAOA compare with the exact classical optimum?
4. How does the solution change when the carbon penalty is increased?
5. How does the solution change when the risk penalty is increased?

---

# 36. Suggested experiments

## Experiment 1 — No carbon penalty

Set:

$$
\lambda_C=0
$$

Optimize financial risk only.

This gives a baseline.

---

## Experiment 2 — Carbon-neutral optimization

Use:

$$
\lambda_C>0
$$

and compare the resulting carbon exposure.

Expected result:

```text
carbon exposure should move closer to zero
```

---

## Experiment 3 — Change carbon penalty

Run:

```text
λC = small
λC = medium
λC = large
```

Observe:

* carbon exposure,
* financial risk,
* total objective.

This demonstrates the trade-off between:

```text
carbon neutrality
```

and:

```text
financial risk
```

---

## Experiment 4 — QAOA vs exact classical

Compare:

```text
Exact optimum
vs
QAOA best measured solution
```

Metrics:

```text
objective value
carbon exposure
financial risk
portfolio composition
```

---

# 37. What success looks like

A successful result does NOT require:

> "QAOA makes money."

Instead, success means:

1. the QUBO is mathematically correct,
2. it converts correctly into an Ising Hamiltonian,
3. Qrisp can construct and optimize the QAOA circuit,
4. QAOA finds a valid portfolio,
5. the portfolio has low carbon imbalance,
6. the portfolio has reasonable financial risk,
7. the result can be compared against the exact classical optimum.

---

# 38. Potential final result table

The final paper/project could have a table like:

| Method            | Long positions | Short positions | Carbon exposure | Risk | Objective |
| ----------------- | -------------- | --------------- | --------------: | ---: | --------: |
| Classical optimum | ...            | ...             |             ... |  ... |       ... |
| QAOA              | ...            | ...             |             ... |  ... |       ... |

And potentially:

|  λC | Carbon exposure | Risk | Objective |
| --: | --------------: | ---: | --------: |
|   0 |             ... |  ... |       ... |
|   1 |             ... |  ... |       ... |
|  10 |             ... |  ... |       ... |
| 100 |             ... |  ... |       ... |

The exact values will come from the actual dataset and optimization.

---

# 39. Current status

The project is currently at the **data preparation stage**.

The EIA data downloader has been written.

The current script downloads:

```text
WTI
Natural Gas
Gasoline
Heating Oil
EIA emissions data
```

and attempts to clean them.

The current issue is an EIA XLS parsing problem.

The script originally searched for a literal `"Date"` header and failed with:

```text
ValueError:
Could not find the EIA Date header row.
```

The fix is to detect the date column from actual datetime values instead of relying on the spreadsheet's header text.

After the data pipeline works, the next steps are:

```text
1. Verify energy_futures.csv
2. Verify energy_returns.csv
3. Verify emissions.csv
4. Verify units / carbon normalization
5. Calculate covariance matrix
6. Build the QUBO
7. Convert QUBO → Ising
8. Implement QAOA in Qrisp
9. Decode QAOA results
10. Compare against exact classical enumeration
11. Run carbon-penalty experiments
12. Produce graphs/tables
13. Write the methodology and results
```

---

# 40. Important implementation principle

Do not jump directly into QAOA before verifying the classical mathematical formulation.

The recommended development order is:

```text
DATA
 ↓
classical portfolio calculations
 ↓
QUBO
 ↓
brute-force optimum
 ↓
QUBO → Ising verification
 ↓
Qrisp Hamiltonian
 ↓
QAOA
 ↓
comparison
```

This makes debugging much easier.

If the QAOA answer looks wrong, we can determine whether the problem is:

```text
data
→ carbon normalization
→ QUBO
→ Ising conversion
→ Qrisp implementation
→ QAOA parameters
```

rather than debugging everything at once.

---

# 41. Final conceptual summary

The project can be explained simply as:

> We take real historical energy-futures data from the U.S. EIA and assign each energy future a carbon-intensity value. We then represent the decision to go long or short each future using binary variables. A QUBO objective penalizes carbon imbalance and financial risk while enforcing portfolio constraints. We convert that QUBO into an Ising Hamiltonian and use Qrisp's QAOA implementation to search for a low-cost quantum solution. Finally, we compare the QAOA solution with an exact classical solution to determine how well QAOA solves the carbon-hedging problem.

The central mathematical objective is:

$$
\boxed{
H(x,y)
=
\lambda_C(c^Ts)^2
+
\lambda_Rs^T\Sigma s
-
\lambda_P\mu^Ts
+
\lambda_K
\left(\sum_i x_i-K\right)^2
+
\lambda_K
\left(\sum_i y_i-K\right)^2
+
\lambda_E\sum_i x_iy_i
}
$$

with:

$$
s_i=x_i-y_i
$$

and:

$$
x_i,y_i\in\{0,1\}
$$

Then:

$$
x_i=\frac{1+Z_i}{2}
$$

is used to transform the binary QUBO into an Ising representation suitable for QAOA.

---

# 42. Instructions for the next ChatGPT

Please continue this project from the information above.

The immediate priority is:

**Get the EIA data pipeline working correctly.**

After that:

1. inspect the actual downloaded EIA datasets,
2. verify the four futures are being parsed correctly,
3. verify dates and prices,
4. verify the carbon coefficients and units,
5. design a defensible common carbon-exposure normalization,
6. construct the QUBO mathematically,
7. implement the QUBO as an Ising Hamiltonian,
8. use **Qrisp QAOA**, not just a generic QUBO solver,
9. create an exact classical benchmark,
10. compare QAOA against the classical optimum.

Be careful with units and do not invent carbon coefficients.

Also keep the Borsuk-Ulam theorem as **motivation/inspiration**, not as a false proof that a carbon-neutral hedge must exist.

The main goal is a technically correct, understandable quantum-optimization project using real EIA energy-futures data.

```
```
