<script lang="ts">
	import { sgn, usd, usdShort, OPTION_COLORS, type Live } from '#lib/desk.ts';

	let { live }: { live: Live } = $props();

	let width = $state(800);
	const rowH = 54;
	const pad = { top: 8, right: 24, bottom: 30, left: 132 };
	const height = $derived(pad.top + pad.bottom + rowH * live.options.length);
	const innerW = $derived(Math.max(10, width - pad.left - pad.right));

	const rows = $derived(
		live.options.map((o, i) => {
			const u = live.outcomes[o.name];
			const flat = !(u && u.std > 1e-6);
			return { o, u, flat, color: OPTION_COLORS[i] };
		})
	);
	const lo = $derived(Math.min(0, ...rows.map((r) => (r.flat ? r.o.hedged_value : r.u['5']))));
	const hi = $derived(Math.max(0, ...rows.map((r) => (r.flat ? r.o.hedged_value : r.u['95']))));
	const x = (v: number) => pad.left + ((v - lo) / (hi - lo || 1)) * innerW;
	const ticks = $derived.by(() => {
		const step0 = (hi - lo) / 6;
		const mag = 10 ** Math.floor(Math.log10(step0 || 1));
		const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => s >= step0) ?? step0;
		const out: number[] = [];
		for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(+v.toPrecision(10));
		return out;
	});
	const best = $derived(rows.find((r) => r.o.name === live.best)!);
	const q = $derived(live.quantity);
</script>

<div class="flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-2">
	<span class="flex items-center gap-1.5"><svg width="12" height="12"><path d="M6 1 L11 6 L6 11 L1 6 Z" fill="var(--color-ink)" /></svg>Hedged: the value you lock in today</span>
	<span class="flex items-center gap-1.5"><span class="h-2.5 w-5 rounded-sm bg-ink-3/30"></span>Unhedged: middle half of outcomes</span>
	<span class="flex items-center gap-1.5"><span class="h-0.5 w-5 bg-ink-3"></span>Unhedged: 9 in 10 outcomes</span>
	<span class="flex items-center gap-1.5"><span class="h-1 w-5 rounded bg-ink-3"></span>Hedged: 9 in 10 outcomes (futures vs physical gap)</span>
</div>

<div class="mt-2 w-full" bind:clientWidth={width}>
	<svg {width} {height} class="block max-w-full" role="img" aria-label="Deal value per option, hedged versus unhedged">
		{#each ticks as t (t)}
			<line x1={x(t)} x2={x(t)} y1={pad.top} y2={height - pad.bottom} class={t === 0 ? 'stroke-ink-3' : 'stroke-line'} stroke-dasharray={t === 0 ? '3 3' : ''} />
			<text x={x(t)} y={height - 10} text-anchor="middle" class="fill-ink-3 text-[11px]">{t === 0 ? '0' : sgn(t, Math.abs(t) < 10 ? 1 : 0)}</text>
		{/each}
		{#each rows as r, i (r.o.name)}
			{@const cy = pad.top + rowH * i + rowH / 2}
			<text x={0} y={cy - 4} class="fill-ink text-[13px] font-semibold">{r.o.name}{r.o.name === live.best ? ' (best)' : ''}</text>
			<text x={0} y={cy + 12} class="fill-ink-3 text-[11px]">{r.o.qp_month} average</text>
			{#if !r.flat}
				<line x1={x(r.u['5'])} x2={x(r.u['95'])} y1={cy} y2={cy} stroke={r.color} stroke-opacity="0.55" stroke-width="2" />
				<rect x={x(r.u['25'])} y={cy - 9} width={Math.max(1, x(r.u['75']) - x(r.u['25']))} height="18" rx="3" fill={r.color} fill-opacity="0.16" stroke={r.color} stroke-opacity="0.5" />
			{/if}
			{#if r.u?.h5 != null && r.u.h95 != null && r.u.h95 - r.u.h5 > 0.01}
				<line x1={x(r.u.h5)} x2={x(r.u.h95)} y1={cy + 13} y2={cy + 13} stroke={r.color} stroke-width="3" stroke-linecap="round" />
			{/if}
			<path
				d="M{x(r.o.hedged_value)} {cy - 9} L{x(r.o.hedged_value) + 9} {cy} L{x(r.o.hedged_value)} {cy + 9} L{x(r.o.hedged_value) - 9} {cy} Z"
				fill={r.color}
				stroke="var(--color-panel)"
				stroke-width="2"
			/>
		{/each}
	</svg>
</div>

<div class="mt-3 grid gap-3 text-sm sm:grid-cols-2">
	<div class="rounded-lg border border-line px-3 py-2">
		<div class="text-xs text-ink-3">{best.o.name}, hedged</div>
		<div class="font-semibold">{sgn(best.o.hedged_value)} $/{live.unit} · {usd(best.o.hedged_value * q)} on the cargo</div>
		<div class="text-xs text-ink-3">Known today, whatever the price does.</div>
	</div>
	<div class="rounded-lg border border-line px-3 py-2">
		<div class="text-xs text-ink-3">{best.o.name}, unhedged</div>
		{#if best.flat}
			<div class="font-semibold">Same as hedged: this month matches the sale</div>
		{:else}
			<div class="font-semibold">{sgn(best.u['5'], 0)} to {sgn(best.u['95'], 0)} $/{live.unit} · {usdShort(best.u['5'] * q)} to {usdShort(best.u['95'] * q)} on the cargo</div>
			<div class="text-xs text-ink-3">9 in 10 simulated outcomes. Same average, far more risk.</div>
		{/if}
	</div>
</div>
