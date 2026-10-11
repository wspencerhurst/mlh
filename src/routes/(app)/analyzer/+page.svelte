<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import { desk, fmt, sgn, usd, longDate } from '#lib/desk.ts';
	import { evaluateFlow, readFlow, writeFlow, type ContractFlow } from '#lib/contract-flow.ts';
import DecisionCopilot from '#lib/components/DecisionCopilot.svelte';
	import type { Rec } from '#lib/engine.ts';

	let flow = $state<ContractFlow | null>(null);
	let result = $state<Rec | null>(null);
	let loading = $state(true);
	let error = $state('');
	const market = $derived(flow ? desk?.markets[flow.market] : null);
	const selected = $derived(result?.options.find((option) => option.name === result?.best) ?? null);
	const ordered = $derived(result ? [...result.options].sort((a, b) => b.score - a.score) : []);
	const tickets = $derived(selected && result ? result.tickets[selected.name] ?? [] : []);

	onMount(() => {
		flow = readFlow();
		if (!flow) {
			loading = false;
			error = 'There is no contract setup in this session yet.';
			return;
		}
		result = evaluateFlow(flow);
		if (!result) error = 'The desk market is unavailable for this contract.';
		else if (result.error) error = result.error;
		else writeFlow({ ...flow, result });
		loading = false;
	});

	async function editTerms() {
		if (flow) writeFlow(flow);
		await goto(resolve('/(app)/contracts'));
	}
	async function continueToAction() {
		if (!flow || !result || result.error) return;
		writeFlow({ ...flow, result });
		await goto(resolve('/(app)/action'));
	}
function applyScenario(next: ContractFlow) {
	const nextResult = evaluateFlow(next);
	if (!nextResult || nextResult.error) return;
	flow = { ...structuredClone(next), result: nextResult };
	result = nextResult;
	error = '';
	writeFlow(flow);
}
</script>

<svelte:head>
	<title>Pricing-period analysis · Goldmine</title>
</svelte:head>

<div class="mx-auto max-w-6xl px-4 pb-16 pt-7 sm:px-6 sm:pt-10">
	<div class="flow-in">
		<div class="flex flex-wrap items-start justify-between gap-4">
			<div>
				<p class="text-xs font-semibold tracking-wide text-accent">Step 2 of 3 · Pricing analysis</p>
				<h1 class="mt-2 font-display text-3xl font-bold tracking-tight sm:text-4xl">Choose the quotation period</h1>
				<p class="mt-2 max-w-2xl text-sm leading-6 text-ink-2">A deterministic evaluation of your contract against the desk curve, carry, funding and current policy parameters.</p>
			</div>
			<button class="rounded-lg border border-line bg-panel px-3 py-2 text-sm font-semibold text-ink-2 hover:border-accent hover:text-accent" onclick={editTerms}>Edit contract terms</button>
		</div>

		{#if loading}
			<div class="mt-7 animate-pulse space-y-4" aria-label="Loading analysis">
				<div class="h-32 rounded-2xl bg-panel"></div><div class="h-56 rounded-2xl bg-panel"></div>
			</div>
		{:else if error || !result || !market}
			<div class="mt-7 rounded-2xl border border-warn/30 bg-warn-wash p-6" role="alert">
				<h2 class="font-display text-lg font-bold">{error || 'Analysis unavailable'}</h2>
				<p class="mt-1 text-sm text-ink-2">Return to contract setup to load the desk inputs and run the evaluation.</p>
					<button class="mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-[#141414]" onclick={editTerms}>Return to contract setup</button>
			</div>
		{:else if selected && flow}
			<section class="mt-6 overflow-hidden rounded-2xl border border-line bg-panel shadow-sm">
				<div class="border-b border-line bg-best-wash px-5 py-5 sm:px-7">
					<div class="flex flex-wrap items-start justify-between gap-4">
						<div>
							<p class="text-xs font-semibold tracking-wide text-best">Desk recommendation · {market.name}</p>
							<h2 class="mt-2 font-display text-3xl font-bold tracking-tight sm:text-4xl">Declare {selected.name}</h2>
							<p class="mt-1 text-sm text-ink-2">{selected.qp_month} average · {result.declare_now ? 'Declare now' : `Keep the choice open until ${longDate(result.deadline)}`}</p>
						</div>
						<div class="min-w-40 rounded-xl border border-best/20 bg-panel/80 px-4 py-3">
							<p class="text-xs text-ink-3">Expected value</p>
							<p class="mt-1 font-display text-2xl font-bold tabular-nums">{sgn(selected.mean)} <span class="text-sm font-medium text-ink-3">$/{result.unit}</span></p>
							<p class="text-xs text-ink-3">{usd(selected.mean * result.quantity)} on the contract</p>
						</div>
					</div>
					<p class="mt-4 max-w-4xl text-sm leading-6 text-ink-2">
						{#if result.declare_now}
							{#if market.policy_choice === 'rule'}
								The forward-curve rule selects {selected.name} and declares immediately for this market.
							{:else if result.days_to_deadline <= 0}
								The declaration deadline has arrived. The learned policy selects {selected.name}.
							{:else}
								The estimated value of waiting ({fmt(result.wait_value, 4)} $/{result.unit}) is below the hedge-switching threshold ({fmt(result.wait_threshold, 4)} $/{result.unit}).
							{/if}
						{:else}
							The estimated value of waiting ({fmt(result.wait_value, 4)} $/{result.unit}) is above the hedge-switching threshold ({fmt(result.wait_threshold, 4)} $/{result.unit}), so the learned policy keeps the declaration open. The model estimates a {fmt(result.p_change * 100, 1)}% chance that another period overtakes the leader by the deadline.
						{/if}
						The hedge sizing is {Math.round(selected.h * 100)}% at the current risk setting.
					</p>
				</div>

				<div class="grid gap-0 lg:grid-cols-[1.15fr_.85fr]">
					<div class="p-5 sm:p-7">
						<div class="flex items-baseline justify-between gap-3">
							<h3 class="font-display text-lg font-bold">Compare eligible periods</h3>
							<span class="text-xs text-ink-3">{market.policy_choice === 'learned' ? 'Learned policy' : 'Forward-curve rule'} · λ {result.settings.lambda.toFixed(2)}</span>
						</div>
						<div class="mt-4 space-y-2">
							{#each ordered as option (option.name)}
								{@const top = option.name === selected.name}
								<div class="rounded-xl border px-3 py-3 sm:px-4 {top ? 'border-best/30 bg-best-wash' : 'border-line bg-panel'}">
									<div class="flex flex-wrap items-center justify-between gap-2">
										<div class="flex items-center gap-2">
											<span class="grid h-8 min-w-10 place-items-center rounded-lg {top ? 'bg-best text-white' : 'bg-canvas text-ink-2'} font-display font-bold">{option.name}</span>
											<div>
												<p class="text-sm font-semibold">{option.qp_month} average{top ? ' · recommended' : ''}</p>
												<p class="text-xs text-ink-3">{Math.round(option.h * 100)}% hedge · {result.tickets[option.name]?.length ?? 0} futures legs</p>
											</div>
										</div>
										<div class="text-right">
											<p class="font-semibold tabular-nums">{sgn(option.mean)} <span class="text-xs font-normal text-ink-3">$/{result.unit}</span></p>
											<p class="text-xs tabular-nums text-ink-3">risk-adjusted score {sgn(option.score)}</p>
										</div>
									</div>
								</div>
							{/each}
						</div>
						<p class="mt-3 text-xs leading-5 text-ink-3">Expected value is the deal value after purchase cost and financing. The score applies your risk appetite to the modelled bad case; it is calculated by the existing desk engine.</p>
					</div>

					<aside class="border-t border-line bg-canvas/70 p-5 sm:p-7 lg:border-l lg:border-t-0">
						<h3 class="font-display text-lg font-bold">Hedge to prepare</h3>
						<p class="mt-1 text-sm text-ink-2">Futures tickets generated for {selected.name}. These are draft instructions until you choose to run the demo execution.</p>
						{#if tickets.length}
							<ul class="mt-4 space-y-2">
								{#each tickets as ticket (ticket.symbol)}
									<li class="rounded-xl border border-line bg-panel p-3">
										<div class="flex items-center justify-between gap-2">
											<span class="rounded-md px-2 py-1 text-xs font-bold {ticket.side === 'BUY' ? 'bg-good-wash text-good' : 'bg-bad-wash text-bad'}">{ticket.side === 'BUY' ? 'Buy' : 'Sell'}</span>
											<span class="font-display text-lg font-bold tabular-nums">{Math.abs(ticket.lots)} <span class="text-sm font-medium text-ink-3">lots</span></span>
										</div>
										<p class="mt-2 font-semibold">{ticket.contract} <span class="font-mono text-xs text-ink-3">{ticket.symbol}</span></p>
										<p class="mt-1 text-xs text-ink-3">Reference settlement {fmt(ticket.settle)} · {ticket.covers.join(' and ')}</p>
									</li>
								{/each}
							</ul>
						{:else}
							<div class="mt-4 rounded-xl border border-line bg-panel px-4 py-5">
								<p class="font-semibold">No futures tickets for this period</p>
								<p class="mt-1 text-sm text-ink-3">The selected pricing period does not require a futures hedge under these terms.</p>
							</div>
						{/if}
						<dl class="mt-4 grid grid-cols-2 gap-3">
							<div class="rounded-lg bg-panel p-3"><dt class="text-xs text-ink-3">Compared with default</dt><dd class="mt-1 font-semibold tabular-nums">{sgn(result.edge_vs_default)} <span class="text-xs font-normal text-ink-3">$/unit</span></dd></div>
							<div class="rounded-lg bg-panel p-3"><dt class="text-xs text-ink-3">Bad case, worst 5% avg</dt><dd class="mt-1 font-semibold tabular-nums">{sgn(-selected.cvar)} <span class="text-xs font-normal text-ink-3">$/unit</span></dd></div>
						</dl>
					</aside>
				</div>
			</section>

			<DecisionCopilot {flow} {result} onapply={applyScenario} />

			<div class="mt-4 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
				<p class="text-xs leading-5 text-ink-3">Market snapshot {longDate(result.asof)} · delivery {result.delivery} · {result.quantity.toLocaleString()} {result.unit} · {result.exchange}</p>
					<button class="min-h-11 rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-[#141414] transition hover:brightness-110 disabled:opacity-50" disabled={!result || !!result.error} onclick={continueToAction}>Open approval queue <span aria-hidden="true">→</span></button>
			</div>
		{/if}
	</div>
</div>
