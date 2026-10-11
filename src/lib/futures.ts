export type FuturesContract = {
	symbol: string;
	month: string; // YYYY-MM
	expiry: string | null;
	last: number | null;
	settle: number | null;
	change: number | null;
	open_interest: number | null;
	volume: number | null;
};

export type FuturesCurve = {
	retrieved_at: string;
	source: string;
	method: string;
	underlying: string;
	contracts: FuturesContract[];
};

// Written by the Nimble retrieval step; absent until that has run.
const files = import.meta.glob<FuturesCurve>('/data/gold_futures.json', { eager: true, import: 'default' });
export const futures: FuturesCurve | null = Object.values(files)[0] ?? null;

// Settle first so every point on the curve is from the same snapshot.
export const price = (c: FuturesContract) => c.settle ?? c.last;

/** Expiry date, falling back to the 3rd-last business day of the contract month (COMEX GC rule). */
export function expiryOf(c: FuturesContract): { t: number; approx: boolean } {
	if (c.expiry) return { t: Date.parse(c.expiry), approx: false };
	const [y, m] = c.month.split('-').map(Number);
	const d = new Date(Date.UTC(y, m, 0));
	let biz = 0;
	while (true) {
		const wd = d.getUTCDay();
		if (wd !== 0 && wd !== 6 && ++biz === 3) break;
		d.setUTCDate(d.getUTCDate() - 1);
	}
	return { t: d.getTime(), approx: true };
}

/** Annualised continuously-compounded carry implied by F = S·e^(rT). */
export const impliedCarry = (f: number, s: number, years: number) => (years > 0 ? Math.log(f / s) / years : NaN);
