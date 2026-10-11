# Trade desk: mock Checker execution with Sentry alerts

The trade desk simulates a trader sending a hedge through Checker Finance's RFQ and order API.
Checker is mocked; the request and response shapes follow the real API (see
[checker-finance.md](checker-finance.md)). When a trade fails, the server raises a Sentry alert with
the trade's full background so the failure can be investigated.

## Flow

```
Trade ticket (UI)
  │  POST /api/trades { instrumentPair, side, quantity, referencePrice, scenario }
  ▼
simulateTrade()                          src/lib/server/checker/simulate.ts
  1. RFQ        POST /request-for-quotes            → RFQ sent to LP-A, LP-B, LP-C
  2. Quotes     GET  /request-for-quotes/{id}/quotes → best price picked (lowest for BUY, highest for SELL)
  3. Accept     POST /quotes/{id}/accept             → 15 s quote expiry enforced
  4. Execute    POST /request-for-quotes/{id}/execute → order created (NEW)
  5. Order      GET  /orders/{id} (polled)           → PARTIALLY_FILLED → FILLED
  6. Settlement POST /withdrawals, GET /withdrawals/{id} → PENDING → COMPLETED
  │
  ├─ ok    → JSON result with the timeline
  └─ error → reportTradeFailure() sends a Sentry event, and the result includes the event ID
```

The whole flow runs inside one request. The mock keeps its state in memory for that request only,
which avoids needing shared state across Worker isolates. Time is simulated: each mock call advances
a clock by a realistic latency. The UI then replays the returned timeline step by step, faster than
the simulated times.

## Scenarios

Chosen on the ticket. Each one fails at a fixed point in the flow:

| Scenario | Where it fails | Error code | What happens |
|---|---|---|---|
| `happy` | none | none | Best quote accepted, order fully filled, settlement wire `COMPLETED` |
| `quote_expired` | accept | `QUOTE_EXPIRED` (409) | Trader takes 16–22 s to accept a quote that expires after 15 s |
| `lp_rejected` | order | `ORDER_REJECTED` (422) | LP rejects the order: counterparty credit limit exceeded |
| `partial_fill` | order | `ORDER_INCOMPLETE` (409) | Order `STOPPED` after a partial fill (liquidity withdrawn); the filled part still settles |
| `payment_failed` | settlement | `PAYMENT_FAILED` (402) | Order filled, then the settlement wire `FAILED` (BUY: insufficient funds; SELL: beneficiary name mismatch) |

## Pricing and fills

- Each LP quotes the reference price plus a spread of 2–8 bps, plus up to 10 bps for larger sizes.
  BUY quotes are above the reference price and SELL quotes below it. The reference price is the
  latest XAUUSD spot close or the futures settle shown on the page.
- Fills are whole units. GC futures trade in whole contracts of 100 oz, and the API rejects
  fractional futures quantities with a 400.
- Notional (USD) = filled quantity × price × 100 for GC contracts, or × 1 for XAU-USD spot (per oz).

## API

`POST /api/trades` (requires a login session; the auth hook redirects anonymous requests to `/login`)

Request:

```json
{ "instrumentPair": "GCZ26", "side": "SELL", "quantity": 10, "referencePrice": 4216.3, "scenario": "payment_failed" }
```

Validation:
- `instrumentPair` must be `XAU-USD` or a GC symbol (`GC` + month code + 2-digit year).
- `quantity` must be greater than 0 and at most 100,000, and an integer for futures.
- `referencePrice` must be between 100 and 100,000.
- An unknown `scenario` falls back to `happy`.

Response (`TradeResult`, in `src/lib/checker/types.ts`):

```jsonc
{
  "ok": false,
  "ticket": { … },
  "timeline": [ { "at": 85, "step": "rfq", "ok": true, "title": "…", "request": { … }, "response": { … } }, … ],
  "rfq": { … }, "quotes": [ … ], "order": { … }, "payment": { … },
  "notionalUsd": 4217290,
  "error": { "code": "PAYMENT_FAILED", "step": "settlement", "message": "…" },
  "sentry": { "sent": true, "eventId": "…" }
}
```

## Sentry alerts

Sentry runs through the SvelteKit SDK, which is initialised in `src/hooks.server.ts` with
`initCloudflareSentryHandle`. The DSN is in `src/lib/sentry.ts`. The org is `mlh-yu` and the
project is `goldmine`. `reportTradeFailure()` (`src/lib/server/sentry.ts`) captures one exception
per failed trade. The event contains:

| Field | Content |
|---|---|
| Exception | type = error code (e.g. `PAYMENT_FAILED`), value = failure message |
| Fingerprint | `checker` + error code + step, so each kind of failure groups into one issue |
| Tags | `checker.mode=mock`, `trade.scenario`, `trade.step`, `trade.error_code`, `trade.instrument`, `trade.side`, `trade.provider`, `order.status`, `payment.status` |
| Contexts | `trade` (quantity, filled and unfilled amounts, reference price, notional), `rfq`, `quote` (accepted or expired), `order` (status, fills, LP notes), `payment` (amount, rail, status, reason) |
| Breadcrumbs | The trade timeline: one HTTP breadcrumb per mock Checker call, with failed steps at level `error` |
| Extra | All quotes received |

Useful issue searches: `trade.error_code:PAYMENT_FAILED`, `trade.provider:LP-B`,
`checker.mode:mock`. The failure card on the page links to
`https://mlh-yu.sentry.io/issues/?query=<eventId>`.

On Workers, the SDK sends events after the response using the execution context's `waitUntil`, so
reporting does not slow the response. If the SDK has no client (e.g. Sentry was not initialised),
the result says `sent: false` with a reason, and the UI shows it.

To set up an alert rule in Sentry: Alerts → Create alert → Issues, with the filter
`tags[checker.mode] equals mock` and the action "Send a notification" (email or Slack).

## Files

| File | Purpose |
|---|---|
| `src/lib/checker/types.ts` | Checker resource types, scenarios, `TradeTicket` / `TradeResult` (used by the client and the server) |
| `src/lib/server/checker/mock.ts` | `MockChecker`: in-memory RFQs, quotes, orders and withdrawals; the simulated clock; `CheckerError` |
| `src/lib/server/checker/simulate.ts` | `simulateTrade()`: runs the flow and builds the timeline |
| `src/lib/server/sentry.ts` | `reportTradeFailure()`: scoped Sentry capture with tags, contexts and breadcrumbs |
| `src/routes/api/trades/+server.ts` | `POST /api/trades`: validates the ticket, simulates the trade, reports failures |
| `src/lib/components/TradeDesk.svelte` | Ticket form, timeline replay with request/response detail, result card, blotter |

## Moving to the real Checker sandbox

1. Implement the same calls as `MockChecker` with HMAC-signed `fetch` calls to
   `https://api-staging.checker.finance/api/v1` (see the auth section in
   [checker-finance.md](checker-finance.md)).
2. Store `CHECKER_API_KEY` and `CHECKER_API_SECRET` as Worker secrets and choose the
   implementation with `CHECKER_MODE=mock|sandbox`.
3. Replace the single-request flow with real polling. The UI already renders the same resource
   shapes, so only the transport changes.
4. Check that Checker supports gold (`GET /meta/assets`). Their docs only show crypto pairs.

## Testing locally

```sh
cp .dev.vars.example .dev.vars    # set APP_PASSWORD and SESSION_SECRET
npm run build
npx wrangler dev .svelte-kit/cloudflare/_worker.js --port 8799
```

Log in at http://localhost:8799/login, open **Trade** (`/trade`), pick a scenario and send the RFQ.
To exercise the API directly, log in with curl to get the session cookie, then:

```sh
curl -b cookies.txt -H 'origin: http://localhost:8799' -H 'content-type: application/json' \
  -d '{"instrumentPair":"GCZ26","side":"BUY","quantity":10,"referencePrice":4216.3,"scenario":"lp_rejected"}' \
  http://localhost:8799/api/trades
```
