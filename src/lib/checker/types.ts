// Shapes follow Checker's Trading API (docs/checker-finance.md); field names and enums are verbatim.

export type Side = 'BUY' | 'SELL';

export interface RequestForQuoteCreationResource {
	instrumentPair: string;
	quantity: number;
	side: Side;
	providers: string[];
}

export interface RequestForQuoteResource extends RequestForQuoteCreationResource {
	requestForQuoteId: string;
	status: 'CREATED' | 'OPEN' | 'CLOSED' | 'CANCELLED' | 'EXPIRED';
}

export interface QuoteResource {
	quoteId: string;
	requestForQuoteId: string;
	price: number;
	instrumentPair: string;
	benchmarkName: string;
	quantity: number;
	expiry: string;
	provider: string;
	status: 'PENDING' | 'ACCEPTED' | 'REJECTED' | 'EXPIRED';
}

export interface Fill {
	fillId: string;
	quantity: number;
	price: number;
	date: string;
}

export type OrderStatus =
	| 'PENDING_NEW'
	| 'NEW'
	| 'ACCEPTED_FOR_BIDDING'
	| 'PARTIALLY_FILLED'
	| 'FILLED'
	| 'DONE_FOR_DAY'
	| 'CANCELED'
	| 'PENDING_CANCEL'
	| 'PENDING_REPLACE'
	| 'STOPPED'
	| 'REJECTED'
	| 'SUSPENDED'
	| 'CALCULATED'
	| 'EXPIRED';

export interface OrderResource {
	orderId: string;
	instrumentPair: string;
	quantity: number;
	side: Side;
	status: OrderStatus;
	price: number;
	clientId: string;
	date: string;
	provider: string;
	clientOrderId: string;
	requestForQuoteId?: string;
	notes?: string;
	tags?: string[];
	fills?: Fill[];
}

/** Payments API withdrawal, used here for the settlement payment. Shape is our assumption. */
export interface PaymentResource {
	withdrawalId: string;
	amount: number;
	currency: 'USD';
	rail: 'CRYPTO' | 'ACH' | 'FEDWIRE' | 'SWIFT';
	status: 'PENDING' | 'COMPLETED' | 'FAILED';
	failureReason?: string;
}

export const SCENARIOS = {
	happy: { label: 'Settled', hint: 'Best quote accepted, fully filled, payment completed' },
	quote_expired: { label: 'Quote expired', hint: 'Trader accepts after the quote expiry' },
	lp_rejected: { label: 'LP rejects order', hint: 'Liquidity provider rejects on credit limit' },
	partial_fill: { label: 'Partial fill', hint: 'Order stops with quantity left unfilled' },
	payment_failed: { label: 'Payment fails', hint: 'Order filled but settlement wire is returned' }
} as const;
export type Scenario = keyof typeof SCENARIOS;

export interface TradeTicket {
	instrumentPair: string; // "XAU-USD" (oz) or a GC contract symbol such as "GCZ26" (contracts)
	side: Side;
	quantity: number;
	referencePrice: number; // USD/oz
	scenario: Scenario;
}

export type Step = 'rfq' | 'quotes' | 'accept' | 'execute' | 'order' | 'settlement';

export interface TimelineEvent {
	at: number; // ms after the ticket was submitted (simulated)
	step: Step;
	ok: boolean;
	title: string;
	detail?: string;
	request?: { method: string; path: string; body?: unknown };
	response?: unknown;
}

export interface TradeResult {
	ok: boolean;
	ticket: TradeTicket;
	timeline: TimelineEvent[];
	rfq?: RequestForQuoteResource;
	quotes: QuoteResource[];
	order?: OrderResource;
	payment?: PaymentResource;
	notionalUsd?: number;
	error?: { code: string; step: Step; message: string };
	sentry?: { sent: boolean; eventId?: string; reason?: string };
}
