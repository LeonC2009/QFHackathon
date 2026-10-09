# Quantum Topological Carbon Hedging for Energy Futures

## Project Progress Report

This document explains what the project is trying to do, what has been implemented, how the implementation works, what has been verified, and what remains to be done.

The project is an academic quantum-optimization demonstration. It uses real historical energy-futures data from the U.S. Energy Information Administration (EIA), formulates a long/short carbon-hedging problem as a binary QUBO, converts that model into an Ising-style cost Hamiltonian, and runs a small QAOA experiment with Qrisp.

The purpose is methodological rather than commercial. The project is not a trading bot, a price-forecasting system, or a claim that quantum optimization currently outperforms classical optimization.

---

## 1. Main Research Question

The central question is:

> Can a QUBO/Ising formulation solved using QAOA identify a low-risk long/short energy-futures portfolio with approximately neutral carbon exposure?

The project combines three types of information:

1. **Market data**: historical daily futures prices.
2. **Environmental data**: carbon-dioxide combustion coefficients.
3. **Optimization structure**: binary long/short decisions, risk, carbon exposure, and portfolio constraints.

The intended workflow is:

```text
EIA futures data
        |
        v
clean historical prices
        |
        v
daily returns and covariance matrix
        |
        v
carbon exposure normalization
        |
        v
binary long/short portfolio model
        |
        v
QUBO
        |
        v
Ising coefficients
        |
        v
Qrisp QAOA
        |
        v
measured bitstrings and decoded portfolios
        |
        v
comparison with exact classical enumeration
```

---

## 2. Conceptual Goal

The portfolio contains four energy futures. For each asset, the optimizer can choose one of three practical states:

```text
not selected
long
short
```

A long position contributes positive exposure to the portfolio. A short position contributes negative exposure. If carbon exposure is assigned consistently to each position, the long and short positions can partially cancel one another.

The intended result is not simply the portfolio with the smallest absolute emissions. Instead, the optimizer balances:

- carbon neutrality,
- financial risk,
- exactly two long positions,
- exactly two short positions,
- and the requirement that an asset cannot be long and short simultaneously.

The portfolio is therefore a carbon-hedging portfolio rather than a portfolio that merely selects the lowest-carbon assets.

---

## 3. Assets and Data Source

The project uses four real EIA NYMEX Contract 1 daily futures series:

| Internal asset name | Instrument | Price unit |
| --- | --- | --- |
| `wti` | Cushing, Oklahoma crude oil futures, Contract 1 | USD/barrel |
| `natural_gas` | Natural gas futures, Contract 1 | USD/MMBtu |
| `gasoline` | New York Harbor Reformulated RBOB Regular Gasoline futures, Contract 1 | USD/gallon |
| `heating_oil` | New York Harbor No. 2 Heating Oil futures, Contract 1 | USD/gallon |

The data source is the U.S. Energy Information Administration. The selected research period is:

```text
2015-01-01 through 2024-04-05
```

April 5, 2024 is important because the historical EIA NYMEX series used by this project ends there.

The downloader saves the original downloaded files under:

```text
data/raw/
```

The cleaned per-asset files are saved under `data/`, along with combined prices, returns, emissions metadata, and optimization artifacts.

---

## 4. Data Preparation

The data-preparation script is [download_data.py](download_data.py).

It performs the following operations:

1. Downloads the four EIA futures workbooks.
2. Downloads the EIA carbon-coefficient workbook.
3. Saves the raw files for traceability.
4. Finds the worksheet containing the historical observations.
5. Detects the date column from actual parseable date values.
6. Detects the numeric price column.
7. Restricts observations to the project period.
8. Removes duplicate dates.
9. Sorts observations chronologically.
10. Aligns all assets on common trading dates.
11. Calculates daily percentage returns.
12. Writes emissions and asset metadata files.

### 4.1 Why worksheet selection was necessary

The EIA workbooks do not always put the time series on the first worksheet. The first worksheet can be a workbook-contents page, while the actual series is on a worksheet such as `Data 1`.

The parser therefore reads the available worksheets and selects the one containing the largest number of dates inside the research window.

This is more robust than assuming a fixed worksheet name or assuming the first sheet contains the data.

### 4.2 Why literal header detection was removed

The original parser expected a literal cell containing `Date`. This failed because EIA workbook formatting varies between files.

The current parser instead checks each column, attempts to parse its values as dates, and counts values within the research period. The column with the most valid in-range dates is treated as the date column.

The same principle is used when identifying the numeric price column: the parser searches the remaining columns for one containing enough numeric observations.

### 4.3 Correct daily series URLs

The gasoline and heating-oil URLs initially pointed to annual series because the endpoint suffix used `DPGa`. That produced only nine observations in the selected date range.

The endpoints were corrected to the daily series suffix `DPGd`. After that correction, both series contained more than 2,300 daily observations, as expected.

---

## 5. Data Outputs

The downloader currently produces the following important files:

```text
data/wti.csv
data/natural_gas.csv
data/gasoline.csv
data/heating_oil.csv
data/energy_futures.csv
data/energy_returns.csv
data/emissions.csv
data/asset_metadata.csv
data/raw/*.xls
data/raw/eia_co2_vol_mass.xlsx
```

The verified output sizes are:

| Dataset | Rows | Date range |
| --- | ---: | --- |
| WTI cleaned prices | 2,330 | 2015-01-02 to 2024-04-05 |
| Natural gas cleaned prices | 2,334 | 2015-01-02 to 2024-04-05 |
| Gasoline cleaned prices | 2,318 | 2015-01-02 to 2024-04-05 |
| Heating oil cleaned prices | 2,318 | 2015-01-02 to 2024-04-05 |
| Combined futures prices | 2,315 | 2015-01-02 to 2024-04-05 |
| Daily returns | 2,314 | 2015-01-05 to 2024-04-05 |

The individual files have slightly different row counts because each series has its own publication and holiday calendar. The combined file contains only dates shared by all four assets.

The combined price file has this structure:

```text
date,wti_price_usd_per_bbl,gasoline_price_usd_per_gallon,heating_oil_price_usd_per_gallon,natural_gas_price_usd_per_mmbtu
```

The returns file has this structure:

```text
date,wti,natural_gas,gasoline,heating_oil
```

The values in the returns file are daily percentage changes:

$$
 r_{i,t} = \frac{P_{i,t}}{P_{i,t-1}} - 1
$$

where $P_{i,t}$ is the price of asset $i$ on day $t$.

---

## 6. Carbon Coefficients and Unit Convention

The assets have different price units, so raw prices and raw carbon coefficients cannot be placed directly into one vector without a convention.

The project uses the following academic normalization:

```text
one selected position = $1,000 notional exposure
```

For each asset, the $1,000 notional is converted into an approximate physical quantity using the sample mean futures price. That quantity is converted into MMBtu using an energy-content convention. Finally, the relevant EIA carbon factor is applied.

For asset $i$:

$$
 c_i =
 \frac{1000}{\overline{P_i}}
 \times e_i
 \times f_i
$$

where:

- $\overline{P_i}$ is the sample mean futures price,
- $e_i$ is the MMBtu per price-unit conversion,
- $f_i$ is the carbon factor in kg CO2/MMBtu,
- $c_i$ is the approximate kg CO2 associated with one $1,000 notional position.

The energy-content conventions in the implementation are:

| Asset | MMBtu conversion |
| --- | ---: |
| WTI | 5.8 MMBtu/barrel |
| Natural gas | 1.0 MMBtu/MMBtu |
| Gasoline | 0.125 MMBtu/gallon |
| Heating oil | 0.1385 MMBtu/gallon |

The current carbon exposure coefficients are:

| Asset | kg CO2 per $1,000 position |
| --- | ---: |
| WTI | 7,082.13 |
| Natural gas | 16,673.90 |
| Gasoline | 4,620.47 |
| Heating oil | 4,973.94 |

These values should be treated as a documented modeling convention for this demonstration, not as a complete lifecycle-emissions assessment. They approximate combustion-related exposure under an equal-dollar position convention.

The EIA factors used by the data script are:

| Asset | Fuel label | Factor |
| --- | --- | ---: |
| WTI | crude oil | 74.47 kg CO2/MMBtu |
| Natural gas | natural gas | 52.91 kg CO2/MMBtu |
| Gasoline | finished motor gasoline | 70.66 kg CO2/MMBtu |
| Heating oil | distillate/home-heating fuel | 74.14 kg CO2/MMBtu |

The crude-oil coefficient is explicitly labeled in the script rather than silently reusing the heating-oil coefficient.

A future version should verify the energy-content assumptions and contract specifications against authoritative documentation if the project is developed into a formal research result.

---

## 7. Binary Portfolio Variables

There are four assets and two binary variables for each asset.

For every asset $i$:

$$
 x_i \in \{0,1\}
$$

represents the long decision, and:

$$
 y_i \in \{0,1\}
$$

represents the short decision.

The current variable order is:

```text
x_wti
x_natural_gas
x_gasoline
x_heating_oil
y_wti
y_natural_gas
y_gasoline
y_heating_oil
```

There are therefore:

$$
4 \times 2 = 8
$$

binary variables and, consequently, eight qubits in the QAOA experiment.

The signed net position is:

$$
 s_i = x_i - y_i
$$

Thus:

```text
s_i = +1  means long
s_i = -1  means short
s_i = 0   means not selected
```

---

## 8. Optimization Objective

The implementation is in [optimize_portfolio.py](optimize_portfolio.py).

The conceptual objective is:

$$
 H(x,y) =
 \lambda_C(c^T s)^2
 + \lambda_R s^T \Sigma s
 + \lambda_K\left(\sum_i x_i - K\right)^2
 + \lambda_K\left(\sum_i y_i - K\right)^2
 + \lambda_E\sum_i x_i y_i
$$

where:

- $c$ is the carbon exposure vector,
- $\Sigma$ is the daily-return covariance matrix,
- $K=2$ is the requested number of long and short positions,
- $\lambda_C$ controls carbon imbalance,
- $\lambda_R$ controls financial risk,
- $\lambda_K$ enforces cardinality,
- $\lambda_E$ enforces long/short exclusivity.

The optional expected-return term from the project specification is not included yet. The first implementation intentionally focuses on carbon neutrality, risk, and hard portfolio structure.

### 8.1 Carbon term

The net carbon exposure is:

$$
 C = c^T s
$$

The square:

$$
 C^2 = (c^T s)^2
$$

penalizes both positive and negative imbalance. A portfolio with exposure $+10,000$ and one with exposure $-10,000$ receive the same carbon penalty.

### 8.2 Financial-risk term

The covariance matrix is calculated from the daily returns:

$$
 \Sigma_{ij} = \operatorname{Cov}(r_i,r_j)
$$

For a signed position vector $s$, the portfolio variance is:

$$
 R = s^T\Sigma s
$$

This is the financial-risk contribution used by the model.

### 8.3 Cardinality constraints

The model asks for exactly two long and two short positions:

$$
 \sum_i x_i = 2
$$

and:

$$
 \sum_i y_i = 2
$$

Each equality is converted into a squared penalty. The penalty is zero when the target is met and positive otherwise.

### 8.4 Exclusivity constraint

The same asset should not be selected on both sides. The model applies:

$$
 \lambda_E x_i y_i
$$

for every asset. If both binary variables are one, the objective increases by the exclusivity penalty.

---

## 9. Objective Scaling Correction

The first direct implementation revealed a numerical issue during exact enumeration.

The physical carbon coefficients are thousands of kg CO2 per position. Squaring those raw values creates terms on the order of tens or hundreds of millions. The original cardinality and exclusivity penalties were only 10,000, so an invalid portfolio could look cheaper than a valid portfolio simply because it canceled carbon perfectly while violating the structural constraints.

That is not the intended model behavior.

The implementation now scales the objective inputs before constructing the QUBO:

```text
normalized carbon = carbon / mean(carbon)
normalized risk = covariance / max(covariance)
```

The model still reports the physical carbon exposure and unscaled financial risk for the final portfolio. Only the internal optimization balance is normalized.

The current scales are:

```text
carbon scale = 8,337.609 kg CO2
risk scale   = 0.00564746
```

This keeps the numerical magnitudes comparable and lets the 10,000 cardinality and exclusivity penalties act as hard constraints for this small demonstration.

This scaling is an important part of the implementation because QUBO coefficients are sensitive to relative magnitude. A future research version should perform a systematic sensitivity analysis over the penalty weights rather than treating these values as universally optimal.

---

## 10. QUBO Construction

The implementation creates an 8 by 8 symmetric matrix $Q$ such that:

$$
 H(b) = b^T Q b + C_0
$$

where $b$ is the eight-element binary vector and $C_0$ is the constant generated by the cardinality penalties.

The position mapping can be written as a matrix $B$:

$$
 s = B b
$$

where the first four variables contribute positively and the last four variables contribute negatively.

The carbon term becomes:

$$
(c^T B b)^2
= b^T B^T c c^T B b
$$

The risk term becomes:

$$
(Bb)^T\Sigma(Bb)
= b^T B^T\Sigma B b
$$

The cardinality and exclusivity penalties are then added to the same matrix.

The resulting model is written to:

```text
data/optimization_model.json
```

That JSON file contains:

- asset names,
- binary variable order,
- notional convention,
- energy-content conversions,
- physical carbon coefficients,
- covariance matrix,
- QUBO matrix,
- QUBO constant,
- Ising fields,
- Ising couplings,
- exact classical optimum.

This makes the model inspectable without rerunning the data download.

---

## 11. QUBO to Ising Conversion

For each binary variable $b_i$, use:

$$
 b_i = \frac{1 + z_i}{2}
$$

where:

$$
 z_i \in \{-1,+1\}
$$

is the corresponding Ising or Pauli-Z variable.

Substituting this transformation into the QUBO gives:

$$
 b^T Q b
= \text{constant}
+ \sum_i h_i z_i
+ \sum_{i<j} J_{ij} z_i z_j
$$

For the symmetric QUBO representation used here, the exported coefficients are calculated as:

$$
 h_i = \frac{1}{2}\sum_j Q_{ij}
$$

and:

$$
 J_{ij} = \frac{1}{2}Q_{ij}, \qquad i<j
$$

up to the overall constant, which does not change the minimizing bitstring.

The implementation stores these values as `ising_fields` and `ising_couplings` in `optimization_model.json`.

The QAOA cost operator uses the equivalent QUBO phase-separator form. This is mathematically the same cost model as the exported Ising representation; the Qrisp circuit applies the corresponding global phase, single-qubit Z rotations, and two-qubit ZZ rotations.

---

## 12. Exact Classical Benchmark

The exact benchmark is deliberately included before relying on QAOA.

There are eight binary variables, so the complete search space contains:

$$
2^8 = 256
$$

possible bitstrings.

[optimize_portfolio.py](optimize_portfolio.py) enumerates every one of those states, evaluates the QUBO objective, decodes the long and short positions, and calculates physical metrics.

The exact minimum found so far is:

```text
Long:
    natural_gas
    gasoline

Short:
    wti
    heating_oil
```

Its metrics are:

| Metric | Value |
| --- | ---: |
| Objective | 2.5468417491 |
| Carbon exposure | 9,238.304 kg CO2 per signed portfolio |
| Financial risk | 0.0074496586 |
| Long count | 2 |
| Short count | 2 |
| Long/short overlap | none |

The carbon exposure is not zero. This is an important result rather than a failure: with the current assets, equal-dollar position convention, and exactly two long plus two short positions, exact carbon neutrality is not necessarily attainable.

The model finds the lowest-cost valid state, not a guaranteed zero-exposure state.

There is also a sign-reversed equivalent portfolio because the main objective uses squared carbon exposure and quadratic risk. Swapping every long position with its corresponding short position changes the sign of carbon exposure but preserves squared carbon imbalance and variance.

---

## 13. Qrisp QAOA Implementation

The QAOA runner is [run_qaoa.py](run_qaoa.py).

Qrisp was installed into the project virtual environment. The implementation uses:

```python
from qrisp import QuantumVariable, gphase, rz, rzz
from qrisp.qaoa import QAOAProblem, RX_mixer
```

The QAOA problem contains:

1. a cost operator derived from the QUBO matrix,
2. Qrisp's RX mixer,
3. a classical cost function used during parameter optimization.

The current experiment uses:

```text
depth    = 1
shots    = 256
max_iter = 10
```

The eight QUBO variables are represented by an eight-qubit `QuantumVariable`.

The cost operator applies:

- a global phase for the constant part,
- `rz` rotations for one-qubit Z terms,
- `rzz` rotations for pairwise ZZ terms.

The QAOA process is:

```text
prepare a uniform superposition
        |
        v
apply cost and mixer layers
        |
        v
optimize QAOA angles with a classical optimizer
        |
        v
measure 256 samples
        |
        v
rank measured bitstrings by QUBO energy
        |
        v
decode the best bitstring as long/short positions
```

The output is saved to:

```text
data/qaoa_result.json
```

---

## 14. QAOA Result Achieved So Far

A verified QAOA run produced the bitstring:

```text
01101001
```

Using the documented variable order, this means:

```text
x_wti          = 0
x_natural_gas  = 1
x_gasoline     = 1
x_heating_oil  = 0

y_wti          = 1
y_natural_gas  = 0
y_gasoline     = 0
y_heating_oil  = 1
```

Therefore the decoded portfolio is:

```text
LONG:
    natural_gas
    gasoline

SHORT:
    wti
    heating_oil
```

The QAOA result matches the exact classical optimum for this run.

| Metric | QAOA | Exact classical |
| --- | ---: | ---: |
| Constant-adjusted objective | 2.5468417491 | 2.5468417491 |
| Carbon exposure | 9,238.304 kg CO2 | 9,238.304 kg CO2 |
| Financial risk | 0.0074496586 | 0.0074496586 |
| Long positions | natural gas, gasoline | natural gas, gasoline |
| Short positions | WTI, heating oil | WTI, heating oil |

The measured probability of the best bitstring varies between runs because QAOA sampling is stochastic. One verified run recorded a probability of approximately:

```text
0.01171875
```

The probability is not itself the objective. The important comparison is whether the measured candidate is valid and how its objective and physical metrics compare with the exact optimum.

QAOA can also return the sign-reversed portfolio, which has the same squared objective and risk under this symmetric formulation. That is a valid degeneracy of the model, not necessarily an implementation error.

---

## 15. Commands Used to Reproduce the Work

The project uses the virtual environment in `.venv`.

### 15.1 Prepare the data

```bash
.venv/bin/python download_data.py
```

This downloads the EIA files and regenerates the cleaned CSV files.

### 15.2 Build and benchmark the QUBO

```bash
.venv/bin/python optimize_portfolio.py
```

This regenerates:

```text
data/optimization_model.json
```

and prints the exact classical optimum.

### 15.3 Run QAOA

```bash
.venv/bin/python run_qaoa.py
```

This runs the Qrisp simulator and regenerates:

```text
data/qaoa_result.json
```

### 15.4 Check syntax

```bash
python3 -m py_compile download_data.py optimize_portfolio.py run_qaoa.py
```

The scripts have passed this syntax check.

---

## 16. What Has Been Achieved

The project has progressed through the following stages:

### Data stage

- Selected four real EIA energy-futures series.
- Corrected the gasoline and heating-oil endpoints to daily series.
- Made the parser robust to EIA worksheet structure.
- Removed the fragile literal `Date` header assumption.
- Saved raw workbooks for auditability.
- Created aligned daily prices.
- Created daily returns.
- Created emissions and asset metadata tables.

### Mathematical-model stage

- Defined binary long and short variables.
- Defined the signed position vector $s=x-y$.
- Defined equal-dollar position normalization.
- Converted price units into approximate MMBtu quantities.
- Converted MMBtu quantities into kg CO2 exposure.
- Computed the return covariance matrix.
- Added carbon, risk, cardinality, and exclusivity terms.
- Corrected objective scaling so structural penalties are effective.
- Constructed the full 8-variable QUBO.

### Ising stage

- Converted the QUBO into Ising fields and pairwise couplings.
- Exported those coefficients for inspection and reuse.
- Built the QAOA phase separator with Z and ZZ operations.

### Quantum stage

- Installed Qrisp.
- Created an eight-qubit QAOA problem.
- Ran a depth-one QAOA experiment.
- Measured candidate bitstrings.
- Decoded the best candidate into long and short positions.
- Compared its objective, carbon exposure, and risk with the exact classical result.

### Validation stage

- Confirmed the downloader creates thousands of daily observations rather than annual observations.
- Confirmed the common futures file contains 2,315 rows.
- Confirmed the return file contains 2,314 rows.
- Confirmed the exact search evaluates all 256 binary states.
- Confirmed QAOA produced the exact optimum in a verified run.

---

## 17. What Has Not Been Claimed

The current result should not be described as any of the following:

- a profitable trading strategy,
- a production-ready hedge,
- a guarantee of carbon neutrality,
- proof that QAOA is better than classical enumeration,
- proof that QAOA scales efficiently for larger portfolios,
- a lifecycle-emissions analysis,
- a proof that the Borsuk-Ulam theorem guarantees a feasible portfolio,
- a claim that the chosen energy-content assumptions are the only valid convention.

The current result demonstrates a complete computational pipeline on a deliberately small problem.

---

## 18. Remaining Limitations

### 18.1 Small problem size

Eight qubits and 256 classical states are intentionally manageable. The exact classical benchmark is so cheap that this experiment cannot demonstrate a practical quantum advantage.

The value of the project is showing the complete modeling path with real data and a transparent benchmark.

### 18.2 Carbon normalization assumptions

The equal-$1,000 position convention is useful for a clean demonstration, but it is not a complete futures-contract risk model. A real futures portfolio would need contract multipliers, margin, contract sizes, rolling behavior, and potentially different notionals.

### 18.3 Combustion rather than lifecycle emissions

The carbon coefficients represent combustion-related emissions factors. They do not include extraction, refining, transport, leakage, or other lifecycle components.

### 18.4 Historical covariance instability

The covariance matrix is estimated from one historical period. It is not guaranteed to represent future relationships between the assets.

### 18.5 QAOA parameter sensitivity

The current QAOA experiment uses depth one and only ten classical optimization iterations. Better parameters, more layers, more shots, or a different optimizer could change the measured distribution.

### 18.6 No expected-return objective yet

The project specification allows an expected-return term:

$$
-\lambda_P \mu^T s
$$

It is intentionally omitted from the first working model. Adding it should be a separate experiment because historical average returns can be noisy and can dominate the other terms if not scaled carefully.

### 18.7 No constraint-preserving mixer yet

The current QAOA experiment uses Qrisp's standard RX mixer. It explores all bitstrings and relies on penalty terms to suppress invalid states.

A future version could use a constraint-preserving mixer or a carefully designed initial state, but that would change the QAOA implementation and should be evaluated separately.

---

## 19. Recommended Next Experiments

### Experiment 1: Carbon-penalty sweep

Run the exact benchmark for several carbon weights:

```text
lambda_C = 0
lambda_C = 0.1
lambda_C = 1
lambda_C = 10
lambda_C = 100
```

Record:

- carbon exposure,
- financial risk,
- objective,
- long positions,
- short positions.

This will show the trade-off between financial risk and carbon neutrality.

### Experiment 2: Risk-penalty sweep

Vary the risk weight while holding the carbon weight fixed. This shows whether the optimizer changes positions when it prioritizes covariance risk more strongly.

### Experiment 3: QAOA depth comparison

Run:

```text
depth = 1
 depth = 2
 depth = 3
```

Use the same model and compare:

- best measured objective,
- probability of the best state,
- valid-state frequency,
- distance from the exact optimum.

### Experiment 4: More QAOA shots

Increase the number of shots after parameter optimization. More shots provide a better estimate of the measured distribution but do not automatically improve the learned parameters.

### Experiment 5: Explicit validity checks

Add a validation function that rejects or labels any candidate that violates:

```text
sum(x) == 2
sum(y) == 2
x_i * y_i == 0 for every asset
```

The current exact benchmark already calculates these terms through the QUBO. Explicit reporting would make QAOA diagnostics clearer.

### Experiment 6: QUBO-to-Ising numerical test

For every one of the 256 bitstrings, compare:

1. the original QUBO energy,
2. the Ising energy after $b_i=(1+z_i)/2$,
3. the difference after removing the constant.

This verifies the conversion independently of Qrisp.

### Experiment 7: Expected-return extension

Only after the base model is stable, add:

$$
-\lambda_P \mu^T s
$$

and test whether the expected-return term changes the result in a sensible way.

### Experiment 8: Improved carbon specification

If the project becomes a formal research study, replace the approximate mean-price equal-dollar convention with a documented futures contract convention based on:

- contract multiplier,
- energy content,
- price unit,
- position notional,
- and the intended interpretation of a long or short contract.

---

## 20. Recommended Paper or Presentation Structure

A final write-up could use this structure:

1. **Introduction**
   - carbon exposure in energy markets,
   - motivation for long/short hedging,
   - quantum optimization motivation.

2. **Research question**
   - whether QAOA can identify a low-risk approximately carbon-neutral portfolio.

3. **Data**
   - EIA source,
   - four futures,
   - research period,
   - cleaning and alignment.

4. **Carbon normalization**
   - equal-dollar position convention,
   - MMBtu conversion,
   - emissions factors,
   - limitations.

5. **Mathematical formulation**
   - binary variables,
   - signed positions,
   - carbon term,
   - covariance risk,
   - cardinality and exclusivity.

6. **QUBO and Ising conversion**
   - matrix construction,
   - binary-to-spin transformation,
   - fields and couplings.

7. **QAOA implementation**
   - Qrisp,
   - cost operator,
   - mixer,
   - depth, shots, optimizer.

8. **Classical benchmark**
   - enumeration of all 256 states,
   - exact optimum.

9. **Results**
   - QAOA output,
   - classical comparison,
   - carbon and risk metrics.

10. **Sensitivity experiments**
    - carbon penalty,
    - risk penalty,
    - QAOA depth.

11. **Limitations**
    - small system,
    - data and emissions assumptions,
    - lack of quantum advantage claim.

12. **Conclusion**
    - whether the pipeline successfully demonstrates the proposed methodology.

---

## 21. Current Bottom Line

The project has moved beyond data preparation and now has a complete first working optimization pipeline:

```text
real EIA futures data
        |
        v
clean aligned prices
        |
        v
daily returns and covariance
        |
        v
normalized carbon exposures
        |
        v
8-variable long/short QUBO
        |
        v
Ising fields and couplings
        |
        v
8-qubit Qrisp QAOA
        |
        v
portfolio decoded and benchmarked
```

The most important achieved result is not merely that QAOA produced a bitstring. It is that the entire path from raw public data to a decoded quantum-optimization portfolio is now executable and checkable.

The first verified QAOA result agrees with the exact classical optimum for the current model. That establishes a useful baseline for the next phase: controlled experiments on carbon penalties, risk weights, QAOA depth, and improved unit conventions.
