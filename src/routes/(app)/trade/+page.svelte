<script lang="ts">
	import { onMount } from 'svelte';
	import TradeDesk from '#lib/components/TradeDesk.svelte';
	import { market, ensureSpot, curveOf, latestUsd } from '#lib/market.svelte.ts';

	onMount(ensureSpot);
	const spotUsd = $derived(latestUsd(market.spot));
	const instruments = $derived([
		...(spotUsd ? [{ symbol: 'XAU-USD', label: 'XAU-USD spot', price: spotUsd.c, unit: 'oz' }] : []),
		...curveOf(spotUsd).map((r) => ({ symbol: r.c.symbol, label: `${r.c.symbol} future`, price: r.f, unit: 'contracts' }))
	]);
</script>

<svelte:head>
	<title>Trade desk · Goldmine</title>
</svelte:head>

<section class="py-10 sm:py-14">
	<div class="mx-auto max-w-6xl px-4 sm:px-6">
		<h1 class="font-display text-3xl font-bold tracking-tight">Trade desk</h1>
		<p class="mt-1 max-w-2xl text-sm text-ink-2">
			Execute hedge trades through a mock of Checker's RFQ and order API. Pick a scenario to see a trade settle or fail;
			failures raise a Sentry alert with the full trade context.
		</p>
		<div class="mt-6">
			{#if instruments.length}
				<TradeDesk {instruments} />
			{:else}
				<div class="h-64 animate-pulse rounded-xl bg-canvas"></div>
			{/if}
		</div>
	</div>
</section>
