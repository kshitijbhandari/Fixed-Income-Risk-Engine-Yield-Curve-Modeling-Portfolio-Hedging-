# Yield Curve Modeling and Bond Portfolio Hedging

A fixed-income risk management tool built on 25 years of free US Treasury data from FRED. It fits yield curve models, stress tests a bond portfolio across 26 scenarios, and evaluates hedging strategies using Treasury futures.

Live dashboard: [yield-curve-modeling-hedging.streamlit.app](https://yield-curve-modeling-hedging.streamlit.app/)

---

## What it does

- Fits the Nelson-Siegel yield curve model to daily Treasury data and tracks how the curve changes over time
- Builds a Diebold-Li factor model to capture level, slope, and curvature dynamics, and simulates 10,000 forward yield paths over a 12-month horizon
- Stress tests a $51.5M bond portfolio across 26 rate scenarios including historical crises, Fed moves, and user-defined shifts
- Computes portfolio risk metrics including DV01, modified duration, convexity, and key rate durations
- Designs and evaluates three Treasury futures hedging strategies and measures their effectiveness across all scenarios

---

## Notebooks

| Notebook | Description |
|---|---|
| `01_Curve_Fitting` | Fits Nelson-Siegel and Svensson models to 25 years of daily data |
| `02_diebold_li` | Diebold-Li factor model, VAR dynamics, Monte Carlo simulation |
| `03_scenario_generation` | Builds the full library of 26 stress scenarios |
| `04_bondpl_riskmetrics` | Bond pricing, DV01, key rate durations, scenario P&L |
| `05_hedging_scenario_updated` | Hedging strategy design and effectiveness analysis |

---

## Key Results

**Curve fitting:**

| Metric | Value |
|---|---|
| NS median RMSE (fixed lambda) | 49 basis points |
| NS median RMSE (optimized lambda) | 4.9 basis points |
| Dates fitted | 6,851 |
| Days under 10bps error | 91.6% |

**Portfolio:**

| Metric | Value |
|---|---|
| Market value | $51.5M |
| Modified duration | 6.22 years |
| Total DV01 | $16,054 |
| Number of bonds | 12 |
| Maturity range | 2 to 30 years |

**Worst case scenarios (unhedged):**

| Scenario | P&L |
|---|---|
| 2022 Rate Shock | -$11.1M |
| Parallel +300bps | -$9.8M |
| Stagflation | -$8.2M |
| Parallel +200bps | -$6.6M |
| Bear Steepener | -$5.6M |

**Hedging results (S4 recommended strategy):**

| Metric | Value |
|---|---|
| Contracts | 51 TU, 93 FV, 125 TY, 51 US |
| Transaction cost | $24,200 |
| Cost as % of AUM | 0.047% |
| Average effectiveness | 80.4% across all scenarios |
| Worst case loss with S4 | -$2.4M (vs -$11.1M unhedged) |

---

## How to run

```bash
pip install -r requirements.txt
```

Get a free FRED API key at https://fred.stlouisfed.org/docs/api/api_key.html and set it as an environment variable:

```bash
export FRED_API_KEY=your_key_here
```

Run notebooks in order from 01 to 06. Each notebook saves outputs to the `data/` folder which the next one loads from.

To launch the dashboard locally:

```bash
streamlit run app.py
```

---

## Stack

Python | pandas | numpy | scipy | statsmodels | matplotlib | seaborn | fredapi | streamlit | plotly
