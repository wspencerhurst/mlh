import type { OrderResource, Step, TimelineEvent, TradeResult, TradeTicket } from '#lib/checker/types.ts';
import { CheckerError, MockChecker, PROVIDERS } from './mock.ts';

const MAX_POLLS = 6;

/** Units per contract: GC futures are 100 oz, CL (WTI) futures 1,000 bbl; spot is quoted per oz. */
export const ozPerUnit = (instrumentPair: string) =>
	/^GC[FGHJKMNQUVXZ]\d{2}$/.test(instrumentPair) ? 100 : /^CL[FGHJKMNQUVXZ]\d{2}$/.test(instrumentPair) ? 1000 : 1;

const fmt = (v: number) => v.toLocaleString('en-US', { maximumFractionDigits: 2 });

/** Runs one ticket through RFQ → quotes → accept → execute → order fills → settlement. */
export function simulateTrade(ticket: TradeTicket): TradeResult {
	const api = new MockChecker(ticket.scenario, ticket.referencePrice);
	const timeline: TimelineEvent[] = [];
	const result: TradeResult = { ok: false, ticket, timeline, quotes: [] };
	const log = (e: Omit<TimelineEvent, 'at'>) => timeline.push({ at: api.clock, ...e });
	let step: Step = 'rfq';

	try {
		const rfqBody = {
			instrumentPair: ticket.instrumentPair,
			quantity: ticket.quantity,
			side: ticket.side,
			providers: PROVIDERS
		};
		const rfq = api.createRfq(rfqBody);
		result.rfq = rfq;
		log({
			step,
			ok: true,
			title: `RFQ ${rfq.requestForQuoteId} sent to ${PROVIDERS.length} LPs`,
			request: { method: 'POST', path: '/api/v1/request-for-quotes', body: rfqBody },
			response: rfq
		});

		step = 'quotes';
		const quotes = api.listQuotes(rfq.requestForQuoteId);
		result.quotes = quotes;
		const best = quotes.reduce((a, b) => ((ticket.side === 'BUY' ? b.price < a.price : b.price > a.price) ? b : a));
		log({
			step,
			ok: true,
			title: `${quotes.length} quotes received, best ${best.provider} @ ${fmt(best.price)}`,
			detail: quotes.map((q) => `${q.provider} ${fmt(q.price)}`).join(' · '),
			request: { method: 'GET', path: `/api/v1/request-for-quotes/${rfq.requestForQuoteId}/quotes` },
			response: quotes
		});

		step = 'accept';
		const accepted = api.acceptQuote(best.quoteId);
		log({
			step,
			ok: true,
			title: `Accepted ${accepted.provider} quote ${accepted.quoteId}`,
			request: { method: 'POST', path: `/api/v1/quotes/${accepted.quoteId}/accept` },
			response: accepted
		});

		step = 'execute';
		const clientOrderId = `gm-${Date.now().toString(36)}`;
		let order: OrderResource = api.execute(rfq.requestForQuoteId, clientOrderId);
		result.order = order;
		log({
			step,
			ok: true,
			title: `RFQ executed, order ${order.orderId} ${order.status}`,
			request: { method: 'POST', path: `/api/v1/request-for-quotes/${rfq.requestForQuoteId}/execute` },
			response: order
		});

		step = 'order';
		for (let i = 0; i < MAX_POLLS && !['FILLED', 'REJECTED', 'STOPPED', 'CANCELED'].includes(order.status); i++) {
			order = api.pollOrder(order.orderId);
			result.order = order;
			const filled = (order.fills ?? []).reduce((s, f) => s + f.quantity, 0);
			const ok = order.status === 'FILLED' || order.status === 'PARTIALLY_FILLED';
			log({
				step,
				ok,
				title: `Order ${order.status}: ${fmt(filled)} / ${fmt(order.quantity)} filled`,
				detail: order.notes,
				request: { method: 'GET', path: `/api/v1/orders/${order.orderId}` },
				response: order
			});
		}

		const filledQty = (order.fills ?? []).reduce((s, f) => s + f.quantity, 0);
		const notional = Math.round(filledQty * order.price * ozPerUnit(order.instrumentPair) * 100) / 100;
		result.notionalUsd = notional;
		if (order.status === 'REJECTED')
			throw new CheckerError('ORDER_REJECTED', 422, order.notes ?? `Order ${order.orderId} rejected`);

		step = 'settlement';
		if (filledQty > 0) {
			const pending = api.createWithdrawal(notional);
			result.payment = pending;
			log({
				step,
				ok: true,
				title: `Settlement wire ${pending.withdrawalId} for $${fmt(pending.amount)} ${pending.status}`,
				request: { method: 'POST', path: '/api/v1/withdrawals', body: { amount: pending.amount, currency: 'USD', rail: pending.rail } },
				response: pending
			});
			const final = api.pollWithdrawal(pending.withdrawalId, order.side);
			result.payment = final;
			log({
				step,
				ok: final.status === 'COMPLETED',
				title: `Settlement ${final.status}`,
				detail: final.failureReason,
				request: { method: 'GET', path: `/api/v1/withdrawals/${final.withdrawalId}` },
				response: final
			});
			if (final.status === 'FAILED') throw new CheckerError('PAYMENT_FAILED', 402, final.failureReason ?? 'Settlement failed');
		}

		if (order.status !== 'FILLED') {
			step = 'order';
			throw new CheckerError(
				'ORDER_INCOMPLETE',
				409,
				order.notes ?? `Order ${order.orderId} ended ${order.status} with ${fmt(order.quantity - filledQty)} unfilled`
			);
		}

		result.ok = true;
	} catch (e) {
		const err = e instanceof CheckerError ? e : new CheckerError('INTERNAL', 500, String(e));
		result.error = { code: err.code, step, message: err.message };
		if (!timeline.some((t) => !t.ok && t.step === step))
			log({ step, ok: false, title: `${err.code} (${err.status})`, detail: err.message });
	}
	return result;
}
