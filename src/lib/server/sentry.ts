import * as Sentry from '@sentry/sveltekit';
import type { TradeResult } from '#lib/checker/types.ts';

/** Raise a Sentry alert for a failed mock trade, with the trade's full background attached. */
export function reportTradeFailure(result: TradeResult): NonNullable<TradeResult['sentry']> {
	const { ticket, error, rfq, order, payment, quotes, timeline } = result;
	if (!error) return { sent: false, reason: 'no error' };
	if (!Sentry.getClient()) return { sent: false, reason: 'Sentry is not initialised on the server' };

	const accepted = quotes.find((q) => q.status === 'ACCEPTED' || q.status === 'EXPIRED');
	const filled = (order?.fills ?? []).reduce((s, f) => s + f.quantity, 0);
	const t0 = Date.now() - (timeline.at(-1)?.at ?? 0);

	const err = new Error(error.message);
	err.name = error.code;

	const eventId = Sentry.withScope((scope) => {
		scope.setLevel('error');
		scope.setFingerprint(['checker', error.code, error.step]);
		scope.setTags({
			'checker.mode': 'mock',
			'trade.scenario': ticket.scenario,
			'trade.step': error.step,
			'trade.error_code': error.code,
			'trade.instrument': ticket.instrumentPair,
			'trade.side': ticket.side,
			'trade.provider': order?.provider ?? accepted?.provider ?? 'none',
			'order.status': order?.status ?? 'none',
			'payment.status': payment?.status ?? 'none'
		});
		scope.setContext('trade', {
			instrument: ticket.instrumentPair,
			side: ticket.side,
			quantity: ticket.quantity,
			reference_price: ticket.referencePrice,
			filled_quantity: filled,
			unfilled_quantity: ticket.quantity - filled,
			notional_usd: result.notionalUsd ?? null
		});
		if (rfq) scope.setContext('rfq', { id: rfq.requestForQuoteId, status: rfq.status, providers: rfq.providers.join(', ') });
		if (accepted)
			scope.setContext('quote', {
				id: accepted.quoteId,
				provider: accepted.provider,
				price: accepted.price,
				status: accepted.status,
				expiry: accepted.expiry
			});
		if (order)
			scope.setContext('order', {
				id: order.orderId,
				client_order_id: order.clientOrderId,
				status: order.status,
				price: order.price,
				fills: order.fills?.length ?? 0,
				notes: order.notes ?? null
			});
		if (payment)
			scope.setContext('payment', {
				id: payment.withdrawalId,
				amount: payment.amount,
				rail: payment.rail,
				status: payment.status,
				reason: payment.failureReason ?? null
			});
		scope.setExtra('quotes', quotes);
		// The trade timeline becomes the breadcrumb trail leading up to the failure.
		for (const t of timeline)
			scope.addBreadcrumb({
				timestamp: (t0 + t.at) / 1000,
				category: `checker.${t.step}`,
				level: t.ok ? 'info' : 'error',
				type: t.request ? 'http' : 'default',
				message: t.title + (t.detail ? `: ${t.detail}` : ''),
				data: t.request ? { method: t.request.method, url: t.request.path } : undefined
			});
		return Sentry.captureException(err, { mechanism: { type: 'checker', handled: true } });
	});

	return { sent: true, eventId };
}
