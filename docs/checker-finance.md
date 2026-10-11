# Checker Finance: trade execution (mocked)

Docs: https://docs.checker.finance (LLM index: https://docs.checker.finance/llms.txt).
Notes taken 2026-10-11 from the docs pages; the spec pages were last updated 2026-09-18.

## Why we use it

The QP optimiser outputs target positions (e.g. "sell 3 GCZ26, buy 200 oz spot"). Checker is the
execution layer: we send those trades as RFQs to liquidity providers, take the best quote, and track
the resulting order and fills. For the hackathon we call a **mock** with the same request/response
shapes, so we can switch to the sandbox later by changing the base URL and adding credentials.

## What Checker is

A provider-agnostic orchestration API connecting clients (banks, PSPs, OTC desks) to liquidity
providers. Two product lines: **Trade & Convert** (orders, RFQs, quotes, venue prices) and
**Accounts & Payments** (fiat accounts, beneficiaries, payouts). We only need Trade & Convert.

Note: every example in the docs uses crypto pairs (`BTC-USD`). The docs do not say whether gold
(XAU, or tokenised gold such as PAXG/XAUT) is supported. Check `GET /meta/assets` against the sandbox
before relying on it. The mock uses `XAU-USD` for spot and `GCZ26`-style symbols for futures; both
are our own naming and not confirmed by Checker.

## Environments

| | Trading API | Market Data API |
|---|---|---|
| Sandbox | `https://api-staging.checker.finance/api/v1` | not documented |
| Production | `https://api.checker.finance/api/v1` | `https://md.checker.finance/api/v1` |

Sandbox access is requested at https://dev.checker.finance (issues an API key + secret).

## Authentication (Trading API)

HMAC request signing. Every request sends three headers:

| Header | Value |
|---|---|
| `x-api-key` | API key (public) |
| `x-nonce` | unique per request, e.g. a UUID (replay protection) |
| `x-signature` | `base64(HMAC-SHA256(secret, "<api-key>:<nonce>:<path>"))` |

`<path>` is the request path only, e.g. `/api/v1/orders`: no host, no query string. The secret is
never sent. In a Worker this is `crypto.subtle.importKey('raw', …, {name:'HMAC', hash:'SHA-256'})` +
`crypto.subtle.sign`.

The Market Data API uses a single `X-API-Key` header instead.

## Trading API endpoints

Paths are relative to `/api/v1`.

### Reference data
| Method | Path | Returns |
|---|---|---|
| GET | `/meta/assets` | `AssetResource[]`: `assetId`, `name`, `symbol`, `type`, `status`, `precision`, … |
| GET | `/meta/liquidity-providers` | `ProviderResource[]`: `providerId`, `name`, `category`, `type`, `status`, … |

### RFQ flow
| Method | Path | Notes |
|---|---|---|
| POST | `/request-for-quotes` | body `RequestForQuoteCreationResource`; returns a string (location/ID of the RFQ) |
| GET | `/request-for-quotes/{requestForQuoteId}` | `RequestForQuoteResource` |
| GET | `/request-for-quotes/{requestForQuoteId}/status` | string |
| GET | `/request-for-quotes/{requestForQuoteId}/quotes` | `QuoteResource[]` |
| GET | `/request-for-quotes?status=…` | RFQs with that status (`status` required) |
| PUT/PATCH | `/request-for-quotes/{id}` | amend (see the "Amend an existing RFQ" reference page) |
| DELETE | `/request-for-quotes/{id}` | cancel |
| POST | `/quotes/{quoteId}/accept` | returns `QuoteResource` with `status: ACCEPTED` |
| POST | `/request-for-quotes/{requestForQuoteId}/execute` | executes the trade; returns a string |
| POST | `/quotes` | LP side: submit a quote (`QuoteCreationResource`) |

The RFQ guide also describes `POST /request-for-quotes/{id}/finalize` with `{ "winningQuoteId": "…" }`,
but that path is not in the API reference, which has `accept` + `execute` instead. **Follow the
reference.**

### Orders
| Method | Path | Notes |
|---|---|---|
| POST | `/orders` | body `OrderCreationResource`; returns `OrderResource` |
| GET | `/orders` | `OrderResource[]` |
| GET | `/orders/{orderId}` | `OrderResource` |

## Schemas

```ts
type Side = 'BUY' | 'SELL';

interface RequestForQuoteCreationResource {
	instrumentPair: string; // "BTC-USD"
	quantity: number;
	side: Side;
	providers: string[]; // LP ids
}

interface RequestForQuoteResource extends RequestForQuoteCreationResource {
	requestForQuoteId: string;
	status: 'CREATED' | 'OPEN' | 'CLOSED' | 'CANCELLED' | 'EXPIRED';
	quotes?: QuoteResource[]; // present in the guide's example response
}

interface QuoteResource {
	quoteId: string;
	requestForQuoteId: string;
	price: number;
	instrumentPair: string;
	benchmarkName: string;
	quantity: number;
	expiry: string; // ISO date-time
	provider: string;
	status: 'PENDING' | 'ACCEPTED' | 'REJECTED' | 'EXPIRED';
}

interface OrderCreationResource {
	instrumentPair: string;
	quantity: number;
	side: Side;
	price: number;
	clientId: string;
	date: string; // ISO date-time
	provider: string;
	clientOrderId: string; // our idempotency key
	requestForQuoteId?: string;
	blockChain?: string;
	notes?: string;
	tags?: string[];
}

interface OrderResource extends OrderCreationResource {
	orderId: string;
	status:
		| 'PENDING_NEW' | 'NEW' | 'ACCEPTED_FOR_BIDDING' | 'PARTIALLY_FILLED' | 'FILLED'
		| 'DONE_FOR_DAY' | 'CANCELED' | 'PENDING_CANCEL' | 'PENDING_REPLACE' | 'STOPPED'
		| 'REJECTED' | 'SUSPENDED' | 'CALCULATED' | 'EXPIRED';
	fills?: { fillId: string; quantity: number; price: number; date: string }[];
}
```

`fills` appears in the trade-order guide's example but not in the OpenAPI `OrderResource`. Treat it as
optional.

## Market Data API (optional)

- `GET /instruments/{symbol}/venues` returns `{ venue_instruments: [{ venue_code, instrument_symbol, venue_symbol, is_active, is_blacklisted, … }], total }`
- `GET /prices/{instrument}/venue/{venue}` returns `{ instrument_symbol, venue_code, price (string), timestamp, source_method, provenance }`
- `GET /prices/{instrument}` (waterfall), plus candles endpoints

We already have spot (EODHD) and futures (Nimble), so this is only useful for a pre-trade price check.

## Mock plan for the demo

Implemented: see [trade-desk.md](trade-desk.md).

Goal: simulate a trader turning the QP result into executed trades.

1. **Optimiser output → tickets.** Each non-zero position change becomes a ticket
   `{ instrumentPair, side, quantity }`.
2. **RFQ.** `POST /request-for-quotes` to 3 mock LPs (`LP-A`, `LP-B`, `LP-C`). The mock returns an ID and moves status `CREATED → OPEN`.
3. **Quotes.** The mock generates one `QuoteResource` per LP. Price = reference price (latest
   spot or futures settle) ± a random spread of a few bps, worse for larger size, with `expiry` 15 s out.
4. **Trader picks the best quote** in the UI, with a countdown to expiry. Call `POST /quotes/{id}/accept`, then
   `POST /request-for-quotes/{id}/execute`. The RFQ moves to `CLOSED`; the other quotes are `REJECTED`.
5. **Order.** The mock creates an `OrderResource` (`requestForQuoteId` set, `clientOrderId` =
   our ticket id, `tags: ["qp-hedge"]`) that goes `NEW → PARTIALLY_FILLED → FILLED` over a few
   seconds, with 1–3 `fills`. The UI polls `GET /orders/{orderId}`.
6. **Blotter.** `GET /orders` shows executed trades and realised hedge vs target.

Implementation notes:
- Put the client behind an interface (`createRfq`, `listQuotes`, `acceptQuote`, `executeRfq`,
  `getOrder`, `listOrders`). There are two implementations: `MockChecker` (in-memory/seeded RNG, running
  server-side so the browser behaves as it would with the real API) and `HttpChecker` (HMAC-signed fetch).
  Select with an env var `CHECKER_MODE=mock|sandbox`.
- Use the exact field names and enum values above so a switch to the sandbox needs no UI changes.
- Simulate errors too: an expired quote (accepting after `expiry`), a rejected order, and partial fills
  that stop short.
- Secrets for sandbox mode: `CHECKER_API_KEY`, `CHECKER_API_SECRET` (Worker secrets, never in the browser).
