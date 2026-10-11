import { sentrySvelteKit } from '@sentry/sveltekit/vite';
import tailwindcss from '@tailwindcss/vite';
import adapter from '@sveltejs/adapter-cloudflare';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	assetsInclude: ['**/*.parquet'],
	plugins: [
		// Must come before sveltekit(). Source maps upload only when SENTRY_AUTH_TOKEN is set.
		sentrySvelteKit({
			org: 'mlh-yu',
			project: 'goldmine',
			adapter: 'cloudflare'
		}),
		tailwindcss(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			adapter: adapter()
		})
	]
});
