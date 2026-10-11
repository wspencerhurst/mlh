import { parquetReadObjects } from 'hyparquet';
import type { Point } from '#lib/spot.ts';

export const GROUPS = [
	{ id: 'oil', label: 'Crude oil' },
	{ id: 'fuel', label: 'Fuels' },
	{ id: 'gas', label: 'Gas' },
	{ id: 'metal', label: 'Metals' },
	{ id: 'agri', label: 'Grain' }
] as const;
export type Group = (typeof GROUPS)[number]['id'];

export type CommodityMeta = { label: string; group: Group; unit: string };

// Short labels and units for display; the parquet's own `name`/`unit` columns are longer.
export const COMMODITIES: Record<string, CommodityMeta> = {
	WTI: { label: 'WTI crude', group: 'oil', unit: '$/bbl' },
	BRENT: { label: 'Brent crude', group: 'oil', unit: '$/bbl' },
	GASOLINE_US: { label: 'US gasoline', group: 'fuel', unit: '$/gal' },
	DIESEL_USGULF: { label: 'Diesel, US Gulf', group: 'fuel', unit: '$/gal' },
	HEATING_OIL_NYH: { label: 'Heating oil, NYH', group: 'fuel', unit: '$/gal' },
	JET_FUEL_USGULF: { label: 'Jet fuel, US Gulf', group: 'fuel', unit: '$/gal' },
	NATURAL_GAS: { label: 'Henry Hub gas', group: 'gas', unit: '$/MMBtu' },
	NATGAS_EU: { label: 'EU gas', group: 'gas', unit: '$/MMBtu' },
	LNG_ASIA: { label: 'Asia LNG', group: 'gas', unit: '$/MMBtu' },
	PROPANE_MBTX: { label: 'Propane', group: 'gas', unit: '$/gal' },
	ALUMINUM: { label: 'Aluminium', group: 'metal', unit: '$/t' },
	COPPER: { label: 'Copper', group: 'metal', unit: '$/t' },
	WHEAT: { label: 'Wheat', group: 'agri', unit: '$/t' }
};

// Validated for all-pairs separation (incl. colour-blind) on the navy chart surface; supports 3 series.
export const SLOT_COLORS = ['#3987e5', '#d95926', '#199e70'] as const;
export const MAX_SELECTED = SLOT_COLORS.length;

export type CommoditySeries = { code: string; interval: string; points: Point[] };
export type CommodityData = Record<string, CommoditySeries>;

function toMs(d: unknown): number {
	if (d instanceof Date) return d.getTime();
	if (typeof d === 'bigint') return Number(d / 1000n); // microseconds
	if (typeof d === 'number') return d > 1e14 ? d / 1000 : d;
	return Date.parse(String(d));
}

export async function loadCommodities(): Promise<CommodityData> {
	const res = await fetch('/data/commodities.parquet');
	if (!res.ok) throw new Error(`HTTP ${res.status} loading commodity prices`);
	const file = await res.arrayBuffer();
	const rows = (await parquetReadObjects({ file, columns: ['code', 'date', 'value', 'interval'] })) as Record<
		string,
		unknown
	>[];

	const out: CommodityData = {};
	for (const r of rows) {
		const code = String(r.code);
		if (!(code in COMMODITIES)) continue;
		(out[code] ??= { code, interval: String(r.interval), points: [] }).points.push({
			t: toMs(r.date),
			y: Number(r.value)
		});
	}
	for (const s of Object.values(out)) s.points.sort((a, b) => a.t - b.t);
	return out;
}

export function sliceFrom(points: Point[], start: number): Point[] {
	let i = 0;
	while (i < points.length && points[i].t < start) i++;
	return points.slice(i);
}

/** Indexed to 100 at the first point; skips non-positive bases (WTI went negative in April 2020). */
export function rebase(points: Point[]): Point[] {
	const base = points.find((p) => p.y > 0)?.y;
	return base ? points.map((p) => ({ t: p.t, y: (p.y / base) * 100 })) : [];
}
