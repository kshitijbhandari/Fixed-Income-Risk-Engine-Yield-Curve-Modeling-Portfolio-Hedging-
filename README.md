# Yield Curve Modeling and Bond Portfolio Hedging

A fixed-income risk management pipeline built entirely on free FRED data. The system fits yield curve models to 25 years of daily Treasury yields, extracts factor dynamics, stress tests a bond portfolio across 26 scenarios, and constructs Treasury futures hedging overlays.

Live dashboard: [yield-curve-modeling-hedging.streamlit.app](https://yield-curve-modeling-hedging.streamlit.app/)

---

## Overview

The project is structured as a sequential pipeline across five notebooks. Each stage builds on the outputs of the previous one.

```
FRED API
   -> Curve Fitting (Nelson-Siegel / Svensson)
      -> Factor Model + Monte Carlo (Diebold-Li VAR)
         -> Scenario Library (26 stress scenarios)
            -> Portfolio Pricing + Risk Metrics
               -> Hedging Strategy Design + Evaluation
                  -> Streamlit Dashboard
```

---

## Methodology

### 1. Yield Curve Fitting

The Nelson-Siegel model represents the yield curve as a function of three factors:

- Level (beta0): the long-run rate the curve converges to
- Slope (beta1): the difference between short and long rates
- Curvature (beta2): the hump or dip in the middle of the curve

Each factor has a loading that decays with maturity at a rate controlled by lambda. The textbook convention fixes lambda at 0.0609 based on Diebold and Li (2006). On this dataset that produced a median RMSE of 49 basis points. Letting lambda be a free parameter and optimizing it via L-BFGS-B with multiple starting points reduced median RMSE to 4.9 basis points across 6,851 trading days.

The Svensson extension adds a second curvature term for additional flexibility. It improves RMSE slightly (3.7 bps median on a 10% sample) but adds two more parameters and does not materially change the hedging results, so Nelson-Siegel is used throughout the main pipeline.

### 2. Diebold-Li Factor Model

The Diebold-Li framework treats the three Nelson-Siegel factors (Level, Slope, Curvature) as a joint time series and models their dynamics. A VAR(1) model is estimated on monthly factor observations, capturing cross-factor mean reversion and covariance structure.

Factor validity is confirmed against market proxies before estimation:
- Level correlates 0.981 with the 30-year yield
- Slope correlates 0.998 with the 30yr minus 3mo spread
- Curvature correlates 0.758 with the standard butterfly proxy

The fitted VAR is used to simulate 10,000 yield curve paths forward 12 months by drawing from the residual covariance matrix. This produces a distribution of possible yield curves at the 12-month horizon, from which percentile envelopes (p5 through p95) are extracted.

### 3. Scenario Generation

26 stress scenarios are built on top of the current base curve:

- 5 parallel shifts: +100, +200, +300, -100, -200 basis points
- 4 curve shape scenarios: bear steepener, bull steepener, bear flattener, bull flattener
- 2 special shapes: inversion (short rates up 200bps, long end flat) and hump (2-5yr up 150bps)
- 3 historical events: Taper Tantrum 2013 (+138bps peak), COVID 2020 (-129bps), 2022 rate shock (+454bps at 1mo)
- 7 macro scenarios: Fed hike/cut scenarios (25/50/75bps short-end only), stagflation (long end +50 to +200bps), flight to quality (short up, long down)
- 5 Monte Carlo percentile curves from the Diebold-Li simulation

### 4. Portfolio Pricing and Risk Metrics

A $51.5M portfolio of 12 US Treasury bonds spanning 2 to 30 year maturities is priced by discounting cash flows on Nelson-Siegel fitted spot curves. Each scenario produces a new yield curve, and the portfolio is fully repriced under each one.

Risk metrics computed per bond and at the portfolio level:
- Modified duration: rate of price change per 1% yield move
- DV01: dollar value of a 1 basis point move (total portfolio DV01 = $16,054)
- Convexity: second-order adjustment for large rate moves
- Key rate durations: partial sensitivities at each tenor, showing where the portfolio is most exposed

The key rate duration profile shows the portfolio's largest exposure at the 5-year tenor. A simple duration approximation understates losses by roughly 20% in severe scenarios like the 2022 shock because it ignores curve shape effects and convexity.

### 5. Hedging Strategy Design

Three hedging overlays are constructed using Treasury futures contracts across four instruments: TU (2yr), FV (5yr), TY (10yr), and US (30yr). Each contract has a known DV01 per lot, which is used to solve for the optimal number of contracts.

**S1 (Duration Neutral):** Shorts enough TY contracts to bring total portfolio DV01 to zero. Works well for parallel rate moves but fails on curve shape changes because it treats all rate risk as a single number.

**S2 (KRD Hedge):** Allocates contracts across all four futures to match the portfolio's key rate duration profile at each tenor. Better at handling steepeners, flatteners, inversions, and humps. Slightly weaker on pure parallel moves.

**S4 (Combined):** Scales the S2 KRD contract mix to provide full DV01 coverage. Designed to capture the strengths of both approaches. This is the recommended strategy.

---

## Results

**Curve fitting:**

| Metric | Value |
|---|---|
| NS median RMSE (fixed lambda) | 49 basis points |
| NS median RMSE (optimized lambda) | 4.9 basis points |
| Days under 10bps error | 91.6% of 6,851 dates |
| Slope factor correlation | 0.998 |

**Worst case scenarios (unhedged):**

| Scenario | P&L |
|---|---|
| 2022 Rate Shock | -$11.1M |
| Parallel +300bps | -$9.8M |
| Stagflation | -$8.2M |
| Parallel +200bps | -$6.6M |
| Bear Steepener | -$5.6M |

**Hedge effectiveness across all 26 scenarios:**

| Strategy | Avg Effectiveness | Cost |
|---|---|---|
| S1: Duration Neutral | 57.8% | $22,800 |
| S2: KRD Hedge | 52.4% | $14,428 |
| S4: Combined | 63.0% | $24,200 |

S1 is 0% effective on inversion and hump scenarios because the average rate move across tenors is near zero, producing a near-zero hedge ratio. S2 and S4 handle these cases because they allocate contracts at specific tenor buckets rather than the full-curve average.

**S4 cost vs protection (worst case):**

| Metric | Value |
|---|---|
| Transaction cost | $24,200 |
| Cost as % of AUM | 0.047% |
| Worst case loss unhedged | -$11.1M |
| Worst case loss with S4 | -$2.4M |
| Loss avoided | $8.7M |

---

## Dashboard

The Streamlit dashboard provides an interactive interface over the full pipeline. It fetches live Treasury yields from FRED daily and updates the base curve automatically.

Tabs:
- **Live Curve:** current yield curve vs historical snapshots, yield history by tenor, Nelson-Siegel factor evolution
- **Portfolio Risk:** bond table, DV01 by maturity bucket, key rate duration profile
- **Stress Test:** interactive scenario selector, rate moves heatmap, custom parallel shift tool
- **Hedging:** effectiveness heatmap, unhedged vs hedged P&L by strategy
- **Cost Analysis:** transaction costs, loss avoided, return on hedge cost

---

## How to Run

```bash
pip install -r requirements.txt
```

Get a free FRED API key at https://fred.stlouisfed.org/docs/api/api_key.html

Set the key as an environment variable:

```bash
export FRED_API_KEY=your_key_here
```

Run notebooks in order from 01 to 05. Each saves outputs to the `data/` folder which the next notebook loads from.

To run the dashboard locally:

```bash
streamlit run app.py
```

---

## Stack

Python | pandas | numpy | scipy | statsmodels | matplotlib | seaborn | fredapi | streamlit | plotly
