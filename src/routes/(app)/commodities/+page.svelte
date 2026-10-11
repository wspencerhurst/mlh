<script lang="ts">
	import CommodityChart from '#lib/components/CommodityChart.svelte';
</script>

<svelte:head>
	<title>Commodities · Goldmine</title>
</svelte:head>

<section class="py-10 sm:py-14">
	<div class="mx-auto max-w-6xl px-4 sm:px-6">
		<h1 class="font-display text-3xl font-bold tracking-tight">Commodities</h1>
		<p class="mt-1 max-w-2xl text-sm text-ink-2">
			Oil, fuels, gas, metals and wheat from <code class="text-ink-2">data/commodities.parquet</code>. Pick up to three to
			compare; Price is available when they share a unit.
		</p>
		<CommodityChart />
	</div>
</section>
