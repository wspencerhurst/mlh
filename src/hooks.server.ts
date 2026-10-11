import * as Sentry from '@sentry/sveltekit';
import { redirect } from '@sveltejs/kit';
import { sequence } from '@sveltejs/kit/hooks';
import type { Handle } from '@sveltejs/kit/hooks';
import { getAuthSecrets, MISCONFIGURED_MESSAGE, SESSION_COOKIE, verifySessionToken } from '#lib/server/auth.ts';
import { SENTRY_DSN } from '#lib/sentry.ts';

const PUBLIC_PATHS = new Set(['/login', '/logout']);

const authHandle: Handle = async ({ event, resolve }) => {
	const secrets = getAuthSecrets();
	if (!secrets) {
		// Fail closed: never let anyone in when the secrets are not configured.
		return new Response(MISCONFIGURED_MESSAGE, {
			status: 500,
			headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' }
		});
	}

	event.locals.authenticated = await verifySessionToken(secrets.sessionSecret, event.cookies.get(SESSION_COOKIE));

	const path = event.url.pathname.replace(/\/$/, '') || '/';
	if (!event.locals.authenticated && !PUBLIC_PATHS.has(path)) {
		const target = event.url.pathname + event.url.search;
		redirect(303, target === '/' ? '/login' : `/login?redirectTo=${encodeURIComponent(target)}`);
	}

	return resolve(event);
};

export const handle = sequence(
	Sentry.initCloudflareSentryHandle({
		dsn: SENTRY_DSN,
		environment: import.meta.env.MODE,
		tracesSampleRate: 1.0
	}),
	Sentry.sentryHandle(),
	authHandle
);

export const handleError = Sentry.handleErrorWithSentry();
