import { loadSpot, type Bar, type SpotData } from './spot.ts';
import { futures, price, expiryOf, impliedCarry, type FuturesContract } from './futures.ts';
import type { ContractType } from './openmineral/types.ts';

// State shared across pages. It is only written in the browser (after mount or on user input),
// so the server-side copy of this module never holds per-user data.

/** Spot prices, loaded once and kept while navigating between pages. */
export const market = $state<{ spot: SpotData | null; error: string | null }>({ spot: null, error: null });

let loading: Promise<void> | null = null;
export function ensureSpot() {
	loading ??= loadSpot()
		.then((d) => {
			market.spot = d;
			market.error = null;
		})
		.catch((e) => {
			market.error = String(e);
			loading = null;
		});
	return loading;
}

/** The Open Mineral contract picked on /contracts and its payable gold, used by /optimiser. */
export const desk = $state<{ contract: ContractType | null; exposureOz: number }>({ contract: null, exposureOz: 0 });

export type CurvePoint = {
	c: FuturesContract;
	f: number;
	exp: { t: number; approx: boolean };
	years: number;
	basis: number;
	carry: number;
};

/** Futures curve against the latest XAUUSD close. */
export function curveOf(spotUsd: Bar | null): CurvePoint[] {
	if (!futures || !spotUsd) return [];
	return futures.contracts
		.filter((c) => price(c) !== null)
		.map((c) => {
			const exp = expiryOf(c);
			const f = price(c)!;
			const years = (exp.t - spotUsd.t) / (365.25 * 86_400_000);
			return { c, f, exp, years, basis: f - spotUsd.c, carry: impliedCarry(f, spotUsd.c, years) };
		});
}

export const latestUsd = (spot: SpotData | null) => spot?.XAUUSD.at(-1) ?? null;
