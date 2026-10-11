import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { clearSessionCookie } from '#lib/server/auth.ts';

export const POST: RequestHandler = ({ cookies }) => {
	clearSessionCookie(cookies);
	redirect(303, '/login');
};
