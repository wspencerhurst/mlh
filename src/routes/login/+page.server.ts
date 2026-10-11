import { error, fail, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import {
	createSessionToken,
	getAuthSecrets,
	MISCONFIGURED_MESSAGE,
	safeEqual,
	safeRedirectTarget,
	setSessionCookie
} from '#lib/server/auth.ts';

export const load: PageServerLoad = ({ locals, url }) => {
	if (locals.authenticated) redirect(303, safeRedirectTarget(url.searchParams.get('redirectTo'), url.origin));
};

export const actions: Actions = {
	default: async ({ request, cookies, url }) => {
		const secrets = getAuthSecrets();
		if (!secrets) error(500, MISCONFIGURED_MESSAGE);

		const password = (await request.formData()).get('password');
		if (typeof password !== 'string' || !password) {
			return fail(400, { error: 'Enter the password.' });
		}
		if (!(await safeEqual(password, secrets.password))) {
			return fail(401, { error: 'Incorrect password.' });
		}

		setSessionCookie(cookies, await createSessionToken(secrets.sessionSecret));
		redirect(303, safeRedirectTarget(url.searchParams.get('redirectTo'), url.origin));
	}
};
