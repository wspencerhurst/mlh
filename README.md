<h1 align="center">Goldmine</h1>

<p align="center"><b>Pick the month. Lock it in. Know why.</b></p>

<h3 align="center">🟢 Live app: <a href="https://goldmine.techarge.workers.dev/">goldmine.techarge.workers.dev</a></h3>

<p align="center">
  <a href="https://goldmine.techarge.workers.dev/"><img alt="Open the live app" src="https://img.shields.io/badge/Open%20the%20live%20app-goldmine.techarge.workers.dev-afc149?style=for-the-badge"></a>
  <a href="https://spencerhurst.com/goldmine/"><img alt="Watch the launch video" src="https://img.shields.io/badge/%E2%96%B6%20Launch%20video-2%3A12-e4bd70?style=for-the-badge"></a>
</p>

<p align="center">
  <a href="https://spencerhurst.com/goldmine/"><img src="docs/media/highlights.gif" alt="Goldmine highlights: valuing each quotation period, the wait-or-declare decision, exact futures hedge tickets and backtest results" width="100%"></a>
  <br><sub>Highlights. Click for the full launch video, with sound.</sub>
</p>

---

Decision support for physical commodity traders: pick the **Quotation Period (QP)** under a
physical contract (which month's average price you pay, e.g. M+1 / M+2 / M+3) and build the
futures hedge that locks it in, maximizing risk-adjusted realized value. Gold (COMEX GC) is the
primary market; WTI crude (NYMEX CL) is the second.

- **Engine** (Python, `qp_hedge/`): deterministic valuation and hedging, replay environment with no
  look-ahead, policy search on synthetic markets, walk-forward backtests.
- **Learned policy**: seven readable numbers tuned by cross-entropy policy search on simulated markets
  with randomized, realistic contract terms (`qp_hedge/terms.py`). It decides when to declare (option
  value of waiting vs switching cost, adjusted for curve shape) and fine-tunes hedge size. It is used for
  a market only if it beat the simple rule in the training-period backtest.
- **Web app** (SvelteKit on Cloudflare Workers, `src/`): the desk at `/` runs the valuation in the browser
  (`src/lib/engine.ts`), so the contract picker (Open Mineral), contract form and risk-appetite slider
  update the recommendation instantly; approved orders execute through the Checker mock. `/details`
  explains the model, assumptions and data.
- Design write-up (architecture, data, synthetic data, reward, evaluation): [docs/DESIGN.md](docs/DESIGN.md).
  Checker execution plan: [docs/checker-finance.md](docs/checker-finance.md).

## Third-party tools

Built at [AI Engineer NYC 2026](https://www.mlh.com/events/ai-engineer-nyc-2026) (MLH). Sponsor tools
used, by prize category:

| | Tool | Prize category | How Goldmine uses it |
|---|---|---|---|
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/logos/nimble-dark.svg"><img src="docs/logos/nimble.svg" alt="Nimble" width="110"></picture> | [Nimble](https://nimbleway.com) | Best Use of Nimble | Extract API pulls the daily CME futures settlements (COMEX gold, NYMEX crude) that form the live forward curve, archived in `data/cme/` (`qp_hedge/nimble.py`, `qp_hedge/live.py`). Search API collects market news for the recommendation. |
| <img src="docs/logos/sentry.svg" alt="Sentry" width="40"> | [Sentry](https://sentry.io) | Best Use of Sentry | Raises an alert when an approved trade is not executed or fails at the Checker RFQ, order or payment step. Each event carries the trade, quote, order and payment details as tags and contexts (`src/lib/server/sentry.ts`, [docs/trade-desk.md](docs/trade-desk.md)). Also reports client and server errors from the web app. |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/logos/tiger-data-dark.png"><img src="docs/logos/tiger-data.png" alt="Tiger Data" width="110"></picture> | [Tiger Data](https://www.tigerdata.com) | Best Use of Tiger Data | Two TimescaleDB hypertables. `cme_settlements` stores every live CME settlement pulled by Nimble; the `cme_settlements_weekly` continuous aggregate and the `curve_spreads` view (2nd and 3rd listed contracts vs the front, the M+1 / M+2 / M+3 choice) give the curve history (`db/settlements.sql`, `qp_hedge/tiger.py`). `trades` records every Checker trade with its status, failure step and Sentry event ID; the `trades_daily` continuous aggregate feeds the `/trades` blotter page (`db/trades.sql`, `src/lib/server/tiger.ts`). |
| <img src="docs/logos/snowflake.svg" alt="Snowflake" width="40"> | [Snowflake](https://www.snowflake.com) | Best Use of Snowflake | Data warehouse for the engine's outputs, loaded with the Python connector (`qp_hedge/warehouse.py`, `scripts/load_snowflake.py`): CME settlements, all 4,510 walk-forward backtest cargoes and today's QP recommendations, in `GOLDMINE.PUBLIC`. Views compute the policy scorecard (mean, std, worst and 5th percentile per cargo), the QP each policy elected and the curve spreads (`db/snowflake.sql`). A Streamlit in Snowflake dashboard (`dashboard/streamlit_app.py`) shows the recommendation, scorecard, cumulative P&L and spreads. A Cortex AI summary of the recommendation for the desk is also built (`qp_hedge/cortex.py`); it stays off on our trial account, which blocks Cortex functions. |

Other tools:

| | Tool | Use |
|---|---|---|
| <img src="docs/logos/cloudflare.svg" alt="Cloudflare" width="40"> | [Cloudflare Workers](https://workers.cloudflare.com) | Hosts the web app; deployed with Wrangler from GitHub Actions |
| <img src="docs/logos/svelte.svg" alt="Svelte" width="32"> | [SvelteKit](https://svelte.dev) | Web app framework |
| | [EODHD](https://eodhd.com) | XAUUSD spot history and commodity price series |
| | [Checker](docs/checker-finance.md) | Trade execution API (mocked) for approved hedge orders |
| | [Open Mineral](https://www.openmineral.com) | Physical contract source (mocked) for the contract picker |

## Engine

```bash
pip install -r requirements.txt
cp .env.example .env              # NIMBLE_API_KEY; optional TIGER_DATABASE_URL, SNOWFLAKE_ACCOUNT/USER/API_KEY/WAREHOUSE
python tests/test_engine.py       # no-look-ahead + accounting tests
python run_pipeline.py gold crude # calibrate, train, replay -> outputs/results_*.json (~25 min)
python run_live.py                # today's recommendations -> outputs/live_*.json, outputs/proposals.json
python scripts/export_web.py      # -> data/desk.json, read by the web app at build time
python scripts/load_tiger.py      # Tiger Data schema + backfill of data/cme/ (TIGER_DATABASE_URL)
psql "$TIGER_DATABASE_URL" -f db/trades.sql   # trade blotter schema
python scripts/load_snowflake.py  # Snowflake tables, views and Streamlit dashboard (SNOWFLAKE_*)
```

## Web app

```sh
npm install
cp .dev.vars.example .dev.vars    # APP_PASSWORD, SESSION_SECRET for local dev
npm run dev
```

`npm run build` builds the Worker; `npm run preview` serves the production build.

### Deployment

`.github/workflows/deploy.yml` builds, type-checks and deploys the `goldmine` Worker with Wrangler.

- Push to `main`: production `wrangler deploy --secrets-file`. The Worker secrets `APP_PASSWORD` and `SESSION_SECRET` come from the GitHub secrets of the same names and ship with the deployed version (a separate `wrangler secret put` fails when a PR preview has uploaded a newer, undeployed version).
- Pull request: build and type-check, then `wrangler versions upload`. The preview URL is written to the job summary. Fork PRs have no secrets, so the upload is skipped and only the build runs.
- `workflow_dispatch`: runs the workflow manually. It deploys only when run on `main`.

| Secret | Purpose |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token used by Wrangler |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |
| `APP_PASSWORD` | Login password, pushed as a Worker secret |
| `SESSION_SECRET` | Session signing key, pushed as a Worker secret |
| `TIGER_DATABASE_URL` | Optional Tiger Data connection string for the trade blotter, pushed as a Worker secret |

```sh
gh secret set CLOUDFLARE_API_TOKEN
gh secret set CLOUDFLARE_ACCOUNT_ID --body "<account-id>"
gh secret set APP_PASSWORD
gh secret set SESSION_SECRET --body "$(openssl rand -hex 32)"
```

## Data the web app reads

`data/desk.json` (written by `scripts/export_web.py`), per market (`gold`, `crude`):

| Key | Contents |
|---|---|
| `live` | recommendation: `best`, `declare_now`, `options[]` (QP month, hedged value), `tickets`, live `curve[]`, Monte Carlo outcome histograms per QP |
| `track` | cumulative realized P&L per policy by delivery month (walk-forward replay) |
| `scorecard` | per-policy mean, std, worst cargo, difference vs baseline with 95% CI |
| `proposals` | approval queue items with a `checker` RFQ ticket (`instrumentPair`, `side`, `quantity`) |

## Data sources

EODHD XAUUSD (proxy for the LBMA Gold Price) · COMEX gold futures history from Yahoo Finance
(`GC=F`, 2000–today) · live CME settlements and FRED rates fetched with [Nimble](https://nimbleway.com)
(archived daily in `data/cme/`) · EIA NYMEX crude futures and spot history.
