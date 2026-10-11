// Subset of the open-mineral backend schemas (Techarge/open-mineral openapi/openapi.json).
// Field names and enums are verbatim; schemas we do not read (wsmd, insurance, deductions…) are omitted.

export const QP_CODES = [
	'TBA',
	'M-6', 'M-5', 'M-4', 'M-3', 'M-2', 'M-1', 'M', 'M+1', 'M+2', 'M+3', 'M+4', 'M+5', 'M+6',
	'MOAS+1', 'MOAS+2', 'MOAS+3', 'MOAS+4', 'MOAS+5', 'MOAS+6',
	'MOSS+1', 'MOSS+2', 'MOSS+3', 'MOSS+4', 'MOSS+5', 'MOSS+6'
] as const;
export type QPEnum = (typeof QP_CODES)[number];
export type QPCalcEnum = 'single' | 'average' | 'part_average';
export type EnumAllMetals = 'Cu' | 'Zn' | 'Pb' | 'Sn' | 'Ni' | 'Ag' | 'Au' | 'Pd';
export type UnitsEnum =
	| 'unknown' | 'dmt' | 'wmt' | 'mt' | '%' | 'g' | 'kg' | 'lb' | 'oz' | 'ppm'
	| '$/oz' | '$/lb' | '$/g' | '$/kg' | '$/wmt' | '$/dmt';

export interface UserRef {
	email: string;
	name: string;
}

/** Verify[T]: a value extracted from the contract PDF, with its page number and verification state. */
export interface Verify<T> {
	val: T;
	pg: number;
	verified?: boolean | null;
	verified_date?: string | null;
	user?: UserRef | null;
}

export interface QuotationalPeriodVerify {
	exchange: Verify<string>;
	index: Verify<string>;
	period: Verify<QPEnum[]>;
	is_verified: boolean;
}

export interface MetalVerify {
	name: Verify<EnumAllMetals>;
	units: Verify<UnitsEnum>;
	amount: Verify<string>; // Decimal serialised as string
	xl_formula: Verify<string>;
	payment_rule: Verify<string>;
	is_verified: boolean;
}

export interface ConcentrateVerify {
	name: Verify<string>;
	metals: Partial<Record<EnumAllMetals, MetalVerify>>;
	weight: Verify<string>;
	units: Verify<UnitsEnum>;
	tolerance: Verify<number>;
	tolerance_units: Verify<UnitsEnum>;
	is_verified: boolean;
}

export interface ShipmentVerify {
	ship_no: Verify<number>;
	payables: Record<string, ConcentrateVerify>;
	date: Verify<string>; // ISO date of shipment
	is_verified: boolean;
}

export interface PartyVerify {
	name: Verify<string>;
	address: Verify<string>;
	contract: Verify<string>;
	is_verified: boolean;
}

export interface ContractVerifyType {
	buyer: PartyVerify;
	seller: PartyVerify;
	shipments: Record<string, ShipmentVerify>;
	qp: Partial<Record<EnumAllMetals, QuotationalPeriodVerify>>;
	price_payable: Verify<string>;
	delivery_terms: Verify<string>;
	is_verified: boolean;
}

export interface ContractType {
	id: number;
	created_at: string;
	updated_at: string;
	updated_by: UserRef | null;
	name: string;
	file: string | null;
	status: string;
	owned_by_trader: UserRef | null;
	owned_by_operator: UserRef | null;
	verify_mapping: ContractVerifyType | null;
}

export interface Page<T> {
	items: T[];
	total: number | null;
	page: number | null;
	size: number | null;
	pages?: number | null;
}

export interface JWTTokenPair {
	access_token: string;
	refresh_token: string;
}
