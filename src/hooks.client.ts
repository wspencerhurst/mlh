import * as Sentry from '@sentry/sveltekit';
import { SENTRY_DSN } from '#lib/sentry.ts';

Sentry.init({
	dsn: SENTRY_DSN,
	environment: import.meta.env.MODE,
	tracesSampleRate: 1.0,
	// The SDK's SvelteKit browser tracing subscribes to `$app/stores`, which SvelteKit 3 removed: it throws
	// during start-up and stops the page from hydrating. Keep error reporting, drop that integration.
	integrations: (defaults) => defaults.filter((i) => i.name !== 'BrowserTracing')
});

export const handleError = Sentry.handleErrorWithSentry();
