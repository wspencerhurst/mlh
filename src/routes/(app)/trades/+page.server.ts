import * as Sentry from '@sentry/sveltekit';
import type { PageServerLoad } from './$types';
import { getTigerUrl, withTiger } from '#lib/server/tiger.ts';

export interface BlotterRow {
	executedAt: string;
	instrument: string;
	side: string;
	quantity: number;
	filledQuantity: number;
	ok: boolean;
	scenario: string;
	errorStep: string | null;
	errorCode: string | null;
	sentryEventId: string | null;
}

export const load: PageServerLoad = async () => {
	if (!getTigerUrl()) return { configured: false as const };
	try {
		const data = await withTiger(async (sql) => {
			const [recent, daily, steps] = await Promise.all([
				sql<BlotterRow[]>`
					select executed_at::text as "executedAt", instrument, side, quantity, filled_quantity as "filledQuantity",
						ok, scenario, error_step as "errorStep", error_code as "errorCode", sentry_event_id as "sentryEventId"
					from trades order by executed_at desc limit 50`,
				sql<{ day: string; trades: number; failures: number; filled: number; notional: number }[]>`
					select day::text, sum(trades)::int as trades, sum(failures)::int as failures,
						coalesce(sum(filled_quantity), 0)::float8 as filled, coalesce(sum(notional_usd), 0)::float8 as notional
					from trades_daily where day >= now() - interval '14 days'
					group by day order by day desc`,
				sql<{ step: string; failures: number }[]>`
					select error_step as step, count(*)::int as failures
					from trades where not ok and error_step is not null and executed_at >= now() - interval '14 days'
					group by error_step order by failures desc`
			]);
			return { recent: [...recent], daily: [...daily], steps: [...steps] };
		});
		return { configured: true as const, error: null, ...data! };
	} catch (err) {
		console.error('Tiger Data query failed', err);
		Sentry.captureException(err, { tags: { 'tiger.op': 'load_blotter' } });
		return { configured: true as const, error: 'Could not read the trade blotter.', recent: [], daily: [], steps: [] };
	}
};
