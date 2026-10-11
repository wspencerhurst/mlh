import { desk } from '#lib/desk.ts';
import { evaluate, type MarketIn, type Rec, type Settings, type Terms } from '#lib/engine.ts';

export type MarketKey = 'gold' | 'crude';
export const FLOW_KEY = 'goldmine.contract-flow.v1';

export type ContractFlow = {
	market: MarketKey;
	terms: Terms;
	settings: Settings;
	result?: Rec;
};

export function marketInput(key: MarketKey): MarketIn | null {
	const source = desk?.markets[key];
	if (!source) return null;
	return {
		...source.live,
		product: source.product,
		theta: source.theta,
		policy_choice: source.policy_choice
	} as unknown as MarketIn;
}

export function defaultsFor(key: MarketKey): Pick<ContractFlow, 'terms' | 'settings'> | null {
	const market = desk?.markets[key];
	const input = marketInput(key);
	if (!market || !input) return null;
	const raw = market.live as unknown as { terms?: Terms; funding_spread?: number; cost_per_unit?: number };
	if (!raw.terms) return null;
	return {
		terms: structuredClone(raw.terms),
		settings: {
			lambda: market.lambda,
			funding_spread: raw.funding_spread ?? 0,
			cost_per_unit: raw.cost_per_unit ?? 0,
			partial: true
		}
	};
}

export function evaluateFlow(flow: ContractFlow): Rec | null {
	const input = marketInput(flow.market);
	return input ? evaluate(input, flow.terms, flow.settings) : null;
}

export function readFlow(): ContractFlow | null {
	try {
		const raw = sessionStorage.getItem(FLOW_KEY);
		if (!raw) return null;
		const parsed = JSON.parse(raw) as ContractFlow;
		return parsed && (parsed.market === 'gold' || parsed.market === 'crude') && parsed.terms && parsed.settings ? parsed : null;
	} catch {
		return null;
	}
}

export function writeFlow(flow: ContractFlow) {
	try {
		sessionStorage.setItem(FLOW_KEY, JSON.stringify(flow));
	} catch {
		// Session storage is an optional handoff for this browser-only demo.
	}
}
