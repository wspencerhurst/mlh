<script lang="ts">
	import { sgn, usd, longDate, type Live } from '#lib/desk.ts';

	let { live }: { live: Live } = $props();

	const best = $derived(live.options.find((o) => o.name === live.best)!);
	// expected value at the chosen hedge ratio when the engine provides it, else the fully hedged value
	const locked = $derived('mean' in best ? (best as { mean: number }).mean : best.hedged_value);
	const orders = $derived(live.tickets[live.best] ?? []);
	const plan = $derived(live.plans[live.best]);
	const thing = $derived(live.name === 'Gold' ? 'gold' : 'oil');
	const purpose = (covers: string[], side: 'BUY' | 'SELL') =>
		covers
			.map((c) =>
				c.startsWith('sale')
					? `Locks in your ${c}: if ${thing} falls, this gains what your sale loses.`
					: `Locks in your ${c}: if ${thing} rises, this gains what your purchase costs extra.`
			)
			.join(' ') || (side === 'BUY' ? `Gains if ${thing} rises.` : `Gains if ${thing} falls.`);
</script>

{#if orders.length === 0}
	<div class="rounded-lg bg-canvas px-4 py-3 text-sm text-ink-2">
		<b class="text-ink">No hedge needed.</b> You buy and sell on the same month's average ({best.qp_month}), so any move in the
		{thing} price changes both sides equally and cancels out. The deal value of {sgn(best.hedged_value)} $/{live.unit} is already
		locked.
	</div>
{:else}
	<ol class="relative flex flex-col gap-5 border-l-2 border-line pl-6">
		<li class="relative">
						<span class="absolute -left-[33px] grid h-6 w-6 place-items-center rounded-full bg-accent text-xs font-bold text-[#141414]">1</span>
			<div class="font-semibold">Today: place {orders.length === 1 ? 'one futures order' : `${orders.length} futures orders`}</div>
			<div class="text-xs text-ink-3">{live.exchange}, executed at today's settlement price (trade-at-settlement)</div>
			<ul class="mt-2 flex flex-col gap-2">
				{#each orders as o (o.symbol)}
					<li class="flex flex-col gap-0.5 rounded-lg border border-line px-3 py-2 sm:flex-row sm:items-baseline sm:gap-3">
						<span class="shrink-0 font-semibold whitespace-nowrap">
							<span class={o.side === 'BUY' ? 'text-good' : 'text-bad'}>{o.side}</span>
							{Math.abs(o.lots)} × {o.contract}
							<span class="font-normal text-ink-3">({(Math.abs(o.lots) * live.lot).toLocaleString()} {live.unit})</span>
						</span>
						<span class="text-sm text-ink-2">{purpose(o.covers, o.side)}</span>
					</li>
				{/each}
			</ul>
		</li>
		{#each plan.unwind as u, i (u.month + u.contract)}
			<li class="relative">
				<span class="absolute -left-[33px] grid h-6 w-6 place-items-center rounded-full border-2 border-accent bg-panel text-xs font-bold text-accent">{i + 2}</span>
				<div class="font-semibold">
					During {u.month}: {u.side === 'BUY' ? 'buy back' : 'sell'} about {u.lots_per_day} {u.contract} each trading day
					<span class="font-normal text-ink-3">({u.lots_total} in total)</span>
				</div>
				<div class="text-sm text-ink-2">
					<b class="font-semibold text-ink">Why:</b> your {u.why} price is the average of the daily prices in {u.month}. Each trading day,
					one day's slice (about {Math.round(u.lots_per_day * live.lot).toLocaleString()} {live.unit}) of that price becomes final and
					can no longer move, so that slice no longer needs protecting. Closing the same slice of futures that day, at that day's
					price, keeps the hedge exactly matched to what is still open.
				</div>
			</li>
		{/each}
		<li class="relative">
			<span class="absolute -left-[33px] grid h-6 w-6 place-items-center rounded-full bg-good text-xs font-bold text-white">✓</span>
			<div class="font-semibold">Flat by {plan.flat_by ? longDate(plan.flat_by) : 'the end of the last pricing month'}</div>
			<div class="text-sm text-ink-2">
				Result: the deal is expected to earn {sgn(locked)} $/{live.unit} ({usd(locked * live.quantity)} on this cargo) whatever
				the {thing} price does. What remains is the gap between futures and the physical price, which the bad case above includes.
			</div>
		</li>
	</ol>
{/if}
