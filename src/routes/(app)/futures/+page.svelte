<script lang="ts">
	import { onMount } from 'svelte';
	import LineChart from '#lib/components/LineChart.svelte';
	import { futures } from '#lib/futures.ts';
	import { TICKER_META, fmtNum, fmtDate } from '#lib/spot.ts';
	import { market, ensureSpot, curveOf, latestUsd } from '#lib/market.svelte.ts';

	onMount(ensureSpot);
	const spotUsd = $derived(latestUsd(market.spot));
	const curve = $derived(curveOf(spotUsd));
</script>

<svelte:head>
	<title>Futures curve · Goldmine</title>
</svelte:head>

<section class="py-10 sm:py-14">
	<div class="mx-auto max-w-6xl px-4 sm:px-6">
		<h1 class="font-display text-3xl font-bold tracking-tight">COMEX gold futures curve</h1>
		{#if futures}
			<p class="mt-1 text-sm text-ink-2">
				{futures.underlying} · retrieved {new Date(futures.retrieved_at).toLocaleString('en-GB')} via {futures.method}
			</p>
			{#if curve.length > 1 && spotUsd}
				<div class="mt-6 rounded-xl border border-line bg-panel p-3 sm:p-4">
					<div class="mb-2 px-1 text-xs text-ink-3">Futures price by expiry. Dashed line: XAUUSD spot {fmtNum(spotUsd.c)}</div>
					<LineChart
						series={[{ name: 'GC', color: TICKER_META.XAUUSD.color, points: curve.map((r) => ({ t: r.exp.t, y: r.f })) }]}
						baseline={spotUsd.c}
						height={300}
					/>
				</div>
			{/if}
			<div class="mt-6 overflow-x-auto rounded-xl border border-line">
				<table class="w-full min-w-[640px] text-sm tabular-nums">
					<thead class="bg-canvas text-xs text-ink-2">
						<tr>
							<th class="px-4 py-2 text-left">Contract</th>
							<th class="px-4 py-2 text-left">Expiry</th>
							<th class="px-4 py-2 text-right">Price</th>
							<th class="px-4 py-2 text-right">Chg</th>
							<th class="px-4 py-2 text-right">Basis vs spot</th>
							<th class="px-4 py-2 text-right">Implied carry</th>
							<th class="px-4 py-2 text-right">Open int.</th>
						</tr>
					</thead>
					<tbody>
						{#each curve as r (r.c.symbol)}
							<tr class="border-t border-line">
								<td class="px-4 py-2 font-semibold">{r.c.symbol}</td>
								<td class="px-4 py-2 text-ink-2">{fmtDate(r.exp.t)}{r.exp.approx ? '*' : ''}</td>
								<td class="px-4 py-2 text-right">{fmtNum(r.f, 1)}</td>
								<td class="px-4 py-2 text-right {(r.c.change ?? 0) >= 0 ? 'text-good' : 'text-bad'}">
									{r.c.change === null ? '–' : fmtNum(r.c.change, 1)}
								</td>
								<td class="px-4 py-2 text-right">{fmtNum(r.basis, 1)}</td>
								<td class="px-4 py-2 text-right">{isFinite(r.carry) ? fmtNum(r.carry * 100) + '%' : '–'}</td>
								<td class="px-4 py-2 text-right text-ink-2">{r.c.open_interest?.toLocaleString() ?? '–'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<p class="mt-2 text-xs text-ink-3">* Expiry estimated as the third-last business day of the contract month. Source: {futures.source}</p>
		{:else}
			<div class="mt-6 rounded-xl border border-dashed border-line p-8 text-center">
				<p class="font-display text-lg font-bold">Waiting for Nimble</p>
				<p class="mx-auto mt-2 max-w-lg text-sm text-ink-2">
					The futures curve appears here once <code class="text-ink-2">data/gold_futures.json</code> has been written
					by the Nimble retrieval step.
				</p>
			</div>
		{/if}
	</div>
</section>
