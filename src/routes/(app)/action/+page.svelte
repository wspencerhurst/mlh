<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import ApprovalQueue from '#lib/components/ApprovalQueue.svelte';
	import { desk, longDate, type Proposal } from '#lib/desk.ts';
	import { readFlow, type ContractFlow } from '#lib/contract-flow.ts';

	let flow = $state<ContractFlow | null>(null);
	let loading = $state(true);
	let notice = $state('');

	const market = $derived(flow ? desk?.markets[flow.market] ?? null : null);
	const rec = $derived(flow?.result ?? null);
	const best = $derived(rec?.options.find((option) => option.name === rec.best) ?? null);
	const queueProposals = $derived.by((): Proposal[] => {
		if (!flow || !market || !rec || !best) return [];
		const activeFlow = flow;
		const activeMarket = market;
		const activeRec = rec;
		const activeBest = best;
		const group = `${activeFlow.market}-${activeRec.delivery}-${activeBest.name}-${activeRec.asof}`;
		const proposals: Proposal[] = [
			{
				id: `${group}-qp`,
				kind: 'QP_DECLARATION',
				market: activeFlow.market,
				deal: activeMarket.name,
				summary: `Declare ${activeBest.name} (${activeBest.qp_month} average)`,
				group,
				status: 'PENDING_APPROVAL',
				details: {
					quotation_period: activeBest.name,
					delivery: activeRec.delivery,
					quantity: activeRec.quantity,
					unit: activeRec.unit
				}
			},
			...(activeRec.tickets[activeBest.name] ?? []).map((leg): Proposal => {
				const lots = Math.abs(leg.lots);
				const lotSize = activeMarket.live.lot;
				return {
					id: `${group}-${leg.symbol}-${lots}`,
					kind: 'FUTURES_ORDER',
					market: activeFlow.market,
					deal: activeMarket.name,
					summary: `${leg.side} ${lots} ${leg.contract}`,
					group,
					status: 'PENDING_APPROVAL',
					details: {
						instrument: leg.contract,
						side: leg.side,
						lots,
						lot_size: lotSize,
						unit: activeRec.unit,
						ref_price: leg.settle,
						notional_usd: lots * lotSize * leg.settle,
						covers: leg.covers.join(', ')
					},
					checker: {
						instrumentPair: leg.symbol,
						side: leg.side,
						quantity: lots,
						clientOrderId: `${group}-${leg.symbol}`,
						tags: ['qp-hedge']
					}
				};
			})
		];
		return proposals;
	});

	onMount(() => {
		flow = readFlow();
		if (!flow?.result) notice = 'Run the contract evaluation first to prepare its approval queue.';
		loading = false;
	});

	async function backToAnalysis() {
		await goto(resolve('/(app)/analyzer'));
	}
</script>

<svelte:head>
	<title>Approval queue · Goldmine</title>
	<meta name="description" content="Review and approve the analyzer's contract declaration and hedge tickets." />
</svelte:head>

<div class="mx-auto max-w-6xl px-4 pb-16 pt-7 sm:px-6 sm:pt-10">
	<div class="flow-in">
		<div class="flex flex-wrap items-start justify-between gap-4">
			<div>
				<p class="text-xs font-semibold tracking-wide text-accent">Step 3 of 3 · Action</p>
				<h1 class="mt-2 font-display text-3xl font-bold tracking-tight sm:text-4xl">Approval queue</h1>
				<p class="mt-2 max-w-2xl text-sm leading-6 text-ink-2">Review the analyzer’s contract declaration and hedge orders. Approve the items you want to process.</p>
			</div>
			<button class="rounded-lg border border-line bg-panel px-3 py-2 text-sm font-semibold text-ink-2 hover:border-accent hover:text-accent" onclick={backToAnalysis}>Back to analysis</button>
		</div>

		{#if loading}
			<div class="mt-5 animate-pulse space-y-3" aria-label="Loading approval queue"><div class="h-24 rounded-xl bg-panel"></div><div class="h-48 rounded-xl bg-panel"></div></div>
		{:else if !flow || !rec || !best || !market}
			<div class="mt-5 rounded-2xl border border-line bg-panel p-6">
				<h2 class="font-display text-lg font-bold">{notice || 'No analyzer recommendation found'}</h2>
				<p class="mt-1 text-sm text-ink-2">Start at Contracts to enter the deal terms and run the analyzer.</p>
				<button class="mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-[#141414]" onclick={() => goto(resolve('/(app)/contracts'))}>Go to Contracts</button>
			</div>
		{:else}
			<section class="mt-6 grid gap-3 sm:grid-cols-3">
				<div class="rounded-xl border border-line bg-panel p-4">
					<p class="text-xs text-ink-3">Recommended declaration</p>
					<p class="mt-1 font-display text-lg font-bold">Declare {best.name}</p>
					<p class="mt-1 text-xs text-ink-2">{best.qp_month} average · delivery {rec.delivery}</p>
				</div>
				<div class="rounded-xl border border-line bg-panel p-4">
					<p class="text-xs text-ink-3">Contract size</p>
					<p class="mt-1 font-display text-lg font-bold tabular-nums">{rec.quantity.toLocaleString()} {rec.unit}</p>
					<p class="mt-1 text-xs text-ink-2">{market.name} · {market.live.exchange}</p>
				</div>
				<div class="rounded-xl border border-line bg-panel p-4">
					<p class="text-xs text-ink-3">Analyzer snapshot</p>
					<p class="mt-1 font-display text-lg font-bold">{longDate(rec.asof)}</p>
					<p class="mt-1 text-xs text-ink-2">Risk-adjusted recommendation · {best.name}</p>
				</div>
			</section>

			<section class="mt-4 rounded-2xl border border-line bg-panel p-4 shadow-sm sm:p-6">
				<ApprovalQueue proposals={queueProposals} showDemoControls={true} />
			</section>
		{/if}
	</div>
</div>
