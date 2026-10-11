import { env } from 'cloudflare:workers';
import type { Cookies } from '@sveltejs/kit';

export const SESSION_COOKIE = 'goldmine_session';
export const SESSION_TTL_SECONDS = 60 * 60 * 24 * 7; // 7 days

export interface AuthSecrets {
	password: string;
	sessionSecret: string;
}

/**
 * Read the auth secrets from the Worker env. SvelteKit 3's Cloudflare adapter does not
 * populate `event.platform`, so read them from `cloudflare:workers` (the adapter shims
 * this module in `vite dev`). Typed loosely on purpose: the generated `Env` only contains
 * APP_PASSWORD / SESSION_SECRET when a local `.dev.vars` exists, so this must type-check
 * either way. Returns null when either secret is missing.
 */
export function getAuthSecrets(): AuthSecrets | null {
	const vars = env as Partial<Record<'APP_PASSWORD' | 'SESSION_SECRET', unknown>> | undefined;
	const password = vars?.APP_PASSWORD;
	const sessionSecret = vars?.SESSION_SECRET;
	if (typeof password !== 'string' || !password) return null;
	if (typeof sessionSecret !== 'string' || !sessionSecret) return null;
	return { password, sessionSecret };
}

const encoder = new TextEncoder();

function toBase64Url(bytes: Uint8Array): string {
	let bin = '';
	for (const b of bytes) bin += String.fromCharCode(b);
	return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function fromBase64Url(s: string): Uint8Array<ArrayBuffer> | null {
	if (!/^[A-Za-z0-9_-]*$/.test(s)) return null;
	try {
		const bin = atob(s.replace(/-/g, '+').replace(/_/g, '/'));
		const out = new Uint8Array(bin.length);
		for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
		return out;
	} catch {
		return null;
	}
}

function hmacKey(secret: string, usage: 'sign' | 'verify'): Promise<CryptoKey> {
	return crypto.subtle.importKey('raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, [usage]);
}

/** Constant-time string comparison: hash both sides so lengths match, then compare every byte. */
export async function safeEqual(a: string, b: string): Promise<boolean> {
	const [ha, hb] = await Promise.all([
		crypto.subtle.digest('SHA-256', encoder.encode(a)),
		crypto.subtle.digest('SHA-256', encoder.encode(b))
	]);
	const x = new Uint8Array(ha);
	const y = new Uint8Array(hb);
	let diff = 0;
	for (let i = 0; i < x.length; i++) diff |= x[i] ^ y[i];
	return diff === 0;
}

/** Token format: base64url(JSON payload) + "." + base64url(HMAC-SHA256(payload)). */
export async function createSessionToken(secret: string, now = Date.now()): Promise<string> {
	const payload = toBase64Url(encoder.encode(JSON.stringify({ exp: Math.floor(now / 1000) + SESSION_TTL_SECONDS })));
	const sig = await crypto.subtle.sign('HMAC', await hmacKey(secret, 'sign'), encoder.encode(payload));
	return `${payload}.${toBase64Url(new Uint8Array(sig))}`;
}

export async function verifySessionToken(secret: string, token: string | undefined, now = Date.now()): Promise<boolean> {
	if (!token) return false;
	const parts = token.split('.');
	if (parts.length !== 2) return false;
	const [payload, sigText] = parts;
	const sig = fromBase64Url(sigText);
	if (!sig) return false;

	// crypto.subtle.verify compares the MAC in constant time
	const ok = await crypto.subtle.verify('HMAC', await hmacKey(secret, 'verify'), sig, encoder.encode(payload));
	if (!ok) return false;

	const raw = fromBase64Url(payload);
	if (!raw) return false;
	try {
		const { exp } = JSON.parse(new TextDecoder().decode(raw)) as { exp?: unknown };
		return typeof exp === 'number' && exp > Math.floor(now / 1000);
	} catch {
		return false;
	}
}

const cookieOptions = { path: '/', httpOnly: true, secure: true, sameSite: 'lax' } as const;

export function setSessionCookie(cookies: Cookies, token: string) {
	cookies.set(SESSION_COOKIE, token, { ...cookieOptions, maxAge: SESSION_TTL_SECONDS });
}

export function clearSessionCookie(cookies: Cookies) {
	cookies.delete(SESSION_COOKIE, cookieOptions);
}

/** Only allow same-origin relative paths ("/foo?bar"), never "//evil.com" or absolute URLs. */
export function safeRedirectTarget(value: string | null | undefined, origin: string): string {
	if (!value || !value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) return '/';
	try {
		const url = new URL(value, origin);
		if (url.origin !== origin) return '/';
		if (url.pathname === '/login' || url.pathname === '/logout') return '/';
		return url.pathname + url.search + url.hash;
	} catch {
		return '/';
	}
}

export const MISCONFIGURED_MESSAGE =
	'Server misconfigured: APP_PASSWORD and SESSION_SECRET must be set as Worker secrets. Access is denied until they are.';
