<script lang="ts">
	import { onMount } from 'svelte';
	import type { Terms } from '#lib/engine.ts';
	import { OpenMineralClient, MOCK_BASE_URL } from '#lib/openmineral/client.ts';
	import { importables, type Importable } from '#lib/openmineral/terms.ts';

	// eslint-disable-next-line @typescript-eslint/no-unused-vars, no-useless-assignment -- written back to the parent via bind:terms
	let { terms = $bindable(), base, asof }: { terms: Terms; base: Terms; asof: string } = $props();

	// The bundled Open Mineral mock runs inside this app; point MOCK_BASE_URL at a real deployment for live contracts.
	const client = new OpenMineralClient(MOCK_BASE_URL);
	let items = $state<Importable[]>([]);
	let status = $state<'loading' | 'ready' | 'error'>('loading');
	let error = $state('');
	let chosen = $state('standard');

	onMount(async () => {
		try {
			await client.login('trader@open-mineral.demo', 'demo'); // public demo account of the bundled mock
			const page = await client.listContracts();
			items = importables(page.items, base, asof);
			status = 'ready';
		} catch (e) {
			status = 'error';
			error = String(e);
		}
	});

	const current = $derived(items.find((i) => i.key === chosen) ?? null);
	function pick(key: string) {
		chosen = key;
		if (key === 'standard') terms = $state.snapshot(base) as Terms;
		else {
			const it = items.find((i) => i.key === key);
			if (it?.terms) terms = $state.snapshot(it.terms) as Terms;
		}
	}
</script>

<div class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-line bg-panel px-4 py-2.5 text-sm shadow-sm">
	<label for="contract-src" class="font-display font-bold">Contract</label>
	<select
		id="contract-src"
		class="min-w-0 max-w-full flex-1 rounded-md border border-line bg-panel px-2 py-1 sm:max-w-md"
		value={chosen}
		onchange={(e) => pick((e.currentTarget as HTMLSelectElement).value)}
	>
		<option value="standard">Standard template (edit below)</option>
		{#if status === 'ready'}
			<optgroup label="Open Mineral">
				{#each items as it (it.key)}
					<option value={it.key} disabled={!it.terms}>{it.label}{it.reason ? ` (${it.reason})` : ''}</option>
				{/each}
			</optgroup>
		{/if}
	</select>
	{#if status === 'loading'}
		<span class="text-xs text-ink-3">Loading Open Mineral contracts…</span>
	{:else if status === 'error'}
		<span class="text-xs text-bad" title={error}>Open Mineral unavailable</span>
	{:else if current}
		<span class="flex min-w-0 items-center gap-2 text-xs text-ink-2">
			<span class="rounded-full px-2 py-0.5 font-semibold {current.verified ? 'bg-good-wash text-good' : 'bg-warn-wash text-warn'}">
				{current.verified ? 'Verified' : 'Unverified'}
			</span>
			<span class="truncate">{current.detail}</span>
		</span>
	{:else}
		<span class="text-xs text-ink-3">{items.filter((i) => i.terms).length} Open Mineral gold shipments available</span>
	{/if}
</div>
