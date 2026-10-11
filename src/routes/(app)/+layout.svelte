<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

const NAV = [
	{ route: '/(app)/contracts', label: 'Contracts' },
	{ route: '/(app)/desk', label: 'Desk analytics' },
		{ route: '/(app)/spot', label: 'Spot' },
		{ route: '/(app)/commodities', label: 'Commodities' },
		{ route: '/(app)/futures', label: 'Futures' },
		{ route: '/(app)/trade', label: 'Trade' },
	{ route: '/(app)/trades', label: 'Trade blotter' },
		{ route: '/(app)/details', label: 'Details' }
	] as const;
	const LINKS = NAV.map((n) => ({ ...n, href: resolve(n.route) }));
	const active = (href: string) => page.url.pathname === href || (href !== '/' && page.url.pathname.startsWith(href + '/'));
</script>

<header class="sticky top-0 z-40 border-b border-line bg-panel/90 backdrop-blur">
	<!-- MLH tri-colour stripe -->
	<div class="flex h-1">
		<div class="flex-1 bg-mlh-red"></div>
		<div class="flex-1 bg-mlh-blue"></div>
		<div class="flex-1 bg-mlh-yellow"></div>
	</div>

	<div class="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3 sm:px-6">
		<a href={resolve('/(app)/contracts')} class="flex shrink-0 items-center gap-2 font-display text-xl font-bold tracking-tight">
			<span class="grid h-8 w-8 place-items-center rounded-md bg-mlh-yellow text-sm font-bold text-mlh-navy">Au</span>
			Goldmine
		</a>
	<nav class="ml-4 hidden flex-1 gap-1 text-sm lg:flex" aria-label="Main">
			{#each LINKS as item (item.href)}
				<a
					href={item.href}
					aria-current={active(item.href) ? 'page' : undefined}
					class="rounded-md px-3 py-1.5 transition {active(item.href)
						? 'bg-canvas font-semibold text-ink'
						: 'text-ink-2 hover:text-ink'}">{item.label}</a
				>
			{/each}
		</nav>
		<form method="POST" action="/logout" class="ml-auto shrink-0">
			<button class="rounded-lg border border-line px-3 py-1.5 text-sm text-ink-2 hover:text-ink">Sign out</button>
		</form>
	</div>

	<!-- Mobile: scrollable nav row -->
	<nav class="flex gap-1 overflow-x-auto px-4 pb-2 text-sm lg:hidden" aria-label="Main">
		{#each LINKS as item (item.href)}
			<a
				href={item.href}
				aria-current={active(item.href) ? 'page' : undefined}
				class="shrink-0 rounded-md px-3 py-1.5 {active(item.href) ? 'bg-canvas font-semibold text-ink' : 'text-ink-2'}"
				>{item.label}</a
			>
		{/each}
	</nav>
</header>

<main class="min-h-[70vh]">
	{@render children()}
</main>

<footer class="border-t border-line py-8 text-center text-xs text-ink-3">
	Built at AI Engineer NYC 2026 · Market data: Nimble · Monitoring: Sentry · Storage: Tiger Data · Analytics: Snowflake ·
	Execution: Checker demo · Contracts: Athena
</footer>
