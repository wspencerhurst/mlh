// In-browser decision engine: mirrors qp_hedge/live.py so the contract form and risk settings
// recompute instantly. Python remains the source of truth for backtests and training.
//
//   value of option o   V_o = (S̄_sale + δ_s)·g(t_s) − (S̄_o + δ_o + premium)·g(t_o) − provisional financing
//   risk (normal)       σ(h)² = (h·σ_hedge)² + ((1−h)·σ_unhedged)²
//   score               (mean) − λ·CVaR₅%  with CVaR₅% = 2.063·σ − mean
//   declare now if      value of waiting <= 10^wait_k · switching cost · e^(slope_k·slope%)  (learned)

import type { Leg, Live, Option, Outcome, Plan, Unwind } from './desk.ts';

export type OptionTerm = { name: string; offset: number; premium: number };
export type Terms = {
	delivery: number;
	quantity: number;
	options: OptionTerm[];
	default_qp: string;
	purchase_diff: number;
	sale_offset: number;
	sale_diff: number;
	deadline_bdays: number;
	pay_lag: number;
	pay_rule: 'after_qp' | 'after_delivery';
	provisional_pct: number;
};
export type Settings = { lambda: number; funding_spread: number; cost_per_unit: number; partial: boolean };

export type HedgeErr = Record<string, { std_bps: number; mean_bps: number; cvar5_bps: number; n: number }>;
export type MarketIn = Live & {
	product: string;
	days: string[];
	ltd_map: Record<string, string>;
	vol_spread: number;
	vol_ann: number;
	hedge_err: HedgeErr;
	cost_per_unit: number;
	funding_spread: number;
	terms: Terms;
	theta?: { wait_k: number; h_pre: number; h_post: number; hysteresis: number; tilt: number; basis_k: number; slope_k: number };
	/** today's index-vs-futures gap as a z-score, and the curve slope (C2-C1)/C1 */
	basis_z?: number;
	curve_slope?: number;
	/** 'learned' if the learned policy beat the rule in the training-period replay, else 'rule' (declare now). */
	policy_choice?: 'learned' | 'rule';
};

export type EvalOption = Option & {
	offset: number;
	gap: number;
	sigma_u: number;
	sigma_h: number;
	h: number;
	mean: number;
	sigma: number;
	cvar: number;
	score: number;
	valid: boolean;
};

export type Rec = Omit<Live, 'options' | 'outcomes'> & {
	options: EvalOption[];
	outcomes: Record<string, Outcome & { h5: number; h95: number }>;
	hedge_ratio: number;
	rule: { name: string; value: number };
	edge_vs_rule: number;
	p_change: number;
	wait_value: number;
	z: number;
	settings: Settings;
	terms: Terms;
	error: string | null;
};

const DAY = 86_400_000;
const YEAR = 365 * DAY;
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const ymAdd = (k: number, n: number) => {
	const t = Math.floor(k / 100) * 12 + (k % 100) - 1 + n;
	return Math.floor(t / 12) * 100 + (t % 12) + 1;
};
export const ymLabel = (k: number) => `${MON[(k % 100) - 1]}${String(Math.floor(k / 100)).slice(2)}`;
export const optName = (off: number) => (off === 0 ? 'M' : `M${off > 0 ? '+' : '−'}${Math.abs(off)}`.replace('−', '-'));
const ymOf = (iso: string) => Number(iso.slice(0, 4)) * 100 + Number(iso.slice(5, 7));
const ms = (iso: string) => Date.parse(iso + 'T00:00:00Z');
const monthStart = (k: number) => `${Math.floor(k / 100)}-${String(k % 100).padStart(2, '0')}-01`;
const phi = (z: number) => Math.exp(-0.5 * z * z) / Math.sqrt(2 * Math.PI);
function Phi(z: number) {
	// Abramowitz-Stegun 7.1.26
	const t = 1 / (1 + 0.3275911 * (Math.abs(z) / Math.SQRT2));
	const y = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-(z * z) / 2);
	return z >= 0 ? 0.5 * (1 + y) : 0.5 * (1 - y);
}
const CVAR_K = phi(1.6449) / 0.05; // expected shortfall multiplier of a normal at 5%

export function evaluate(m: MarketIn, terms: Terms, s: Settings): Rec {
	const days = m.days;
	const asofMs = ms(m.asof);
	const firstIdx = (iso: string) => {
		let lo = 0;
		let hi = days.length;
		while (lo < hi) {
			const mid = (lo + hi) >> 1;
			if (days[mid] < iso) lo = mid + 1;
			else hi = mid;
		}
		return lo;
	};
	const fixingDays = (k: number) => days.filter((d) => ymOf(d) === k);
	const lastBday = (k: number) => {
		const f = fixingDays(k);
		return f.length ? f[f.length - 1] : monthStart(ymAdd(k, 1));
	};
	const shift = (iso: string, n: number) => days[Math.min(days.length - 1, Math.max(0, firstIdx(iso) + n))];
	const ltd = (k: number) => m.ltd_map[String(k)] ?? lastBday(k);
	const front = (d: string) => {
		let k = ymOf(d);
		for (let i = 0; i < 6 && ltd(k) < d; i++) k = ymAdd(k, 1);
		return k;
	};

	// curve in log space against time to expiry; gold also anchors spot at tau = 0
	const live = m.curve.filter((c) => c.oi > 0 && c.tau > 0.005).sort((a, b) => a.tau - b.tau);
	const knots = live.map((c) => [(ms(c.ltd ?? ltd(c.ym)) - asofMs) / YEAR, Math.log(c.settle)] as [number, number]);
	if (m.product === 'GC') knots.unshift([0, Math.log(m.spot)]);
	const fwd = (t: number) => {
		if (t <= knots[0][0]) return Math.exp(knots[0][1]);
		for (let i = 1; i < knots.length; i++)
			if (t <= knots[i][0]) {
				const [t0, f0] = knots[i - 1];
				const [t1, f1] = knots[i];
				return Math.exp(f0 + ((f1 - f0) * (t - t0)) / (t1 - t0));
			}
		return Math.exp(knots[knots.length - 1][1]);
	};
	const expIndex = (d: string) =>
		m.product === 'GC' ? fwd(Math.max(0, ms(d) - asofMs) / YEAR) : fwd(Math.max(0, ms(ltd(front(d))) - asofMs) / YEAR);

	const Q = Math.max(1, terms.quantity);
	const lot = m.lot;
	const fund = m.rate + s.funding_spread;
	const payDate = (q: number) => shift(lastBday(terms.pay_rule === 'after_qp' ? q : terms.delivery), terms.pay_lag);
	const qSale = ymAdd(terms.delivery, terms.sale_offset);
	const qOpt = terms.options.map((o) => ymAdd(terms.delivery, o.offset));
	const horizon = [...qOpt, qSale].map(payDate).sort().at(-1)!;
	const g = (d: string) => 1 + (fund * (ms(horizon) - ms(d))) / DAY / 360;
	const avgExp = (q: number) => {
		const f = fixingDays(q);
		return f.length ? f.reduce((a, d) => a + expIndex(d), 0) / f.length : NaN;
	};
	const saleVal = (avgExp(qSale) + terms.sale_diff) * g(payDate(qSale));
	const provDay = lastBday(terms.delivery);
	const provPay = shift(provDay, terms.pay_lag);

	// hedge contract for each fixing day: most liquid of the next three alive (gold), front month (crude)
	const hedgeMonth = (d: string) => {
		const alive = live.filter((c) => (c.ltd ?? ltd(c.ym)) >= d).slice(0, 3);
		if (!alive.length) return live[live.length - 1].ym;
		if (m.product === 'CL') return alive[0].ym;
		return alive.reduce((a, b) => (b.oi > a.oi ? b : a)).ym;
	};
	const legs = (q: number, sign: number) => {
		const f = fixingDays(q);
		const out = new Map<number, number>();
		for (const d of f) {
			const k = hedgeMonth(d);
			out.set(k, (out.get(k) ?? 0) + (-sign * Q) / f.length);
		}
		return out;
	};
	const settleOf = (k: number) => live.find((c) => c.ym === k)?.settle ?? NaN;
	const sym = (k: number) => `${m.product}${'FGHJKMNQUVXZ'[(k % 100) - 1]}${String(Math.floor(k / 100)).slice(2)}`;

	// unhedged risk: variance of the difference of two monthly averages of a lognormal price
	const tt = (q: number) => fixingDays(q).map((d) => Math.max(0, ms(d) - asofMs) / YEAR);
	const meanMin = (a: number[], b: number[]) => {
		let sum = 0;
		for (const x of a) for (const y of b) sum += Math.min(x, y);
		return a.length && b.length ? sum / (a.length * b.length) : 0;
	};
	const tS = tt(qSale);
	const sigmaU = (q: number) => {
		const tO = tt(q);
		const v = meanMin(tS, tS) + meanMin(tO, tO) - 2 * meanMin(tS, tO);
		return m.spot * m.vol_ann * Math.sqrt(Math.max(0, v));
	};
	const errGaps = Object.keys(m.hedge_err ?? {}).map(Number);
	const sigmaH = (gap: number) => {
		if (!errGaps.length) return 0;
		// match on the size of the gap: history only has one direction for some markets
		const near = errGaps.reduce((a, b) => (Math.abs(Math.abs(b) - Math.abs(gap)) < Math.abs(Math.abs(a) - Math.abs(gap)) || (Math.abs(b) === Math.abs(gap) && b === gap) ? b : a));
		const base = m.hedge_err[String(near)].std_bps;
		const scale = near !== 0 && Math.abs(gap) !== Math.abs(near) ? Math.sqrt(Math.abs(gap) / Math.abs(near)) : 1;
		return ((base * scale) / 1e4) * m.spot;
	};

	const hGrid = s.partial ? [0, 0.25, 0.5, 0.75, 1] : [1];
	const tickets: Record<string, Leg[]> = {};
	const plans: Record<string, Plan> = {};
	const outcomes: Rec['outcomes'] = {};
	const opts: EvalOption[] = terms.options.map((o, i) => {
		const q = qOpt[i];
		const eAvg = avgExp(q);
		let cost = (eAvg + terms.purchase_diff + o.premium) * g(payDate(q));
		if (terms.provisional_pct) cost += terms.provisional_pct * expIndex(provDay) * (g(provPay) - g(payDate(q)));
		const value = saleVal - cost;
		const buy = legs(q, -1);
		const sell = legs(qSale, +1);
		const net = new Map(buy);
		for (const [k, v] of sell) net.set(k, (net.get(k) ?? 0) + v);
		const fullLots = [...net].filter(([, v]) => Math.round(v / lot) !== 0);
		const gap = o.offset - terms.sale_offset;
		const su = sigmaU(q);
		const sh = q === qSale ? 0 : sigmaH(gap);
		const valid = Number.isFinite(value) && fixingDays(q).length > 0;
		// best hedge ratio for this option under the risk appetite
		let best = { h: 1, mean: -Infinity, sigma: 0, cvar: 0, score: -Infinity, lots: 0 };
		for (const h of q === qSale || !fullLots.length ? [1] : hGrid) {
			const lots = fullLots.reduce((n, [, v]) => n + Math.abs(Math.round((v * h) / lot)), 0);
			const mean = value - (s.cost_per_unit * 2 * lots * lot) / Q;
			const sigma = Math.hypot(h * sh, (1 - h) * su);
			const cvar = CVAR_K * sigma - mean;
			const score = mean - s.lambda * cvar;
			if (score > best.score + 1e-12) best = { h, mean, sigma, cvar, score, lots };
		}
		// learned adjustment: hedge a bit more or less when the index-vs-futures gap is unusually wide
		if (m.policy_choice === 'learned' && m.theta && best.h > 0 && best.h < 1.5 && fullLots.length && q !== qSale) {
			const h = Math.min(1.5, Math.max(0, best.h + m.theta.basis_k * Math.max(-3, Math.min(3, m.basis_z ?? 0))));
			const lots = fullLots.reduce((n, [, v]) => n + Math.abs(Math.round((v * h) / lot)), 0);
			const mean = value - (s.cost_per_unit * 2 * lots * lot) / Q;
			const sigma = Math.hypot(h * sh, (1 - h) * su);
			const cvar = CVAR_K * sigma - mean;
			best = { h, mean, sigma, cvar, score: mean - s.lambda * cvar, lots };
		}
		const h = best.h;
		tickets[o.name] = fullLots
			.map(([k, v]) => ({ k, lots: Math.round((v * h) / lot) }))
			.filter((x) => x.lots !== 0)
			.sort((a, b) => a.k - b.k)
			.map(({ k, lots }) => ({
				contract: `${m.product} ${ymLabel(k)}`,
				symbol: sym(k),
				ym: k,
				lots,
				side: lots > 0 ? 'BUY' : 'SELL',
				settle: settleOf(k),
				covers: [
					...(buy.has(k) ? [`purchase (${ymLabel(q)} average)`] : []),
					...(sell.has(k) ? [`sale (${ymLabel(qSale)} average)`] : [])
				]
			}));
		const unwind: Unwind[] = [];
		if (tickets[o.name].length) {
			for (const [qq, leg, why] of [
				[qSale, sell, 'sale'],
				[q, buy, 'purchase']
			] as const) {
				const n = fixingDays(qq).length || 1;
				for (const [k, v] of [...leg].sort((a, b) => a[0] - b[0]))
					unwind.push({
						month: ymLabel(qq),
						ym: qq,
						contract: `${m.product} ${ymLabel(k)}`,
						side: v > 0 ? 'SELL' : 'BUY',
						lots_total: Math.round(Math.abs(v * h) / lot),
						lots_per_day: Math.round(((Q * h) / n / lot) * 10) / 10,
						why
					});
			}
			unwind.sort((a, b) => a.ym - b.ym);
		}
		plans[o.name] = { unwind, flat_by: unwind.length ? lastBday(Math.max(q, qSale)) : null };
		const fullCost = (s.cost_per_unit * 2 * fullLots.reduce((n2, [, v]) => n2 + Math.abs(Math.round(v / lot)), 0) * lot) / Q;
		const hedged = value - fullCost;
		outcomes[o.name] = {
			mean: value,
			std: su,
			hist: [],
			edges: [],
			'5': value - 1.6449 * su,
			'25': value - 0.6745 * su,
			'50': value,
			'75': value + 0.6745 * su,
			'95': value + 1.6449 * su,
			h5: hedged - 1.6449 * sh,
			h95: hedged + 1.6449 * sh
		};
		return {
			name: o.name,
			offset: o.offset,
			gap,
			qp_month: ymLabel(q),
			qp_ym: q,
			exp_avg: eAvg,
			value,
			hedged_value: hedged,
			pay_date: payDate(q),
			lots_traded: best.lots,
			sigma_u: su,
			sigma_h: sh,
			valid,
			...best
		};
	});

	const valid = opts.filter((o) => o.valid);
	const ranked = [...valid].sort((a, b) => b.score - a.score);
	const top = ranked[0];
	const dflt = valid.find((o) => o.name === terms.default_qp) ?? valid[0];
	// the baseline rule: best forward month, declared now, fully hedged, valued as the curve implies
	const rule = valid.reduce((a, b) => (b.hedged_value > a.hedged_value ? b : a), valid[0]);
	const deadlineIdx = firstIdx(monthStart(Math.min(...qOpt))) - terms.deadline_bdays;
	const deadline = deadlineIdx >= 0 ? days[deadlineIdx] : m.asof;
	const daysLeft = Math.max(0, deadlineIdx + 1);

	// declare now or wait (optimal stopping): keep the choice open only while its value is above the
	// learned multiple of what switching hedges would cost, adjusted for the curve's slope
	let z = Infinity;
	let pChange = 0;
	let waitValue = 0;
	if (top && ranked[1] && daysLeft > 0) {
		const lead = top.score - ranked[1].score;
		const sd = Math.max(1e-9, (m.vol_spread * Math.max(1, Math.abs(top.offset - ranked[1].offset))) / 2) * Math.sqrt(daysLeft);
		z = lead / sd;
		pChange = Phi(-z);
		waitValue = Math.max(0, sd * phi(z) - lead * Phi(-z));
	}
	const th = m.theta;
	const slopePct = Math.max(-3, Math.min(3, (m.curve_slope ?? 0) * 100));
	const threshold = th ? 10 ** th.wait_k * 2 * s.cost_per_unit * Math.exp(th.slope_k * slopePct) : 0;
	const declareNow = !daysLeft || m.policy_choice === 'rule' || waitValue <= threshold;

	return {
		...(m as Live),
		deal: `${m.name} cargo ${ymLabel(terms.delivery)} (${Math.round(Q).toLocaleString()} ${m.unit})`,
		delivery: ymLabel(terms.delivery),
		quantity: Q,
		default_qp: dflt?.name ?? terms.default_qp,
		sale_qp: ymLabel(qSale),
		deadline,
		days_to_deadline: daysLeft,
		funding: fund,
		options: opts,
		best: top?.name ?? '',
		edge_vs_default: top && dflt ? top.mean - dflt.mean : 0,
		declare_now: declareNow,
		margin: top && ranked[1] ? top.score - ranked[1].score : 0,
		wait_threshold: threshold,
		tickets,
		plans,
		outcomes,
		hedge_ratio: top?.h ?? 1,
		rule: { name: rule?.name ?? '', value: rule?.hedged_value ?? 0 },
		edge_vs_rule: top && rule ? top.mean - rule.hedged_value : 0,
		p_change: pChange,
		wait_value: waitValue,
		z,
		settings: s,
		terms,
		error: valid.length ? null : 'No valid quotation period: check the delivery month and options.'
	};
}
