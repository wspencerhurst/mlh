import type { RequestHandler } from './$types';
import { authorize, listContracts } from '#lib/server/openmineral/mock.ts';
import { respond } from '#lib/server/openmineral/respond.ts';

export const GET: RequestHandler = ({ request, url }) =>
	respond(() => {
		authorize(request.headers.get('authorization'));
		const page = Math.max(1, Number(url.searchParams.get('page')) || 1);
		const size = Math.min(100, Math.max(1, Number(url.searchParams.get('size')) || 50));
		return listContracts(page, size);
	});
