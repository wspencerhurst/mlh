<script lang="ts">
	import 'katex/dist/katex.min.css';
	import Tex from '#lib/components/Tex.svelte';
	import { desk, fmt, sgn } from '#lib/desk.ts';

	const g = desk?.markets.gold;
	const c = desk?.markets.crude;
	const KNOBS = [
		{ k: 'wait_k', tex: 'w', name: 'Waiting threshold', what: 'Declare once the value of waiting is below 10^w × switching cost (log scale)' },
		{ k: 'slope_k', tex: 's', name: 'Curve-shape effect', what: 'How contango/backwardation moves that threshold' },
		{ k: 'h_pre', tex: 'h_{\\text{pre}}', name: 'Hedge before declaring', what: 'Share of the full hedge held while waiting' },
		{ k: 'h_post', tex: 'h_{\\text{post}}', name: 'Hedge after declaring', what: 'Share of the full hedge once declared' },
		{ k: 'basis_k', tex: 'b', name: 'Gap effect on hedge', what: 'Change in hedge share per unit of gap z-score' },
		{ k: 'hysteresis', tex: '\\eta', name: 'Switching buffer', what: '$/unit a month must lead by before switching' },
		{ k: 'tilt', tex: '\\phi', name: 'Momentum tilt', what: 'Weight on the 20-day change in curve slope' }
	] as const;
	const TOC = [
		['short', 'In short'],
		['terms', 'Terms'],
		['value', 'Valuing a month'],
		['hedge', 'The hedge'],
		['policy', 'Rule and learned policy'],
		['risk', 'Risk appetite'],
		['reward', 'Reward and score'],
		['tests', 'Testing and results'],
		['assumptions', 'Assumptions'],
		['contracts', 'Training contracts'],
		['data', 'Data'],
		['limits', 'Limits']
	];
	const row = (m: typeof g, role: string) => m?.scorecard.find((r) => r.role === role);
	const H = 'font-display text-xl font-bold scroll-mt-24';
</script>

<svelte:head>
	<title>How it works · Goldmine</title>
	<meta name="description" content="Model, assumptions, data and results behind the Goldmine quotation-period desk." />
</svelte:head>

<div class="mx-auto max-w-3xl px-4 pt-8 pb-20 sm:px-6">
	<h1 class="font-display text-3xl font-bold tracking-tight">How it works</h1>
	<p class="mt-2 text-ink-2">The model, its assumptions, data and results, in one page.</p>
	<nav class="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-sm" aria-label="On this page">
		{#each TOC as [id, label] (id)}<a class="text-accent hover:underline" href="#{id}">{label}</a>{/each}
	</nav>

	<div class="mt-8 flex flex-col gap-9 text-ink-2 [&_b]:text-ink [&_td]:align-top">
		<section>
			<h2 id="short" class={H}>In short</h2>
			<ul class="mt-2 flex list-disc flex-col gap-1 pl-5">
				<li><b>Decides</b> which quotation period (QP) to declare on a physical cargo, when to declare it, and the futures hedge that locks the value in.</li>
				<li><b>Inputs:</b> the parsed contract (form or Open Mineral), today's futures curve, spot, interest rates, your settings.</li>
				<li><b>A deterministic engine</b> values every month and sizes the hedge. <b>A learned policy</b> (7 numbers) decides when to declare and fine-tunes the hedge size.</li>
				<li><b>Tested</b> by replaying real history with no future data at decision time, against a simple rule.</li>
			</ul>
		</section>

		<section>
			<h2 id="terms" class={H}>Terms</h2>
			<table class="mt-2 w-full text-sm">
				<tbody>
					<tr class="border-b border-line"><td class="w-36 py-1.5 pr-3 font-semibold text-ink">QP</td><td class="py-1.5">The month whose average price you pay or receive.</td></tr>
					<tr class="border-b border-line"><td class="py-1.5 pr-3 font-semibold text-ink">M</td><td class="py-1.5">The cargo's delivery (or shipment) month, not today. M+1 = the month after.</td></tr>
					<tr class="border-b border-line"><td class="py-1.5 pr-3 font-semibold text-ink">Declare</td><td class="py-1.5">Tell the seller in writing which QP you choose, before the deadline. Final. If you don't, the default QP applies.</td></tr>
					<tr class="border-b border-line"><td class="py-1.5 pr-3 font-semibold text-ink">Unwind</td><td class="py-1.5">Closing 1/N of the hedge on each of the N pricing days, as each day's price becomes final.</td></tr>
					<tr class="border-b border-line"><td class="py-1.5 pr-3 font-semibold text-ink">Gap (basis)</td><td class="py-1.5">Difference between the physical index (spot) and the futures used to hedge.</td></tr>
					<tr><td class="py-1.5 pr-3 font-semibold text-ink">bps</td><td class="py-1.5">Basis points of the cargo's value (0.01%), so cargoes of any price compare.</td></tr>
				</tbody>
			</table>
		</section>

		<section>
			<h2 id="value" class={H}>Valuing a month</h2>
			<Tex block tex={'\\mathbb{E}[\\bar S_o] = \\tfrac{1}{N_o}\\textstyle\\sum_{d \\in o} F(\\text{contract trading on } d)'} />
			<Tex block tex={'V_o = (\\bar S_{\\text{sale}} + \\delta_s)\\,g(t_s) - (\\bar S_o + \\delta_o + \\pi_o)\\,g(t_o),\\qquad g(t) = 1 + r\\,\\tfrac{T-t}{360}'} />
			<p class="text-sm">
				Expected price comes from today's futures curve. <Tex tex="\delta" /> = differentials, <Tex tex="\pi" /> = seller premium,
				<Tex tex="t" /> = payment date, <Tex tex="r" /> = your funding rate. Provisional payments are financed from arrival. Moving every
				payment to one date shows whether a later month's higher price is outweighed by paying later.
			</p>
		</section>

		<section>
			<h2 id="hedge" class={H}>The hedge</h2>
			<Tex block tex={'h_k = -\\,\\beta \\textstyle\\sum_{\\text{legs}} s\\,Q\\,\\tfrac{n_k}{N}'} />
			<p class="text-sm">
				Futures in contract <Tex tex="k" /> for the <Tex tex="n_k" /> pricing days still to fix that trade in it. <Tex tex="s" /> = +1 sale,
				−1 purchase; <Tex tex="\beta \approx 1" /> from 10-day price changes. Gold hedges in the most liquid of the next three COMEX months;
				crude in the front NYMEX month. Each pricing day 1/N of the hedge is closed at settlement.
			</p>
		</section>

		<section>
			<h2 id="policy" class={H}>Rule and learned policy</h2>
			<p class="mt-2"><b>Rule (baseline):</b> declare the month with the highest <Tex tex="V_o" /> today, fully hedged.</p>
			<p class="mt-2"><b>Learned policy:</b> a 7-number rule tuned by reinforcement learning, not a neural network. Each day before declaring:</p>
			<ol class="mt-1 list-decimal pl-5 text-sm">
				<li><b>Pick a month:</b> highest <Tex tex={'V_o + \\phi \\cdot \\text{momentum}'} />; switch only if it leads by more than <Tex tex="\eta" />.</li>
				<li>
					<b>Declare or wait</b> (optimal stopping): keep the option to switch only while it is worth more than switching would cost.
					<Tex block tex={'W = \\sigma\\varphi(z) - \\ell\\,\\Phi(-z),\\quad z = \\ell/\\sigma,\\qquad \\text{declare if } W \\le 10^{w}\\cdot 2c\\cdot e^{s\\cdot\\text{slope}}'} />
					<Tex tex="\ell" /> = lead of the best month, <Tex tex="\sigma" /> = how much the gap between the two months can move by the deadline,
					<Tex tex="c" /> = cost per unit traded, slope = (C2 − C1)/C1 in %.
				</li>
				<li><b>Size the hedge:</b> <Tex tex={'h = h_{\\text{pre or post}} + b \\cdot z_{\\text{gap}}'} />, where <Tex tex={'z_{\\text{gap}}'} /> is today's spot-vs-futures gap against its last 250 days.</li>
			</ol>
			<div class="mt-3 overflow-x-auto">
				<table class="w-full text-sm">
					<thead><tr class="border-b border-line text-left text-xs text-ink-3"><th class="py-1.5 pr-3 font-medium">Number</th><th class="py-1.5 pr-3 font-medium">Controls</th><th class="py-1.5 pr-3 text-right font-medium">Gold</th><th class="py-1.5 text-right font-medium">Crude</th></tr></thead>
					<tbody>
						{#each KNOBS as kb (kb.k)}
							<tr class="border-b border-line">
								<td class="py-1.5 pr-3 whitespace-nowrap"><Tex tex={kb.tex} /> {kb.name}</td>
								<td class="py-1.5 pr-3">{kb.what}</td>
								<td class="py-1.5 pr-3 text-right tabular-nums">{g?.theta?.[kb.k] != null ? fmt(g.theta[kb.k], 2) : '–'}</td>
								<td class="py-1.5 text-right tabular-nums">{c?.theta?.[kb.k] != null ? fmt(c.theta[kb.k], 2) : '–'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<p class="mt-3 text-sm">
				<b>Training:</b> cross-entropy method. 160 simulated cargoes, each with a random realistic contract; try 24 settings, keep the best 6
				by the score below, resample around them, 8 rounds. Simulated markets replay real daily moves (price, rates, spot-vs-futures gap) from
				the training years in random 20-day blocks.
			</p>
			<p class="mt-2 text-sm">
				<b>Which one the desk uses:</b> by default, the learned policy only where it beat the rule in the training-period backtest.
				Crude passed. Gold uses the learned policy by choice: it beat the rule out of sample (smaller worst case) but its training-period
				edge was not statistically clear. Both tabs now use the <b>learned policy</b>.
			</p>
		</section>

		<section>
			<h2 id="risk" class={H}>Risk appetite</h2>
			<Tex block tex={'\\text{score} = \\mathbb{E}[P] - \\lambda\\,\\text{CVaR}_{5\\%},\\qquad \\text{CVaR}_{5\\%} \\approx 2.06\\,\\sigma - \\mathbb{E}[P]'} />
			<p class="text-sm">
				The slider sets <Tex tex="\lambda" />: the profit you would give up to make the average of the worst 5 in 100 outcomes $1 better.
				The desk tries every month at hedge sizes 0–100% and picks the best score. <Tex tex="\sigma" /> = unhedged price risk (volatility
				× gap between purchase and sale months) and, when hedged, the spot-vs-futures gap risk measured on real history.
			</p>
		</section>

		<section>
			<h2 id="reward" class={H}>Reward and score</h2>
			<Tex block tex={'r_t = \\Delta\\text{MTM}_t,\\quad \\textstyle\\sum_t r_t = P = \\text{physical} + \\text{futures} - \\text{costs} \\pm \\text{financing};\\qquad J = \\mathbb{E}[P] - 0.5\\,\\text{CVaR}_{5\\%}(P)'} />
			<p class="text-sm">
				Realized money, in bps of the cargo's value so 2001 and 2026 count equally. CVaR penalises the bad tail. Results are shown as
				<Tex tex={'P - P_{\\text{rule}}'} /> on the same cargo, which removes common market noise.
			</p>
		</section>

		<section>
			<h2 id="tests" class={H}>Testing and results</h2>
			<ul class="mt-2 flex list-disc flex-col gap-1 pl-5 text-sm">
				<li><b>Walk-forward:</b> trained on gold {g?.train_window[0].slice(0, 4)}–{g?.train_window[1].slice(0, 4)} and crude {c?.train_window[0].slice(0, 4)}–{c?.train_window[1].slice(0, 4)}; tested only on later cargoes.</li>
				<li><b>No look-ahead:</b> a decision on day <Tex tex="t" /> uses data up to <Tex tex="t-1" /> and trades at day <Tex tex="t" />'s settlement. A test scrambles later prices and checks no earlier action changes.</li>
				<li><b>Error bars:</b> 95% intervals by block bootstrap (neighbouring cargoes overlap).</li>
			</ul>
			<div class="mt-3 overflow-x-auto">
				<table class="w-full text-sm">
					<thead><tr class="border-b border-line text-left text-xs text-ink-3"><th class="py-1.5 pr-3 font-medium">Per cargo</th><th class="py-1.5 pr-3 text-right font-medium">Gold, bps ({g?.n_test})</th><th class="py-1.5 text-right font-medium">Crude, $/bbl ({c?.n_test})</th></tr></thead>
					<tbody>
						{#each [['baseline', 'Rule'], ['learned', 'Learned policy'], ['default', 'Default month, hedged'], ['ml', '12-month ML pick, unhedged']] as [role, label] (role)}
							{@const a = row(g, role)}
							{@const b = row(c, role)}
							<tr class="border-b border-line">
								<td class="py-1.5 pr-3">{label}</td>
								<td class="py-1.5 pr-3 text-right tabular-nums">{a ? `${sgn(a.mean, 1)} (worst ${sgn(a.worst, 0)})` : '–'}</td>
								<td class="py-1.5 text-right tabular-nums">{b ? `${sgn(b.mean, 2)} (worst ${sgn(b.worst, 2)})` : '–'}</td>
							</tr>
						{/each}
						<tr>
							<td class="py-1.5 pr-3">Learned vs rule, random contracts</td>
							<td class="py-1.5 pr-3 text-right tabular-nums">{g?.random_terms ? `${sgn(g.random_terms.vs_rule, 1)} [${sgn(g.random_terms.ci_lo, 1)}, ${sgn(g.random_terms.ci_hi, 1)}]` : '–'}</td>
							<td class="py-1.5 text-right tabular-nums">{c?.random_terms ? `${sgn(c.random_terms.vs_rule, 2)} [${sgn(c.random_terms.ci_lo, 2)}, ${sgn(c.random_terms.ci_hi, 2)}]` : '–'}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</section>

		<section>
			<h2 id="assumptions" class={H}>Assumptions</h2>
			<table class="mt-2 w-full text-sm">
				<tbody>
					<tr class="border-b border-line"><td class="w-40 py-1.5 pr-3 font-semibold text-ink">Execution</td><td class="py-1.5">At the day's settlement price (trade-at-settlement), so no timing slippage.</td></tr>
					<tr class="border-b border-line"><td class="py-1.5 pr-3 font-semibold text-ink">Fees and bid/ask</td><td class="py-1.5">$0.12/oz gold ($12 per contract), $0.015/bbl crude ($15 per contract), per trade: opening, each daily unwind, rolls. Editable.</td></tr>
					<tr class="border-b border-line"><td class="py-1.5 pr-3 font-semibold text-ink">Lots</td><td class="py-1.5">Whole contracts: 100 oz (GC), 1,000 bbl (CL).</td></tr>
					<tr class="border-b border-line"><td class="py-1.5 pr-3 font-semibold text-ink">Financing</td><td class="py-1.5">Simple interest, act/360, at 3-month T-bill + your spread (default 1.5%), on physical payments, provisional payments and daily margin.</td></tr>
					<tr class="border-b border-line"><td class="py-1.5 pr-3 font-semibold text-ink">Forward prices</td><td class="py-1.5">Today's futures settlements are unbiased forecasts; months not listed are interpolated (gold via spot carry).</td></tr>
					<tr class="border-b border-line"><td class="py-1.5 pr-3 font-semibold text-ink">Index</td><td class="py-1.5">Gold priced on spot (proxy for LBMA PM); crude on WTI Cushing spot. Averages use exchange business days.</td></tr>
					<tr class="border-b border-line"><td class="py-1.5 pr-3 font-semibold text-ink">Gap risk</td><td class="py-1.5">Measured on real history per month gap; used for the risk score and the bad case.</td></tr>
					<tr><td class="py-1.5 pr-3 font-semibold text-ink">Not modelled</td><td class="py-1.5">Initial margin funding, market impact of very large orders, credit limits, quantity tolerance options.</td></tr>
				</tbody>
			</table>
		</section>

		<section>
			<h2 id="contracts" class={H}>Training contracts</h2>
			<p class="mt-2 text-sm">Each simulated cargo gets a random contract within these ranges. The track record uses the standard contracts (gold 20,000 oz, M+1/M+2/M+3, sale on M+1 + $1.50; crude 600,000 bbl, M−1/M/M+1, sale on M+1 + $0.25).</p>
			<div class="mt-2 overflow-x-auto">
				<table class="w-full text-sm">
					<thead><tr class="border-b border-line text-left text-xs text-ink-3"><th class="py-1.5 pr-3 font-medium">Term</th><th class="py-1.5 pr-3 font-medium">Gold</th><th class="py-1.5 font-medium">Crude</th></tr></thead>
					<tbody>
						<tr class="border-b border-line"><td class="py-1.5 pr-3">Quantity</td><td class="py-1.5 pr-3">5,000–50,000 oz</td><td class="py-1.5">300,000–1,000,000 bbl</td></tr>
						<tr class="border-b border-line"><td class="py-1.5 pr-3">Declarable months</td><td class="py-1.5 pr-3">M+1…3, M…M+2, M+1…2, M+1…4</td><td class="py-1.5">M−1…M+1, M…M+1, M−1…M+2, M…M+2</td></tr>
						<tr class="border-b border-line"><td class="py-1.5 pr-3">Sale priced on</td><td class="py-1.5" colspan="2">One of the declarable months</td></tr>
						<tr class="border-b border-line"><td class="py-1.5 pr-3">Sale differential</td><td class="py-1.5 pr-3">$0.50–3.00/oz</td><td class="py-1.5">$0.10–0.60/bbl</td></tr>
						<tr class="border-b border-line"><td class="py-1.5 pr-3">Seller premium</td><td class="py-1.5 pr-3">30% of deals: $0–0.30/oz per later month</td><td class="py-1.5">30% of deals: $0–0.05/bbl per later month</td></tr>
						<tr class="border-b border-line"><td class="py-1.5 pr-3">Deadline</td><td class="py-1.5" colspan="2">3–10 business days before the first declarable month</td></tr>
						<tr class="border-b border-line"><td class="py-1.5 pr-3">Final payment</td><td class="py-1.5 pr-3">3–10 days after the QP</td><td class="py-1.5">3–10 days after the QP or delivery</td></tr>
						<tr class="border-b border-line"><td class="py-1.5 pr-3">Provisional payment</td><td class="py-1.5 pr-3">0% (half), 50% or 90%</td><td class="py-1.5">None</td></tr>
						<tr><td class="py-1.5 pr-3">Funding cost</td><td class="py-1.5" colspan="2">T-bill + 0.5–3.0%</td></tr>
					</tbody>
				</table>
			</div>
		</section>

		<section>
			<h2 id="data" class={H}>Data</h2>
			<div class="mt-2 overflow-x-auto">
				<table class="w-full text-sm">
					<thead><tr class="border-b border-line text-left text-xs text-ink-3"><th class="py-1.5 pr-3 font-medium">Data</th><th class="py-1.5 pr-3 font-medium">Source</th><th class="py-1.5 font-medium">Used for</th></tr></thead>
					<tbody>
						<tr class="border-b border-line"><td class="py-1.5 pr-3">Live futures curves (GC, CL)</td><td class="py-1.5 pr-3">CME settlements via Nimble, archived daily</td><td class="py-1.5">Today's recommendation</td></tr>
						<tr class="border-b border-line"><td class="py-1.5 pr-3">3-month T-bill</td><td class="py-1.5 pr-3">FRED via Nimble</td><td class="py-1.5">Financing</td></tr>
						<tr class="border-b border-line"><td class="py-1.5 pr-3">Gold spot, 1979–today</td><td class="py-1.5 pr-3">EODHD (XAUUSD)</td><td class="py-1.5">Index, volatility, backtest</td></tr>
						<tr class="border-b border-line"><td class="py-1.5 pr-3">COMEX gold front month, 2000–today</td><td class="py-1.5 pr-3">Yahoo Finance (GC=F)</td><td class="py-1.5">Hedge P&amp;L, gap risk</td></tr>
						<tr class="border-b border-line"><td class="py-1.5 pr-3">WTI futures (4 months) and spot, 1986–2024</td><td class="py-1.5 pr-3">EIA</td><td class="py-1.5">Crude backtest, gap risk</td></tr>
						<tr><td class="py-1.5 pr-3">Physical contracts</td><td class="py-1.5 pr-3">Open Mineral (sample contracts, bundled mock)</td><td class="py-1.5">Contract terms on the desk</td></tr>
					</tbody>
				</table>
			</div>
			<p class="mt-2 text-sm">The desk shows a snapshot ({desk ? new Date(desk.generated_at).toLocaleDateString('en-GB') : '–'}); refresh with <code>run_live.py</code> and <code>export_web.py</code>.</p>
		</section>

		<section>
			<h2 id="limits" class={H}>Limits</h2>
			<ul class="mt-2 flex list-disc flex-col gap-1 pl-5 text-sm">
				<li>Gold months other than the active COMEX contract are priced by carry, not traded history.</li>
				<li>Crude history ends in April 2024 (EIA stopped publishing futures).</li>
				<li>One cargo at a time; no portfolio netting across cargoes.</li>
				<li>Risk numbers assume normal tails; real bad cases can be worse.</li>
			</ul>
		</section>
	</div>
</div>
