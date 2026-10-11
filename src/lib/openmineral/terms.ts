// Map an Open Mineral contract shipment onto the desk's contract terms (purchase side).
import type { Terms } from '../engine.ts';
import { ymAdd, ymLabel, optName } from '../engine.ts';
import { DEFAULT_VOYAGE_DAYS, exposures, qpFor } from './qp.ts';
import type { ContractType, QPEnum } from './types.ts';

export type Importable = {
	key: string; // `${contractId}:${shipNo}`
	contract: ContractType;
	shipNo: number;
	label: string; // short, for the picker
	detail: string; // one line under it
	terms: Terms | null; // null when it cannot be priced on the desk
	reason: string | null; // why not, if terms is null
	verified: boolean;
};

const ym = (t: number) => {
	const d = new Date(t);
	return d.getUTCFullYear() * 100 + d.getUTCMonth() + 1;
};

/** QP code -> month offset from the shipment month (MOAS counts from arrival, assumed DEFAULT_VOYAGE_DAYS later). */
function offsetFromShipment(code: QPEnum, shipMs: number): number | null {
	const m = code.match(/^(M|MOAS|MOSS)([+-]\d)?$/);
	if (!m) return null;
	const n = Number(m[2] ?? 0);
	if (m[1] === 'MOAS') {
		const a = ym(shipMs + DEFAULT_VOYAGE_DAYS * 86_400_000);
		const s = ym(shipMs);
		return n + (Math.floor(a / 100) - Math.floor(s / 100)) * 12 + (a % 100) - (s % 100);
	}
	return n; // M±n and MOSS±n count from the shipment month
}

/** "Provisional 95% on arrival" -> 0.95; "100% within 3 business days of QP close" -> 0 provisional, lag 3. */
function payment(text: string): { provisional: number; lag: number | null } {
	const prov = text.match(/provisional\s*(\d+(?:\.\d+)?)\s*%/i);
	const lag = text.match(/within\s*(\d+)\s*business days/i);
	return { provisional: prov ? Number(prov[1]) / 100 : 0, lag: lag ? Number(lag[1]) : null };
}

export function importables(contracts: ContractType[], base: Terms, asof: string): Importable[] {
	const asofYm = Number(asof.slice(0, 4)) * 100 + Number(asof.slice(5, 7));
	const out: Importable[] = [];
	for (const c of contracts) {
		const qp = qpFor(c, 'Au');
		const verified = !!c.verify_mapping?.is_verified;
		if (!qp) continue; // no gold in this contract
		const codes = qp.period.val.filter((p) => p !== 'TBA');
		const ex = exposures(c, 'Au', codes[0] ?? 'M');
		const pay = payment(c.verify_mapping?.price_payable.val ?? '');
		for (const e of ex) {
			const shipYm = ym(e.shipmentDate);
			const offs = [...new Set(codes.map((k) => offsetFromShipment(k, e.shipmentDate)).filter((x): x is number => x !== null))].sort((a, b) => a - b);
			const oz = Math.round(e.payableOz / 10) * 10;
			const firstQp = offs.length ? ymAdd(shipYm, offs[0]) : shipYm;
			let reason: string | null = null;
			if (!offs.length) reason = 'Quotation period to be agreed (TBA)';
			else if (firstQp <= asofYm) reason = `Pricing already started (${ymLabel(firstQp)})`;
			else if (oz <= 0) reason = 'No payable gold';
			const options = offs.map((o) => ({ name: optName(o), offset: o, premium: 0 }));
			const terms: Terms | null = reason
				? null
				: {
						...base,
						delivery: shipYm,
						quantity: oz,
						options,
						default_qp: options[0].name,
						sale_offset: options.some((o) => o.offset === base.sale_offset) ? base.sale_offset : options[0].offset,
						provisional_pct: pay.provisional,
						pay_rule: 'after_qp',
						pay_lag: pay.lag ?? base.pay_lag
					};
			out.push({
				key: `${c.id}:${e.shipNo}`,
				contract: c,
				shipNo: e.shipNo,
				label: `${c.name.split(' ')[0]} · shipment ${e.shipNo} · ${ymLabel(shipYm)}`,
				detail: `${c.name.replace(/^OM-\S+\s*/, '')} · ${oz.toLocaleString()} oz payable · QP ${codes.join(' / ')}${pay.provisional ? ` · ${Math.round(pay.provisional * 100)}% provisional` : ''}`,
				terms,
				reason,
				verified
			});
		}
	}
	return out;
}
