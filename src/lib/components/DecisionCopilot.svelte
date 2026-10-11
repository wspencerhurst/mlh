<script lang="ts">
	import { desk, fmt, sgn } from '#lib/desk.ts';
	import { evaluateFlow, type ContractFlow } from '#lib/contract-flow.ts';
	import type { Rec } from '#lib/engine.ts';

	let { flow, result, onapply }: { flow: ContractFlow; result: Rec; onapply: (flow: ContractFlow) => void } = $props();

	type Reply = { title: string; points: string[]; kind: 'answer' | 'unavailable' };
	type ScenarioKind = 'risk' | 'funding';

	const staleAfterMs = 48 * 60 * 60 * 1000;
	const selected = $derived(result.options.find((option) => option.name === result.best) ?? null);
	const defaultOption = $derived(result.options.find((option) => option.name === result.default_qp) ?? null);
	const ruleOption = $derived(result.options.find((option) => option.name === result.rule.name) ?? null);
	const staleInfo = $derived.by(() => {
		const generatedAt = desk?.generated_at;
		if (!generatedAt) return { stale: false, age: 'Unavailable', known: false };
		const timestamp = Date.parse(generatedAt);
		if (!Number.isFinite(timestamp)) return { stale: false, age: 'Unavailable', known: false };
		const ageMs = Math.max(0, Date.now() - timestamp);
		const hours = ageMs / (60 * 60 * 1000);
		return {
			stale: ageMs > staleAfterMs,
			age: hours < 1 ? 'Less than 1 hour' : `${Math.floor(hours)} hours`,
			known: true
		};
	});

	let open = $state(false);
	let question = $state('');
	let reply = $state<Reply | null>(null);
	let unsupported = $state(false);
	let scenarioKind = $state<ScenarioKind | null>(null);
	let draft = $state<ContractFlow | null>(null);
	let appliedNotice = $state(false);

	const scenarioResult = $derived(draft ? evaluateFlow(draft) : null);
	const scenarioUnavailable = $derived(
		!!draft && (!scenarioResult || !!scenarioResult.error)
	);
	const scenarioBest = $derived(
		scenarioResult?.options.find((option) => option.name === scenarioResult.best) ?? null
	);
	const unit = $derived(result.unit || 'unit');

	function price(value: number | undefined) {
		return Number.isFinite(value) ? `${sgn(value as number)} $/${unit}` : 'Unavailable';
	}

	function spread(value: number) {
		return `${(value * 100).toFixed(3)}% (${(value * 10_000).toFixed(1)} bps)`;
	}

	function sourceList() {
		return [
			`Market snapshot: ${result.asof || 'unavailable'} · ${result.exchange || 'exchange unavailable'} · spot ${Number.isFinite(result.spot) ? fmt(result.spot) : 'unavailable'} ${unit}`,
			`Contract: delivery ${flow.terms.delivery}, quantity ${flow.terms.quantity.toLocaleString()} ${unit}; periods ${flow.terms.options.map((option) => `${option.name} premium ${fmt(option.premium)}`).join(', ') || 'unavailable'}; default ${flow.terms.default_qp}`,
			`Pricing terms: purchase differential ${fmt(flow.terms.purchase_diff)}, sale ${flow.terms.sale_offset >= 0 ? 'M+' : 'M'}${flow.terms.sale_offset || ''} with differential ${fmt(flow.terms.sale_diff)}; deadline ${flow.terms.deadline_bdays} business days`,
			`Payment terms: ${flow.terms.pay_rule === 'after_qp' ? 'after quotation period' : 'after delivery'} · ${flow.terms.pay_lag} business-day lag · provisional ${fmt(flow.terms.provisional_pct * 100, 0)}%`,
			`Risk settings: lambda ${fmt(flow.settings.lambda, 2)} · partial hedge ${flow.settings.partial ? 'allowed' : 'not allowed'} · hedge cost ${fmt(flow.settings.cost_per_unit)} $/${unit}`,
			`Funding settings: market rate ${spread(result.rate)} · contract spread ${spread(flow.settings.funding_spread)} · applied rate ${spread(result.funding)}`,
			`Evaluation: selected ${selected?.name ?? 'unavailable'} · mean ${selected ? price(selected.mean) : 'unavailable'} · score ${selected ? price(selected.score) : 'unavailable'} · hedge ${selected ? `${(selected.h * 100).toFixed(0)}%` : 'unavailable'} · bad-case CVaR ${selected ? price(selected.cvar) : 'unavailable'}`
		];
	}

	function response(title: string, points: string[]) {
		unsupported = false;
		reply = { title, points, kind: 'answer' };
	}

	function unavailable(title: string, points: string[]) {
		unsupported = false;
		reply = { title, points, kind: 'unavailable' };
	}

	function explainSelected() {
		if (result.error || !selected) {
			unavailable('Selected period is unavailable', [
				result.error || 'The supplied evaluation has no selected valid quotation period.'
			]);
			return;
		}
		response('Why the engine selects this period', [
			`The current leader is ${selected.name}, the ${selected.qp_month} quotation-period average. Its mean is ${price(selected.mean)} and its risk-adjusted score is ${price(selected.score)}.`,
			`The engine ranks valid periods using mean minus risk lambda multiplied by bad-case CVaR. The selected hedge ratio is ${(selected.h * 100).toFixed(0)}%; bad-case CVaR is ${price(selected.cvar)}.`,
			`The contract default is ${result.default_qp}. The forward-curve rule selects ${result.rule.name}, with a rule value of ${price(result.rule.value)}.`
		]);
	}

	function comparePeriods() {
		if (result.error || !selected) {
			unavailable('Period comparison is unavailable', [
				result.error || 'The supplied evaluation has no selected valid quotation period.'
			]);
			return;
		}
		response('Selected period, contract default and forward-curve rule', [
			`Selected: ${selected.name} (${selected.qp_month}), mean ${price(selected.mean)}, score ${price(selected.score)}.`,
			defaultOption
				? `Contract default: ${defaultOption.name} (${defaultOption.qp_month}), mean ${price(defaultOption.mean)}, score ${price(defaultOption.score)}.`
				: `Contract default ${result.default_qp} is not present as a valid option in this evaluation.`,
			ruleOption
				? `Forward-curve rule: ${ruleOption.name} (${ruleOption.qp_month}), rule value ${price(result.rule.value)}, mean ${price(ruleOption.mean)}.`
				: `Forward-curve rule period ${result.rule.name || 'unavailable'} is not present as a valid option in this evaluation.`
		]);
	}

	function explainRisk() {
		response('Current risk setting', [
			`Risk lambda is ${fmt(flow.settings.lambda, 2)}. The selected period is ${result.best || 'unavailable'} with a hedge ratio of ${selected ? `${(selected.h * 100).toFixed(0)}%` : 'unavailable'}.`,
			selected
				? `Its mean is ${price(selected.mean)}, score is ${price(selected.score)}, and bad-case CVaR is ${price(selected.cvar)}. The engine uses lambda to weight bad-case CVaR in its score.`
				: 'The supplied evaluation does not contain a valid selected period.'
		]);
	}

	function explainFunding() {
		response('Current funding setting', [
			`The contract funding spread is ${spread(flow.settings.funding_spread)}. The supplied evaluation reports applied funding of ${spread(result.funding)} against a market rate of ${spread(result.rate)}.`,
			`Funding enters the evaluation as carry across the contract cash-flow dates. The current selected period is ${result.best || 'unavailable'} with mean ${selected ? price(selected.mean) : 'unavailable'} and score ${selected ? price(selected.score) : 'unavailable'}.`
		]);
	}

	function submitQuestion(event: SubmitEvent) {
		event.preventDefault();
		const normalized = question.trim().toLowerCase();
		if (!normalized) return;
		unsupported = false;
		reply = null;
		if (/\b(preview|scenario|change|increase|decrease|set|what if)\b/.test(normalized)) {
			unsupported = true;
		} else {
			const intents = [
				{
					pattern: /\b(compare|comparison|default|forward[- ]curve|rule)\b/,
					run: comparePeriods
				},
				{ pattern: /\b(risk|lambda)\b/, run: explainRisk },
				{ pattern: /\b(funding|spread|financing)\b/, run: explainFunding },
				{ pattern: /\b(why|recommendation|recommend|selected|quotation period|qp)\b/, run: explainSelected }
			];
			const matches = intents.filter((intent) => intent.pattern.test(normalized));
			if (matches.length !== 1) {
				unsupported = true;
				return;
			}
			matches[0].run();
		}
	}

	function startScenario(kind: ScenarioKind) {
		const next = structuredClone($state.snapshot(flow));
		scenarioKind = kind;
		if (kind === 'risk') {
			next.settings.lambda = Math.min(10, Math.max(0, flow.settings.lambda + Math.max(0.1, flow.settings.lambda * 0.2)));
		} else {
			next.settings.funding_spread = flow.settings.funding_spread + 0.0025;
		}
		draft = next;
		reply = null;
		unsupported = false;
		appliedNotice = false;
	}

	function updateScenarioValue(value: string) {
		if (!draft || !scenarioKind) return;
		const parsed = Number(value);
		if (!Number.isFinite(parsed)) return;
		const next = structuredClone($state.snapshot(draft));
		if (scenarioKind === 'risk') next.settings.lambda = Math.max(0, Math.min(10, parsed));
		else next.settings.funding_spread = parsed / 100;
		draft = next;
	}

	function discardScenario() {
		draft = null;
		scenarioKind = null;
		appliedNotice = false;
	}

	function applyScenario() {
		if (!draft || scenarioUnavailable || !scenarioKind) return;
		// Hand back only the reviewed setting; the parent remains responsible for persistence.
		const next = structuredClone($state.snapshot(flow));
		next.settings = structuredClone($state.snapshot(draft.settings));
		onapply(next);
		discardScenario();
		appliedNotice = true;
	}

	function runShortcut(label: string) {
		question = label;
		reply = null;
		unsupported = false;
		if (label.startsWith('Why')) explainSelected();
		else if (label.startsWith('Compare')) comparePeriods();
		else if (label.startsWith('Preview a changed risk')) startScenario('risk');
		else startScenario('funding');
	}
</script>

<section class="copilot" aria-label="Decision copilot">
	<button
		class="panel-toggle"
		type="button"
		aria-expanded={open}
		aria-controls="copilot-panel"
		onclick={() => (open = !open)}
	>
		<span class="toggle-mark" aria-hidden="true">{open ? '−' : '+'}</span>
		<span class="toggle-copy">
			<span class="eyebrow">Engine-guided review</span>
			<span class="toggle-title">Decision copilot</span>
			<span class="toggle-summary">Ask about the selected quotation period or test a desk-input scenario.</span>
		</span>
		<span class="toggle-state">{open ? 'Close panel' : 'Open panel'}</span>
	</button>

	{#if open}
		<div id="copilot-panel" class="panel-body">
			<div class="context-row">
				<div>
					<p class="eyebrow">Current evaluation</p>
					<p class="context-main">{result.best || 'No selected period'} <span>· {selected?.qp_month ?? 'Period unavailable'}</span></p>
				</div>
				<div class:stale={staleInfo.stale} class="snapshot-badge" role="status">
					<span class="status-dot" aria-hidden="true"></span>
					{#if staleInfo.stale}
						Stale snapshot · {staleInfo.age} old
					{:else if staleInfo.known}
						Snapshot age · {staleInfo.age}
					{:else}
						Snapshot age unavailable
					{/if}
				</div>
			</div>

			{#if staleInfo.stale}
				<p class="stale-note" role="status">The desk snapshot is older than 48 hours. Results remain visible, but treat them as stale and refresh the market inputs before relying on them.</p>
			{/if}
			{#if result.error}
				<p class="unavailable-banner" role="status">Evaluation unavailable: {result.error}</p>
			{/if}

			<div class="shortcuts" aria-label="Prompt shortcuts">
				<button type="button" class="shortcut" onclick={() => runShortcut('Why this quotation period?')}>Why this quotation period?</button>
				<button type="button" class="shortcut" onclick={() => runShortcut('Compare with contract default and forward-curve rule')}>Compare with contract default and forward-curve rule</button>
				<button type="button" class="shortcut" onclick={() => runShortcut('Preview a changed risk appetite')}>Preview a changed risk appetite</button>
				<button type="button" class="shortcut" onclick={() => runShortcut('Preview a higher funding spread')}>Preview a higher funding spread</button>
			</div>

			<form class="question-form" onsubmit={submitQuestion}>
				<label for="copilot-question">Ask a supported question</label>
				<div class="question-controls">
					<input
						id="copilot-question"
						bind:value={question}
						placeholder="For example: why this period, compare the default, risk lambda or funding"
						autocomplete="off"
					/>
					<button type="submit" class="ask-button">Ask</button>
				</div>
			</form>

			{#if unsupported}
				<div class="unsupported" role="status" aria-live="polite">
					<strong>Unsupported request</strong>
					<p>No answer was generated. Ask about why the period was selected, compare the default or rule, risk lambda, or funding.</p>
				</div>
			{/if}

			{#if appliedNotice}
				<p class="applied-note" role="status" aria-live="polite">Scenario inputs were passed to the parent for review. No proposal or order was created or sent.</p>
			{/if}

			{#if draft && scenarioKind}
				<div class="scenario" aria-label="Scenario preview">
					<div class="scenario-heading">
						<div>
							<p class="eyebrow">Separate scenario draft</p>
							<h3>{scenarioKind === 'risk' ? 'Risk appetite preview' : 'Funding spread preview'}</h3>
						</div>
						<span class="draft-tag">Not applied</span>
					</div>
					<p class="scenario-intro">This recalculates a structured copy of the contract flow. The current inputs remain unchanged until you apply them.</p>
					<label class="value-label" for="scenario-value">
						{scenarioKind === 'risk' ? 'Proposed risk lambda' : 'Proposed funding spread (%)'}
						<span>{scenarioKind === 'risk' ? fmt(draft.settings.lambda, 2) : spread(draft.settings.funding_spread)}</span>
					</label>
					<input
						id="scenario-value"
						class="value-input"
						type="number"
						step={scenarioKind === 'risk' ? '0.05' : '0.01'}
						min={scenarioKind === 'risk' ? '0' : undefined}
						max={scenarioKind === 'risk' ? '10' : undefined}
						value={scenarioKind === 'risk' ? draft.settings.lambda : draft.settings.funding_spread * 100}
						oninput={(event) => updateScenarioValue(event.currentTarget.value)}
						aria-label={scenarioKind === 'risk' ? 'Adjust proposed risk lambda' : 'Adjust proposed funding spread in percent'}
					/>

					{#if staleInfo.stale}
						<p class="stale-note compact" role="status">Stale snapshot results are shown for review and are not blocked.</p>
					{/if}
					{#if scenarioUnavailable}
						<p class="unavailable-banner" role="status">Scenario evaluation unavailable{scenarioResult?.error ? `: ${scenarioResult.error}` : ': market inputs could not be evaluated.'}</p>
					{:else if scenarioResult && scenarioBest}
						<div class="comparison-wrap">
							<table class="comparison">
								<caption>Current and proposed engine results</caption>
								<thead>
									<tr><th scope="col">Metric</th><th scope="col">Current</th><th scope="col">Proposed</th></tr>
								</thead>
								<tbody>
									<tr><th scope="row">Best period</th><td>{result.best || 'Unavailable'}</td><td>{scenarioResult.best || 'Unavailable'}</td></tr>
									<tr><th scope="row">Mean</th><td>{selected ? price(selected.mean) : 'Unavailable'}</td><td>{price(scenarioBest.mean)}</td></tr>
									<tr><th scope="row">Score</th><td>{selected ? price(selected.score) : 'Unavailable'}</td><td>{price(scenarioBest.score)}</td></tr>
									<tr><th scope="row">Hedge ratio</th><td>{selected ? `${(selected.h * 100).toFixed(0)}%` : 'Unavailable'}</td><td>{(scenarioBest.h * 100).toFixed(0)}%</td></tr>
									<tr><th scope="row">Bad-case CVaR</th><td>{selected ? price(selected.cvar) : 'Unavailable'}</td><td>{price(scenarioBest.cvar)}</td></tr>
									<tr><th scope="row">Snapshot date</th><td>{result.asof || 'Unavailable'}</td><td>{scenarioResult.asof || 'Unavailable'}</td></tr>
								</tbody>
							</table>
						</div>
					{/if}
					<div class="scenario-actions">
						<button type="button" class="discard-button" onclick={discardScenario}>Discard scenario</button>
						<button type="button" class="apply-button" disabled={scenarioUnavailable} onclick={applyScenario}>Apply scenario inputs</button>
					</div>
					<p class="safety-note">Applying sends only the reviewed setting to the parent. It does not approve, create, send or modify a proposal or order.</p>
				</div>
			{/if}

			{#if reply}
				<div class:response-unavailable={reply.kind === 'unavailable'} class="response" aria-live="polite" aria-atomic="true">
					<div class="response-heading">
						<div>
							<p class="eyebrow">{reply.kind === 'answer' ? 'Engine-generated explanation · no language model' : 'Evaluation status'}</p>
							<h3>{reply.title}</h3>
						</div>
						{#if reply.kind === 'answer'}<span class="engine-seal" aria-hidden="true">ƒ</span>{/if}
					</div>
					<ul class="response-points">
						{#each reply.points as point, index (index)}<li>{point}</li>{/each}
					</ul>
					<div class="sources">
						<h4>Sources</h4>
						<ul>{#each sourceList() as source, index (index)}<li>{source}</li>{/each}</ul>
					</div>
				</div>
			{/if}

			<section class="calculation" aria-labelledby="copilot-calculation-heading">
				<h3 id="copilot-calculation-heading">How this answer is calculated</h3>
				<ol>
					<li>Read the current desk market snapshot and the contract terms supplied to this component.</li>
					<li>Evaluate eligible quotation periods with the contract-flow engine, including cash-flow carry and the configured funding.</li>
					<li>Calculate hedge choices, period mean and bad-case CVaR from the supplied market inputs.</li>
					<li>Rank valid periods by the engine score using the current risk lambda. Scenario previews repeat these steps on a separate draft.</li>
				</ol>
			</section>
			<p class="engine-footnote">All explanations are deterministic and use only the desk evaluation and contract inputs.</p>
		</div>
	{/if}
</section>

<style>
	.copilot {
		--copilot-ink: #17251f;
		--copilot-muted: #52635a;
		--copilot-subtle: #7b8981;
		--copilot-line: #dce1dc;
		--copilot-panel: #fbfcfa;
		--copilot-wash: #f1f5ef;
		--copilot-accent: #265d50;
		--copilot-ochre: #aa7724;
		overflow: hidden;
		border: 1px solid var(--copilot-line);
		border-radius: 18px;
		background: var(--copilot-panel);
		color: var(--copilot-ink);
		box-shadow: 0 10px 28px rgb(34 55 43 / 5%);
	}

	button, input { font: inherit; }
	button:focus-visible, input:focus-visible {
		outline: 3px solid #bc8a38;
		outline-offset: 3px;
	}
	button { cursor: pointer; }

	.panel-toggle {
		display: grid;
		width: 100%;
		grid-template-columns: 38px minmax(0, 1fr) auto;
		align-items: center;
		gap: 13px;
		padding: 16px 18px;
		border: 0;
		background:
			linear-gradient(100deg, rgb(235 242 234 / 75%), transparent 72%),
			var(--copilot-panel);
		color: inherit;
		text-align: left;
	}
	.panel-toggle:hover { background-color: #f2f6f1; }
	.toggle-mark {
		display: grid;
		width: 36px;
		height: 36px;
		place-items: center;
		border: 1px solid #d5e1d7;
		border-radius: 11px;
		background: #eaf1eb;
		color: var(--copilot-accent);
		font-size: 22px;
		font-weight: 500;
	}
	.toggle-copy { display: grid; gap: 2px; }
	.eyebrow {
		margin: 0;
		color: var(--copilot-accent);
		font-size: 10px;
		font-weight: 700;
		letter-spacing: .02em;
	}
	.toggle-title { font-family: var(--font-display); font-size: 18px; font-weight: 700; letter-spacing: -.025em; }
	.toggle-summary { color: var(--copilot-muted); font-size: 12px; line-height: 1.5; }
	.toggle-state { color: var(--copilot-muted); font-size: 11px; font-weight: 700; white-space: nowrap; }

	.panel-body { border-top: 1px solid var(--copilot-line); padding: 19px; }
	.context-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; }
	.context-main { margin: 3px 0 0; font-family: var(--font-display); font-size: 17px; font-weight: 700; }
	.context-main span { color: var(--copilot-muted); font-family: var(--font-sans); font-size: 13px; font-weight: 500; }
	.snapshot-badge {
		display: inline-flex;
		align-items: center;
		gap: 7px;
		border: 1px solid #d5e5d9;
		border-radius: 999px;
		background: #eff6f0;
		padding: 6px 10px;
		color: #286144;
		font-size: 11px;
		font-weight: 700;
	}
	.snapshot-badge.stale { border-color: #edd3a2; background: #fff5e2; color: #8a570d; }
	.status-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
	.stale-note, .unavailable-banner, .applied-note {
		margin: 12px 0 0;
		border: 1px solid #edd3a2;
		border-radius: 10px;
		background: #fff7e8;
		padding: 10px 12px;
		color: #78510e;
		font-size: 12px;
		line-height: 1.55;
	}
	.unavailable-banner { border-color: #e6c5be; background: #fcf0ed; color: #883c2e; }
	.applied-note { border-color: #cee0d2; background: #eff7f0; color: #286144; }
	.shortcuts { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 15px; }
	.shortcut {
		min-height: 34px;
		border: 1px solid var(--copilot-line);
		border-radius: 9px;
		background: #fff;
		padding: 6px 10px;
		color: #314b3e;
		font-size: 11px;
		font-weight: 650;
		text-align: left;
		transition: border-color 140ms ease, background 140ms ease, transform 140ms ease;
	}
	.shortcut:hover { transform: translateY(-1px); border-color: #9cb9a4; background: #f5f9f5; }
	.question-form { margin-top: 15px; }
	.question-form label, .value-label { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 6px; color: #374a3e; font-size: 11px; font-weight: 700; }
	.question-controls { display: flex; gap: 8px; }
	.question-controls input, .value-input {
		min-width: 0;
		width: 100%;
		border: 1px solid var(--copilot-line);
		border-radius: 9px;
		background: #fff;
		padding: 10px 12px;
		color: var(--copilot-ink);
		font-size: 12px;
	}
	.question-controls input::placeholder { color: #849087; }
	.ask-button, .apply-button {
		border: 1px solid var(--copilot-accent);
		border-radius: 9px;
		background: var(--copilot-accent);
		padding: 0 17px;
		color: white;
		font-size: 12px;
		font-weight: 700;
	}
	.ask-button:hover, .apply-button:not(:disabled):hover { background: #1d4d42; }
	.unsupported {
		margin-top: 13px;
		border: 1px dashed #d6a888;
		border-radius: 11px;
		background: #fff8f1;
		padding: 12px 14px;
		color: #774b2d;
		font-size: 12px;
	}
	.unsupported p { margin: 3px 0 0; line-height: 1.5; }
	.scenario, .response {
		margin-top: 16px;
		border: 1px solid var(--copilot-line);
		border-radius: 14px;
		background: #f8faf7;
		padding: 15px;
	}
	.scenario { border-color: #d6dfcf; background: linear-gradient(130deg, #f5f8f1, #fbfcfa 72%); }
	.scenario-heading, .response-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
	.scenario h3, .response h3 { margin: 3px 0 0; font-family: var(--font-display); font-size: 17px; font-weight: 700; letter-spacing: -.02em; }
	.draft-tag { border: 1px solid #e4d2ad; border-radius: 999px; background: #fff7e8; padding: 5px 9px; color: #815b1b; font-size: 10px; font-weight: 700; }
	.scenario-intro { margin: 7px 0 13px; color: var(--copilot-muted); font-size: 12px; line-height: 1.55; }
	.value-label { margin: 0 0 5px; align-items: baseline; }
	.value-label span { color: var(--copilot-accent); font-variant-numeric: tabular-nums; }
	.value-input { max-width: 260px; font-variant-numeric: tabular-nums; }
	.compact { margin-top: 9px; }
	.comparison-wrap { overflow-x: auto; margin-top: 14px; border: 1px solid var(--copilot-line); border-radius: 10px; background: #fff; }
	.comparison { width: 100%; min-width: 460px; border-collapse: collapse; text-align: left; font-size: 11px; }
	.comparison caption { padding: 10px 12px; color: var(--copilot-muted); font-size: 10px; font-weight: 700; text-align: left; }
	.comparison th, .comparison td { border-top: 1px solid #e9ede8; padding: 8px 11px; vertical-align: top; }
	.comparison thead th { background: #f3f6f2; color: #506158; font-size: 10px; font-weight: 700; }
	.comparison tbody th { color: #4d5d53; font-weight: 600; }
	.comparison td { font-variant-numeric: tabular-nums; }
	.scenario-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; margin-top: 13px; }
	.discard-button { border: 1px solid var(--copilot-line); border-radius: 9px; background: #fff; padding: 9px 12px; color: #43564a; font-size: 11px; font-weight: 700; }
	.apply-button { min-height: 36px; }
	.apply-button:disabled { cursor: not-allowed; opacity: .45; }
	.safety-note { margin: 9px 0 0; color: var(--copilot-subtle); font-size: 10px; line-height: 1.5; text-align: right; }
	.response { border-color: #d7e3d8; background: #f8fbf7; }
	.response-unavailable { border-color: #e6c5be; background: #fcf7f5; }
	.engine-seal { display: grid; width: 27px; height: 27px; place-items: center; border: 1px solid #ccded0; border-radius: 8px; color: var(--copilot-accent); font-family: Georgia, serif; font-size: 17px; font-style: italic; }
	.response-points { display: grid; gap: 8px; margin: 13px 0 0; padding-left: 18px; color: #354a3d; font-size: 12px; line-height: 1.6; }
	.response-points li::marker { color: var(--copilot-ochre); }
	.sources { margin-top: 14px; border-top: 1px solid #dfe7de; padding-top: 10px; }
	.sources h4 { margin: 0; color: #496052; font-size: 10px; font-weight: 700; }
	.sources ul { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 5px 15px; margin: 7px 0 0; padding-left: 15px; color: #65746a; font-size: 10px; line-height: 1.45; }
	.calculation { margin-top: 15px; border-top: 1px solid var(--copilot-line); padding-top: 12px; }
	.calculation h3 { margin: 0; color: #354c3f; font-size: 11px; font-weight: 700; }
	.calculation ol { display: grid; gap: 6px; margin: 10px 0 0; padding-left: 19px; color: var(--copilot-muted); font-size: 11px; line-height: 1.55; }
	.engine-footnote { margin: 11px 0 0; color: var(--copilot-subtle); font-size: 10px; }

	@media (max-width: 600px) {
		.panel-toggle { grid-template-columns: 34px minmax(0, 1fr); gap: 10px; padding: 14px; }
		.toggle-mark { width: 32px; height: 32px; }
		.toggle-state { grid-column: 2; margin-top: -4px; }
		.panel-body { padding: 14px; }
		.sources ul { grid-template-columns: 1fr; }
		.question-controls { align-items: stretch; }
		.question-controls input { padding-inline: 9px; }
		.ask-button { padding-inline: 12px; }
		.safety-note { text-align: left; }
	}

	@media (prefers-reduced-motion: reduce) {
		.shortcut { transition: none; }
		.shortcut:hover { transform: none; }
	}
</style>
