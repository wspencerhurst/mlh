import { json } from '@sveltejs/kit';
import { OpenMineralError } from './mock.ts';

/** Run a mock handler and map OpenMineralError to FastAPI's `{ detail }` error body. */
export function respond(fn: () => unknown): Response {
	try {
		return json(fn());
	} catch (e) {
		if (e instanceof OpenMineralError) return json({ detail: e.detail }, { status: e.status });
		throw e;
	}
}
