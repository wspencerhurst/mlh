<script lang="ts">
	import { ymAdd, ymLabel, optName, type Settings, type Terms } from '#lib/engine.ts';

	let {
		terms = $bindable(),
		settings = $bindable(),
		asof,
		unit,
		initialOpen = false,
		onreset
	}: {
		terms: Terms;
		settings: Settings;
		asof: string;
		unit: string;
		initialOpen?: boolean;
		onreset: () => void;
	} = $props();

	let open = $derived(initialOpen);
	const OFFSETS = [-1, 0, 1, 2, 3, 4];
	const asofYm = $derived(Number(asof.slice(0, 4)) * 100 + Number(asof.slice(5, 7)));
	const months = $derived(Array.from({ length: 10 }, (_, i) => ymAdd(asofYm, i + 1)));
	const premiumStep = $derived.by(() => {
		const sorted = [...terms.options].sort((a, b) => a.offset - b.offset);
		return sorted.length > 1 ? (sorted.at(-1)!.premium - sorted[0].premium) / (sorted.at(-1)!.offset - sorted[0].offset || 1) : 0;
	});

	function toggle(off: number) {
		const has = terms.options.some((o) => o.offset === off);
		let next = has ? terms.options.filter((o) => o.offset !== off) : [...terms.options, { name: optName(off), offset: off, premium: 0 }];
		if (!next.length) return;
		next = next.sort((a, b) => a.offset - b.offset);
		const lo = next[0].offset;
		next = next.map((o) => ({ ...o, premium: +(premiumStep * (o.offset - lo)).toFixed(4) }));
		terms = { ...terms, options: next, default_qp: next.some((o) => o.name === terms.default_qp) ? terms.default_qp : next[0].name };
	}
	function setPremium(v: number) {
		const lo = Math.min(...terms.options.map((o) => o.offset));
		terms = { ...terms, options: terms.options.map((o) => ({ ...o, premium: +(v * (o.offset - lo)).toFixed(4) })) };
	}

</script>

<div class="rounded-xl border border-line bg-panel shadow-sm">
	<button class="flex w-full items-center justify-between gap-3 px-5 py-3 text-left" onclick={() => (open = !open)} aria-expanded={open}>
		<span>
			<span class="font-display text-base font-bold">Deal &amp; settings</span>
			<span class="ml-2 text-sm text-ink-3">
				{(+terms.quantity).toLocaleString()} {unit} · delivery {ymLabel(terms.delivery)} · options {terms.options.map((o) => o.name).join(', ')} ·
				sale {terms.options.length ? optName(terms.sale_offset) : ''} average · funding +{(settings.funding_spread * 100).toFixed(2)}%
			</span>
		</span>
		<span class="text-sm text-accent">{open ? 'Hide' : 'Edit'}</span>
	</button>
	{#if open}
		<div class="grid gap-6 border-t border-line px-5 py-4 lg:grid-cols-[1.4fr_1fr]">
			<!-- Contract -->
			<div>
				<div class="flex flex-wrap items-baseline justify-between gap-2">
					<h3 class="text-sm font-semibold">Contract terms</h3>
				</div>

				<div class="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
					<label class="flex flex-col gap-1">
						<span class="text-xs text-ink-3">Delivery month (= M, not today)</span>
						<select id="t-delivery" class="rounded-md border border-line bg-panel px-2 py-1.5" bind:value={terms.delivery}>
							{#each months as k (k)}<option value={k}>{ymLabel(k)}</option>{/each}
						</select>
					</label>
					<label class="flex flex-col gap-1">
						<span class="text-xs text-ink-3">Quantity ({unit})</span>
						<input id="t-qty" type="number" min="1" step={unit === 'oz' ? 1000 : 50000} class="rounded-md border border-line px-2 py-1.5" bind:value={terms.quantity} />
					</label>
					<label class="flex flex-col gap-1">
						<span class="text-xs text-ink-3">Sale priced on</span>
						<select id="t-sale" class="rounded-md border border-line bg-panel px-2 py-1.5" bind:value={terms.sale_offset}>
							{#each OFFSETS as o (o)}<option value={o}>{optName(o)} ({ymLabel(ymAdd(terms.delivery, o))}) average</option>{/each}
						</select>
					</label>
				</div>

				<div class="mt-3 text-sm">
					<span class="text-xs text-ink-3">Quotation periods you may declare (months counted from delivery month M = {ymLabel(terms.delivery)})</span>
					<div class="mt-1 flex flex-wrap gap-1.5">
						{#each OFFSETS as o (o)}
							{@const on = terms.options.some((x) => x.offset === o)}
							<button
								class="rounded-md border px-2.5 py-1 text-xs font-semibold {on ? 'border-accent bg-accent-wash text-accent' : 'border-line text-ink-3 hover:text-ink'}"
								aria-pressed={on}
								onclick={() => toggle(o)}>{optName(o)} <span class="font-normal opacity-70">{ymLabel(ymAdd(terms.delivery, o))}</span></button
							>
						{/each}
					</div>
				</div>

				<div class="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
					<label class="flex flex-col gap-1">
						<span class="text-xs text-ink-3">Default if not declared</span>
						<select id="t-default" class="rounded-md border border-line bg-panel px-2 py-1.5" bind:value={terms.default_qp}>
							{#each terms.options as o (o.name)}<option value={o.name}>{o.name}</option>{/each}
						</select>
					</label>
					<label class="flex flex-col gap-1">
						<span class="text-xs text-ink-3">Sale differential ($/{unit})</span>
						<input id="t-sdiff" type="number" step="0.05" class="rounded-md border border-line px-2 py-1.5" bind:value={terms.sale_diff} />
					</label>
					<label class="flex flex-col gap-1">
						<span class="text-xs text-ink-3">Seller premium per later month ($/{unit})</span>
						<input id="t-prem" type="number" step="0.01" min="0" class="rounded-md border border-line px-2 py-1.5" value={+premiumStep.toFixed(4)} oninput={(e) => setPremium(+(e.currentTarget as HTMLInputElement).value || 0)} />
					</label>
					<label class="flex flex-col gap-1">
						<span class="text-xs text-ink-3">Declare by (business days before first QP)</span>
						<input id="t-dl" type="number" min="0" max="20" class="rounded-md border border-line px-2 py-1.5" bind:value={terms.deadline_bdays} />
					</label>
					<label class="flex flex-col gap-1">
						<span class="text-xs text-ink-3">Final payment</span>
						<select id="t-payrule" class="rounded-md border border-line bg-panel px-2 py-1.5" bind:value={terms.pay_rule}>
							<option value="after_qp">After the QP ends</option>
							<option value="after_delivery">After delivery</option>
						</select>
					</label>
					<label class="flex flex-col gap-1">
						<span class="text-xs text-ink-3">Payment lag (business days)</span>
						<input id="t-lag" type="number" min="0" max="60" class="rounded-md border border-line px-2 py-1.5" bind:value={terms.pay_lag} />
					</label>
					<label class="flex flex-col gap-1">
						<span class="text-xs text-ink-3">Provisional payment at arrival</span>
						<select id="t-prov" class="rounded-md border border-line bg-panel px-2 py-1.5" bind:value={terms.provisional_pct}>
							{#each [0, 0.5, 0.8, 0.9, 0.95] as p (p)}<option value={p}>{Math.round(p * 100)}%</option>{/each}
						</select>
					</label>
				</div>
			</div>

			<!-- Settings -->
			<div class="flex flex-col gap-4 lg:border-l lg:border-line lg:pl-6">
				<h3 class="text-sm font-semibold">Your settings</h3>
				<div class="grid grid-cols-2 gap-3 text-sm">
					<label class="flex flex-col gap-1">
						<span class="text-xs text-ink-3">Funding cost over T-bill (%)</span>
						<input
							id="s-fund"
							type="number"
							step="0.25"
							class="rounded-md border border-line px-2 py-1.5"
							value={+(settings.funding_spread * 100).toFixed(2)}
							oninput={(e) => (settings = { ...settings, funding_spread: (+(e.currentTarget as HTMLInputElement).value || 0) / 100 })}
						/>
					</label>
					<label class="flex flex-col gap-1">
						<span class="text-xs text-ink-3">Hedging cost ($/{unit}, per trade)</span>
						<input id="s-cost" type="number" step="0.005" min="0" class="rounded-md border border-line px-2 py-1.5" bind:value={settings.cost_per_unit} />
					</label>
				</div>
				<label class="flex items-center gap-2 text-sm">
					<input id="s-partial" type="checkbox" class="accent-accent" bind:checked={settings.partial} />
					<span>Allow partial or no hedge <span class="text-ink-3">(otherwise always hedge fully)</span></span>
				</label>
				<button class="self-start text-xs font-semibold text-ink-3 hover:text-ink" onclick={onreset}>Reset to defaults</button>
			</div>
		</div>
	{/if}
</div>
