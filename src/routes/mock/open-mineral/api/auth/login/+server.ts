import type { RequestHandler } from './$types';
import { login } from '#lib/server/openmineral/mock.ts';
import { respond } from '#lib/server/openmineral/respond.ts';

// The backend's path ends in a slash; accept both forms.
export const trailingSlash = 'ignore';

// OAuth2 password flow: form-encoded username/password, returns a JWT pair.
export const POST: RequestHandler = async ({ request }) => {
	const form = await request.formData().catch(() => null);
	return respond(() => login(String(form?.get('username') ?? ''), String(form?.get('password') ?? '')));
};
