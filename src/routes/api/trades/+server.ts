import { error, json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { SCENARIOS, type Scenario, type TradeTicket } from '#lib/checker/types.ts';
import { simulateTrade } from '#lib/server/checker/simulate.ts';
import { reportTradeFailure } from '#lib/server/sentry.ts';
import { recordTrade } from '#lib/server/tiger.ts';

// Mock Checker execution: runs the whole RFQ → order → settlement flow in one request.
export const POST: RequestHandler = async ({ request }) => {
	const b = (await request.json().catch(() => null)) as Partial<TradeTicket> | null;
	if (!b) error(400, 'Invalid JSON');

	const ticket: TradeTicket = {
		instrumentPair: String(b.instrumentPair ?? ''),
		side: b.side === 'SELL' ? 'SELL' : 'BUY',
		quantity: Number(b.quantity),
		referencePrice: Number(b.referencePrice),
		scenario: (b.scenario && b.scenario in SCENARIOS ? b.scenario : 'happy') as Scenario
	};
	if (!/^(XAU-USD|(GC|CL)[FGHJKMNQUVXZ]\d{2})$/.test(ticket.instrumentPair)) error(400, 'Unsupported instrument');
	if (!(ticket.quantity > 0 && ticket.quantity <= 100_000)) error(400, 'Quantity must be between 0 and 100,000');
	if (/^(GC|CL)/.test(ticket.instrumentPair) && !Number.isInteger(ticket.quantity))
		error(400, 'Futures trade in whole contracts');
	if (!(ticket.referencePrice > 1 && ticket.referencePrice < 100_000)) error(400, 'Reference price out of range');

	const result = simulateTrade(ticket);
	if (!result.ok) result.sentry = reportTradeFailure(result);
	recordTrade(result);
	return json(result);
};
