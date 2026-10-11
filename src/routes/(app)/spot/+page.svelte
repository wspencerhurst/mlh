<script lang="ts">
	import { onMount } from 'svelte';
	import LineChart from '#lib/components/LineChart.svelte';
	import Histogram from '#lib/components/Histogram.svelte';
	import { market, ensureSpot } from '#lib/market.svelte.ts';
	import {
		TICKERS,
		TICKER_META,
		RANGES,
		rangeStart,
		sliceFrom,
		closes,
		rebased,
		rollingVol,
		drawdown,
		logReturns,
		aggregate,
		stats,
		correlation,
		fmtNum,
		fmtDate,
		type SpotData,
		type Ticker,
		type Range
	} from '#lib/spot.ts';

	const VIEWS = [
		{ id: 'price', label: 'Price', hint: 'Daily close in quote currency' },
		{ id: 'candles', label: 'Candles', hint: 'OHLC, auto-bucketed for long ranges' },
		{ id: 'rebased', label: 'Rebased', hint: 'Indexed to 100 at range start' },
		{ id: 'drawdown', label: 'Drawdown', hint: '% below running peak' },
		{ id: 'vol', label: 'Rolling vol', hint: 'Annualised volatility of daily log returns' },
		{ id: 'dist', label: 'Return dist.', hint: 'Histogram of daily log returns' }
	] as const;
	type View = (typeof VIEWS)[number]['id'];

	let selected = $state<Ticker[]>(['XAUUSD']);
	let range = $state<Range>('1Y');
	let view = $state<View>('price');
	let logScale = $state(false);
	let volWindow = $state(21);

	onMount(ensureSpot);
	const data = $derived(market.spot);
	const error = $derived(market.error);

	const end = $derived(data ? Math.max(...TICKERS.map((k) => data![k].at(-1)?.t ?? 0)) : 0);
	const start = $derived(rangeStart(range, end));
	const windowed = $derived(
		data ? Object.fromEntries(selected.map((k) => [k, sliceFrom(data![k], start)])) as Record<Ticker, SpotData[Ticker]> : null
	);

	const lineSeries = $derived.by(() => {
		if (!data || !windowed) return [];
		return selected.map((k) => {
			const bars = windowed[k];
			const points =
				view === 'rebased'
					? rebased(bars)
					: view === 'drawdown'
						? drawdown(bars)
						: view === 'vol'
							? rollingVol(sliceFrom(data![k], start - volWindow * 2 * 86_400_000), volWindow).filter((p) => p.t >= start)
							: closes(bars);
			return { name: k, color: TICKER_META[k].color, points };
		});
	});

	let chartWidth = $state(800);
	const candleData = $derived(
		windowed && selected[0] ? { name: selected[0], ...aggregate(windowed[selected[0]], Math.floor(chartWidth / 7)) } : null
	);

	const tileStats = $derived(windowed ? selected.map((k) => ({ k, s: stats(windowed[k]) })) : []);
	const corr = $derived(
		data
			? TICKERS.map((a) => TICKERS.map((b) => (a === b ? 1 : correlation(sliceFrom(data![a], start), sliceFrom(data![b], start)))))
			: null
	);

	function toggle(k: Ticker) {
		if (selected.includes(k)) {
			if (selected.length > 1) selected = selected.filter((x) => x !== k);
		} else selected = TICKERS.filter((x) => x === k || selected.includes(x));
	}

	const priceMixed = $derived(view === 'price' && selected.length > 1);
</script>

<svelte:head>
	<title>Spot prices · Goldmine</title>
</svelte:head>

	<section class="py-10 sm:py-14">
	<div class="mx-auto max-w-6xl px-4 sm:px-6">
		<div class="flex flex-wrap items-end justify-between gap-4">
			<div>
				<h1 class="font-display text-3xl font-bold tracking-tight">Spot price explorer</h1>
				<p class="mt-1 text-sm text-ink-2">
					<code class="text-ink-2">data/gold_prices.parquet</code>, read in the browser
					{#if data}· {TICKERS.reduce((n, k) => n + data![k].length, 0).toLocaleString()} rows{/if}
				</p>
			</div>
		</div>

		{#if error}
			<p class="mt-8 rounded-lg border border-bad/40 bg-bad-wash p-4 text-sm">Failed to load parquet: {error}</p>
		{:else if !data}
			<div class="mt-8 h-96 animate-pulse rounded-xl bg-canvas"></div>
		{:else}
			<!-- Controls -->
			<div class="mt-8 flex flex-col gap-4 lg:flex-row lg:flex-wrap lg:items-center lg:justify-between">
				<div class="flex flex-wrap gap-2" role="group" aria-label="Instruments">
					{#each TICKERS as k (k)}
						{@const on = selected.includes(k)}
						<button
							class="flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-semibold transition {on
								? 'border-line bg-canvas'
								: 'border-line text-ink-3 hover:text-ink-2'}"
							aria-pressed={on}
							onclick={() => toggle(k)}
						>
							<span class="h-2.5 w-2.5 rounded-full" style:background={on ? TICKER_META[k].color : 'transparent'} style:border="2px solid {TICKER_META[k].color}"></span>
							{k}
						</button>
					{/each}
				</div>
				<div class="flex flex-wrap gap-1 rounded-lg bg-canvas p-1" role="group" aria-label="Range">
					{#each RANGES as r (r)}
						<button
							class="rounded-md px-2.5 py-1 text-xs font-semibold transition {range === r
								? 'bg-mlh-yellow text-mlh-navy'
								: 'text-ink-2 hover:text-ink'}"
							onclick={() => (range = r)}>{r}</button
						>
					{/each}
				</div>
			</div>

			<div class="mt-3 flex flex-wrap items-center gap-2">
				{#each VIEWS as v (v.id)}
					<button
						title={v.hint}
						class="rounded-full border px-3 py-1 text-xs font-semibold transition {view === v.id
							? 'border-mlh-blue bg-mlh-blue text-white'
							: 'border-line text-ink-2 hover:text-ink'}"
						onclick={() => (view = v.id)}>{v.label}</button
					>
				{/each}
				{#if view === 'price' || view === 'candles'}
					<label class="ml-auto flex items-center gap-2 text-xs text-ink-2">
						<input type="checkbox" bind:checked={logScale} class="accent-accent" /> Log scale
					</label>
				{:else if view === 'vol'}
					<label class="ml-auto flex items-center gap-2 text-xs text-ink-2">
						Window
						<select bind:value={volWindow} class="rounded border border-line bg-panel px-2 py-1">
							<option value={10}>10d</option>
							<option value={21}>21d</option>
							<option value={63}>63d</option>
							<option value={126}>126d</option>
						</select>
					</label>
				{/if}
			</div>

			<!-- Chart -->
			<div class="mt-4 rounded-xl border border-line bg-panel p-3 sm:p-4" bind:clientWidth={chartWidth}>
				<div class="mb-2 flex flex-wrap items-center justify-between gap-2 px-1 text-xs text-ink-3">
					<span>{VIEWS.find((v) => v.id === view)?.hint}</span>
					{#if view === 'candles' && candleData}
						<span>{candleData.name} · {candleData.period} candles{selected.length > 1 ? ' (first selected instrument)' : ''}</span>
					{:else if priceMixed}
						<span>Mixed currencies, try Rebased to compare</span>
					{/if}
				</div>
				{#if view === 'candles' && candleData}
					<LineChart candles={candleData} log={logScale} />
				{:else if view === 'dist'}
					<Histogram
						series={selected.map((k) => ({ name: k, color: TICKER_META[k].color, values: logReturns(windowed![k]).map((p) => p.y) }))}
					/>
				{:else}
					<LineChart
						series={lineSeries}
						log={view === 'price' && logScale}
						unit={view === 'drawdown' || view === 'vol' ? '%' : ''}
						baseline={view === 'rebased' ? 100 : view === 'drawdown' ? 0 : null}
					/>
				{/if}
			</div>

			<!-- Stats -->
			<div class="mt-6 grid gap-4 md:grid-cols-3">
				{#each tileStats as { k, s } (k)}
					{#if s}
						<div class="rounded-xl border border-line bg-panel p-4">
							<div class="flex items-center justify-between">
								<span class="flex items-center gap-2 font-display font-bold">
									<span class="h-2.5 w-2.5 rounded-full" style:background={TICKER_META[k].color}></span>{k}
								</span>
								<span class="text-xs text-ink-3">{fmtDate(s.lastDate)}</span>
							</div>
							<div class="mt-2 flex items-baseline gap-2">
								<span class="text-2xl font-bold tabular-nums">{fmtNum(s.last)}</span>
								<span class="text-xs text-ink-3">{TICKER_META[k].ccy}/oz</span>
								<span class="ml-auto text-sm font-semibold tabular-nums {s.changePct >= 0 ? 'text-good' : 'text-bad'}">
									{s.changePct >= 0 ? '+' : ''}{fmtNum(s.changePct)}%
								</span>
							</div>
							<dl class="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs tabular-nums">
								<dt class="text-ink-3">Range high</dt><dd class="text-right">{fmtNum(s.high)}</dd>
								<dt class="text-ink-3">Range low</dt><dd class="text-right">{fmtNum(s.low)}</dd>
								<dt class="text-ink-3">Ann. volatility</dt><dd class="text-right">{fmtNum(s.annVolPct, 1)}%</dd>
								<dt class="text-ink-3">Max drawdown</dt><dd class="text-right">{fmtNum(s.maxDrawdownPct, 1)}%</dd>
								<dt class="text-ink-3">Observations</dt><dd class="text-right">{s.n.toLocaleString()}</dd>
							</dl>
						</div>
					{/if}
				{/each}
				{#if corr}
					<div class="rounded-xl border border-line bg-panel p-4 md:col-start-3">
						<div class="font-display font-bold">Return correlation</div>
						<p class="text-xs text-ink-3">Daily log returns, {range} window. Feeds the QP covariance.</p>
						<table class="mt-3 w-full text-xs tabular-nums">
							<thead>
								<tr><th></th>{#each TICKERS as k (k)}<th class="pb-1 text-right font-semibold text-ink-2">{k.slice(3)}</th>{/each}</tr>
							</thead>
							<tbody>
								{#each TICKERS as a, i (a)}
									<tr>
										<th class="py-1 text-left font-semibold text-ink-2">{a.slice(3)}</th>
										{#each corr[i] as v, j (j)}
											<td class="py-1 text-right" style:background="rgba(29,83,159,{isFinite(v) ? Math.abs(v) * 0.6 : 0})">
												{isFinite(v) ? fmtNum(v) : '–'}
											</td>
										{/each}
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>
		{/if}
	</div>
</section>
