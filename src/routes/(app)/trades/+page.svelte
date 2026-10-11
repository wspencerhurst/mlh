<script lang="ts">
	import { fmtNum } from '#lib/spot.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const totals = $derived(
		data.configured
			? data.daily.reduce(
					(t, d) => ({ trades: t.trades + d.trades, failures: t.failures + d.failures, notional: t.notional + d.notional }),
					{ trades: 0, failures: 0, notional: 0 }
				)
			: { trades: 0, failures: 0, notional: 0 }
	);
	const failureRate = $derived(totals.trades ? (totals.failures / totals.trades) * 100 : 0);
	const time = (s: string) => s.slice(0, 19).replace('T', ' ');
</script>

<svelte:head>
	<title>Trade blotter · Goldmine</title>
</svelte:head>

<section class="py-10 sm:py-14">
	<div class="mx-auto max-w-6xl px-4 sm:px-6">
		<h1 class="font-display text-3xl font-bold tracking-tight">Trade blotter</h1>
		<p class="mt-1 max-w-2xl text-sm text-ink-2">
			Every mock Checker trade is recorded in a Tiger Data (TimescaleDB) hypertable; the daily summary comes from a
			continuous aggregate.
		</p>

		{#if !data.configured}
			<p class="mt-6 rounded-xl border border-line bg-panel p-5 text-sm text-ink-2">
				Tiger Data not configured. Set the TIGER_DATABASE_URL secret to record and show trades.
			</p>
		{:else if data.error}
			<p class="mt-6 rounded-xl border border-line bg-bad-wash p-5 text-sm text-bad">{data.error}</p>
		{:else}
			<div class="mt-6 grid gap-4 sm:grid-cols-3">
				<div class="rounded-xl border border-line bg-panel p-5">
					<div class="text-xs text-ink-2">Trades (14 days)</div>
					<div class="mt-1 text-2xl font-semibold tabular-nums">{totals.trades}</div>
				</div>
				<div class="rounded-xl border border-line bg-panel p-5">
					<div class="text-xs text-ink-2">Failure rate</div>
					<div class="mt-1 text-2xl font-semibold tabular-nums">{fmtNum(failureRate, 1)}%</div>
					<div class="mt-1 text-xs text-ink-3">{totals.failures} failed</div>
				</div>
				<div class="rounded-xl border border-line bg-panel p-5">
					<div class="text-xs text-ink-2">Failures by step</div>
					{#if data.steps.length}
						<ul class="mt-1 space-y-0.5 text-sm tabular-nums">
							{#each data.steps as s (s.step)}
								<li class="flex justify-between"><span>{s.step}</span><span class="font-semibold">{s.failures}</span></li>
							{/each}
						</ul>
					{:else}
						<div class="mt-1 text-sm text-ink-3">None</div>
					{/if}
				</div>
			</div>

			{#if data.daily.length}
				<div class="mt-6 overflow-x-auto rounded-xl border border-line">
					<table class="w-full min-w-[520px] text-sm tabular-nums">
						<thead class="bg-canvas text-xs text-ink-2">
							<tr>
								<th class="px-4 py-2 text-left">Day</th>
								<th class="px-4 py-2 text-right">Trades</th>
								<th class="px-4 py-2 text-right">Failures</th>
								<th class="px-4 py-2 text-right">Filled qty</th>
								<th class="px-4 py-2 text-right">Notional (USD)</th>
							</tr>
						</thead>
						<tbody>
							{#each data.daily as d (d.day)}
								<tr class="border-t border-line">
									<td class="px-4 py-2">{d.day.slice(0, 10)}</td>
									<td class="px-4 py-2 text-right">{d.trades}</td>
									<td class="px-4 py-2 text-right">{d.failures}</td>
									<td class="px-4 py-2 text-right">{fmtNum(d.filled, 0)}</td>
									<td class="px-4 py-2 text-right">{fmtNum(d.notional, 0)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}

			<h2 class="mt-8 font-display text-xl font-bold tracking-tight">Recent trades</h2>
			{#if data.recent.length}
				<div class="mt-3 overflow-x-auto rounded-xl border border-line">
					<table class="w-full min-w-[760px] text-sm tabular-nums">
						<thead class="bg-canvas text-xs text-ink-2">
							<tr>
								<th class="px-4 py-2 text-left">Time (UTC)</th>
								<th class="px-4 py-2 text-left">Instrument</th>
								<th class="px-4 py-2 text-right">Filled / Qty</th>
								<th class="px-4 py-2 text-left">Status</th>
								<th class="px-4 py-2 text-left">Failure</th>
								<th class="px-4 py-2 text-left">Sentry event</th>
							</tr>
						</thead>
						<tbody>
							{#each data.recent as r, i (i)}
								<tr class="border-t border-line">
									<td class="px-4 py-2 text-ink-2">{time(r.executedAt)}</td>
									<td class="px-4 py-2"
										><span class={r.side === 'BUY' ? 'text-good' : 'text-bad'}>{r.side}</span> {r.instrument}</td
									>
									<td class="px-4 py-2 text-right">{fmtNum(r.filledQuantity, 0)} / {fmtNum(r.quantity, 0)}</td>
									<td class="px-4 py-2">
										{#if r.ok}
											<span class="rounded-full bg-good-wash px-2 py-0.5 text-xs font-semibold text-good">Settled</span>
										{:else}
											<span class="rounded-full bg-bad-wash px-2 py-0.5 text-xs font-semibold text-bad">Failed</span>
										{/if}
									</td>
									<td class="px-4 py-2">{r.errorStep ? `${r.errorStep} · ${r.errorCode}` : '–'}</td>
									<td class="px-4 py-2 font-mono text-xs text-ink-2">{r.sentryEventId ?? '–'}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{:else}
				<p class="mt-3 text-sm text-ink-2">No demo trades recorded yet. Send an approved action to Checker to record one.</p>
			{/if}
		{/if}
	</div>
</section>
