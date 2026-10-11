<script lang="ts">
	import type { ContractType, EnumAllMetals, QPEnum } from '#lib/openmineral/types.ts';
	import { DEFAULT_VOYAGE_DAYS, G_PER_OZ, exposures, fmtMonth, parseQp, qpFor } from '#lib/openmineral/qp.ts';
	import { fmtDate, fmtNum } from '#lib/spot.ts';

	type Future = { symbol: string; month: string; price: number };
	let {
		contract,
		futures,
		spot,
		onexposure
	}: {
		contract: ContractType | null;
		futures: Future[];
		spot: number | null;
		/** Payable gold in oz for the current selection; 0 when another metal is shown. */
		onexposure?: (oz: number) => void;
	} = $props();

	const PRECIOUS: EnumAllMetals[] = ['Au', 'Ag', 'Pd'];
	const GC_OZ = 100;

	let metal = $state<EnumAllMetals>('Au');
	let voyageDays = $state(DEFAULT_VOYAGE_DAYS);

	const metals = $derived(contract ? (Object.keys(contract.verify_mapping?.qp ?? {}) as EnumAllMetals[]) : []);
	const qp = $derived(contract ? qpFor(contract, metal) : undefined);

	// A new contract resets the metal to gold when it has a gold QP, and the period to the first declared option.
	$effect.pre(() => {
		if (metals.length && !metals.includes(metal)) metal = metals.includes('Au') ? 'Au' : metals[0];
	});
	let code = $derived<QPEnum>(qp?.period.val[0] ?? 'TBA');

	const rows = $derived(contract ? exposures(contract, metal, code, voyageDays) : []);
	const totalOz = $derived(rows.reduce((s, r) => s + r.payableOz, 0));
	const precious = $derived(PRECIOUS.includes(metal));
	const usesArrival = $derived(qp?.period.val.some((c) => parseQp(c)?.basis === 'arrival') ?? false);

	// Hedge each shipment with the first GC contract expiring in or after its pricing month.
	const hedgeFor = (month: string) => futures.find((f) => f.month >= month) ?? null;
	const hedged = $derived(
		metal === 'Au' ? rows.map((r) => ({ r, fut: r.window ? hedgeFor(r.window.month) : null })) : []
	);
	const valueUsd = $derived(hedged.reduce((s, { r, fut }) => s + r.payableOz * (fut?.price ?? spot ?? 0), 0));

	$effect(() => {
		onexposure?.(metal === 'Au' ? totalOz : 0);
	});

	const qty = (oz: number) => (precious ? `${fmtNum(oz, 0)} oz` : `${fmtNum((oz * G_PER_OZ) / 1e6, 1)} t`);
	const verifiedClass = (v: boolean | null | undefined) => (v ? 'text-good' : 'text-best');
</script>

{#if !contract}
	<div class="rounded-xl border border-dashed border-line p-8 text-center">
		<p class="font-display text-lg font-bold">No contract selected</p>
		<p class="mx-auto mt-2 max-w-lg text-sm text-ink-2">Connect to Open Mineral above and pick a contract to load its quotational period.</p>
	</div>
{:else if !metals.length}
	<p class="rounded-xl border border-line bg-panel p-6 text-sm text-ink-2">{contract.name} has no quotational period on record.</p>
{:else}
	<div class="rounded-xl border border-line bg-panel p-4 sm:p-5">
		<div class="flex flex-wrap items-start justify-between gap-4">
			<div class="min-w-0">
				<div class="text-xs text-ink-3">Contract #{contract.id} · {contract.verify_mapping?.delivery_terms.val}</div>
				<h3 class="font-display text-xl font-bold">{contract.name}</h3>
			</div>
			<div class="flex flex-wrap gap-1 rounded-lg bg-canvas p-1" role="group" aria-label="Metal">
				{#each metals as m (m)}
					<button
						class="rounded-md px-2.5 py-1 text-xs font-semibold transition {metal === m ? 'bg-mlh-yellow text-mlh-navy' : 'text-ink-2 hover:text-ink'}"
						onclick={() => (metal = m)}>{m}</button
					>
				{/each}
			</div>
		</div>

		{#if qp}
			<!-- QP terms as extracted from the contract -->
			<dl class="mt-4 grid gap-3 text-sm sm:grid-cols-3">
				{#each [{ k: 'Exchange', f: qp.exchange }, { k: 'Index', f: qp.index }] as row (row.k)}
					<div class="rounded-lg bg-canvas p-3">
						<dt class="flex justify-between text-xs text-ink-3">
							{row.k}<span class={verifiedClass(row.f.verified)}>p.{row.f.pg} · {row.f.verified ? 'verified' : 'unverified'}</span>
						</dt>
						<dd class="mt-1 font-semibold">{row.f.val}</dd>
					</div>
				{/each}
				<div class="rounded-lg bg-canvas p-3">
					<dt class="flex justify-between text-xs text-ink-3">
						Period{qp.period.val.length > 1 ? ' (declare one)' : ''}
						<span class={verifiedClass(qp.period.verified)}>p.{qp.period.pg} · {qp.period.verified ? 'verified' : 'unverified'}</span>
					</dt>
					<dd class="mt-1 flex flex-wrap gap-1.5">
						{#each qp.period.val as c (c)}
							<button
								class="rounded-full border px-2.5 py-0.5 text-xs font-semibold transition {code === c
									? 'border-mlh-blue bg-mlh-blue text-white'
									: 'border-line text-ink-2 hover:text-ink'}"
								onclick={() => (code = c)}>{c}</button
							>
						{/each}
					</dd>
				</div>
			</dl>
			{#if usesArrival}
				<label class="mt-3 flex items-center gap-2 text-xs text-ink-2">
					Voyage days (shipment → arrival, for MOAS)
					<input type="number" min="0" max="120" bind:value={voyageDays} class="w-20 rounded border border-line bg-panel px-2 py-1" />
				</label>
			{/if}
		{/if}

		<!-- Per-shipment pricing windows -->
		<div class="mt-5 overflow-x-auto">
			<table class="w-full min-w-[720px] text-sm tabular-nums">
				<thead class="text-xs text-ink-2">
					<tr class="border-b border-line">
						<th class="py-2 pr-3 text-left">Ship.</th>
						<th class="px-3 py-2 text-left">Shipment date</th>
						<th class="px-3 py-2 text-right">Weight</th>
						<th class="px-3 py-2 text-right">Grade</th>
						<th class="px-3 py-2 text-right">Payable</th>
						<th class="px-3 py-2 text-left">QP window</th>
						<th class="px-3 py-2 text-right">Pricing days</th>
						{#if metal === 'Au'}<th class="py-2 pl-3 text-right">Hedge</th>{/if}
					</tr>
				</thead>
				<tbody>
					{#each rows as r, i (r.shipNo + r.product)}
						{@const fut = hedged[i]?.fut}
						<tr class="border-b border-line" title={r.paymentRule}>
							<td class="py-2 pr-3 font-semibold">#{r.shipNo}</td>
							<td class="px-3 py-2 text-ink-2">{fmtDate(r.shipmentDate)}</td>
							<td class="px-3 py-2 text-right">{fmtNum(r.dmt, r.dmt < 10 ? 2 : 0)} dmt</td>
							<td class="px-3 py-2 text-right">{fmtNum(r.grade, 1)} {r.gradeUnits}</td>
							<td class="px-3 py-2 text-right font-semibold">{qty(r.payableOz)}</td>
							<td class="px-3 py-2">
								{#if r.window}
									<span class="font-semibold">{fmtMonth(r.window.month)}</span>
									<span class="text-xs text-ink-3">{fmtDate(r.window.start)} – {fmtDate(r.window.end)}</span>
								{:else}
									<span class="text-best">TBA</span>
								{/if}
							</td>
							<td class="px-3 py-2 text-right">{r.window?.pricingDays ?? '–'}</td>
							{#if metal === 'Au'}
								<td class="py-2 pl-3 text-right">
									{#if fut}
										Sell {fmtNum(r.payableOz / GC_OZ, 1)} {fut.symbol}
									{:else}
										<span class="text-ink-3">{r.window ? 'Beyond curve' : '–'}</span>
									{/if}
								</td>
							{/if}
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		<!-- Totals -->
		<div class="mt-5 grid gap-3 sm:grid-cols-3">
			<div class="rounded-lg bg-canvas p-3">
				<div class="text-xs text-ink-3">Payable {metal}</div>
				<div class="mt-1 text-2xl font-bold tabular-nums">{qty(totalOz)}</div>
			</div>
			{#if metal === 'Au'}
				<div class="rounded-lg bg-canvas p-3">
					<div class="text-xs text-ink-3">Value at QP-month futures</div>
					<div class="mt-1 text-2xl font-bold tabular-nums">${fmtNum(valueUsd / 1e6, 2)}m</div>
				</div>
				<div class="rounded-lg bg-canvas p-3">
					<div class="text-xs text-ink-3">Optimiser input <em>q</em></div>
					<div class="mt-1 text-2xl font-bold tabular-nums">{fmtNum(totalOz / GC_OZ, 1)} <span class="text-sm font-normal text-ink-3">GC lots</span></div>
				</div>
			{:else}
				<div class="rounded-lg bg-canvas p-3 sm:col-span-2 text-sm text-ink-2">
					The optimiser hedges gold only. Switch to Au to feed this contract into it.
				</div>
			{/if}
		</div>
		<p class="mt-3 text-xs text-ink-3">
			M±n counts from the shipment month, MOAS+n from the arrival month (shipment + voyage days), MOSS+n from the scheduled
			shipment month. Pricing days are weekdays; exchange holidays are not removed. Payable follows the contract's payment rule (hover a row).
		</p>
	</div>
{/if}
