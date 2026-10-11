<script lang="ts">
	import { fmt, OPTION_COLORS, type Live } from '#lib/desk.ts';

	let { live, height = 280 }: { live: Live; height?: number } = $props();

	let width = $state(640);
	let hover = $state<number | null>(null);
	const pad = { top: 26, right: 16, bottom: 30, left: 60 };
	const innerW = $derived(Math.max(10, width - pad.left - pad.right));
	const innerH = $derived(height - pad.top - pad.bottom);

	const mIdx = (ym: number) => Math.floor(ym / 100) * 12 + (ym % 100) - 1;
	const qps = $derived(live.options.map((o, i) => ({ ...o, color: OPTION_COLORS[i] })));
	const lastQp = $derived(Math.max(...qps.map((o) => mIdx(o.qp_ym))));
	// show the curve out to a few months past the last QP month
	const pts = $derived(live.curve.filter((c) => mIdx(c.ym) <= lastQp + 4));
	const m0 = $derived(Math.min(mIdx(pts[0].ym), ...qps.map((o) => mIdx(o.qp_ym))) - 0.5);
	const m1 = $derived(Math.max(mIdx(pts.at(-1)!.ym), lastQp) + 0.5);
	const lo = $derived(Math.min(...pts.map((p) => p.settle)));
	const hi = $derived(Math.max(...pts.map((p) => p.settle)));
	const span = $derived(hi - lo || hi * 0.01);
	const yLo = $derived(lo - span * 0.15);
	const yHi = $derived(hi + span * 0.15);
	const x = (m: number) => pad.left + ((m - m0) / (m1 - m0)) * innerW;
	const y = (v: number) => pad.top + innerH - ((v - yLo) / (yHi - yLo)) * innerH;
	const colW = $derived(innerW / (m1 - m0));

	const ticks = $derived.by(() => {
		const step0 = (yHi - yLo) / 4;
		const mag = 10 ** Math.floor(Math.log10(step0));
		const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => s >= step0) ?? step0;
		const out: number[] = [];
		for (let v = Math.ceil(yLo / step) * step; v <= yHi; v += step) out.push(+v.toPrecision(10));
		return out;
	});
	const maxOi = $derived(Math.max(1, ...pts.map((p) => p.oi)));
	const line = $derived(pts.map((p, i) => `${i ? 'L' : 'M'}${x(mIdx(p.ym)).toFixed(1)},${y(p.settle).toFixed(1)}`).join(''));
	const hp = $derived(hover === null ? null : pts[hover]);
</script>

<div class="relative w-full" bind:clientWidth={width}>
	<svg {width} {height} class="block max-w-full" role="img" aria-label="Futures curve with quotation period months">
		{#each qps as o (o.name)}
			<rect x={x(mIdx(o.qp_ym)) - colW / 2} y={pad.top} width={colW} height={innerH} fill={o.color} fill-opacity={o.name === live.best ? 0.16 : 0.07} />
			<text x={x(mIdx(o.qp_ym))} y={pad.top - 9} text-anchor="middle" class="text-[11px] {o.name === live.best ? 'fill-ink font-semibold' : 'fill-ink-3'}">{o.name}</text>
		{/each}
		{#each ticks as v (v)}
			<line x1={pad.left} x2={pad.left + innerW} y1={y(v)} y2={y(v)} class="stroke-line" />
			<text x={pad.left - 8} y={y(v)} dy="0.32em" text-anchor="end" class="fill-ink-3 text-[11px]">{fmt(v, v < 200 ? 2 : 0)}</text>
		{/each}
		<path d={line} fill="none" stroke="var(--color-ink-2)" stroke-width="1.75" />
		{#each pts as p, i (p.ym)}
			<circle cx={x(mIdx(p.ym))} cy={y(p.settle)} r={3 + 3 * Math.sqrt(p.oi / maxOi)} fill="var(--color-panel)" stroke="var(--color-ink-2)" stroke-width="1.75" />
			<rect
				x={x(mIdx(p.ym)) - colW / 2}
				y={pad.top}
				width={colW}
				height={innerH}
				fill="transparent"
				role="presentation"
				onpointerenter={() => (hover = i)}
				onpointerleave={() => (hover = null)}
			/>
			{#if pts.length <= 14 || i % 2 === 0}
				<text x={x(mIdx(p.ym))} y={height - 10} text-anchor="middle" class="fill-ink-3 text-[11px]">{p.label}</text>
			{/if}
		{/each}
	</svg>
	{#if hp}
		{@const left = x(mIdx(hp.ym))}
		<div
			class="pointer-events-none absolute top-8 z-10 rounded-lg border border-line bg-panel px-3 py-2 text-xs shadow-lg"
			style:left="{left > width / 2 ? left - 170 : left + 14}px"
		>
			<div class="font-semibold">{live.exchange} {hp.label}</div>
			<div class="text-ink-2">Settle {fmt(hp.settle, hp.settle < 200 ? 2 : 1)}</div>
			<div class="text-ink-3">Open interest {hp.oi.toLocaleString()}</div>
		</div>
	{/if}
</div>
