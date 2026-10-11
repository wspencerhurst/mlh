import type {
	Fill,
	OrderResource,
	PaymentResource,
	QuoteResource,
	RequestForQuoteCreationResource,
	RequestForQuoteResource,
	Scenario,
	Side
} from '#lib/checker/types.ts';

export const PROVIDERS = ['LP-A', 'LP-B', 'LP-C'];
const QUOTE_TTL_MS = 15_000;

/** Error shaped like Checker's error responses ({ code, status }). */
export class CheckerError extends Error {
	constructor(
		readonly code: string,
		readonly status: number,
		message: string
	) {
		super(message);
	}
}

const id = (prefix: string) => `${prefix}_${crypto.randomUUID().replace(/-/g, '').slice(0, 16)}`;

/**
 * In-memory stand-in for Checker's Trading and Payments APIs. Time is simulated: each call
 * advances `clock` by a realistic latency so the timeline replays like a live trade.
 * The scenario decides where (if anywhere) the flow fails.
 */
export class MockChecker {
	clock = 0;
	private readonly start = Date.now();
	private rfqs = new Map<string, RequestForQuoteResource>();
	private quotes = new Map<string, QuoteResource>();
	private orders = new Map<string, OrderResource>();
	private payments = new Map<string, PaymentResource>();

	constructor(
		private readonly scenario: Scenario,
		private readonly referencePrice: number
	) {}

	private tick(min: number, max: number) {
		this.clock += Math.round(min + Math.random() * (max - min));
	}
	private iso() {
		return new Date(this.start + this.clock).toISOString();
	}

	// POST /request-for-quotes
	createRfq(body: RequestForQuoteCreationResource): RequestForQuoteResource {
		this.tick(80, 160);
		if (!(body.quantity > 0)) throw new CheckerError('VALIDATION_ERROR', 400, 'quantity must be positive');
		const rfq: RequestForQuoteResource = { ...body, requestForQuoteId: id('rfq'), status: 'OPEN' };
		this.rfqs.set(rfq.requestForQuoteId, rfq);
		return rfq;
	}

	// GET /request-for-quotes/{id}/quotes: LPs answer around the reference price
	listQuotes(rfqId: string): QuoteResource[] {
		const rfq = this.rfqs.get(rfqId);
		if (!rfq) throw new CheckerError('NOT_FOUND', 404, `RFQ ${rfqId} not found`);
		this.tick(600, 1400);
		const sign = rfq.side === 'BUY' ? 1 : -1;
		const sizeBps = Math.min(10, rfq.quantity / 50);
		const expiry = new Date(this.start + this.clock + QUOTE_TTL_MS).toISOString();
		return rfq.providers.map((provider) => {
			const bps = 2 + Math.random() * 6 + sizeBps;
			const q: QuoteResource = {
				quoteId: id('qt'),
				requestForQuoteId: rfqId,
				price: Math.round(this.referencePrice * (1 + (sign * bps) / 10_000) * 100) / 100,
				instrumentPair: rfq.instrumentPair,
				benchmarkName: 'LBMA Gold PM',
				quantity: rfq.quantity,
				expiry,
				provider,
				status: 'PENDING'
			};
			this.quotes.set(q.quoteId, q);
			return q;
		});
	}

	// POST /quotes/{id}/accept
	acceptQuote(quoteId: string): QuoteResource {
		const q = this.quotes.get(quoteId);
		if (!q) throw new CheckerError('NOT_FOUND', 404, `Quote ${quoteId} not found`);
		// Trader hesitates; in the expiry scenario long enough to miss the window.
		if (this.scenario === 'quote_expired') this.tick(16_000, 22_000);
		else this.tick(2_000, 6_000);
		if (this.start + this.clock > Date.parse(q.expiry)) {
			q.status = 'EXPIRED';
			throw new CheckerError('QUOTE_EXPIRED', 409, `Quote ${quoteId} from ${q.provider} expired at ${q.expiry}`);
		}
		q.status = 'ACCEPTED';
		for (const other of this.quotes.values())
			if (other.requestForQuoteId === q.requestForQuoteId && other !== q) other.status = 'REJECTED';
		return q;
	}

	// POST /request-for-quotes/{id}/execute: creates the order with the winning LP
	execute(rfqId: string, clientOrderId: string): OrderResource {
		const rfq = this.rfqs.get(rfqId);
		const q = [...this.quotes.values()].find((x) => x.requestForQuoteId === rfqId && x.status === 'ACCEPTED');
		if (!rfq || !q) throw new CheckerError('NOT_FOUND', 404, `No accepted quote for RFQ ${rfqId}`);
		this.tick(150, 400);
		rfq.status = 'CLOSED';
		const order: OrderResource = {
			orderId: id('ord'),
			instrumentPair: rfq.instrumentPair,
			quantity: rfq.quantity,
			side: rfq.side,
			status: 'NEW',
			price: q.price,
			clientId: 'goldmine-desk',
			date: this.iso(),
			provider: q.provider,
			clientOrderId,
			requestForQuoteId: rfqId,
			tags: ['qp-hedge'],
			fills: []
		};
		this.orders.set(order.orderId, order);
		return order;
	}

	// GET /orders/{id}: each poll advances the order one state
	pollOrder(orderId: string): OrderResource {
		const o = this.orders.get(orderId);
		if (!o) throw new CheckerError('NOT_FOUND', 404, `Order ${orderId} not found`);
		this.tick(700, 1800);
		const filled = (o.fills ?? []).reduce((s, f) => s + f.quantity, 0);
		const remaining = round(o.quantity - filled);

		if (this.scenario === 'lp_rejected') {
			o.status = 'REJECTED';
			o.notes = `${o.provider}: counterparty credit limit exceeded`;
			return structuredClone(o);
		}
		if (this.scenario === 'partial_fill' && filled > 0) {
			o.status = 'STOPPED';
			o.notes = `${o.provider}: liquidity withdrawn, ${remaining} unfilled`;
			return structuredClone(o);
		}
		// Fills are whole units (GC trades in whole contracts).
		const slice = Math.floor(remaining * (0.3 + Math.random() * 0.4));
		const lastSlice = this.scenario !== 'partial_fill' && (filled > 0 || slice === 0 || Math.random() < 0.3);
		const qty = lastSlice ? remaining : slice;
		if (qty === 0) {
			o.status = 'STOPPED';
			o.notes = `${o.provider}: liquidity withdrawn, ${remaining} unfilled`;
			return structuredClone(o);
		}
		o.fills!.push(this.fill(qty, o.price));
		o.status = round(filled + qty) >= o.quantity ? 'FILLED' : 'PARTIALLY_FILLED';
		return structuredClone(o);
	}

	private fill(quantity: number, price: number): Fill {
		return { fillId: id('fill'), quantity, price, date: this.iso() };
	}

	// Payments API: POST /withdrawals
	createWithdrawal(amount: number): PaymentResource {
		this.tick(300, 600);
		const p: PaymentResource = {
			withdrawalId: id('wd'),
			amount: Math.round(amount * 100) / 100,
			currency: 'USD',
			rail: 'FEDWIRE',
			status: 'PENDING'
		};
		this.payments.set(p.withdrawalId, p);
		return { ...p };
	}

	// Payments API: GET /withdrawals/{id}
	pollWithdrawal(withdrawalId: string, side: Side): PaymentResource {
		const p = this.payments.get(withdrawalId);
		if (!p) throw new CheckerError('NOT_FOUND', 404, `Withdrawal ${withdrawalId} not found`);
		this.tick(1500, 3000);
		if (this.scenario === 'payment_failed') {
			p.status = 'FAILED';
			p.failureReason =
				side === 'BUY' ? 'R01 Insufficient funds in settlement account' : 'Beneficiary bank returned wire: account name mismatch';
		} else p.status = 'COMPLETED';
		return { ...p };
	}
}

const round = (v: number) => Math.round(v * 1e4) / 1e4;
