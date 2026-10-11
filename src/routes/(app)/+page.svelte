<script lang="ts">
	import { onMount } from 'svelte';
	import ApprovalQueue from '#lib/components/ApprovalQueue.svelte';
	import CurveChart from '#lib/components/CurveChart.svelte';
	import OutcomeChart from '#lib/components/OutcomeChart.svelte';
	import HedgePlan from '#lib/components/HedgePlan.svelte';
	import DealSetup from '#lib/components/DealSetup.svelte';
	import ContractSource from '#lib/components/ContractSource.svelte';
	import LineChart from '#lib/components/LineChart.svelte';
	import { desk, fmt, sgn, usd, longDate, ymToT, ROLE_COLOR, OPTION_COLORS, type Proposal } from '#lib/desk.ts';
	import { evaluate, type MarketIn, type Settings, type Terms } from '#lib/engine.ts';

	const TABS = [
		{ id: 'gold', label: 'Gold', sub: 'COMEX GC' },
		{ id: 'crude', label: 'Crude oil', sub: 'NYMEX WTI' }
	] as const;
	type Tab = (typeof TABS)[number]['id'];
	let tab = $state<Tab>('gold');

	const marketIn = (t: Tab): MarketIn | null => {
		const mk = desk?.markets[t];
		return mk ? ({ ...mk.live, theta: mk.theta, policy_choice: mk.policy_choice } as unknown as MarketIn) : null;
	};
	const defaultsFor = (t: Tab) => {
		const mi = marketIn(t);
		return mi
			? {
					terms: structuredClone(mi.terms) as Terms,
					settings: { lambda: desk!.markets[t].lambda ?? 0.5, funding_spread: mi.funding_spread, cost_per_unit: mi.cost_per_unit, partial: true } as Settings
				}
			: null;
	};
	// one set of terms and settings per market, kept when switching tabs
	let setup = $state({ gold: defaultsFor('gold')!, crude: defaultsFor('crude')! });

	onMount(() => {
		const h = location.hash.slice(1);
		if (h === 'gold' || h === 'crude') tab = h;
	});
	function choose(t: Tab) {
		tab = t;
		history.replaceState(null, '', '#' + t);
	}

	const m = $derived(desk?.markets[tab]);
	const MI = $derived(marketIn(tab));
	const cur = $derived(setup[tab]);
	const L = $derived(MI && cur ? evaluate(MI, cur.terms, cur.settings) : null);
	const best = $derived(L ? (L.options.find((o) => o.name === L.best) ?? null) : null);
	const dflt = $derived(L ? (L.options.find((o) => o.name === L.default_qp) ?? null) : null);
	const proposals = $derived.by((): Proposal[] => {
		if (!L || !best) return [];
		const group = `${tab}-${L.delivery}-${best.name}-${best.h}`;
		const when = L.declare_now ? 'now' : `by ${L.deadline} (hedge now)`;
		return [
			{
				id: `${group}-qp`,
				kind: 'QP_DECLARATION',
				market: tab,
				deal: L.deal,
				summary: `Declare ${best.name} (${best.qp_month} average) ${when}`,
				group,
				status: 'PENDING_APPROVAL',
				details: { qp: best.name, deadline: L.deadline, quantity: L.quantity, unit: L.unit }
			},
			...L.tickets[best.name].map(
				(t): Proposal => ({
					id: `${group}-${t.symbol}-${t.lots}`,
					kind: 'FUTURES_ORDER',
					market: tab,
					deal: L.deal,
					summary: `${t.side} ${Math.abs(t.lots)} ${t.contract}`,
					group,
					status: 'PENDING_APPROVAL',
					details: {
						instrument: t.contract,
						side: t.side,
						lots: Math.abs(t.lots),
						lot_size: L.lot,
						unit: L.unit,
						ref_price: t.settle,
						notional_usd: Math.abs(t.lots) * L.lot * t.settle
					},
					checker: { instrumentPair: t.symbol, side: t.side, quantity: Math.abs(t.lots), clientOrderId: `${group}-${t.symbol}`, tags: ['qp-hedge'] }
				})
			)
		];
	});
	const track = $derived(
		m ? m.track.map((s) => ({ name: s.label, color: ROLE_COLOR[s.role], points: s.points.map(([ym, cum]) => ({ t: ymToT(ym), y: cum })) })) : []
	);
	const score = $derived(m ? m.scorecard : []);
	const baseline = $derived(score.find((r) => r.role === 'baseline'));
	const learned = $derived(score.find((r) => r.role === 'learned'));
	const u = $derived(L?.unit ?? '');
	const riskLabel = (l: number) => (l === 0 ? 'Max profit' : l < 0.35 ? 'Relaxed' : l < 1 ? 'Balanced' : l < 2 ? 'Cautious' : 'Very cautious');
	const dp = 2;
	const metricDp = $derived(m?.metric === 'bps' ? 1 : 2);
</script>

<svelte:head>
	<title>Goldmine · Quotation period desk</title>
	<meta name="description" content="Which quotation period to declare on a physical cargo, and the futures hedge that locks it in." />
</svelte:head>

<div class="mx-auto max-w-6xl px-4 pt-6 pb-16 sm:px-6">
	{#if !desk || !m || !L || !best || !dflt || !cur}
		<div class="mt-10 rounded-xl border border-dashed border-line bg-panel p-10 text-center">
			<p class="font-display text-lg font-bold">No engine output yet</p>
			<p class="mt-2 text-sm text-ink-2">Run <code>python run_live.py</code> and <code>python scripts/export_web.py</code> to write <code>data/desk.json</code>.</p>
		</div>
	{:else}
		<!-- Market tabs -->
		<div class="flex flex-wrap items-end justify-between gap-3">
			<div class="inline-flex rounded-lg border border-line bg-panel p-1" role="tablist" aria-label="Market">
				{#each TABS as t (t.id)}
					<button
						role="tab"
						aria-selected={tab === t.id}
						class="rounded-md px-4 py-1.5 text-sm font-semibold transition {tab === t.id ? 'bg-accent text-white' : 'text-ink-2 hover:text-ink'}"
						onclick={() => choose(t.id)}
					>
						{t.label} <span class="ml-1 font-normal opacity-70">{t.sub}</span>
					</button>
				{/each}
			</div>
			<label class="flex items-center gap-3 rounded-lg border border-line bg-panel px-3 py-1.5 text-sm" for="risk">
				<span class="text-xs font-semibold text-ink-2">Risk appetite</span>
				<span class="text-[11px] text-ink-3">Profit</span>
				<input id="risk" type="range" min="0" max="3" step="0.05" class="w-36 accent-accent sm:w-48" bind:value={setup[tab].settings.lambda} />
				<span class="text-[11px] text-ink-3">Safety</span>
				<span class="w-24 text-xs font-semibold text-ink tabular-nums">{riskLabel(cur?.settings.lambda ?? 0.5)} · {(cur?.settings.lambda ?? 0.5).toFixed(2)}</span>
			</label>
		</div>

		<p class="mt-2 text-xs text-ink-2">
			<b class="font-semibold">Risk appetite {(cur?.settings.lambda ?? 0.5).toFixed(2)}</b> means: give up ${(cur?.settings.lambda ?? 0.5).toFixed(2)}
			of expected profit to make the bad case (average of the worst 5 in 100 outcomes) $1 better, per {L.unit}. 0 = only expected profit counts.
		</p>
		<p class="mt-1 text-xs text-ink-3">Live {L.exchange} settlements {longDate(L.asof)} via Nimble · spot {fmt(L.spot, 2)} · T-bill {fmt(L.rate * 100, 2)}% · your funding {fmt(L.funding * 100, 2)}%</p>

		{#if MI?.product === 'GC'}
			<div class="mt-3">
				{#key tab}<ContractSource bind:terms={setup[tab].terms} base={defaultsFor(tab)!.terms} asof={L.asof} />{/key}
			</div>
		{/if}

		<div class="mt-3">
			<DealSetup
				bind:terms={setup[tab].terms}
				bind:settings={setup[tab].settings}
				asof={L.asof}
				unit={L.unit}
				onreset={() => (setup[tab] = defaultsFor(tab)!)}
			/>
		</div>

		<!-- 1. Decision -->
		<section class="mt-5 grid gap-4 lg:grid-cols-[1.15fr_1fr]">
			<div class="rounded-xl border border-line bg-panel p-5 shadow-sm">
				<div class="flex flex-wrap items-baseline justify-between gap-2">
					<div class="text-xs font-semibold tracking-wide text-ink-3 uppercase">Recommendation · {L.deal}</div>
					<span
						class="rounded-full bg-accent-wash px-2 py-0.5 text-[11px] font-semibold text-accent"
						title={m.policy_choice === 'learned'
							? 'The learned policy beat the rule in the training-period backtest, so it decides when to declare.'
							: 'The learned policy did not beat the rule in training, so the rule decides: declare now.'}
						>{m.policy_choice === 'learned' ? 'Learned policy' : 'Rule'} · risk-adjusted</span
					>
				</div>
				<h1 class="mt-2 font-display text-3xl font-bold tracking-tight sm:text-4xl">
					Declare <span class="text-best">{best.name}</span>
					<span class="text-xl font-medium text-ink-2 sm:text-2xl">· {best.qp_month} average{L.declare_now ? '' : `, by ${longDate(L.deadline)}`}</span>
				</h1>
				<p class="mt-2 text-ink-2">
					{#if L.declare_now}
						Declare {best.name} now{L.tickets[best.name].length ? ' and place the hedge' : ''}. There is only a {fmt(L.p_change * 100, 0)}% chance another month overtakes it
						before the deadline, so keeping the choice open is not worth it.
					{:else}
						{L.tickets[best.name].length ? `Place the hedge for ${best.name} now, but wait to declare` : 'Wait to declare'}: there is a
						{fmt(L.p_change * 100, 0)}% chance another month overtakes it before the deadline. Keeping the choice open is worth about
						{sgn(L.wait_value)} $/{u}.
					{/if}
					{#if best.h < 1}
						At your risk appetite the best hedge is <b class="text-ink">{Math.round(best.h * 100)}%</b> of the full position.
					{/if}
				</p>
				<div class="mt-4 rounded-lg bg-canvas px-3 py-2.5">
					<div class="text-xs font-semibold tracking-wide text-ink-3 uppercase">Hedge to place today</div>
					{#if L.tickets[best.name].length}
						<div class="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-base font-semibold">
							{#each L.tickets[best.name] as t (t.symbol)}
								<span><span class={t.side === 'BUY' ? 'text-good' : 'text-bad'}>{t.side === 'BUY' ? 'Buy' : 'Sell'}</span> {Math.abs(t.lots)} {L.exchange} {t.contract} futures</span>
							{/each}
						</div>
						<div class="text-xs text-ink-3">
							{(L.tickets[best.name].reduce((n, t) => n + Math.abs(t.lots), 0) * L.lot).toLocaleString()} {u} of contracts at today's settlement{best.h < 1 ? ` · ${Math.round(best.h * 100)}% hedge` : ''} · then unwound daily as prices fix (see plan below)
						</div>
					{:else}
						<div class="mt-1 text-base font-semibold">{best.h === 0 && best.sigma_u > 0 ? 'No hedge: you chose maximum profit, so the price risk is kept' : 'No hedge needed: this month matches your sale'}</div>
					{/if}
				</div>
				<dl class="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
					<div class="border-t border-line pt-2">
						<dt class="text-xs text-ink-3">Expected deal value</dt>
						<dd class="mt-0.5 text-lg font-semibold tabular-nums">{sgn(best.mean, dp)} <span class="text-sm font-normal text-ink-3">$/{u}</span></dd>
						<dd class="text-xs text-ink-3">{usd(best.mean * L.quantity)} on the cargo</dd>
					</div>
					<div class="border-t border-line pt-2">
						<dt class="text-xs text-ink-3">vs default ({dflt.name})</dt>
						<dd class="mt-0.5 text-lg font-semibold tabular-nums">{sgn(L.edge_vs_default, dp)} <span class="text-sm font-normal text-ink-3">$/{u}</span></dd>
						<dd class="text-xs text-ink-3">{usd(L.edge_vs_default * L.quantity)} on the cargo</dd>
					</div>
					<div class="border-t border-line pt-2">
						<dt class="text-xs text-ink-3">vs rule ({L.rule.name}, fully hedged)</dt>
						<dd class="mt-0.5 text-lg font-semibold tabular-nums">{Math.abs(L.edge_vs_rule) < 0.005 ? 'Same' : sgn(L.edge_vs_rule, dp)} {#if Math.abs(L.edge_vs_rule) >= 0.005}<span class="text-sm font-normal text-ink-3">$/{u}</span>{/if}</dd>
						<dd class="text-xs text-ink-3">{Math.abs(L.edge_vs_rule) < 0.005 ? 'as the curve implies' : 'trades value for lower risk'}</dd>
					</div>
					<div class="border-t border-line pt-2">
						<dt class="text-xs text-ink-3">Bad case (worst 5% avg)</dt>
						<dd class="mt-0.5 text-lg font-semibold tabular-nums {best.cvar > 0 ? 'text-bad' : ''}">{sgn(-best.cvar, dp)} <span class="text-sm font-normal text-ink-3">$/{u}</span></dd>
						<dd class="text-xs text-ink-3">Declare by {longDate(L.deadline)} · {L.days_to_deadline} days</dd>
					</div>
				</dl>
				{#if L.error}<p class="mt-3 text-sm text-bad">{L.error}</p>{/if}
				{#if m.live.explanation}
					<div class="mt-4 rounded-lg bg-canvas px-3 py-2.5">
						<div class="flex flex-wrap items-baseline justify-between gap-x-3 text-xs">
							<span class="font-semibold tracking-wide text-ink-3 uppercase">Summary · Snowflake Cortex ({m.live.explanation.model})</span>
							<span class="text-ink-3">{longDate(m.live.explanation.generated_at.slice(0, 10))} {m.live.explanation.generated_at.slice(11, 16)} UTC</span>
						</div>
						<p class="mt-1 text-sm text-ink-2">{m.live.explanation.text}</p>
					</div>
				{/if}
			</div>
			<div class="rounded-xl border border-line bg-panel p-5 shadow-sm">
				<ApprovalQueue {proposals} />
			</div>
		</section>

		<!-- 2. Hedge plan -->
		<section class="mt-4 rounded-xl border border-line bg-panel p-5 shadow-sm">
			<div class="flex flex-wrap items-baseline justify-between gap-2">
				<h2 class="font-display text-lg font-bold">Your hedge for {best.name}</h2>
				<span class="text-xs text-ink-3">Exactly what to trade, and when</span>
			</div>
			<div class="mt-4"><HedgePlan live={L} /></div>
		</section>

		<!-- 3. Why this month -->
		<section class="mt-4 rounded-xl border border-line bg-panel p-5 shadow-sm">
			<div class="flex flex-wrap items-baseline justify-between gap-2">
				<h2 class="font-display text-lg font-bold">Why {best.name}</h2>
				<span class="text-xs text-ink-3">You sell on the {L.sale_qp} average. Each option is valued on today's curve, with financing to payment.</span>
			</div>
			<div class="mt-4 grid gap-6 lg:grid-cols-[1.2fr_1fr]">
				<div class="min-w-0">
					<div class="mb-1 text-xs text-ink-3">{L.name} futures curve, {L.exchange} settle ({u === 'oz' ? '$/oz' : '$/bbl'}). Shaded: the months you can price on. Dot size: open interest.</div>
					<CurveChart live={L} />
				</div>
				<div class="min-w-0 overflow-x-auto">
					<table class="w-full text-sm">
						<thead>
							<tr class="border-b border-line text-left text-xs text-ink-3">
								<th class="py-2 pr-2 font-medium">Option</th>
								<th class="py-2 pr-2 text-right font-medium">Value, hedged</th>
								<th class="py-2 pr-2 text-right font-medium">vs default</th>
								<th class="py-2 text-right font-medium">Hedge</th>
							</tr>
						</thead>
						<tbody>
							{#each L.options as o, i (o.name)}
								<tr class="border-b border-line align-top {o.name === L.best ? 'bg-best-wash' : ''}">
									<td class="py-2.5 pr-2">
										<div class="flex items-center gap-2 font-semibold">
											<span class="h-2.5 w-2.5 rounded-sm" style:background={OPTION_COLORS[i]}></span>{o.name}
											{#if o.name === L.best}<span class="rounded bg-best px-1.5 text-[10px] font-bold text-white">BEST</span>{/if}
										</div>
										<div class="text-xs text-ink-3">{o.qp_month} average</div>
									</td>
									<td class="py-2.5 pr-2 text-right tabular-nums">{sgn(o.hedged_value)}</td>
									<td class="py-2.5 pr-2 text-right tabular-nums {o.hedged_value - dflt.hedged_value > 0.005 ? 'text-good' : o.hedged_value - dflt.hedged_value < -0.005 ? 'text-bad' : 'text-ink-3'}">
										{o.name === dflt.name ? 'default' : sgn(o.hedged_value - dflt.hedged_value)}
									</td>
									<td class="py-2.5 text-right text-xs text-ink-3">
										{L.tickets[o.name].length ? `${L.tickets[o.name].reduce((n, t) => n + Math.abs(t.lots), 0)} contracts` : 'none needed'}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
					<p class="mt-2 text-xs text-ink-3"><b class="font-semibold text-ink-2">M</b> = the delivery month ({L.delivery}), not today. M+1 means you pay the average price over the month after delivery. Values: whole deal (sale minus purchase, with financing), $/{u}, after hedging costs.</p>
				</div>
			</div>
		</section>

		<!-- 4. Hedged vs unhedged -->
		<section class="mt-4 rounded-xl border border-line bg-panel p-5 shadow-sm">
			<div class="flex flex-wrap items-baseline justify-between gap-2">
				<h2 class="font-display text-lg font-bold">What the hedge does</h2>
				<span class="text-xs text-ink-3">Deal value, $/{u} · {L.n_paths.toLocaleString()} simulated price paths</span>
			</div>
			<p class="mt-1 max-w-3xl text-sm text-ink-2">
				Without a hedge, a later pricing month is a bet on where the price goes before then. With the hedge, the value is fixed today.
			</p>
			<div class="mt-4"><OutcomeChart live={L} /></div>
		</section>

		<!-- 5. Track record -->
		<section class="mt-4 rounded-xl border border-line bg-panel p-5 shadow-sm">
			<div class="flex flex-wrap items-baseline justify-between gap-2">
				<h2 class="font-display text-lg font-bold">Track record</h2>
				<span class="text-xs text-ink-3">
					{m.n_test} past cargoes, one per month, {m.test_period} · trained on {m.train_window[0].slice(0, 4)}–{m.train_window[1].slice(0, 4)} only · no future data at decision time
				</span>
			</div>
			<div class="mt-3 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
				<div class="min-w-0">
					<div class="mb-1 text-xs text-ink-3">Cumulative realized P&amp;L, $ millions</div>
					<LineChart series={track} height={300} dp={1} unit="M" baseline={0} />
					<div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
						{#each m.track as s (s.role)}
							<span class="flex items-center gap-1.5"><span class="h-0.5 w-4" style:background={ROLE_COLOR[s.role]}></span>{s.label}</span>
						{/each}
					</div>
				</div>
				<div class="min-w-0 overflow-x-auto">
					<table class="w-full text-sm">
						<thead>
							<tr class="border-b border-line text-left text-xs text-ink-3">
								<th class="py-2 pr-2 font-medium">Per cargo, {m.metric}</th>
								<th class="py-2 pr-2 text-right font-medium">Average</th>
								<th class="py-2 pr-2 text-right font-medium">Worst</th>
								<th class="py-2 text-right font-medium">vs rule</th>
							</tr>
						</thead>
						<tbody>
							{#each score as r (r.role)}
								<tr class="border-b border-line {r.role === 'learned' ? 'bg-accent-wash' : ''}">
									<td class="py-2.5 pr-2">
										<span class="flex items-center gap-2"><span class="h-0.5 w-3" style:background={ROLE_COLOR[r.role]}></span>{r.label}</span>
									</td>
									<td class="py-2.5 pr-2 text-right tabular-nums">{sgn(r.mean, metricDp)}</td>
									<td class="py-2.5 pr-2 text-right tabular-nums {r.worst < 0 ? 'text-bad' : ''}">{sgn(r.worst, metricDp)}</td>
									<td class="py-2.5 text-right text-xs tabular-nums">
										{#if r.role === 'baseline'}<span class="text-ink-3">baseline</span>{:else}{sgn(r.vs_base, metricDp)}
											<div class="text-ink-3">[{sgn(r.ci_lo, metricDp)}, {sgn(r.ci_hi, metricDp)}]</div>{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
					{#if baseline && learned}
						<p class="mt-3 text-xs text-ink-2">
							Brackets: 95% confidence interval. The rule is the forward curve's best month, fully hedged. The learned policy
							{learned.ci_lo > 0 ? 'beats it by a statistically clear margin' : learned.ci_hi < 0 ? 'trails it' : 'is not distinguishable from it'} here.
							Unhedged picks swing far more and carry much larger worst cases.
							{#if m.policy_choice === 'rule'}
								<b class="text-ink">So the desk uses the rule here.</b> Trained on many contract types, the learned policy did not beat the
								rule for {m.name.toLowerCase()} in the training years either: the best month is set by carry and funding, so extra
								decisions only add risk.
							{:else if m.policy_basis === 'override'}
								<b class="text-ink">The desk uses the learned policy here by choice</b>: it beat the rule out of sample with a smaller worst
								case, but its edge in the training years was not statistically clear.
							{:else}
								<b class="text-ink">The desk uses the learned policy here</b>: it also beat the rule in the training years and on randomized
								contracts.
							{/if}
						</p>
					{/if}
				</div>
			</div>
		</section>

		<footer class="mt-8 grid gap-2 text-xs text-ink-3 sm:grid-cols-2">
			<p>
				<b class="font-semibold text-ink-2">How it decides.</b> A deterministic engine values every quotation period on the live curve
				(financing, payment terms, hedging costs) and sizes the hedge. A learned policy, trained by policy search on simulated
				markets, decides when to declare.
			</p>
			<p>
				<b class="font-semibold text-ink-2">Data.</b> Live CME settlements and FRED rates fetched with Nimble · gold spot from EODHD ·
				COMEX gold history from Yahoo Finance · crude history from the EIA. Generated {new Date(desk.generated_at).toLocaleString('en-GB')}.
				Decision support only.
			</p>
		</footer>
	{/if}
</div>
