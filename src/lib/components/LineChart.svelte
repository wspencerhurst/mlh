<script lang="ts">
	import { fmtDate, fmtNum, type Bar, type Point } from '#lib/spot.ts';

	type Series = { name: string; color: string; points: Point[] };

	let {
		series = [],
		candles = null,
		log = false,
		unit = '',
		dp = 2,
		height = 380,
		baseline = null,
		maxGapDays = 10
	}: {
		series?: Series[];
		candles?: { name: string; bars: Bar[] } | null;
		log?: boolean;
		unit?: string;
		dp?: number;
		height?: number;
		baseline?: number | null;
		/** Hover drops a series whose nearest point is further away than this (raise for monthly data). */
		maxGapDays?: number;
	} = $props();

	let width = $state(800);
	let hoverX = $state<number | null>(null);

	const pad = { top: 16, right: 64, bottom: 28, left: 12 };
	const innerW = $derived(Math.max(10, width - pad.left - pad.right));
	const innerH = $derived(height - pad.top - pad.bottom);

	const allT = $derived(
		candles ? candles.bars.map((b) => b.t) : series.flatMap((s) => [s.points[0]?.t, s.points.at(-1)?.t])
	);
	const tMin = $derived(Math.min(...allT.filter((t) => t !== undefined)));
	const tMax = $derived(Math.max(...allT.filter((t) => t !== undefined)));

	const yExtent = $derived.by(() => {
		let lo = Infinity;
		let hi = -Infinity;
		if (candles) {
			for (const b of candles.bars) {
				lo = Math.min(lo, b.l);
				hi = Math.max(hi, b.h);
			}
		} else {
			for (const s of series)
				for (const p of s.points) {
					lo = Math.min(lo, p.y);
					hi = Math.max(hi, p.y);
				}
		}
		if (baseline !== null) {
			lo = Math.min(lo, baseline);
			hi = Math.max(hi, baseline);
		}
		if (!isFinite(lo)) return [0, 1];
		if (lo === hi) return [lo - 1, hi + 1];
		const m = (hi - lo) * 0.05;
		return log && lo > 0 ? [lo / (1 + m / hi), hi * (1 + m / hi)] : [lo - m, hi + m];
	});

	const useLog = $derived(log && yExtent[0] > 0);
	const tf = (v: number) => (useLog ? Math.log(v) : v);

	const x = (t: number) => pad.left + ((t - tMin) / (tMax - tMin || 1)) * innerW;
	const y = (v: number) =>
		pad.top + innerH - ((tf(v) - tf(yExtent[0])) / (tf(yExtent[1]) - tf(yExtent[0]))) * innerH;

	function niceTicks(lo: number, hi: number, n = 5) {
		const step0 = (hi - lo) / n;
		const mag = 10 ** Math.floor(Math.log10(step0));
		const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) ?? step0;
		const out: number[] = [];
		for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(+v.toPrecision(12));
		return out;
	}

	const yTicks = $derived(niceTicks(yExtent[0], yExtent[1]));

	const xTicks = $derived.by(() => {
		const span = tMax - tMin;
		const n = Math.max(2, Math.floor(innerW / 110));
		return Array.from({ length: n }, (_, i) => tMin + (span * (i + 0.5)) / n);
	});

	const xFmt = (t: number) => {
		const days = (tMax - tMin) / 86_400_000;
		const d = new Date(t);
		const opts: Intl.DateTimeFormatOptions =
			days > 3 * 365 ? { year: 'numeric' } : days > 120 ? { month: 'short', year: '2-digit' } : { day: 'numeric', month: 'short' };
		return d.toLocaleDateString('en-GB', { ...opts, timeZone: 'UTC' });
	};

	const paths = $derived(
		series.map((s) => ({
			...s,
			d: s.points.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.y).toFixed(1)}`).join('')
		}))
	);

	const candleW = $derived(candles ? Math.max(1, Math.min(12, (innerW / candles.bars.length) * 0.7)) : 0);

	function nearest<T extends { t: number }>(arr: T[], t: number): T | undefined {
		let lo = 0;
		let hi = arr.length - 1;
		if (hi < 0) return undefined;
		while (lo < hi) {
			const mid = (lo + hi) >> 1;
			if (arr[mid].t < t) lo = mid + 1;
			else hi = mid;
		}
		if (lo > 0 && Math.abs(arr[lo - 1].t - t) < Math.abs(arr[lo].t - t)) lo--;
		return arr[lo];
	}

	const hoverT = $derived(hoverX === null ? null : tMin + ((hoverX - pad.left) / innerW) * (tMax - tMin));
	const hover = $derived.by(() => {
		if (hoverT === null) return null;
		if (candles) {
			const b = nearest(candles.bars, hoverT);
			return b ? { t: b.t, bar: b, rows: [] as { name: string; color: string; y: number }[] } : null;
		}
		const rows = series
			.map((s) => ({ name: s.name, color: s.color, p: nearest(s.points, hoverT) }))
			.filter((r) => r.p && Math.abs(r.p.t - hoverT) <= maxGapDays * 86_400_000)
			.map((r) => ({ name: r.name, color: r.color, y: r.p!.y, t: r.p!.t }));
		return rows.length ? { t: rows[0].t, bar: null, rows } : null;
	});

	function onMove(e: PointerEvent) {
		const rect = (e.currentTarget as SVGElement).getBoundingClientRect();
		const px = e.clientX - rect.left;
		hoverX = px >= pad.left && px <= pad.left + innerW ? px : null;
	}
</script>

<div class="relative w-full" bind:clientWidth={width}>
	<svg
		{width}
		{height}
		class="block max-w-full touch-none select-none"
		role="img"
		aria-label="Price chart"
		onpointermove={onMove}
		onpointerleave={() => (hoverX = null)}
	>
		{#each yTicks as v (v)}
			<line x1={pad.left} x2={pad.left + innerW} y1={y(v)} y2={y(v)} class="stroke-line" />
			<text x={pad.left + innerW + 8} y={y(v)} dy="0.32em" class="fill-ink-3 text-[11px] tabular-nums">
				{v === 0 ? 0 : fmtNum(v, Math.abs(v) < 10 ? 2 : 0)}{unit}
			</text>
		{/each}
		{#if baseline !== null}
			<line
				x1={pad.left}
				x2={pad.left + innerW}
				y1={y(baseline)}
				y2={y(baseline)}
				class="stroke-ink-3"
				stroke-dasharray="4 4"
			/>
		{/if}
		{#each xTicks as t (t)}
			<text x={x(t)} y={height - 8} text-anchor="middle" class="fill-ink-3 text-[11px]">{xFmt(t)}</text>
		{/each}

		{#if candles}
			{#each candles.bars as b (b.t)}
				{@const up = b.c >= b.o}
				<line x1={x(b.t)} x2={x(b.t)} y1={y(b.h)} y2={y(b.l)} class={up ? 'stroke-good' : 'stroke-mlh-red'} />
				<rect
					x={x(b.t) - candleW / 2}
					y={Math.min(y(b.o), y(b.c))}
					width={candleW}
					height={Math.max(1, Math.abs(y(b.o) - y(b.c)))}
					class={up ? 'fill-good' : 'fill-mlh-red'}
				/>
			{/each}
		{:else}
			{#each paths as p (p.name)}
				<path d={p.d} fill="none" stroke={p.color} stroke-width="1.75" stroke-linejoin="round" />
			{/each}
		{/if}

		{#if hover}
			<line
				x1={x(hover.t)}
				x2={x(hover.t)}
				y1={pad.top}
				y2={pad.top + innerH}
				class="stroke-ink-3"
				stroke-dasharray="3 3"
			/>
			{#each hover.rows as r (r.name)}
				<circle cx={x(hover.t)} cy={y(r.y)} r="4" fill={r.color} class="stroke-panel" stroke-width="2" />
			{/each}
		{/if}
	</svg>

	{#if hover}
		{@const left = x(hover.t)}
		<div
			class="pointer-events-none absolute top-3 z-10 min-w-40 rounded-lg border border-line bg-panel/95 px-3 py-2 text-xs shadow-lg"
			style:left="{left > width / 2 ? left - 176 : left + 16}px"
		>
			<div class="mb-1 font-semibold text-ink-2">{fmtDate(hover.t)}</div>
			{#if hover.bar}
				{#each [['Open', hover.bar.o], ['High', hover.bar.h], ['Low', hover.bar.l], ['Close', hover.bar.c]] as const as [k, v] (k)}
					<div class="flex justify-between gap-4 tabular-nums">
						<span class="text-ink-3">{k}</span><span>{fmtNum(v, dp)}</span>
					</div>
				{/each}
			{:else}
				{#each hover.rows as r (r.name)}
					<div class="flex items-center justify-between gap-4 tabular-nums">
						<span class="flex items-center gap-1.5 text-ink-2">
							<span class="h-2 w-2 rounded-full" style:background={r.color}></span>{r.name}
						</span>
						<span class="font-semibold">{fmtNum(r.y, dp)}{unit}</span>
					</div>
				{/each}
			{/if}
		</div>
	{/if}
</div>
