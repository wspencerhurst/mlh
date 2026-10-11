import { parquetReadObjects } from 'hyparquet';

export const TICKERS = ['XAUUSD', 'XAUEUR', 'XAUAUD'] as const;
export type Ticker = (typeof TICKERS)[number];

export const TICKER_META: Record<Ticker, { label: string; ccy: string; color: string }> = {
	XAUUSD: { label: 'Gold / US Dollar', ccy: 'USD', color: '#C48A12' },
	XAUEUR: { label: 'Gold / Euro', ccy: 'EUR', color: '#4F8FE8' },
	XAUAUD: { label: 'Gold / Australian Dollar', ccy: 'AUD', color: '#E73427' }
};

export type Bar = { t: number; o: number; h: number; l: number; c: number; v: number };
export type SpotData = Record<Ticker, Bar[]>;
export type Point = { t: number; y: number };

const DAY = 86_400_000;

function toMs(d: unknown): number {
	if (d instanceof Date) return d.getTime();
	if (typeof d === 'bigint') return Number(d / 1000n); // microseconds
	if (typeof d === 'number') return d > 1e14 ? d / 1000 : d;
	return Date.parse(String(d));
}

export async function loadSpot(): Promise<SpotData> {
	const res = await fetch('/data/gold_prices.parquet');
	if (!res.ok) throw new Error(`HTTP ${res.status} loading spot prices`);
	const file = await res.arrayBuffer();
	const rows = (await parquetReadObjects({
		file,
		columns: ['ticker', 'date', 'open', 'high', 'low', 'close', 'volume']
	})) as Record<string, unknown>[];

	const out = { XAUUSD: [], XAUEUR: [], XAUAUD: [] } as SpotData;
	for (const r of rows) {
		const key = String(r.ticker).split('.')[0] as Ticker;
		if (!(key in out)) continue;
		out[key].push({
			t: toMs(r.date),
			o: Number(r.open),
			h: Number(r.high),
			l: Number(r.low),
			c: Number(r.close),
			v: Number(r.volume)
		});
	}
	for (const k of TICKERS) out[k].sort((a, b) => a.t - b.t);
	return out;
}

export const RANGES = ['1M', '3M', '6M', 'YTD', '1Y', '5Y', '10Y', 'Max'] as const;
export type Range = (typeof RANGES)[number];

export function rangeStart(range: Range, end: number): number {
	const d = new Date(end);
	switch (range) {
		case '1M':
			return end - 31 * DAY;
		case '3M':
			return end - 92 * DAY;
		case '6M':
			return end - 183 * DAY;
		case 'YTD':
			return Date.UTC(d.getUTCFullYear(), 0, 1);
		case '1Y':
			return end - 365 * DAY;
		case '5Y':
			return end - 5 * 365.25 * DAY;
		case '10Y':
			return end - 10 * 365.25 * DAY;
		case 'Max':
			return -Infinity;
	}
}

export function sliceFrom(bars: Bar[], start: number): Bar[] {
	let i = 0;
	while (i < bars.length && bars[i].t < start) i++;
	return bars.slice(i);
}

export const closes = (bars: Bar[]): Point[] => bars.map((b) => ({ t: b.t, y: b.c }));

export function rebased(bars: Bar[]): Point[] {
	if (!bars.length) return [];
	const base = bars[0].c;
	return bars.map((b) => ({ t: b.t, y: (b.c / base) * 100 }));
}

export function logReturns(bars: Bar[]): Point[] {
	const out: Point[] = [];
	for (let i = 1; i < bars.length; i++) {
		if (bars[i - 1].c > 0 && bars[i].c > 0) out.push({ t: bars[i].t, y: Math.log(bars[i].c / bars[i - 1].c) });
	}
	return out;
}

/** Rolling annualised volatility in %, from daily log returns. */
export function rollingVol(bars: Bar[], window = 21): Point[] {
	const r = logReturns(bars);
	const out: Point[] = [];
	let s = 0;
	let s2 = 0;
	for (let i = 0; i < r.length; i++) {
		s += r[i].y;
		s2 += r[i].y ** 2;
		if (i >= window) {
			s -= r[i - window].y;
			s2 -= r[i - window].y ** 2;
		}
		if (i >= window - 1) {
			const mean = s / window;
			const variance = Math.max(0, (s2 - window * mean * mean) / (window - 1));
			out.push({ t: r[i].t, y: Math.sqrt(variance * 252) * 100 });
		}
	}
	return out;
}

/** Drawdown from running peak, in %. */
export function drawdown(bars: Bar[]): Point[] {
	let peak = -Infinity;
	return bars.map((b) => {
		peak = Math.max(peak, b.c);
		return { t: b.t, y: (b.c / peak - 1) * 100 };
	});
}

/** Bucket daily bars into weekly or monthly candles so candles stay readable. */
export function aggregate(bars: Bar[], maxBars: number): { bars: Bar[]; period: string } {
	if (bars.length <= maxBars) return { bars, period: 'Daily' };
	const span = bars.length / maxBars;
	const [period, keyOf] =
		span <= 5
			? ['Weekly', (t: number) => Math.floor((t / DAY + 3) / 7)]
			: span <= 22
				? ['Monthly', (t: number) => new Date(t).getUTCFullYear() * 12 + new Date(t).getUTCMonth()]
				: ['Quarterly', (t: number) => new Date(t).getUTCFullYear() * 4 + Math.floor(new Date(t).getUTCMonth() / 3)];
	const out: Bar[] = [];
	let key = NaN;
	for (const b of bars) {
		const k = keyOf(b.t);
		const last = out[out.length - 1];
		if (k !== key || !last) {
			out.push({ ...b });
			key = k;
		} else {
			last.h = Math.max(last.h, b.h);
			last.l = Math.min(last.l, b.l);
			last.c = b.c;
			last.v += b.v;
		}
	}
	return { bars: out, period };
}

export type Stats = {
	last: number;
	lastDate: number;
	changePct: number;
	high: number;
	low: number;
	annVolPct: number;
	maxDrawdownPct: number;
	n: number;
};

export function stats(bars: Bar[]): Stats | null {
	if (bars.length < 2) return null;
	const r = logReturns(bars).map((p) => p.y);
	const mean = r.reduce((a, b) => a + b, 0) / r.length;
	const variance = r.reduce((a, b) => a + (b - mean) ** 2, 0) / (r.length - 1);
	const last = bars[bars.length - 1];
	return {
		last: last.c,
		lastDate: last.t,
		changePct: (last.c / bars[0].c - 1) * 100,
		high: Math.max(...bars.map((b) => b.h)),
		low: Math.min(...bars.map((b) => b.l)),
		annVolPct: Math.sqrt(variance * 252) * 100,
		maxDrawdownPct: Math.min(...drawdown(bars).map((p) => p.y)),
		n: bars.length
	};
}

/** Pearson correlation of daily log returns, aligned on common dates. */
export function correlation(a: Bar[], b: Bar[]): number {
	const ra = new Map(logReturns(a).map((p) => [p.t, p.y]));
	const xs: number[] = [];
	const ys: number[] = [];
	for (const p of logReturns(b)) {
		const x = ra.get(p.t);
		if (x !== undefined) {
			xs.push(x);
			ys.push(p.y);
		}
	}
	const n = xs.length;
	if (n < 3) return NaN;
	const mx = xs.reduce((s, v) => s + v, 0) / n;
	const my = ys.reduce((s, v) => s + v, 0) / n;
	let sxy = 0;
	let sxx = 0;
	let syy = 0;
	for (let i = 0; i < n; i++) {
		sxy += (xs[i] - mx) * (ys[i] - my);
		sxx += (xs[i] - mx) ** 2;
		syy += (ys[i] - my) ** 2;
	}
	return sxy / Math.sqrt(sxx * syy);
}

export const fmtNum = (v: number, dp = 2) =>
	v.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp });

export const fmtDate = (t: number) =>
	new Date(t).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' });
