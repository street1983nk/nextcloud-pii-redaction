// The few Node.js interfaces the specs use, declared here instead of pulling
// in @types/node: the package list of this suite stays at @playwright/test
// and typescript (plan 01 approval). Only what the helpers call.
declare module 'node:fs' {
	export function readFileSync(path: string, encoding: 'utf8'): string;
	export function readFileSync(path: string): Uint8Array;
	export function existsSync(path: string): boolean;
}

declare module 'node:child_process' {
	export function execFileSync(
		file: string,
		args: readonly string[],
		options?: { stdio?: 'ignore' | 'pipe' | Array<'ignore' | 'pipe'>; timeout?: number; encoding?: 'utf8'; input?: Uint8Array; maxBuffer?: number },
	): string | Uint8Array;
}

// Playwright sends request data as raw bytes only when Buffer.isBuffer(data)
// holds; any other Uint8Array goes out as JSON ({"0":37,...}).
declare const Buffer: {
	from(bytes: Uint8Array): Uint8Array;
	isBuffer(value: unknown): boolean;
};

declare module 'node:url' {
	export function fileURLToPath(url: string | URL): string;
}

declare const process: { env: Record<string, string | undefined> };
