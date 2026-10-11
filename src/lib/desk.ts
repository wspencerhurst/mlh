// Engine output for the trader's desk, written by scripts/export_web.py.

export type Option = {
	name: string; // "M+3"
	qp_month: string; // "Mar27"
	qp_ym: number;
	exp_avg: number;
	value: number;
	hedged_value: number;
	pay_date: string;
	lots_traded: number;
};

export type Leg = { contract: string; symbol: string; ym: number; lots: number; side: 'BUY' | 'SELL'; settle: number; covers: string[] };

export type Unwind = { month: string; ym: number; contract: string; side: 'BUY' | 'SELL'; lots_total: number; lots_per_day: number; why: 'sale' | 'purchase' };
export type Plan = { unwind: Unwind[]; flat_by: string | null };

export type Outcome = { mean: number; std: number; hist: number[]; edges: number[]; '5': number; '25': number; '50': number; '75': number; '95': number; h5?: number; h95?: number };

export type Live = {
	deal: string;
	name: string;
	unit: string;
	lot: number;
	exchange: string;
	asof: string;
	spot: number;
	rate: number;
	funding: number;
	delivery: string;
	deadline: string;
	days_to_deadline: number;
	sale_qp: string;
	quantity: number;
	default_qp: string;
	options: Option[];
	best: string;
	edge_vs_default: number;
	declare_now: boolean;
	margin: number;
	wait_threshold: number;
	tickets: Record<string, Leg[]>;
	plans: Record<string, Plan>;
	curve: { ym: number; label: string; settle: number; oi: number; tau: number; ltd?: string }[];
	outcomes: Record<string, Outcome>;
	n_paths: number;
	explanation?: { text: string; model: string; generated_at: string };
};

export type Role = 'baseline' | 'learned' | 'default' | 'ml';
export type TrackSeries = { label: string; role: Role; points: [number, number, number, string][] };
export type ScoreRow = {
	label: string;
	role: Role;
	mean: number;
	std: number;
	worst: number;
	vs_base: number;
	ci_lo: number;
	ci_hi: number;
	win: number;
};

export type Market = {
	product: string;
	name: string;
	unit: string;
	metric: string;
	test_period: string;
	n_test: number;
	train_window: [string, string];
	live: Live;
	track: TrackSeries[];
	scorecard: ScoreRow[];
	theta: Record<'hysteresis' | 'h_pre' | 'h_post' | 'tilt' | 'wait_k' | 'basis_k' | 'slope_k', number>;
	lambda: number;
	policy_choice: 'learned' | 'rule';
	policy_basis?: 'training' | 'override';
	random_terms: { n: number; vs_rule: number; ci_lo: number; ci_hi: number } | null;
};

export type ProposalStatus = 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED' | 'SUBMITTED' | 'FILLED' | 'FAILED';

export type Proposal = {
	id: string;
	kind: 'QP_DECLARATION' | 'FUTURES_ORDER';
	market: 'gold' | 'crude';
	deal: string;
	summary: string;
	group: string;
	status: ProposalStatus;
	details: Record<string, string | number>;
	checker?: { instrumentPair: string; side: 'BUY' | 'SELL'; quantity: number; clientOrderId: string; tags: string[] };
};

export type Desk = { generated_at: string; markets: { gold: Market; crude: Market }; proposals: Proposal[] };

const files = import.meta.glob<Desk>('/data/desk.json', { eager: true, import: 'default' });
export const desk: Desk | null = Object.values(files)[0] ?? null;

export const ROLE_COLOR: Record<Role, string> = {
	baseline: 'var(--color-s0)',
	learned: 'var(--color-s1)',
	default: 'var(--color-s2)',
	ml: 'var(--color-s3)'
};
export const OPTION_COLORS = ['var(--color-s1)', 'var(--color-s2)', 'var(--color-s3)'];

/** yyyymm -> UTC ms at mid-month (for time axes). */
export const ymToT = (ym: number) => Date.UTC(Math.floor(ym / 100), (ym % 100) - 1, 15);

export const fmt = (v: number, dp = 2) =>
	Number.isFinite(v) ? v.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp }) : '–';
export const sgn = (v: number, dp = 2) => (v > 0 ? '+' : v < 0 ? '−' : '') + fmt(Math.abs(v), dp);
export const usd = (v: number) => (v < 0 ? '−$' : '$') + Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 });
/** Compact money: $163k, −$7.9M. */
export const usdShort = (v: number) => {
	const a = Math.abs(v);
	const s = a >= 1e6 ? (a / 1e6).toFixed(1) + 'M' : a >= 1e3 ? Math.round(a / 1e3) + 'k' : Math.round(a).toString();
	return (v < 0 ? '−$' : '$') + s;
};
export const longDate = (iso: string) =>
	new Date(iso + 'T00:00:00Z').toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
