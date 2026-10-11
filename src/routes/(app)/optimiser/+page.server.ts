import { redirect } from '@sveltejs/kit';

// The quotation-period desk at / replaces the earlier optimiser placeholder.
export const load = () => redirect(308, '/');
