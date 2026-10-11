<script lang="ts">
	import { fmtNum } from '#lib/spot.ts';

	type Series = { name: string; color: string; values: number[] };

	let { series = [], bins = 50, height = 380 }: { series?: Series[]; bins?: number; height?: number } = $props();

	let width = $state(800);
	const pad = { top: 16, right: 16, bottom: 28, left: 12 };
	const innerW = $derived(Math.max(10, width - pad.left - pad.right));
	const innerH = $derived(height - pad.top - pad.bottom);

	// Clip at the 0.5th/99.5th percentile so a few crash days don't flatten the shape.
	const extent = $derived.by(() => {
		const all = series.flatMap((s) => s.values).sort((a, b) => a - b);
		if (!all.length) return [-1, 1];
		const lo = all[Math.floor(all.length * 0.005)];
		const hi = all[Math.ceil(all.length * 0.995) - 1];
		const m = Math.max(Math.abs(lo), Math.abs(hi));
		return [-m, m];
	});

	const hist = $derived(
		series.map((s) => {
			const counts = new Array(bins).fill(0);
			const w = (extent[1] - extent[0]) / bins;
			for (const v of s.values) {
				const i = Math.min(bins - 1, Math.max(0, Math.floor((v - extent[0]) / w)));
				counts[i]++;
			}
			return { ...s, dens: counts.map((c) => c / (s.values.length || 1)) };
		})
	);
	const maxD = $derived(Math.max(1e-9, ...hist.flatMap((h) => h.dens)));

	const x = (v: number) => pad.left + ((v - extent[0]) / (extent[1] - extent[0])) * innerW;
	const y = (d: number) => pad.top + innerH - (d / maxD) * innerH;

	const ticks = $derived([-1, -0.5, 0, 0.5, 1].map((f) => f * extent[1]));
	const pathOf = (dens: number[]) => {
		const w = (extent[1] - extent[0]) / bins;
		let d = `M${x(extent[0])},${y(0)}`;
		dens.forEach((v, i) => {
			d += `L${x(extent[0] + i * w)},${y(v)}L${x(extent[0] + (i + 1) * w)},${y(v)}`;
		});
		return d + `L${x(extent[1])},${y(0)}`;
	};
</script>

<div class="w-full" bind:clientWidth={width}>
	<svg {width} {height} class="block max-w-full" role="img" aria-label="Daily return distribution">
		<line x1={x(0)} x2={x(0)} y1={pad.top} y2={pad.top + innerH} class="stroke-ink-3" stroke-dasharray="4 4" />
		<line x1={pad.left} x2={pad.left + innerW} y1={y(0)} y2={y(0)} class="stroke-line" />
		{#each ticks as t (t)}
			<text x={x(t)} y={height - 8} text-anchor="middle" class="fill-ink-3 text-[11px] tabular-nums">
				{fmtNum(t * 100, 1)}%
			</text>
		{/each}
		{#each hist as h (h.name)}
			<path d={pathOf(h.dens)} fill={h.color} fill-opacity="0.18" stroke={h.color} stroke-width="1.5" />
		{/each}
	</svg>
</div>
