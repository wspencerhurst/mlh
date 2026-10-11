<script lang="ts">
	import { enhance } from '$app/forms';
	import type { PageProps } from './$types';

	let { form }: PageProps = $props();
	let submitting = $state(false);
</script>

<svelte:head>
	<title>Sign in · Goldmine</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<!-- MLH tri-colour stripe -->
<div class="flex h-1">
	<div class="flex-1 bg-mlh-red"></div>
	<div class="flex-1 bg-mlh-blue"></div>
	<div class="flex-1 bg-mlh-yellow"></div>
</div>

<main class="mx-auto flex min-h-[calc(100vh-0.375rem)] max-w-3xl flex-col justify-center px-4 py-12 sm:px-6">
	<div class="mx-auto mb-8 flex w-full max-w-md items-center gap-2 font-display text-2xl font-bold tracking-tight">
		<span class="grid h-9 w-9 place-items-center rounded-md bg-mlh-yellow text-sm font-bold text-mlh-navy">Au</span>
		Goldmine
	</div>

	<div class="mb-8 aspect-video w-full overflow-hidden rounded-xl border border-line bg-black shadow-lg">
		<iframe
			src="/video/mlh-on-the-move.html"
			title="MLH On The Move, a music video by Team Smart Hedge"
			allow="autoplay; fullscreen"
			class="h-full w-full"
		></iframe>
	</div>

	<form
		method="POST"
		class="relative mx-auto w-full max-w-md overflow-hidden rounded-xl border border-line bg-panel p-6 shadow-sm"
		use:enhance={() => {
			submitting = true;
			return async ({ update }) => {
				await update();
				submitting = false;
			};
		}}
	>
		<div class="absolute inset-x-0 top-0 h-1 bg-mlh-yellow"></div>
		<h1 class="font-display text-xl font-bold">Sign in</h1>
		<p class="mt-1 text-sm text-ink-3">Enter the team password to open the desk.</p>

		<label for="password" class="mt-6 block text-sm font-medium text-ink-2">Password</label>
		<!-- svelte-ignore a11y_autofocus -->
		<input
			id="password"
			name="password"
			type="password"
			autocomplete="current-password"
			required
			autofocus
			aria-invalid={form?.error ? 'true' : undefined}
			aria-describedby={form?.error ? 'login-error' : undefined}
			class="mt-2 w-full rounded-lg border border-line bg-panel px-3 py-2.5 text-ink placeholder-ink-3 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
		/>

		{#if form?.error}
			<p id="login-error" role="alert" class="mt-4 rounded-lg border border-bad/30 bg-bad-wash px-3 py-2 text-sm text-bad">
				{form.error}
			</p>
		{/if}

		<button
			type="submit"
			disabled={submitting}
		class="mt-6 w-full rounded-lg bg-accent px-5 py-3 font-semibold text-[#141414] transition hover:brightness-110 disabled:opacity-60"
		>
			{submitting ? 'Signing in…' : 'Sign in'}
		</button>
	</form>

	<p class="mt-6 text-center text-xs text-ink-3">Built at AI Engineer NYC 2026 · MLH Hackathon</p>
</main>
