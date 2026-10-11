<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import AthenaConnect from '#lib/components/AthenaConnect.svelte';
	import DealSetup from '#lib/components/DealSetup.svelte';
	import { desk } from '#lib/desk.ts';
	import { evaluateFlow, defaultsFor, marketInput, readFlow, writeFlow, type ContractFlow, type MarketKey } from '#lib/contract-flow.ts';
	import type { Settings, Terms } from '#lib/engine.ts';

	const blankTerms: Terms = {
		delivery: 202701, quantity: 1, options: [{ name: 'M', offset: 0, premium: 0 }],
		default_qp: 'M', purchase_diff: 0, sale_offset: 0, sale_diff: 0,
		deadline_bdays: 5, pay_lag: 0, pay_rule: 'after_qp', provisional_pct: 0
	};
	let marketKey = $state<MarketKey>('gold');
	let terms = $state<Terms>(defaultsFor('gold')?.terms ?? blankTerms);
	let settings = $state<Settings>(defaultsFor('gold')?.settings ?? { lambda: 0.5, funding_spread: 0, cost_per_unit: 0, partial: true });
	let error = $state('');
	let evaluating = $state(false);
	const source = $derived(desk?.markets[marketKey]);
	const input = $derived(marketInput(marketKey));
	const base = $derived(defaultsFor(marketKey));
	const flowSteps = [
		{ n: '01', label: 'Set up contract', current: true },
		{ n: '02', label: 'Review pricing period', current: false },
		{ n: '03', label: 'Prepare hedge', current: false }
	];

	onMount(() => {
		const saved = readFlow();
		if (saved) {
			marketKey = saved.market;
			terms = saved.terms;
			settings = saved.settings;
		}
	});

	function chooseMarket(key: MarketKey) {
		if (key === marketKey) return;
		const next = defaultsFor(key);
		if (!next) return;
		marketKey = key;
		terms = next.terms;
		settings = next.settings;
	}

	async function continueToAnalysis() {
		error = '';
		if (!source || !input) {
			error = 'Desk market data is unavailable. Try again when the desk snapshot is loaded.';
			return;
		}
		if (!(terms.quantity > 0) || !terms.options.length) {
			error = 'Enter a positive quantity and keep at least one quotation period.';
			return;
		}
		evaluating = true;
		try {
			const flow: ContractFlow = { market: marketKey, terms: $state.snapshot(terms), settings: $state.snapshot(settings) };
			const result = evaluateFlow(flow);
			if (!result || result.error) {
				error = result?.error ?? 'The pricing engine could not evaluate these terms.';
				return;
			}
			writeFlow({ ...flow, result });
			await goto(resolve('/(app)/analyzer'));
		} catch (e) {
			error = `Could not evaluate these terms: ${String(e)}`;
		} finally {
			evaluating = false;
		}
	}
</script>

<svelte:head>
	<title>Contract setup · Goldmine</title>
	<meta name="description" content="Set physical contract terms and evaluate quotation periods." />
</svelte:head>

<div class="mx-auto max-w-6xl px-4 pb-16 pt-7 sm:px-6 sm:pt-10">
	<div class="flow-in">
		<div class="flex flex-wrap items-center justify-between gap-4">
			<div>
				<p class="text-xs font-semibold tracking-wide text-accent">Goldmine · contract workflow</p>
				<h1 class="mt-2 font-display text-3xl font-bold tracking-tight sm:text-4xl">Contracts</h1>
				<p class="mt-2 max-w-2xl text-sm leading-6 text-ink-2">Connect Athena or review the pre-filled demo contract, then confirm the terms before analysis.</p>
			</div>
			<a href={resolve('/(app)/desk')} class="rounded-lg border border-line bg-panel px-3 py-2 text-sm font-semibold text-ink-2 transition hover:border-accent hover:text-accent">Open desk analytics</a>
		</div>

		<nav aria-label="Workflow progress" class="mt-7 grid grid-cols-3 overflow-hidden rounded-xl border border-line bg-panel">
			{#each flowSteps as step, i (step.n)}
				<div class="flex items-center gap-3 border-r border-line px-3 py-3 last:border-r-0 sm:px-5">
						<span class="grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-bold {step.current ? 'bg-accent text-[#141414]' : 'bg-canvas text-ink-3'}">{step.n}</span>
					<span class="hidden text-sm font-semibold sm:inline {step.current ? 'text-ink' : 'text-ink-3'}">{step.label}</span>
					<span class="text-sm font-semibold sm:hidden {step.current ? 'text-ink' : 'text-ink-3'}">{i === 0 ? 'Contract' : i === 1 ? 'Analysis' : 'Hedge'}</span>
				</div>
			{/each}
		</nav>

		{#if !desk || !source || !base || !input}
			<div class="mt-6 rounded-xl border border-warn/30 bg-warn-wash p-5 text-sm text-warn" role="alert">
				<p class="font-semibold">Desk data is not ready</p>
				<p class="mt-1">The desk snapshot is required to calculate a quotation-period recommendation.</p>
			</div>
		{:else}
			<section class="mt-6 rounded-2xl border border-line bg-panel p-4 shadow-sm sm:p-6">
				<div class="flex flex-wrap items-end justify-between gap-4">
					<div>
						<p class="text-xs font-semibold tracking-wide text-ink-3">Purchase contract</p>
						<h2 class="mt-1 font-display text-xl font-bold">Set up the deal</h2>
					</div>
					<div class="flex rounded-lg border border-line bg-canvas p-1" role="group" aria-label="Commodity">
						<button class="rounded-md px-4 py-2 text-sm font-semibold transition {marketKey === 'gold' ? 'bg-panel text-ink shadow-sm' : 'text-ink-2 hover:text-ink'}" aria-pressed={marketKey === 'gold'} onclick={() => chooseMarket('gold')}>Gold</button>
						<button class="rounded-md px-4 py-2 text-sm font-semibold transition {marketKey === 'crude' ? 'bg-panel text-ink shadow-sm' : 'text-ink-2 hover:text-ink'}" aria-pressed={marketKey === 'crude'} onclick={() => chooseMarket('crude')}>Crude oil</button>
					</div>
				</div>

				<div class="mt-5 grid gap-3 sm:grid-cols-3">
					<div class="rounded-xl bg-canvas p-3">
						<p class="text-xs text-ink-3">Desk market</p>
						<p class="mt-1 font-semibold">{source.name} <span class="font-normal text-ink-3">· {source.live.exchange}</span></p>
					</div>
					<div class="rounded-xl bg-canvas p-3">
						<p class="text-xs text-ink-3">Policy snapshot</p>
						<p class="mt-1 font-semibold">{source.policy_choice === 'learned' ? 'Learned desk policy' : 'Forward-curve rule'} <span class="font-normal text-ink-3">· λ {source.lambda.toFixed(2)}</span></p>
					</div>
					<div class="rounded-xl bg-canvas p-3">
						<p class="text-xs text-ink-3">Market data</p>
						<p class="mt-1 font-semibold">{source.live.asof} <span class="font-normal text-ink-3">· spot {source.live.spot.toLocaleString('en-US', { maximumFractionDigits: 2 })}</span></p>
					</div>
				</div>

				<div class="mt-5">
					<AthenaConnect />
				</div>
				<div class="mt-4">
					<DealSetup bind:terms bind:settings asof={source.live.asof} unit={source.unit} initialOpen={true} onreset={() => { terms = structuredClone(base.terms); settings = structuredClone(base.settings); }} />
				</div>

				<div class="mt-6 flex flex-col gap-3 border-t border-line pt-5 sm:flex-row sm:items-center sm:justify-between">
					<div class="text-xs leading-5 text-ink-3">
						<p>Policy parameters and market history come from the current desk snapshot.</p>
						<p>Changing these inputs only affects this browser session.</p>
					</div>
					<button class="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-[#141414] transition hover:brightness-110 disabled:cursor-wait disabled:opacity-60" disabled={evaluating} onclick={continueToAnalysis}>
						{evaluating ? 'Evaluating terms…' : 'Evaluate pricing periods'} <span aria-hidden="true">→</span>
					</button>
				</div>
				{#if error}<p class="mt-3 rounded-lg border border-bad/20 bg-bad-wash px-3 py-2 text-sm text-bad" role="alert">{error}</p>{/if}
			</section>
		{/if}
	</div>
</div>
