import type { ContractType, EnumAllMetals, MetalVerify, QPEnum, QuotationalPeriodVerify } from './types.ts';

export const G_PER_OZ = 31.1034768;

/** Days from shipment to arrival, used for MOAS codes. Contracts do not carry an ETA, so this is an assumption. */
export const DEFAULT_VOYAGE_DAYS = 35;

export type QpBasis = 'shipment' | 'arrival';

/** A calendar month in which the metal is priced, as UTC millis of the 1st and last day. */
export interface PricingWindow {
	code: QPEnum;
	basis: QpBasis;
	offset: number;
	month: string; // YYYY-MM
	start: number;
	end: number;
	pricingDays: number; // weekdays in the month; exchange holidays are ignored
}

export interface ShipmentExposure {
	shipNo: number;
	product: string;
	shipmentDate: number;
	dmt: number;
	grade: number;
	gradeUnits: string;
	paymentRule: string;
	payableGPerT: number;
	payableOz: number;
	window: PricingWindow | null; // null when the QP is TBA
}

const DAY = 86_400_000;

/** Parse a QP code. M±n counts from the shipment month, MOAS+n from the arrival month, MOSS+n from the scheduled shipment month. */
export function parseQp(code: QPEnum): { basis: QpBasis; offset: number } | null {
	if (code === 'TBA') return null;
	const m = code.match(/^(M|MOAS|MOSS)([+-]\d)?$/)!;
	return { basis: m[1] === 'MOAS' ? 'arrival' : 'shipment', offset: Number(m[2] ?? 0) };
}

export function resolveWindow(code: QPEnum, shipmentDate: number, voyageDays = DEFAULT_VOYAGE_DAYS): PricingWindow | null {
	const p = parseQp(code);
	if (!p) return null;
	const ref = new Date(shipmentDate + (p.basis === 'arrival' ? voyageDays * DAY : 0));
	const start = Date.UTC(ref.getUTCFullYear(), ref.getUTCMonth() + p.offset, 1);
	const s = new Date(start);
	const end = Date.UTC(s.getUTCFullYear(), s.getUTCMonth() + 1, 0);
	let pricingDays = 0;
	for (let t = start; t <= end; t += DAY) {
		const wd = new Date(t).getUTCDay();
		if (wd !== 0 && wd !== 6) pricingDays++;
	}
	return { code, basis: p.basis, offset: p.offset, month: s.toISOString().slice(0, 7), start, end, pricingDays };
}

/** Grade in grams per dry metric tonne. */
function gradeGPerT(amount: number, units: string): number | null {
	switch (units) {
		case 'g':
		case 'ppm':
			return amount;
		case 'oz':
			return amount * G_PER_OZ;
		case '%':
			return amount * 10_000;
		case 'kg':
			return amount * 1000;
		default:
			return null;
	}
}

/**
 * Payable grade from the payment rule text, e.g. "Pay 95.5% of Au, min deduction 1.5 g/dmt":
 * the lower of pct × grade and grade − deduction. A rule we cannot parse pays 100%.
 */
export function payableGrade(grade: number, rule: string): number {
	const pct = Number(rule.match(/([\d.]+)\s*%/)?.[1] ?? 100) / 100;
	const minDed = Number(rule.match(/min(?:imum)? deduction\s*([\d.]+)\s*g/i)?.[1] ?? 0);
	const threshold = Number(rule.match(/≥\s*([\d.]+)\s*g/)?.[1] ?? 0);
	if (grade < threshold) return 0;
	return Math.max(0, minDed ? Math.min(grade * pct, grade - minDed) : grade * pct);
}

export function exposures(
	contract: ContractType,
	metal: EnumAllMetals,
	code: QPEnum,
	voyageDays = DEFAULT_VOYAGE_DAYS
): ShipmentExposure[] {
	const vm = contract.verify_mapping;
	if (!vm) return [];
	return Object.values(vm.shipments).flatMap((s) =>
		Object.values(s.payables).flatMap((conc) => {
			const m: MetalVerify | undefined = conc.metals[metal];
			if (!m) return [];
			const dmt = Number(conc.weight.val);
			const grade = Number(m.amount.val);
			const g = gradeGPerT(grade, m.units.val);
			if (g === null || !isFinite(dmt)) return [];
			const payableGPerT = payableGrade(g, m.payment_rule.val);
			const shipmentDate = Date.parse(s.date.val);
			return [
				{
					shipNo: s.ship_no.val,
					product: conc.name.val,
					shipmentDate,
					dmt,
					grade,
					gradeUnits: m.units.val === '%' ? '%' : `${m.units.val}/dmt`,
					paymentRule: m.payment_rule.val,
					payableGPerT,
					payableOz: (dmt * payableGPerT) / G_PER_OZ,
					window: resolveWindow(code, shipmentDate, voyageDays)
				}
			];
		})
	);
}

export const qpFor = (contract: ContractType, metal: EnumAllMetals): QuotationalPeriodVerify | undefined =>
	contract.verify_mapping?.qp[metal];

export const fmtMonth = (month: string) =>
	new Date(`${month}-01T00:00:00Z`).toLocaleDateString('en-GB', { month: 'short', year: 'numeric', timeZone: 'UTC' });
