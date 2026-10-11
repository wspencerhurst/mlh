<script lang="ts">
	import katex from 'katex';

	let { tex, block = false }: { tex: string; block?: boolean } = $props();
	// Rendered to HTML on the server and in the browser; no client-side math pass needed.
	const html = $derived(katex.renderToString(tex, { displayMode: block, throwOnError: false, output: 'html' }));
</script>

<!-- KaTeX output of formulas written in this codebase, never user input -->
{#if block}
	<!-- eslint-disable-next-line svelte/no-at-html-tags -->
	<div class="overflow-x-auto py-1">{@html html}</div>
{:else}
	<!-- eslint-disable-next-line svelte/no-at-html-tags -->
	{@html html}
{/if}
