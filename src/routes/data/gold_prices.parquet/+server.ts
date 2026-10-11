import type { RequestHandler } from './$types';
// Bundled into the Worker (not emitted as a public static asset) so the auth hook guards it.
import parquet from '/data/gold_prices.parquet?inline';

const bytes = Uint8Array.from(atob(parquet.slice(parquet.indexOf(',') + 1)), (c) => c.charCodeAt(0));

export const GET: RequestHandler = () =>
	new Response(bytes, {
		headers: {
			'content-type': 'application/vnd.apache.parquet',
			'cache-control': 'private, max-age=3600'
		}
	});
