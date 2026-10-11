<script lang="ts" module>
	import { MOCK_BASE_URL, OpenMineralClient } from '#lib/openmineral/client.ts';
	import type { ContractType } from '#lib/openmineral/types.ts';

	// Module-level so the connection survives navigating away from the page and back.
	// Demo credentials are the ones the mock backend accepts.
	const session = $state({
		baseUrl: MOCK_BASE_URL,
		username: 'trader@open-mineral.demo',
		password: 'demo',
		client: null as OpenMineralClient | null,
		contracts: [] as ContractType[],
		total: 0
	});
</script>

<script lang="ts">
	import { fmtDate } from '#lib/spot.ts';

	let { contract = $bindable(null) }: { contract: ContractType | null } = $props();

	let busy = $state<'connect' | number | null>(null);
	let error = $state<string | null>(null);

	async function connect(e: SubmitEvent) {
		e.preventDefault();
		busy = 'connect';
		error = null;
		try {
			const c = new OpenMineralClient(session.baseUrl);
			await c.login(session.username, session.password);
			const page = await c.listContracts();
			session.client = c;
			session.contracts = page.items;
			session.total = page.total ?? page.items.length;
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = null;
		}
	}

	function disconnect() {
		session.client?.logout();
		session.client = null;
		session.contracts = [];
		contract = null;
	}

	async function select(id: number) {
		if (!session.client) return;
		busy = id;
		error = null;
		try {
			contract = await session.client.getContract(id);
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = null;
		}
	}

	const shipmentCount = (c: ContractType) => Object.keys(c.verify_mapping?.shipments ?? {}).length;
	const qpMetals = (c: ContractType) => Object.keys(c.verify_mapping?.qp ?? {});
</script>

<div class="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
	<!-- Connection -->
	<form onsubmit={connect} class="relative overflow-hidden rounded-xl border border-line bg-panel p-5">
		<div class="absolute inset-x-0 top-0 h-1 bg-mlh-yellow"></div>
		<div class="flex items-center justify-between">
			<h3 class="font-display text-lg font-bold">Open Mineral</h3>
			<span
				class="rounded-full px-2 py-0.5 text-xs font-semibold {session.client
					? 'bg-good-wash text-good'
					: 'bg-canvas text-ink-2'}">{session.client ? 'Connected' : 'Disconnected'}</span
			>
		</div>
		<p class="mt-1 text-xs text-ink-3">
			Signs in with the backend's OAuth2 password flow, then reads <code class="text-ink-2">/api/gaia/contracts</code>.
		</p>

		<label class="mt-4 block text-xs font-semibold text-ink-2" for="om-url">Backend URL</label>
		<input
			id="om-url"
			bind:value={session.baseUrl}
			disabled={!!session.client}
			class="mt-1 w-full rounded-lg border border-line bg-panel px-3 py-2 font-mono text-sm disabled:opacity-60"
		/>
		{#if session.baseUrl === MOCK_BASE_URL}
			<p class="mt-1 text-xs text-best">Mock backend with demo contracts</p>
		{/if}

		<label class="mt-3 block text-xs font-semibold text-ink-2" for="om-user">Username</label>
		<input
			id="om-user"
			bind:value={session.username}
			disabled={!!session.client}
			autocomplete="off"
			class="mt-1 w-full rounded-lg border border-line bg-panel px-3 py-2 text-sm disabled:opacity-60"
		/>
		<label class="mt-3 block text-xs font-semibold text-ink-2" for="om-pass">Password</label>
		<input
			id="om-pass"
			type="password"
			bind:value={session.password}
			disabled={!!session.client}
			autocomplete="off"
			class="mt-1 w-full rounded-lg border border-line bg-panel px-3 py-2 text-sm disabled:opacity-60"
		/>

		{#if session.client}
			<button type="button" onclick={disconnect} class="mt-5 w-full rounded-lg border border-line px-4 py-2.5 font-semibold hover:bg-canvas">
				Disconnect
			</button>
		{:else}
			<button
				disabled={busy === 'connect'}
				class="mt-5 w-full rounded-lg bg-mlh-yellow px-4 py-2.5 font-semibold text-mlh-navy transition hover:brightness-110 disabled:opacity-60"
			>
				{busy === 'connect' ? 'Connecting…' : 'Connect'}
			</button>
		{/if}
		{#if error}
			<p class="mt-3 rounded-lg border border-bad/40 bg-bad-wash p-3 text-xs">{error}</p>
		{/if}
	</form>

	<!-- Contracts -->
	<div class="min-w-0 rounded-xl border border-line bg-panel">
		<div class="flex items-center justify-between border-b border-line px-4 py-3">
			<h3 class="font-display font-bold">Contracts</h3>
			{#if session.client}<span class="text-xs text-ink-3">{session.total} total</span>{/if}
		</div>
		{#if !session.client}
			<p class="p-8 text-center text-sm text-ink-3">Connect to list contracts.</p>
		{:else if !session.contracts.length}
			<p class="p-8 text-center text-sm text-ink-3">No contracts on this account.</p>
		{:else}
			<ul class="divide-y divide-line">
				{#each session.contracts as c (c.id)}
					{@const on = contract?.id === c.id}
					{@const vm = c.verify_mapping}
					<li>
						<button
							onclick={() => select(c.id)}
							aria-pressed={on}
							class="flex w-full flex-col gap-1 px-4 py-3 text-left transition sm:flex-row sm:items-center sm:gap-4 {on
								? 'bg-accent-wash'
								: 'hover:bg-canvas'}"
						>
							<div class="min-w-0 flex-1">
								<div class="truncate font-semibold">{c.name}</div>
								<div class="truncate text-xs text-ink-3">
									{vm?.seller.name.val ?? '–'} → {vm?.buyer.name.val ?? '–'}
								</div>
							</div>
							<div class="flex flex-wrap items-center gap-2 text-xs">
								{#each qpMetals(c) as m (m)}
									<span class="rounded px-1.5 py-0.5 font-semibold {m === 'Au' ? 'bg-best-wash text-best' : 'bg-canvas text-ink-2'}">{m}</span>
								{/each}
								<span class="text-ink-3">{shipmentCount(c)} ship.</span>
								<span class="text-ink-3">{fmtDate(Date.parse(c.created_at))}</span>
								<span
									class="rounded-full px-2 py-0.5 font-semibold {vm?.is_verified
										? 'bg-good-wash text-good'
										: 'bg-best-wash text-best'}">{c.status}</span
								>
								{#if busy === c.id}<span class="text-ink-3">Loading…</span>{/if}
							</div>
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</div>
