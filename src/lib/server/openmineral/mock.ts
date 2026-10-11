import type {
	ContractType,
	ContractVerifyType,
	EnumAllMetals,
	JWTTokenPair,
	Page,
	QPEnum,
	ShipmentVerify,
	UnitsEnum,
	Verify
} from '#lib/openmineral/types.ts';

// In-memory stand-in for the open-mineral backend (gaia contracts + auth).
// Credentials and data are fixed demo values; nothing here talks to the real system.

export const DEMO_USER = { username: 'trader@open-mineral.demo', password: 'demo' };
const TRADER = { email: DEMO_USER.username, name: 'Demo Trader' };
const OPERATOR = { email: 'ops@open-mineral.demo', name: 'Demo Operator' };
const VERIFIED_AT = '2026-09-02T10:15:00Z';

const v = <T>(val: T, pg: number, verified = true): Verify<T> => ({
	val,
	pg,
	verified,
	verified_date: verified ? VERIFIED_AT : null,
	user: verified ? OPERATOR : null
});

type Lot = { date: string; dmt: number; grades: Partial<Record<EnumAllMetals, [string, UnitsEnum, string]>> };

function shipments(product: string, lots: Lot[]): Record<string, ShipmentVerify> {
	return Object.fromEntries(
		lots.map((lot, i) => [
			String(i + 1),
			{
				ship_no: v(i + 1, 3),
				date: v(lot.date, 3),
				is_verified: true,
				payables: {
					[product]: {
						name: v(product, 4),
						weight: v(String(lot.dmt), 4),
						units: v('dmt' as UnitsEnum, 4),
						tolerance: v(10, 4),
						tolerance_units: v('%' as UnitsEnum, 4),
						is_verified: true,
						metals: Object.fromEntries(
							Object.entries(lot.grades).map(([metal, [amount, units, rule]]) => [
								metal,
								{
									name: v(metal as EnumAllMetals, 5),
									units: v(units, 5),
									amount: v(amount, 5),
									xl_formula: v('', 5, false),
									payment_rule: v(rule, 5),
									is_verified: true
								}
							])
						)
					}
				}
			}
		])
	);
}

const qp = (exchange: string, index: string, period: QPEnum[], verified = true) => ({
	exchange: v(exchange, 6, verified),
	index: v(index, 6, verified),
	period: v(period, 6, verified),
	is_verified: verified
});

function party(name: string, address: string, contract: string) {
	return { name: v(name, 1), address: v(address, 1), contract: v(contract, 1), is_verified: true };
}

const SEED: { name: string; status: string; created: string; mapping: ContractVerifyType }[] = [
	{
		name: 'OM-2026-014 Andina Cu/Au concentrate',
		status: 'verified',
		created: '2026-07-18T08:00:00Z',
		mapping: {
			seller: party('Minera Andina S.A.', 'Av. El Bosque 500, Santiago, Chile', 'OM-2026-014'),
			buyer: party('Pacific Smelting Co.', '2-1 Marunouchi, Tokyo, Japan', 'PSC-26-0331'),
			shipments: shipments('Copper concentrate', [
				{ date: '2026-09-22', dmt: 10_000, grades: { Cu: ['26.5', '%', 'Pay 96.5% of Cu, min deduction 1 unit'], Au: ['4.2', 'g', 'Pay 97% of Au if ≥ 1 g/dmt'] } },
				{ date: '2026-11-15', dmt: 12_000, grades: { Cu: ['25.8', '%', 'Pay 96.5% of Cu, min deduction 1 unit'], Au: ['3.9', 'g', 'Pay 97% of Au if ≥ 1 g/dmt'] } }
			]),
			qp: {
				Cu: qp('LME', 'LME Copper Cash Settlement', ['M+1', 'M+2', 'M+3']),
				Au: qp('LBMA', 'LBMA Gold Price PM', ['M+1', 'M+2', 'M+3'])
			},
			price_payable: v('Provisional 90% on B/L, final on QP close', 7),
			delivery_terms: v('CIF FO Onahama, Japan', 2),
			is_verified: true
		}
	},
	{
		name: 'OM-2026-021 Kivu gold doré',
		status: 'verified',
		created: '2026-08-04T12:30:00Z',
		mapping: {
			seller: party('Kivu Gold Refining SARL', 'Bukavu, DR Congo', 'OM-2026-021'),
			buyer: party('Alpine Precious Metals AG', 'Mendrisio, Switzerland', 'APM-2026-118'),
			shipments: shipments('Gold doré', [
				{ date: '2026-10-28', dmt: 0.12, grades: { Au: ['88.5', '%', 'Pay 99.9% of Au'], Ag: ['9.1', '%', 'Pay 95% of Ag'] } }
			]),
			qp: {
				Au: qp('LBMA', 'LBMA Gold Price AM', ['MOAS+1']),
				Ag: qp('LBMA', 'LBMA Silver Price', ['MOAS+1'])
			},
			price_payable: v('100% within 3 business days of QP close', 7),
			delivery_terms: v('DAP Mendrisio refinery', 2),
			is_verified: true
		}
	},
	{
		name: 'OM-2026-027 Nevada pyrite gold concentrate',
		status: 'verified',
		created: '2026-08-21T15:45:00Z',
		mapping: {
			seller: party('Great Basin Mining LLC', 'Elko, Nevada, USA', 'OM-2026-027'),
			buyer: party('Rhine Metals GmbH', 'Hamburg, Germany', 'RM-26-077'),
			shipments: shipments('Gold concentrate', [
				{ date: '2026-12-10', dmt: 2_500, grades: { Au: ['48', 'g', 'Pay 95.5% of Au, min deduction 1.5 g/dmt'], Ag: ['120', 'g', 'Pay 90% of Ag'] } },
				{ date: '2027-02-05', dmt: 2_500, grades: { Au: ['45', 'g', 'Pay 95.5% of Au, min deduction 1.5 g/dmt'], Ag: ['110', 'g', 'Pay 90% of Ag'] } }
			]),
			qp: {
				// Buyer declares one of these at shipment; the analyser lets you pick.
				Au: qp('COMEX', 'COMEX GC settlement', ['M', 'M+1', 'M+2']),
				Ag: qp('COMEX', 'COMEX SI settlement', ['M+1'])
			},
			price_payable: v('Provisional 95% on arrival', 7),
			delivery_terms: v('CFR Hamburg', 2),
			is_verified: true
		}
	},
	{
		name: 'OM-2026-033 Kalahari Cu/Au concentrate',
		status: 'pending verification',
		created: '2026-09-12T09:10:00Z',
		mapping: {
			seller: party('Kalahari Copper (Pty) Ltd', 'Ghanzi, Botswana', 'OM-2026-033'),
			buyer: party('Nordic Smelters AB', 'Rönnskär, Sweden', 'NS-2026-412'),
			shipments: shipments('Copper concentrate', [
				{ date: '2027-01-20', dmt: 8_000, grades: { Cu: ['28.1', '%', 'Pay 96.65% of Cu'], Au: ['2.6', 'g', 'Pay 90% of Au if ≥ 1 g/dmt'] } }
			]),
			qp: {
				Cu: qp('LME', 'LME Copper Cash Settlement', ['MOSS+2'], false),
				Au: qp('LBMA', 'LBMA Gold Price PM', ['MOSS+2', 'MOSS+3'], false)
			},
			price_payable: v('Provisional 90% on B/L', 7, false),
			delivery_terms: v('CIF FO Rönnskär', 2, false),
			is_verified: false
		}
	},
	{
		name: 'OM-2026-009 Pilbara zinc concentrate',
		status: 'verified',
		created: '2026-06-30T07:20:00Z',
		mapping: {
			seller: party('Pilbara Base Metals Pty', 'Port Hedland, Australia', 'OM-2026-009'),
			buyer: party('Korea Zinc Trading', 'Seoul, South Korea', 'KZ-26-201'),
			shipments: shipments('Zinc concentrate', [
				{ date: '2026-10-05', dmt: 15_000, grades: { Zn: ['52', '%', 'Pay 85% of Zn, min deduction 8 units'] } }
			]),
			qp: { Zn: qp('LME', 'LME Zinc Cash Settlement', ['M+1']) },
			price_payable: v('Provisional 90% on B/L', 7),
			delivery_terms: v('CFR Onsan', 2),
			is_verified: true
		}
	}
];

const CONTRACTS: ContractType[] = SEED.map((s, i) => ({
	id: 1001 + i,
	created_at: s.created,
	updated_at: s.mapping.is_verified ? VERIFIED_AT : s.created,
	updated_by: s.mapping.is_verified ? OPERATOR : null,
	name: s.name,
	file: `contracts/${s.mapping.seller.contract.val}.pdf`,
	status: s.status,
	owned_by_trader: TRADER,
	owned_by_operator: OPERATOR,
	verify_mapping: s.mapping
}));

/** Error shaped like FastAPI's ({ detail }), with the HTTP status the backend would return. */
export class OpenMineralError extends Error {
	constructor(
		readonly status: number,
		readonly detail: string
	) {
		super(detail);
	}
}

// Tokens are opaque to the client; the mock only checks the prefix so a restart does not log users out.
const TOKEN_PREFIX = 'om-mock.';

// POST /api/auth/login/
export function login(username: string, password: string): JWTTokenPair {
	if (username !== DEMO_USER.username || password !== DEMO_USER.password)
		throw new OpenMineralError(401, 'Incorrect username or password');
	const sub = btoa(username);
	return { access_token: `${TOKEN_PREFIX}${sub}.${crypto.randomUUID()}`, refresh_token: `${TOKEN_PREFIX}refresh.${crypto.randomUUID()}` };
}

export function authorize(header: string | null) {
	const token = header?.match(/^Bearer (.+)$/)?.[1];
	if (!token?.startsWith(TOKEN_PREFIX) || token.startsWith(`${TOKEN_PREFIX}refresh.`))
		throw new OpenMineralError(401, 'Not authenticated');
}

// GET /api/gaia/contracts?page=&size=
export function listContracts(page: number, size: number): Page<ContractType> {
	const items = CONTRACTS.slice((page - 1) * size, page * size);
	return { items, total: CONTRACTS.length, page, size, pages: Math.ceil(CONTRACTS.length / size) };
}

// GET /api/gaia/contract/{contract_id}
export function getContract(id: number): ContractType {
	const c = CONTRACTS.find((x) => x.id === id);
	if (!c) throw new OpenMineralError(404, 'Contract not found');
	return c;
}
