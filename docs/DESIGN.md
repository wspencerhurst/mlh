# QP Optimizer & Hedge Engine — design notes

Prototype decision-support system for physical commodity traders: choose the
**Quotation Period (QP)** under a physical contract and construct the hedge, maximizing
risk-adjusted realized value. Primary commodity: **gold** (doré/concentrate payable gold
priced on a monthly average). Secondary: WTI crude (real futures curve + basis risk).

---

## 1. The problem, precisely

A physical contract prices the metal as the *average of a daily index over a QP*
(e.g. LBMA Gold PM over M+1, M+2 or M+3 after the arrival month M), plus a differential.
One party may **declare** the QP before a deadline; otherwise a default applies. Payment
follows the QP (often with a provisional payment at arrival). The trader typically has an
offsetting sale priced on a different QP, so the QP choice creates a *timing* exposure
that is hedged with futures (COMEX GC / NYMEX CL) and unwound day-by-day as the average fixes.

Value of a choice `o`, per unit, financed to a common horizon date `T`:

```
V_o = (avg_sale + diff_s)·g(pay_s) − (avg_o + diff_o + prem_o)·g(pay_o) − provisional financing
      + hedge P&L − transaction costs,         g(d) = 1 + r_fund·(T − d)/360
```

Industry conventions modelled: calendar-month average pricing (cf. CME calendar-month
average / LME MASP / TAPOs), declaration deadlines, “stack and roll” hedging when a QP
month is not yet listed, trade-at-settlement execution, daily unwinding of 1/N of the hedge
on each fixing day, variation margin financing, provisional + final invoicing.

## 2. Deterministic vs learned — the core separation

| Deterministic (exact, auditable) | Learned / statistical |
|---|---|
| Contract parsing → QP windows, deadline, payment dates (exchange calendars) | Whether to *wait* before declaring (value of the option to switch) |
| Fixing schedule → futures-equivalent delta per contract month | Hedge ratio under basis risk (rolling min-variance β, point-in-time) |
| Forward value of each QP (curve + financing + provisional terms) | Hysteresis / switching thresholds given transaction costs |
| Hedge construction, lot rounding, position & risk limits | Any *view* on forward-curve bias (tested — see §6, mostly absent) |
| Execution, VM, costs, financing, P&L ledger | Synthetic-data generation (bootstrap of historical shocks) |

**Key insight.** In a market with a liquid forward curve, once you hedge, the QP decision is
almost fully determined by the forward curve, financing and contract terms. The
deterministic *forward-optimal* policy (declare the QP with the best forward-implied,
financed value; hedge fully) captures most of the value. Learning adds value only around
it: timing of declaration, switching under costs, hedge ratios with basis risk.
For gold (a near-perfect cash-and-carry market) the optimal QP is driven by
`funding spread + lease rate` vs. carry, and **flips with payment terms** (see the
sensitivity grid in `outputs/results_gold.json`).

## 3. Architecture

```
contracts/*.json ──► contracts.py (parsed contract schema)
data (EIA, FRED, EODHD, CME via Nimble) ──► market.py (point-in-time MarketData)
                                         └► synthetic.py (calibrated generators)
env.py  ── deterministic engine: fixings, exposure, valuation, hedge, limits, ledger
        └─ daily replay env: obs(t-1) → policy → action → execution at settle(t)
policies.py  benchmarks + forward-optimal + parametric learnable policy
train.py     CEM policy search on synthetic episodes (risk-adjusted objective)
ml.py        walk-forward supervised “which QP will be cheapest” test
evaluate.py  historical replay, metrics, block-bootstrap CIs vs benchmark
live.py      today's recommendation from the live COMEX curve (Nimble) + Monte Carlo
proposals.py approval queue (PENDING → APPROVED → SUBMITTED) → Checker rail (stub)
```

## 4. Data (free / public) and how Nimble is used

| Need | Source | Notes |
|---|---|---|
| Gold spot (index proxy) | EODHD XAUUSD daily (`data/gold_prices.parquet`) | LBMA Gold Price itself is licensed; spot close is a proxy |
| USD short rate | FRED `DTB3`, **fetched through Nimble** (FRED was unreachable directly) | financing + carry |
| Live COMEX gold curve | CME settlements JSON, **fetched through Nimble** | CME serves only the last few sessions → we **archive every pull** (`data/cme/`), building our own point-in-time curve history |
| Market context | **Nimble search** (lease rates, EFP, tariffs headlines) | shown on the dashboard |
| Crude curve history | EIA NYMEX contracts 1–4 (1983–Apr 2024) | mapped to contract months by the exchange LTD rule (validated, §7) |
| Crude/ULSD physical index | EIA WTI Cushing, USGC ULSD spot | real basis risk |

**Gold futures history.** No free source has every expired COMEX contract month (CME
DataMine is paid; Yahoo drops expired contracts). Yahoo's `GC=F` gives the **real active-month
COMEX price daily since Aug 2000**, rolling on first-notice day. The backtest hedges in that
real contract; other months are priced off it by carry `exp((r − lease)·Δτ)` with the real
T-bill. So hedge P&L includes real futures-vs-spot dislocations (2020 Covid, 2025–26 tariff
premia of $100–185/oz); only the small spreads between months are modelled. Two data
details matter: the first two days of `GC=F` are bad prints (filtered), and spot and futures
closes are taken at different times of day, which biases a daily regression hedge ratio
toward zero (Epps effect). Hedge ratios are therefore estimated on 10-day changes.
The Nimble archive (`data/cme/`) builds a full point-in-time curve history going forward.

**What real basis risk changed.** With modelled forwards the hedged forward-optimal gold
policy looked nearly riskless (std 3.6 bps per cargo). With real futures it earns +35.8 bps
with std 49 bps and a worst cargo of −234 bps; the learned policy earns +38.5 bps and beats
the rule by +2.7 bps (95% CI +0.3 to +5.3). The default QP (matched to the sale, no hedge
needed) earns +9.8 bps almost risk-free, so on a tail-risk-adjusted score it remains
competitive: the extra carry from a later QP comes with real COMEX–London basis risk.

## 5. Simulation environment

* Episode = one cargo: from signing (M−2 for gold) through the last fixing of all QPs.
* Day t: the agent sees data **through t−1**, acts; trades execute at **t settlement** (TAS).
* Index fixings are realized only on days the index was published (data gaps =
  realistic fixing-day risk); hedge planning uses the exchange calendar (known in advance).
* Dense reward = daily change in financed mark-to-market; it telescopes exactly to realized P&L.
* Constraints (per-month and gross lot limits, open-delta limit) are enforced by the
  deterministic layer (action masking/clipping), not by reward penalties.
* Tests (`tests/test_engine.py`): scrambling all prices after a date cannot change any
  earlier action; accounting identities hold to 1e-6.

## 6. Reward function — what and why

**Unit:** realized P&L of the whole deal (physical legs + hedge + costs + financing),
financed to a common horizon date, **normalized by notional at signing (bps)** for gold
(price went from $300 to $4,200, so $/oz is not comparable across years); $/bbl for crude.

**Per-episode reward = P&L − P&L of the baseline on the same episode.** The baseline is the
deterministic forward-optimal policy. Subtracting an action-independent baseline does not
change the optimal policy, but it removes the common market noise (a control variate) and
makes the number directly interpretable as *value added by learning*.

**Risk adjustment across episodes:** objective = `mean − λ·CVaR₅%` (λ = 0.5). CVaR is
coherent, focuses on the tail losses risk committees care about, and is the standard choice
in Deep Hedging (Buehler et al., 2019). For gradient RL the per-step form
`r_t = ΔMTM_t − (κ/2)·ΔMTM_t²` (Kolm & Ritter, 2019) gives a mean-variance equivalent with
dense credit assignment.

**Why not log returns?** A hedged physical deal is not an investment of capital; P&L can be
negative or zero on zero net capital, there is no compounding across cargoes, and log of a
P&L is undefined. Linear P&L (or bps of notional, a linear rescaling) is the right unit.

**Why not Sharpe as the reward?** Sharpe is a ratio of moments over many episodes, not an
additive per-step quantity; it is scale-invariant (an agent can “improve” it by shrinking
both P&L and risk), and it explodes for well-hedged books with near-zero variance. We
*report* a Sharpe-like ratio but optimize mean − λ·CVaR.

## 7. Evaluation methodology

* **Walk-forward:** generators and policies are calibrated/trained only on the training
  window (gold: 1990–2009; crude: 1987–2004) and evaluated by historical replay after it.
* **Benchmarks:** forward-optimal (primary), default QP hedged (naive desk), default QP
  unhedged, perfect foresight (upper bound, not tradable).
* **Statistics:** mean, std, CVaR₅, worst cargo, win rate, and 95% CIs of the mean
  difference vs benchmark by block bootstrap (cargoes overlap in time).
* **Label leakage control** for supervised models: an example is usable only after its last
  fixing date, not after its delivery date.
* **Data validation:** EIA position → contract-month mapping checked by showing the exchange
  LTD rule minimizes same-contract price jumps vs ±1–2 day shifted rules.

## 8. Can synthetic data be high quality?

Partly, and it is worth separating two kinds:

1. **Synthetic contracts** — QP option sets, deadlines, payment terms, sizes, premia. These
   are payoff specifications, so synthesizing them is exact and cheap. High quality.
2. **Synthetic markets** — we use a semi-parametric generator: a parametric curve-shape
   model (crude: level random walk + mean-reverting slope; gold: cash-and-carry with a
   stochastic short rate) driven by **jointly block-bootstrapped historical shocks**,
   which preserves fat tails, cross-correlations and volatility clustering. It matches the
   training window's stylized facts (vol, Samuelson effect, slope persistence, basis).
   **But** it cannot anticipate regime change: crude 2005–2024 spent 70% of days in
   contango vs 38% in the training window. We therefore add **domain randomization**
   (random slope / lease-rate regimes per path) and use synthetic data only for
   training and stress testing — **never for the final performance claim**, which comes
   only from historical replay.

## 9. On “train on the last 12 months to predict which QP to pick”

Tested directly (`ml.py`, results in `outputs/`). It is not a good primary approach:

* One cargo per month ⇒ a 12-month window is ~12 labels (fewer once leakage is
  controlled), far too few for a model.
* “Which QP will be cheapest” unhedged is a bet on the price direction over 1–3 months;
  forwards already price the expected difference, so the predictable part is small and
  the unpredictable part is huge (crude: worst cargo −$47/bbl; gold: ±$250–400/oz).
* Out of sample, rolling-12m and “last year's winner” rules did not beat the forward-based
  choice, and carried an order of magnitude more tail risk.

Better framing for the PoC: deterministic forward-optimal decision + hedge as the baseline,
learning only the residual decisions (timing, switching, hedge ratio), and an honest
walk-forward test of whether any forecasting signal adds value *after* risk.

## 10. Roadmap

1. Archive COMEX/LBMA curves daily via Nimble → replay gold with real basis (EFP).
2. Counterparty-held options (worst-case valuation), tolerance (±10% quantity) options,
   TC/RC-style price participation, multi-cargo books with netting.
3. Replace CEM over 5 parameters with PPO / Deep Hedging over the same environment once
   the decision space grows (multi-cargo, partial hedges, options such as TAPOs).
4. Checker integration: approved proposals → stablecoin settlement of physical payments /
   margin (see `qp_hedge/proposals.py`).
