<script lang="ts">
	let open = $state(false);
	let logoFailed = $state(false);
</script>

<section class="flex flex-col gap-4 rounded-2xl border border-line bg-panel p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between sm:p-5">
	<div class="flex min-w-0 items-center gap-4">
		<div class="grid h-16 w-36 shrink-0 place-items-center rounded-lg bg-white px-3">
			{#if logoFailed}
				<span role="img" aria-label="Athena logo" class="font-semibold text-black">Athena</span>
			{:else}
				<img
					src="/athena-mark.png"
					alt="Athena logo"
					width="467"
					height="200"
					class="h-11 w-full object-contain"
					onerror={() => (logoFailed = true)}
				/>
			{/if}
		</div>
		<div class="min-w-0">
			<div class="flex flex-wrap items-center gap-2">
				<p class="font-semibold">Contract source</p>
				<span class="rounded-full border border-warn/30 bg-warn-wash px-2 py-0.5 text-[11px] font-semibold text-warn">Not connected</span>
			</div>
			<p class="mt-1 max-w-xl text-sm leading-5 text-ink-2">Pull structured contract terms from Athena. Sample terms are pre-filled for this demo.</p>
		</div>
	</div>
	<button
		class="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-[#141414] transition hover:brightness-110"
		onclick={() => (open = true)}
	>
		Connect your account at Athena <span aria-hidden="true">→</span>
	</button>
</section>

{#if open}
	<dialog open aria-modal="true" aria-labelledby="athena-dialog-title" class="fixed inset-0 z-50 m-0 grid h-full w-full max-w-none place-items-center border-0 bg-black/70 p-4 backdrop:bg-black/70">
		<section class="w-full max-w-lg rounded-2xl border border-line bg-panel p-5 shadow-2xl sm:p-6">
			<div class="flex items-start justify-between gap-4">
				<div>
					<p class="text-xs font-semibold tracking-wide text-accent">Athena connection</p>
					<h2 id="athena-dialog-title" class="mt-2 font-display text-xl font-bold">Connect your account</h2>
				</div>
				<button class="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-line text-xl text-ink-2 hover:bg-canvas hover:text-ink" aria-label="Close Athena connection details" onclick={() => (open = false)}>×</button>
			</div>
			<p class="mt-4 text-sm leading-6 text-ink-2">A live Athena connection is not configured in this preview yet. The contract fields below are pre-filled with editable demo terms; no account has been connected.</p>
			<div class="mt-4 rounded-xl border border-line bg-canvas p-4">
				<p class="text-sm font-semibold">Continue with the demo contract</p>
				<p class="mt-1 text-xs leading-5 text-ink-3">Review the deal and settings, then run the analyzer. Athena import can be enabled once its connection details are available.</p>
			</div>
			<div class="mt-5 flex justify-end">
				<button class="min-h-10 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-[#141414] hover:brightness-110" onclick={() => (open = false)}>Continue with demo terms</button>
			</div>
		</section>
	</dialog>
{/if}
