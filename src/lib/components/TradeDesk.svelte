<script lang="ts">
	import { SCENARIOS, type Scenario, type Side, type TimelineEvent, type TradeResult } from '#lib/checker/types.ts';
	import { fmtNum } from '#lib/spot.ts';

	type Instrument = { symbol: string; label: string; price: number; unit: string };
	let { instruments }: { instruments: Instrument[] } = $props();

	let symbol = $state('');
	let side = $state<Side>('SELL');
	let quantity = $state(10);
	let scenario = $state<Scenario>('happy');
	let busy = $state(false);
	let shown = $state<TimelineEvent[]>([]);
	let result = $state<TradeResult | null>(null);
	let blotter = $state<TradeResult[]>([]);
	let open = $state<number | null>(null);
	let fetchError = $state<string | null>(null);

	const inst = $derived(instruments.find((i) => i.symbol === symbol) ?? instruments[0]);
	$effect(() => {
		// Default to the December contract, the most liquid gold future.
		if (!symbol && instruments.length)
			symbol = (instruments.find((i) => /^GCZ/.test(i.symbol)) ?? instruments.find((i) => i.symbol.startsWith('GC')) ?? instruments[0]).symbol;
	});

	const STEP_LABEL = { rfq: 'RFQ', quotes: 'Quotes', accept: 'Accept', execute: 'Execute', order: 'Order', settlement: 'Settle' } as const;
	const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		if (!inst || busy) return;
		busy = true;
		shown = [];
		result = null;
		open = null;
		fetchError = null;
		try {
			const res = await fetch('/api/trades', {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ instrumentPair: inst.symbol, side, quantity, referencePrice: inst.price, scenario })
			});
			if (!res.ok) throw new Error(`${res.status} ${(await res.text()).slice(0, 200)}`);
			const r: TradeResult = await res.json();
			// Replay the simulated timeline, compressed so the demo stays quick.
			let prev = 0;
			for (const ev of r.timeline) {
				await sleep(Math.min(1200, Math.max(250, (ev.at - prev) / 6)));
				prev = ev.at;
				shown = [...shown, ev];
			}
			result = r;
			blotter = [r, ...blotter].slice(0, 8);
		} catch (err) {
			fetchError = String(err);
		} finally {
			busy = false;
		}
	}

	const filledQty = (r: TradeResult) => (r.order?.fills ?? []).reduce((s, f) => s + f.quantity, 0);
	const secs = (ms: number) => `+${(ms / 1000).toFixed(1)}s`;
</script>

<div class="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
	<!-- Ticket -->
	<form onsubmit={submit} class="relative overflow-hidden rounded-xl border border-line bg-panel p-5">
		<div class="absolute inset-x-0 top-0 h-1 bg-mlh-blue"></div>
		<h3 class="font-display text-lg font-bold">Trade ticket</h3>

		<label class="mt-4 block text-xs font-semibold text-ink-2" for="td-inst">Instrument</label>
		<select id="td-inst" bind:value={symbol} class="mt-1 w-full rounded-lg border border-line bg-panel px-3 py-2 text-sm">
			{#each instruments as i (i.symbol)}
				<option value={i.symbol}>{i.label} · {fmtNum(i.price, 1)}</option>
			{/each}
		</select>

		<div class="mt-4 grid grid-cols-2 gap-2" role="group" aria-label="Side">
			{#each ['BUY', 'SELL'] as const as s (s)}
				<button
					type="button"
					aria-pressed={side === s}
					onclick={() => (side = s)}
					class="rounded-lg border py-2 text-sm font-bold transition {side === s
						? s === 'BUY'
							? 'border-good bg-good-wash text-good'
							: 'border-mlh-red bg-bad-wash text-bad'
						: 'border-line text-ink-3'}">{s}</button
				>
			{/each}
		</div>

		<label class="mt-4 block text-xs font-semibold text-ink-2" for="td-qty">Quantity ({inst?.unit ?? ''})</label>
		<input
			id="td-qty"
			type="number"
			min="1"
			step="1"
			bind:value={quantity}
			class="mt-1 w-full rounded-lg border border-line bg-panel px-3 py-2 text-sm tabular-nums"
		/>
		{#if inst}
			<p class="mt-1 text-xs text-ink-3 tabular-nums">
				≈ ${fmtNum(quantity * inst.price * (inst.unit === 'contracts' ? 100 : 1), 0)} notional
			</p>
		{/if}

		<fieldset class="mt-4">
			<legend class="text-xs font-semibold text-ink-2">Scenario (mock)</legend>
			<div class="mt-2 flex flex-wrap gap-1.5">
				{#each Object.entries(SCENARIOS) as [key, s] (key)}
					<button
						type="button"
						title={s.hint}
						aria-pressed={scenario === key}
						onclick={() => (scenario = key as Scenario)}
						class="rounded-full border px-2.5 py-1 text-xs font-semibold transition {scenario === key
							? key === 'happy'
								? 'border-good bg-good-wash text-good'
								: 'border-best bg-best-wash text-best'
							: 'border-line text-ink-2 hover:text-ink'}">{s.label}</button
					>
				{/each}
			</div>
			<p class="mt-2 text-xs text-ink-3">{SCENARIOS[scenario].hint}</p>
		</fieldset>

		<button
			type="submit"
			disabled={busy || !inst || !(quantity > 0)}
			class="mt-5 w-full rounded-lg bg-accent py-3 font-semibold transition hover:brightness-110 disabled:opacity-50"
		>
			{busy ? 'Executing…' : `Send RFQ · ${side} ${quantity} ${inst?.symbol ?? ''}`}
		</button>
	</form>

	<!-- Timeline -->
	<div class="min-w-0 rounded-xl border border-line bg-panel p-5">
		<div class="flex items-center justify-between gap-2">
			<h3 class="font-display text-lg font-bold">Execution</h3>
			<span class="text-xs text-ink-3">Mock Checker API · /api/v1</span>
		</div>

		{#if fetchError}
			<p class="mt-4 rounded-lg border border-bad/40 bg-bad-wash p-3 text-sm">{fetchError}</p>
		{:else if !shown.length && !busy}
			<p class="mt-4 text-sm text-ink-3">Send a ticket to see the RFQ, quotes, fills and settlement.</p>
		{/if}

		<ol class="mt-4 space-y-2">
			{#each shown as ev, i (i)}
				<li class="rounded-lg border {ev.ok ? 'border-line' : 'border-bad/40 bg-bad-wash'}">
					<button
						type="button"
						class="flex w-full items-start gap-3 px-3 py-2 text-left"
						onclick={() => (open = open === i ? null : i)}
						aria-expanded={open === i}
					>
						<span
							class="mt-0.5 w-16 shrink-0 rounded px-1.5 py-0.5 text-center text-[10px] font-bold uppercase {ev.ok
								? 'bg-canvas text-ink-2'
								: 'bg-accent text-[#141414]'}">{STEP_LABEL[ev.step]}</span
						>
						<span class="min-w-0 flex-1">
							<span class="block text-sm break-words">{ev.title}</span>
							{#if ev.detail}<span class="block text-xs break-words text-ink-3">{ev.detail}</span>{/if}
						</span>
						<span class="shrink-0 text-xs text-ink-3 tabular-nums">{secs(ev.at)}</span>
					</button>
					{#if open === i && (ev.request || ev.response)}
						<pre class="max-h-64 overflow-auto border-t border-line px-3 py-2 text-[11px] leading-snug text-ink-2">{ev.request
								? `${ev.request.method} ${ev.request.path}\n${ev.request.body ? JSON.stringify(ev.request.body, null, 2) + '\n' : ''}\n`
								: ''}{JSON.stringify(ev.response, null, 2)}</pre>
					{/if}
				</li>
			{/each}
			{#if busy}
				<li class="h-10 animate-pulse rounded-lg bg-canvas"></li>
			{/if}
		</ol>

		{#if result}
			{#if result.ok}
				<div class="mt-4 rounded-lg border border-good/40 bg-good-wash p-4">
					<div class="font-display font-bold text-good">Trade settled</div>
					<p class="mt-1 text-sm text-ink-2 tabular-nums">
						{result.order?.side}
						{fmtNum(filledQty(result), 0)}
						{result.order?.instrumentPair} @ {fmtNum(result.order?.price ?? 0)} with {result.order?.provider} · ${fmtNum(
							result.notionalUsd ?? 0,
							0
						)} wired ({result.payment?.withdrawalId})
					</p>
				</div>
			{:else if result.error}
				<div class="mt-4 rounded-lg border border-bad/40 bg-bad-wash p-4">
					<div class="font-display font-bold text-bad">Trade failed: {result.error.code}</div>
					<p class="mt-1 text-sm text-ink-2">{result.error.message}</p>
					<p class="mt-2 text-xs text-ink-2">
						{#if result.sentry?.sent}
							Sentry alert sent · event <code class="text-ink-2">{result.sentry.eventId}</code> ·
							<a
								class="underline hover:text-ink"
								href="https://mlh-yu.sentry.io/issues/?query={result.sentry.eventId}"
								target="_blank"
								rel="noreferrer">View in Sentry</a
							>
						{:else}
							Sentry alert not sent: {result.sentry?.reason ?? 'unknown'}
						{/if}
					</p>
				</div>
			{/if}
		{/if}
	</div>
</div>

{#if blotter.length}
	<div class="mt-6 overflow-x-auto rounded-xl border border-line">
		<table class="w-full min-w-[640px] text-sm tabular-nums">
			<thead class="bg-canvas text-xs text-ink-2">
				<tr>
					<th class="px-4 py-2 text-left">Order</th>
					<th class="px-4 py-2 text-left">Instrument</th>
					<th class="px-4 py-2 text-right">Filled / Qty</th>
					<th class="px-4 py-2 text-right">Price</th>
					<th class="px-4 py-2 text-left">LP</th>
					<th class="px-4 py-2 text-left">Status</th>
				</tr>
			</thead>
			<tbody>
				{#each blotter as r, i (i)}
					<tr class="border-t border-line">
						<td class="px-4 py-2 font-mono text-xs text-ink-2">{r.order?.orderId ?? r.rfq?.requestForQuoteId ?? '–'}</td>
						<td class="px-4 py-2"
							><span class={r.ticket.side === 'BUY' ? 'text-good' : 'text-bad'}>{r.ticket.side}</span>
							{r.ticket.instrumentPair}</td
						>
						<td class="px-4 py-2 text-right">{fmtNum(filledQty(r), 0)} / {fmtNum(r.ticket.quantity, 0)}</td>
						<td class="px-4 py-2 text-right">{r.order ? fmtNum(r.order.price) : '–'}</td>
						<td class="px-4 py-2">{r.order?.provider ?? '–'}</td>
						<td class="px-4 py-2">
							{#if r.ok}
								<span class="rounded-full bg-good-wash px-2 py-0.5 text-xs font-semibold text-good">SETTLED</span>
							{:else}
								<span class="rounded-full bg-bad-wash px-2 py-0.5 text-xs font-semibold text-bad">{r.error?.code}</span>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
