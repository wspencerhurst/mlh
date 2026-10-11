<script lang="ts">
	import { usd, type Proposal, type ProposalStatus } from '#lib/desk.ts';
	import { SCENARIOS, type Scenario, type TradeResult } from '#lib/checker/types.ts';

	let { proposals, showDemoControls = false }: { proposals: Proposal[]; showDemoControls?: boolean } = $props();

	let status = $state<Record<string, ProposalStatus>>({});
	let fills = $state<Record<string, string>>({});
	let results = $state<Record<string, TradeResult>>({});
	let note = $state('');
	let sending = $state(false);
	let scenario = $state<Scenario>('happy');
	let filter = $state<'all' | 'pending' | 'approved' | 'completed'>('all');
	let previousIds = '';

	const st = (proposal: Proposal) => status[proposal.id] ?? proposal.status;
	const pendingCount = $derived(proposals.filter((proposal) => st(proposal) === 'PENDING_APPROVAL').length);
	const approvedCount = $derived(proposals.filter((proposal) => st(proposal) === 'APPROVED').length);
	const approvedOrders = $derived(proposals.filter((proposal) => st(proposal) === 'APPROVED' && proposal.kind === 'FUTURES_ORDER').length);
	const approvedDeclarations = $derived(proposals.filter((proposal) => st(proposal) === 'APPROVED' && proposal.kind === 'QP_DECLARATION').length);
	const rejectedCount = $derived(proposals.filter((proposal) => st(proposal) === 'REJECTED').length);
	const completedCount = $derived(proposals.filter((proposal) => ['FILLED', 'FAILED'].includes(st(proposal))).length);
	const visible = $derived.by(() =>
		proposals.filter((proposal) => {
			const current = st(proposal);
			if (filter === 'pending') return current === 'PENDING_APPROVAL';
			if (filter === 'approved') return current === 'APPROVED';
			if (filter === 'completed') return current === 'FILLED' || current === 'FAILED';
			return true;
		})
	);

	const PILL: Record<ProposalStatus, [string, string]> = {
		PENDING_APPROVAL: ['Needs review', 'bg-warn-wash text-warn'],
		APPROVED: ['Approved', 'bg-good-wash text-good'],
		REJECTED: ['Rejected', 'bg-bad-wash text-bad'],
		SUBMITTED: ['Sending', 'bg-accent-wash text-accent'],
		FILLED: ['Completed', 'bg-good-wash text-good'],
		FAILED: ['Needs attention', 'bg-bad-wash text-bad']
	};

	$effect(() => {
		const ids = proposals.map((proposal) => proposal.id).join('|');
		if (ids !== previousIds) {
			previousIds = ids;
			status = {};
			fills = {};
			results = {};
			note = '';
		}
	});

	function set(proposal: Proposal, next: ProposalStatus) {
		if (sending) return;
		status[proposal.id] = next;
		if (next === 'PENDING_APPROVAL' || next === 'APPROVED') {
			delete fills[proposal.id];
			delete results[proposal.id];
		}
		note = '';
	}

	function approveAll() {
		for (const proposal of proposals) {
			if (st(proposal) === 'PENDING_APPROVAL') status[proposal.id] = 'APPROVED';
		}
		note = '';
	}

	function rejectAll() {
		for (const proposal of proposals) {
			if (st(proposal) === 'PENDING_APPROVAL') status[proposal.id] = 'REJECTED';
		}
		note = '';
	}

	function resetQueue() {
		status = {};
		fills = {};
		results = {};
		note = 'Review state reset. No orders were sent.';
	}

	async function send() {
		if (sending || approvedCount === 0) return;
		sending = true;
		note = '';
		let filled = 0;
		let failed = 0;
		let declarations = 0;
		const batch = proposals.filter((proposal) => st(proposal) === 'APPROVED');

		for (const proposal of batch) {
			if (proposal.kind === 'QP_DECLARATION') {
				fills[proposal.id] = 'Declaration recorded in the Goldmine demo. No live Checker order was created.';
				status[proposal.id] = 'FILLED';
				declarations++;
				continue;
			}
			if (!proposal.checker) {
				fills[proposal.id] = 'This proposal has no Checker ticket attached.';
				status[proposal.id] = 'FAILED';
				failed++;
				continue;
			}

			status[proposal.id] = 'SUBMITTED';
			try {
				const response = await fetch('/api/trades', {
					method: 'POST',
					headers: { 'content-type': 'application/json' },
					body: JSON.stringify({
						...proposal.checker,
						referencePrice: Number(proposal.details.ref_price),
						scenario
					})
				});
				const result = (await response.json()) as TradeResult & { message?: string };
				results[proposal.id] = result;
				if (response.ok && result.ok) {
					const fillsList = result.order?.fills ?? [];
					const quantity = fillsList.reduce((total, fill) => total + fill.quantity, 0);
					const price = quantity
						? fillsList.reduce((total, fill) => total + fill.quantity * fill.price, 0) / quantity
						: result.order?.price;
					fills[proposal.id] = `Filled ${quantity || proposal.checker.quantity} @ ${Number(price ?? 0).toFixed(2)} · order ${result.order?.orderId ?? ''}`;
					status[proposal.id] = 'FILLED';
					filled++;
				} else {
					fills[proposal.id] = result.error?.message ?? result.message ?? `Request failed with HTTP ${response.status}`;
					status[proposal.id] = 'FAILED';
					failed++;
				}
			} catch (error) {
				fills[proposal.id] = String(error);
				status[proposal.id] = 'FAILED';
				failed++;
			}
		}

		sending = false;
		if (failed) {
			note = `${filled} filled, ${failed} need attention. Review the result on each ticket.`;
		} else if (filled) {
			note = `Demo run complete: ${filled} Checker mock order${filled === 1 ? '' : 's'} filled${declarations ? ` and ${declarations} declaration recorded` : ''}.`;
		} else {
			note = `${declarations} declaration${declarations === 1 ? '' : 's'} recorded in the demo. No Checker order was sent.`;
		}
	}
</script>

<div class="flex h-full flex-col">
	<div class="flex flex-wrap items-start justify-between gap-3">
		<div>
			<h2 class="font-display text-lg font-bold">Approval queue</h2>
			<p class="mt-1 text-sm text-ink-2">Review the analyzer’s declaration and hedge tickets before sending.</p>
		</div>
		<div class="flex items-center gap-2 rounded-lg border border-line bg-canvas px-3 py-2" aria-label="Checker demo adapter">
<img src="/checker-logo.png" alt="" class="h-5 w-auto" />
			<span class="rounded-full bg-warn-wash px-2 py-0.5 text-[10px] font-bold text-warn">Demo</span>
		</div>
	</div>

	<div class="mt-4 flex flex-wrap gap-2 text-xs">
		<span class="rounded-lg border border-line bg-canvas px-2.5 py-1.5"><b class="text-ink">{pendingCount}</b> need review</span>
		<span class="rounded-lg border border-line bg-canvas px-2.5 py-1.5"><b class="text-good">{approvedCount}</b> approved</span>
		<span class="rounded-lg border border-line bg-canvas px-2.5 py-1.5"><b class="text-ink-2">{completedCount}</b> completed</span>
	</div>

	<div class="mt-4 rounded-xl border border-warn/30 bg-warn-wash p-3 text-xs leading-5 text-warn">
		Demo mode: sends to Goldmine’s local Checker simulator. No live Checker order is placed.
	</div>

	{#if showDemoControls}
		<details class="mt-3 rounded-lg border border-line bg-canvas px-3 py-2">
			<summary class="cursor-pointer text-xs font-semibold text-ink-2">Demo response settings</summary>
			<label class="mt-2 block text-xs text-ink-3" for="checker-scenario">Simulated outcome</label>
			<select id="checker-scenario" class="mt-1 w-full rounded-lg border border-line bg-panel px-3 py-2 text-sm text-ink" bind:value={scenario} disabled={sending}>
				{#each Object.entries(SCENARIOS) as [key, option] (key)}
					<option value={key}>{option.label} — {option.hint}</option>
				{/each}
			</select>
		</details>
	{/if}

	<div class="mt-4 flex flex-wrap items-center justify-between gap-3">
		<div class="flex flex-wrap gap-1" role="group" aria-label="Filter approval queue">
			{#each [
				{ key: 'all', label: `All (${proposals.length})` },
				{ key: 'pending', label: `Needs review (${pendingCount})` },
				{ key: 'approved', label: `Approved (${approvedCount})` },
				{ key: 'completed', label: `Completed (${completedCount})` }
			] as item (item.key)}
				<button
					class="rounded-md px-2.5 py-1.5 text-xs font-semibold transition {filter === item.key ? 'bg-accent text-[#141414]' : 'text-ink-3 hover:bg-canvas hover:text-ink'}"
					aria-pressed={filter === item.key}
					onclick={() => (filter = item.key as typeof filter)}
				>{item.label}</button>
			{/each}
		</div>
		<div class="flex flex-wrap gap-2">
			<button class="rounded-md border border-line px-2.5 py-1.5 text-xs font-semibold text-ink-2 hover:bg-canvas disabled:opacity-40" disabled={pendingCount === 0 || sending} onclick={rejectAll}>Reject pending</button>
			<button class="rounded-md border border-line px-2.5 py-1.5 text-xs font-semibold text-ink hover:bg-canvas disabled:opacity-40" disabled={pendingCount === 0 || sending} onclick={approveAll}>Approve pending</button>
		</div>
	</div>

	<ul class="mt-3 flex flex-col gap-2">
		{#each visible as proposal (proposal.id)}
			{@const current = st(proposal)}
			{@const pill = PILL[current]}
			{@const result = results[proposal.id]}
			<li class="rounded-xl border border-line bg-panel">
				<div class="flex flex-col gap-3 p-3 sm:flex-row sm:items-start sm:justify-between sm:p-4">
					<div class="min-w-0 flex-1">
						<div class="flex flex-wrap items-center gap-2">
							{#if proposal.kind === 'FUTURES_ORDER'}
								<span class="rounded-md px-2 py-1 text-[11px] font-bold {proposal.details.side === 'BUY' ? 'bg-good-wash text-good' : 'bg-bad-wash text-bad'}">{proposal.details.side}</span>
								<h3 class="font-semibold">{proposal.details.lots} × {proposal.details.instrument}</h3>
							{:else}
								<span class="rounded-md bg-accent-wash px-2 py-1 text-[11px] font-bold text-accent">QP</span>
								<h3 class="font-semibold">{proposal.summary}</h3>
							{/if}
							<span class="rounded-full px-2.5 py-1 text-[11px] font-semibold {pill[1]}">{pill[0]}</span>
						</div>
						<p class="mt-2 text-xs leading-5 text-ink-3">
							{#if proposal.kind === 'FUTURES_ORDER'}
								{(Number(proposal.details.lots) * Number(proposal.details.lot_size)).toLocaleString()} {proposal.details.unit} · reference {proposal.details.ref_price} · notional {usd(Number(proposal.details.notional_usd))} · {proposal.checker?.instrumentPair}
							{:else}
								{Number(proposal.details.quantity).toLocaleString()} {proposal.details.unit} · delivery {proposal.details.delivery}
							{/if}
						</p>
						{#if fills[proposal.id]}
							<p class="mt-2 text-xs leading-5 {current === 'FAILED' ? 'text-bad' : 'text-good'}" role="status">{fills[proposal.id]}</p>
						{/if}
					</div>
					<div class="flex shrink-0 flex-wrap gap-2">
						{#if current === 'PENDING_APPROVAL'}
							<button class="min-h-9 rounded-lg border border-line px-3 text-xs font-semibold text-ink hover:bg-canvas disabled:opacity-40" disabled={sending} onclick={() => set(proposal, 'REJECTED')}>Reject</button>
							<button class="min-h-9 rounded-lg bg-accent px-3 text-xs font-semibold text-[#141414] hover:brightness-110 disabled:opacity-40" disabled={sending} onclick={() => set(proposal, 'APPROVED')}>Approve</button>
						{:else if current === 'APPROVED' || current === 'REJECTED'}
							<button class="min-h-9 rounded-lg border border-line px-3 text-xs font-semibold text-ink-2 hover:bg-canvas disabled:opacity-40" disabled={sending} onclick={() => set(proposal, 'PENDING_APPROVAL')}>Undo</button>
						{:else if current === 'FAILED'}
							<button class="min-h-9 rounded-lg border border-line px-3 text-xs font-semibold text-ink hover:bg-canvas disabled:opacity-40" disabled={sending} onclick={() => set(proposal, 'APPROVED')}>Retry</button>
						{/if}
					</div>
				</div>

				<details class="border-t border-line px-3 py-2.5 sm:px-4">
					<summary class="cursor-pointer text-xs font-semibold text-ink-3 hover:text-ink">Review details{#if result} and execution timeline{/if}</summary>
					<dl class="mt-3 grid gap-x-5 gap-y-2 text-xs sm:grid-cols-2">
						{#each Object.entries(proposal.details) as [key, value] (key)}
							<div class="flex min-w-0 justify-between gap-3 border-b border-line/70 pb-1.5">
								<dt class="text-ink-3">{key.replaceAll('_', ' ')}</dt>
								<dd class="truncate text-right font-medium text-ink">{value}</dd>
							</div>
						{/each}
					</dl>
					{#if result}
						<ol class="mt-4 space-y-3">
							{#each result.timeline as event, index (index)}
								<li class="flex gap-3">
									<span class="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full {event.ok ? 'bg-good' : 'bg-bad'}"></span>
									<div class="min-w-0">
										<p class="text-xs font-semibold text-ink">{event.title}</p>
										{#if event.detail}<p class="mt-0.5 text-xs leading-5 text-ink-3">{event.detail}</p>{/if}
										<p class="mt-1 font-mono text-[10px] text-ink-3">{event.request?.method ?? event.step} {event.request?.path ?? ''}</p>
									</div>
								</li>
							{/each}
						</ol>
					{/if}
				</details>
			</li>
		{:else}
			<li class="rounded-xl border border-dashed border-line bg-canvas p-6 text-center text-sm text-ink-3">
				{proposals.length ? 'No tickets match this filter.' : 'No analyzer recommendations are waiting for approval.'}
			</li>
		{/each}
	</ul>

	<div class="mt-auto flex flex-col gap-3 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between">
		<div class="min-h-5 text-xs leading-5 text-ink-3" role="status" aria-live="polite">{note}</div>
		<div class="flex shrink-0 flex-wrap gap-2">
			<button class="rounded-lg border border-line px-3 py-2 text-xs font-semibold text-ink-2 hover:bg-canvas disabled:opacity-40" disabled={sending || (!approvedCount && !completedCount && !rejectedCount)} onclick={resetQueue}>Reset review</button>
			<button
				class="min-h-10 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-[#141414] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
				disabled={approvedCount === 0 || sending}
				onclick={send}
			>
				{#if sending}
					Sending approved tickets…
				{:else if approvedOrders && approvedDeclarations}
					Send {approvedOrders} {approvedOrders === 1 ? 'order' : 'orders'} to Checker + record declaration
				{:else if approvedOrders}
					Send {approvedOrders} approved {approvedOrders === 1 ? 'order' : 'orders'} to Checker
				{:else if approvedDeclarations}
					Record approved declaration
				{:else}
					Send to Checker
				{/if}
			</button>
		</div>
	</div>
</div>
