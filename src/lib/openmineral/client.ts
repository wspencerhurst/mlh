import type { ContractType, JWTTokenPair, Page } from './types.ts';

/** Same-origin mock of the backend. Point `baseUrl` at a real open-mineral deployment to use it instead. */
export const MOCK_BASE_URL = '/mock/open-mineral';

/**
 * Minimal browser client for the open-mineral backend: OAuth2 password login, then
 * bearer-authenticated reads from the gaia contract endpoints.
 */
export class OpenMineralClient {
	private token: string | null = null;

	constructor(readonly baseUrl: string) {}

	get connected() {
		return this.token !== null;
	}

	private async call<T>(path: string, init: RequestInit = {}): Promise<T> {
		const headers = new Headers(init.headers);
		if (this.token) headers.set('authorization', `Bearer ${this.token}`);
		const res = await fetch(this.baseUrl.replace(/\/$/, '') + path, { ...init, headers });
		const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
		if (!res.ok) {
			const detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? res.statusText);
			throw new Error(`${res.status} ${detail}`);
		}
		return body as T;
	}

	async login(username: string, password: string) {
		const form = new URLSearchParams({ grant_type: 'password', username, password });
		const pair = await this.call<JWTTokenPair>('/api/auth/login/', { method: 'POST', body: form });
		this.token = pair.access_token;
	}

	logout() {
		this.token = null;
	}

	listContracts(page = 1, size = 50) {
		return this.call<Page<ContractType>>(`/api/gaia/contracts?page=${page}&size=${size}`);
	}

	getContract(id: number) {
		return this.call<ContractType>(`/api/gaia/contract/${id}`);
	}
}
