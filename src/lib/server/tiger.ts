import { env, waitUntil } from 'cloudflare:workers';
import * as Sentry from '@sentry/sveltekit';
import postgres from 'postgres';
import type { TradeResult } from '#lib/checker/types.ts';

export type Sql = ReturnType<typeof postgres>;

/** Tiger Data (TimescaleDB) connection string from the Worker secret; null when unset. */
export function getTigerUrl(): string | null {
	const url = (env as Partial<Record<'TIGER_DATABASE_URL', unknown>> | undefined)?.TIGER_DATABASE_URL;
	return typeof url === 'string' && url ? url : null;
}

/** Run `fn` with a fresh client (Workers cannot share sockets across requests) and close it afterwards. */
export async function withTiger<T>(fn: (sql: Sql) => Promise<T>): Promise<T | null> {
	const url = getTigerUrl();
	if (!url) return null;
	const sql = postgres(url, { max: 1, fetch_types: false, connect_timeout: 10, idle_timeout: 5 });
	try {
		return await fn(sql);
	} finally {
		await sql.end({ timeout: 2 }).catch(() => {});
	}
}

export async function insertTrade(result: TradeResult): Promise<void> {
	const { ticket, error, order, payment, quotes } = result;
	const accepted = quotes.find((q) => q.status === 'ACCEPTED' || q.status === 'EXPIRED');
	const filled = (order?.fills ?? []).reduce((s, f) => s + f.quantity, 0);
	const json = JSON.parse(JSON.stringify(result));
	await withTiger(
		(sql) => sql`
			insert into trades (
				instrument, side, quantity, reference_price, scenario, ok, error_code, error_step, provider,
				order_status, payment_status, filled_quantity, notional_usd, sentry_event_id, result
			) values (
				${ticket.instrumentPair}, ${ticket.side}, ${ticket.quantity}, ${ticket.referencePrice}, ${ticket.scenario},
				${result.ok}, ${error?.code ?? null}, ${error?.step ?? null}, ${order?.provider ?? accepted?.provider ?? null},
				${order?.status ?? null}, ${payment?.status ?? null}, ${filled}, ${result.notionalUsd ?? null},
				${result.sentry?.eventId ?? null}, ${sql.json(json)}
			)`
	);
}

/** Record a trade in the background; a database error is logged and reported, never thrown. */
export function recordTrade(result: TradeResult): void {
	if (!getTigerUrl()) return;
	waitUntil(
		insertTrade(result).catch((err) => {
			console.error('Tiger Data insert failed', err);
			Sentry.captureException(err, { tags: { 'tiger.op': 'insert_trade' } });
		})
	);
}
