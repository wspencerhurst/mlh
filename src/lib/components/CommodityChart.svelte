<script lang="ts">
	import { onMount } from 'svelte';
	import LineChart from '#lib/components/LineChart.svelte';
	import { RANGES, rangeStart, fmtNum, fmtDate, type Range } from '#lib/spot.ts';
	import {
		GROUPS,
		COMMODITIES,
		SLOT_COLORS,
		MAX_SELECTED,
		loadCommodities,
		sliceFrom,
		rebase,
		type CommodityData
	} from '#lib/commodities.ts';

	let data = $state<CommodityData | null>(null);
	let error = $state<string | null>(null);
	// Fixed slots so a series keeps its colour while others are added or removed.
	let slots = $state<(string | null)[]>(['WTI', 'NATURAL_GAS', 'COPPER']);
	let range = $state<Range>('5Y');
	let mode = $state<'rebased' | 'price'>('rebased');

	onMount(() => {
		loadCommodities()
			.then((d) => (data = d))
			.catch((e) => (error = String(e)));
	});

	const selected = $derived(
		slots.flatMap((code, i) => (code && data?.[code] ? [{ code, color: SLOT_COLORS[i], ...COMMODITIES[code] }] : []))
	);
	const full = $derived(selected.length >= MAX_SELECTED);

	function toggle(code: string) {
		const i = slots.indexOf(code);
		if (i >= 0) {
			if (selected.length > 1) slots[i] = null;
			return;
		}
		const free = slots.indexOf(null);
		if (free >= 0) slots[free] = code;
	}

	// One y-axis only: prices are comparable only when every selected series shares a unit.
	const units = $derived([...new Set(selected.map((s) => s.unit))]);
	const priceOk = $derived(units.length === 1);
	const effMode = $derived(priceOk ? mode : 'rebased');

	const end = $derived(data ? Math.max(...Object.values(data).map((s) => s.points.at(-1)?.t ?? 0)) : 0);
	const start = $derived(rangeStart(range, end));

	const windowed = $derived(
		data ? selected.map((s) => ({ ...s, interval: data![s.code].interval, points: sliceFrom(data![s.code].points, start) })) : []
	);

	// Rebase every series from the same date, else series that start later are indexed to a different base.
	const commonStart = $derived(Math.max(...windowed.map((s) => s.points[0]?.t ?? -Infinity)));
	const series = $derived(
		windowed.map((s) => ({
			name: s.label,
			color: s.color,
			points: effMode === 'rebased' ? rebase(sliceFrom(s.points, commonStart)) : s.points
		}))
	);
	const hasMonthly = $derived(windowed.some((s) => s.interval !== 'daily'));

	const tiles = $derived(
		windowed.map((s) => {
			const first = s.points[0];
			const last = s.points.at(-1);
			return {
				...s,
				last,
				changePct: first && last && first.y > 0 ? (last.y / first.y - 1) * 100 : null,
				high: s.points.length ? Math.max(...s.points.map((p) => p.y)) : null,
				low: s.points.length ? Math.min(...s.points.map((p) => p.y)) : null
			};
		})
	);
</script>

{#if error}
	<p class="mt-8 rounded-lg border border-bad/40 bg-bad-wash p-4 text-sm">Failed to load parquet: {error}</p>
{:else if !data}
	<div class="mt-8 h-96 animate-pulse rounded-xl bg-canvas"></div>
{:else}
	<!-- Commodity picker -->
	<div class="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
		{#each GROUPS as g (g.id)}
			<div>
				<div class="mb-1.5 text-xs font-semibold tracking-wide text-ink-3 uppercase">{g.label}</div>
				<div class="flex flex-wrap gap-1.5">
					{#each Object.entries(COMMODITIES).filter(([, m]) => m.group === g.id) as [code, m] (code)}
						{@const slot = slots.indexOf(code)}
						{@const on = slot >= 0}
						{@const disabled = !on && full}
						<button
							class="flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-semibold transition {on
								? 'border-line bg-canvas'
								: disabled
									? 'cursor-not-allowed border-line text-ink-3'
									: 'border-line text-ink-2 hover:text-ink'}"
							aria-pressed={on}
							{disabled}
							title={disabled ? `Up to ${MAX_SELECTED} at once. Deselect one first.` : `${m.label} (${m.unit})`}
							onclick={() => toggle(code)}
						>
							<span
								class="h-2.5 w-2.5 rounded-full border-2"
								style:border-color={on ? SLOT_COLORS[slot] : 'rgb(255 255 255 / 0.25)'}
								style:background={on ? SLOT_COLORS[slot] : 'transparent'}
							></span>
							{m.label}
						</button>
					{/each}
				</div>
			</div>
		{/each}
	</div>

	<div class="mt-5 flex flex-wrap items-center justify-between gap-3">
		<div class="flex items-center gap-1 rounded-lg bg-canvas p-1" role="group" aria-label="Scale">
			{#each [['rebased', 'Rebased'], ['price', 'Price']] as const as [id, label] (id)}
				<button
					class="rounded-md px-3 py-1 text-xs font-semibold transition {effMode === id
						? 'bg-mlh-blue text-white'
						: priceOk || id === 'rebased'
							? 'text-ink-2 hover:text-ink'
							: 'cursor-not-allowed text-ink-3'}"
					disabled={id === 'price' && !priceOk}
					title={id === 'price' && !priceOk ? 'Selected commodities have different units. Pick ones with the same unit.' : ''}
					onclick={() => (mode = id)}>{label}</button
				>
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

	<!-- Chart -->
	<div class="mt-4 rounded-xl border border-line bg-panel p-3 sm:p-4">
		<div class="mb-2 flex flex-wrap items-center justify-between gap-2 px-1 text-xs text-ink-3">
			<span>
				{effMode === 'rebased'
					? `Indexed to 100 on ${isFinite(commonStart) ? fmtDate(commonStart) : 'range start'}`
					: `Price in ${units[0]}`}
			</span>
			<span class="text-ink-3">
				{selected.length} of {MAX_SELECTED} selected{full ? ' · deselect one to add another' : ''}
			</span>
		</div>
		<LineChart {series} baseline={effMode === 'rebased' ? 100 : null} maxGapDays={hasMonthly ? 31 : 10} />
	</div>

	<!-- Legend and stats -->
	<div class="mt-6 grid gap-4 md:grid-cols-3">
		{#each tiles as s (s.code)}
			<div class="rounded-xl border border-line bg-panel p-4">
				<div class="flex items-center justify-between gap-2">
					<span class="flex items-center gap-2 font-display font-bold">
						<span class="h-2.5 w-2.5 rounded-full" style:background={s.color}></span>{s.label}
					</span>
					<span class="rounded-full bg-canvas px-2 py-0.5 text-[10px] font-semibold text-ink-2 uppercase">{s.interval}</span>
				</div>
				{#if s.last}
					<div class="mt-2 flex items-baseline gap-2">
						<span class="text-2xl font-bold tabular-nums">{fmtNum(s.last.y)}</span>
						<span class="text-xs text-ink-3">{s.unit}</span>
						{#if s.changePct !== null}
							<span class="ml-auto text-sm font-semibold tabular-nums {s.changePct >= 0 ? 'text-good' : 'text-bad'}">
								{s.changePct >= 0 ? '+' : ''}{fmtNum(s.changePct)}%
							</span>
						{/if}
					</div>
					<dl class="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs tabular-nums">
						<dt class="text-ink-3">Latest</dt><dd class="text-right">{fmtDate(s.last.t)}</dd>
						<dt class="text-ink-3">Range high</dt><dd class="text-right">{fmtNum(s.high!)}</dd>
						<dt class="text-ink-3">Range low</dt><dd class="text-right">{fmtNum(s.low!)}</dd>
						<dt class="text-ink-3">Observations</dt><dd class="text-right">{s.points.length.toLocaleString()}</dd>
					</dl>
				{:else}
					<p class="mt-2 text-xs text-ink-3">No data in this range.</p>
				{/if}
			</div>
		{/each}
	</div>
	{#if hasMonthly}
		<p class="mt-3 text-xs text-ink-3">Monthly series are published with a lag of about three months.</p>
	{/if}
{/if}
