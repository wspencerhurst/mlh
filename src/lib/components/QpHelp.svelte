<script lang="ts">
	let dialog = $state<HTMLDialogElement>();

	const CODES = [
		{ code: 'TBA', meaning: 'Not yet agreed. The pricing month is set later, usually by declaration before shipment. Exposure cannot be dated, so it is not hedged here.' },
		{ code: 'M', meaning: 'The calendar month of shipment (bill of lading date).' },
		{ code: 'M+n', meaning: 'n months after the shipment month. M+1 for a 10 Dec shipment prices over January.' },
		{ code: 'M−n', meaning: 'n months before the shipment month. Used when metal is priced ahead of loading, e.g. for long-term offtake.' },
		{ code: 'MOAS+n', meaning: 'n months after the month of arrival of the shipment at the discharge port. The contract has no ETA, so the analyser estimates arrival as shipment date + voyage days.' },
		{ code: 'MOSS+n', meaning: 'n months after the month of scheduled shipment. The analyser uses the shipment date as the scheduled date.' }
	];

	const CALCS = [
		{ name: 'Average', meaning: 'Final price is the arithmetic mean of the index on every pricing day in the QP month. The usual basis for concentrates.' },
		{ name: 'Single', meaning: 'Final price is the index on one day, normally the first or last pricing day of the QP, or a day the declaring party fixes.' },
		{ name: 'Part average', meaning: 'The quantity is split and each part is averaged over a different period (e.g. half over M+1, half over M+2). Spreads price risk across months.' }
	];

	const SOURCES = [
		{ name: 'LBMA Gold Price AM / PM', meaning: 'Twice-daily electronic auction in London, in USD/oz. The fixing is the benchmark for doré and concentrate gold payables.' },
		{ name: 'COMEX GC settlement', meaning: 'Daily settlement price of the CME gold future (100 oz). Contracts priced on COMEX can be hedged in the same instrument, leaving no basis between the contract price and the hedge.' },
		{ name: 'LME cash settlement', meaning: 'Official cash (spot) price for base metals (Cu, Zn, Pb, Ni). Shown for completeness; the optimiser hedges gold only.' }
	];
</script>

<button
	type="button"
	onclick={() => dialog?.showModal()}
	class="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 text-xs font-semibold text-ink-2 hover:text-ink"
	aria-haspopup="dialog"
>
	<span class="grid h-4 w-4 place-items-center rounded-full bg-canvas text-[10px]">?</span>QP guide
</button>

<dialog
	bind:this={dialog}
	onclick={(e) => e.target === dialog && dialog.close()}
	class="m-auto max-h-[85vh] w-[min(46rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-line bg-panel p-0 text-ink backdrop:bg-black/60"
	aria-labelledby="qp-help-title"
>
	<div class="sticky top-0 flex items-center justify-between border-b border-line bg-panel px-5 py-4">
		<h2 id="qp-help-title" class="font-display text-xl font-bold">Quotational periods</h2>
		<button type="button" onclick={() => dialog?.close()} class="rounded px-2 text-lg text-ink-2 hover:text-ink" aria-label="Close">×</button>
	</div>

	<div class="space-y-6 px-5 py-5 text-sm text-ink-2">
		<p>
			A quotational period (QP) is the window over which the metal in a physical contract is priced. The contract names
			an exchange and index (where the price comes from), one or more period codes (when), and a calculation type (how
			the daily prices become one final price). Each payable metal has its own QP.
		</p>

		<section>
			<h3 class="font-display text-base font-bold text-ink">Period codes</h3>
			<dl class="mt-2 divide-y divide-line rounded-lg border border-line">
				{#each CODES as c (c.code)}
					<div class="grid gap-1 px-3 py-2 sm:grid-cols-[6rem_1fr]">
						<dt class="font-mono font-semibold text-best">{c.code}</dt>
						<dd>{c.meaning}</dd>
					</div>
				{/each}
			</dl>
			<p class="mt-2 text-xs text-ink-3">
				Open Mineral stores the codes without definitions. The MOAS and MOSS meanings above are how this app reads them.
			</p>
		</section>

		<section>
			<h3 class="font-display text-base font-bold text-ink">Declaration</h3>
			<p class="mt-1">
				When a contract lists several codes (e.g. <span class="font-mono">M, M+1, M+2</span>), one party, usually the
				buyer, declares which one applies, by a deadline set in the contract and usually before shipment or before the
				earliest QP starts. Until then the exposure month is uncertain. In the analyser, pick a code to see the result of
				each declaration.
			</p>
		</section>

		<section>
			<h3 class="font-display text-base font-bold text-ink">Calculation types</h3>
			<dl class="mt-2 divide-y divide-line rounded-lg border border-line">
				{#each CALCS as c (c.name)}
					<div class="grid gap-1 px-3 py-2 sm:grid-cols-[6rem_1fr]">
						<dt class="font-semibold text-ink">{c.name}</dt>
						<dd>{c.meaning}</dd>
					</div>
				{/each}
			</dl>
			<p class="mt-2 text-xs text-ink-3">The analyser assumes Average over the whole QP month.</p>
		</section>

		<section>
			<h3 class="font-display text-base font-bold text-ink">Price sources</h3>
			<dl class="mt-2 divide-y divide-line rounded-lg border border-line">
				{#each SOURCES as s (s.name)}
					<div class="px-3 py-2">
						<dt class="font-semibold text-ink">{s.name}</dt>
						<dd class="mt-0.5">{s.meaning}</dd>
					</div>
				{/each}
			</dl>
		</section>

		<section>
			<h3 class="font-display text-base font-bold text-ink">How a contract settles</h3>
			<ol class="mt-2 list-decimal space-y-1.5 pl-5">
				<li>
					<strong class="text-ink">Shipment.</strong> The seller issues a provisional invoice, typically 90–95% of value,
					using a provisional price (often the recent index average) and provisional weights and assays.
				</li>
				<li>
					<strong class="text-ink">QP runs.</strong> The index is recorded on each pricing day (weekdays the exchange
					publishes a price).
				</li>
				<li>
					<strong class="text-ink">QP closes.</strong> The final price is calculated from the recorded prices using the
					calculation type.
				</li>
				<li>
					<strong class="text-ink">Final invoice.</strong> Final price × payable metal (from final weights and umpire or
					agreed assays, after the payment rule), less treatment and refining charges and penalties, minus the provisional
					payment. The balance is paid either way.
				</li>
			</ol>
		</section>

		<section>
			<h3 class="font-display text-base font-bold text-ink">How the hedge is executed</h3>
			<p class="mt-1">
				Price risk runs from when the contract quantity is fixed until the QP closes. A seller of gold-bearing material
				hedges by selling futures for the payable ounces, then closes the hedge as the QP prices the metal:
			</p>
			<ul class="mt-2 list-disc space-y-1.5 pl-5">
				<li>
					<strong class="text-ink">Average QP:</strong> buy back 1/n of the futures on each of the n pricing days, so the
					average buy-back price tracks the QP average.
				</li>
				<li><strong class="text-ink">Single-day QP:</strong> buy back the whole position on the pricing day.</li>
				<li><strong class="text-ink">Part average:</strong> size and unwind each part over its own period.</li>
			</ul>
			<p class="mt-2">
				The analyser sizes the hedge as payable ounces ÷ 100 oz per GC lot, in the first GC contract expiring in or after
				the QP month, so the position is still open while the QP prices. A buyer takes the opposite positions.
			</p>
		</section>
	</div>
</dialog>
