import type { RequestHandler } from './$types';
import { authorize, getContract } from '#lib/server/openmineral/mock.ts';
import { respond } from '#lib/server/openmineral/respond.ts';

export const GET: RequestHandler = ({ request, params }) =>
	respond(() => {
		authorize(request.headers.get('authorization'));
		return getContract(Number(params.contract_id));
	});
