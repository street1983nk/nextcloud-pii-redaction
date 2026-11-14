// Shared pieces of the acceptance specs (UI-SPEC, "Prüfvertrag"): users and
// file ids of ci/seed.sh, login, the job API as a user, WebDAV, the background
// job round, the readiness rules before a picture and the picture itself.
//
// No fixed waits anywhere: web-first assertions, waitForResponse and
// expect.poll only. Answers forged with page.route carry values of the closed
// lists below only (T-01-16-03); the real path of every state is proven by
// ci/flow.sh and the check scripts of plan 17.
import { expect, request, type APIRequestContext, type Locator, type Page, type TestInfo } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export const APP_PATH = '/index.php/apps/pii_redaction';
export const ADMIN_PATH = '/index.php/settings/admin/pii_redaction';
export const FILES_PATH = '/index.php/apps/files/files';
export const CANARY = 'PIIKANARIE7Q4XZ9';

/** The fixtures of ci/make_fixtures.py and the stems that must never leak. */
export const PDF = 'Bescheid 2026-114.pdf';
export const DOCX = 'Antrag.docx';
export const ODT = 'Vermerk.odt';
export const TXT = 'notes.txt';
export const FILE_STEMS = ['Bescheid 2026-114', 'Antrag', 'Vermerk'] as const;

// -- closed lists (php/lib/Model, UI-SPEC) -----------------------------------

// Mirrors of php/lib/Model/{Status,Stage,Reason}.php; the contract test
// backend/tests/test_playwright_contract.py compares them value by value.
export const STATUSES = [
	'queued',
	'analyzing',
	'review',
	'submitted',
	'approved',
	'applying',
	'verified',
	'published',
	'failed',
	'stale',
	'cancelled',
	'expired',
] as const;
export const STAGES = [
	'waiting',
	'fetching',
	'converting',
	'rendering',
	'done',
] as const;
export const REASONS = [
	'encrypted_pdf',
	'unsupported_format',
	'too_many_pages',
	'out_of_memory',
	'repeatedly_stuck',
	'leak_detected',
	'check_error',
	'original_changed',
	'original_deleted',
	'target_not_writable',
	'backend_state_lost',
	'download_blocked',
	'not_readable',
	'render_failed',
	'backend_unavailable',
] as const;
export type JobStatus = (typeof STATUSES)[number];
export type JobStage = (typeof STAGES)[number];
export type JobReason = (typeof REASONS)[number];

// -- users --------------------------------------------------------------------

export type User = { name: string; password: string };

function env(name: string): string {
	const value = process.env[name];
	if (value === undefined || value === '') {
		throw new Error(`${name} is not set; the specs run after ci/seed.sh in CI only`);
	}
	return value;
}

export function user(name: string): User {
	return { name, password: name === 'admin' ? env('ADMIN_PASS') : env('CI_PASS') };
}

export const users = {
	admin: (): User => user('admin'),
	alice: (): User => user('alice'),
	bob: (): User => user('bob'),
	carol: (): User => user('carol'),
	dora: (): User => user('dora'),
};

/** The user of a project: alice, dora (high contrast), elke, fleur or greta. */
export function projectUser(testInfo: TestInfo): User {
	const name = testInfo.project.metadata?.user;
	if (typeof name !== 'string' || name === '') {
		throw new Error(`project ${testInfo.project.name} names no user`);
	}
	return user(name);
}

export function language(testInfo: TestInfo): 'en' | 'de' | 'fr' | 'de-du' {
	return testInfo.project.metadata?.language;
}

/** Checks that need no picture per project run once, in en-w1280-light. */
export function isFunctional(testInfo: TestInfo): boolean {
	return testInfo.project.metadata?.functional === true;
}

export function isEnglish(testInfo: TestInfo): boolean {
	return language(testInfo) === 'en';
}

/** Somebody else who shares a file with the project user. */
export function sharer(testInfo: TestInfo): User {
	return projectUser(testInfo).name === 'alice' ? users.dora() : users.alice();
}

/** A user without any access to a job of the project user. */
export function stranger(testInfo: TestInfo): User {
	return projectUser(testInfo).name === 'alice' ? users.bob() : users.alice();
}

/** The suffix of the copy by the language of the initiator (UI-SPEC area 4), NFC. */
export function copySuffix(testInfo: TestInfo): string {
	switch (language(testInfo)) {
		case 'de':
		case 'de-du':
			return '_geschwärzt'.normalize('NFC');
		case 'fr':
			return '_caviardé'.normalize('NFC');
		default:
			return '_redacted';
	}
}

// -- ci/out -------------------------------------------------------------------

const OUT = fileURLToPath(new URL('../out/', import.meta.url));

/** The file ids ci/seed.sh wrote to ci/out/fileids.env. */
export function fileIds(): Record<string, number> {
	const path = `${OUT}fileids.env`;
	if (!existsSync(path)) {
		throw new Error('ci/out/fileids.env is missing, run ci/seed.sh first');
	}
	const ids: Record<string, number> = {};
	for (const line of readFileSync(path, 'utf8').split('\n')) {
		const match = /^([A-Z_]+)=(\d+)\s*$/.exec(line);
		if (match !== null) {
			ids[match[1]] = Number(match[2]);
		}
	}
	return ids;
}

export function fileId(name: string): number {
	const id = fileIds()[name];
	if (id === undefined) {
		throw new Error(`${name} is not in ci/out/fileids.env`);
	}
	return id;
}

/** The bytes of one fixture of ci/make_fixtures.py. */
export function fixture(name: string): Uint8Array {
	return readFileSync(`${OUT}fixtures/${name}`);
}

/** One round of the background jobs (PublishJob is a QueuedJob, cron mode). */
export function cronRound(): void {
	try {
		execFileSync('php', ['-f', `${env('NC_ROOT')}/cron.php`], { stdio: 'ignore', timeout: 120_000 });
	} catch {
		// A round that ends with an error is retried by the next poll.
	}
}

/** occ as the CI runner (the group folder ACL step of the rights picture). */
export function occ(...args: string[]): void {
	execFileSync('php', [`${env('NC_ROOT')}/occ`, ...args], { stdio: 'ignore', timeout: 120_000 });
}

// -- HTTP as a user -------------------------------------------------------------

/**
 * A request context with basic auth and OCS-APIRequest: without a session
 * cookie Nextcloud skips the CSRF check of the app routes (ci/lib.sh).
 */
export async function api(who: User): Promise<APIRequestContext> {
	return request.newContext({
		baseURL: process.env.NC_URL ?? 'http://localhost:8080',
		httpCredentials: { username: who.name, password: who.password, send: 'always' },
		extraHTTPHeaders: { 'OCS-APIRequest': 'true', Accept: 'application/json' },
	});
}

export async function withApi<T>(who: User, run: (context: APIRequestContext) => Promise<T>): Promise<T> {
	const context = await api(who);
	try {
		return await run(context);
	} finally {
		await context.dispose();
	}
}

function davPath(who: User, path: string): string {
	const encoded = path
		.normalize('NFC')
		.split('/')
		.filter((part) => part !== '')
		.map((part) => encodeURIComponent(part))
		.join('/');
	return `/remote.php/dav/files/${encodeURIComponent(who.name)}/${encoded}`;
}

/**
 * The bytes as a Node Buffer: Playwright sends only a Buffer as raw body and
 * serialises every other Uint8Array (TextEncoder, new Uint8Array) as JSON.
 */
function rawBody(bytes: Uint8Array): Uint8Array {
	return Buffer.isBuffer(bytes) ? bytes : Buffer.from(bytes);
}

export async function davPut(who: User, path: string, bytes: Uint8Array): Promise<void> {
	await withApi(who, async (context) => {
		const response = await context.put(davPath(who, path), { data: rawBody(bytes) as never });
		expect([201, 204]).toContain(response.status());
	});
}

/** The bytes of one file as the user reads them over WebDAV. */
export async function davGet(who: User, path: string): Promise<Uint8Array> {
	return withApi(who, async (context) => {
		const response = await context.get(davPath(who, path));
		expect(response.status()).toBe(200);
		return response.body();
	});
}

const PNG_MAGIC = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

// Page 1 of a PDF read from stdin, as PNG on stdout. Nextcloud has no PDF
// preview provider without Imagick and Ghostscript, so the CI instance renders
// the copy in the backend container instead (UI-SPEC, picture "Platzhalter-Kopie":
// fetch over WebDAV, render in the container).
const RENDER_FIRST_PAGE = [
	'import sys, pymupdf',
	'with pymupdf.open(stream=sys.stdin.buffer.read(), filetype="pdf") as d:',
	'    sys.stdout.buffer.write(d[0].get_pixmap(dpi=110).tobytes("png"))',
].join('\n');

/** Shows a PNG alone on the page, decoded and complete, for its picture. */
export async function showPng(page: Page, png: Uint8Array): Promise<void> {
	let binary = '';
	for (const byte of png) {
		binary += String.fromCharCode(byte);
	}
	await page.setContent(`<img id="pii-copy-page" alt="" src="data:image/png;base64,${btoa(binary)}">`);
	const image = page.locator('#pii-copy-page');
	await expect.poll(() => image.evaluate((element: HTMLImageElement) => element.complete && element.naturalWidth > 0)).toBe(true);
}

/** Page 1 of a PDF as PNG, rendered in the backend container of the CI run. */
export function renderFirstPage(pdf: Uint8Array): Uint8Array {
	const png = execFileSync('docker', ['exec', '-i', env('EXAPP_CONTAINER'), '/app/.venv/bin/python', '-I', '-c', RENDER_FIRST_PAGE], {
		input: rawBody(pdf),
		stdio: ['pipe', 'pipe', 'ignore'],
		timeout: 120_000,
		maxBuffer: 64 * 1024 * 1024,
	}) as Uint8Array;
	expect(Array.from(png.subarray(0, PNG_MAGIC.length))).toEqual(PNG_MAGIC);
	return png;
}

export async function davDelete(who: User, path: string): Promise<void> {
	await withApi(who, async (context) => {
		const response = await context.delete(davPath(who, path));
		expect([204, 404]).toContain(response.status());
	});
}

/** A fresh, empty folder: removed first, so a repeated run starts clean. */
export async function davFreshFolder(who: User, path: string): Promise<void> {
	await davDelete(who, path);
	const parts = path.split('/').filter((part) => part !== '');
	await withApi(who, async (context) => {
		for (let i = 1; i <= parts.length; i++) {
			const response = await context.fetch(davPath(who, parts.slice(0, i).join('/')), { method: 'MKCOL' });
			expect([201, 405]).toContain(response.status());
		}
	});
}

const PROPFIND = '<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns"><d:prop><oc:fileid/><d:getetag/></d:prop></d:propfind>';

/** File id and etag of one path, or null when the user cannot see it. */
export async function davStat(who: User, path: string): Promise<{ fileId: number; etag: string } | null> {
	return withApi(who, async (context) => {
		const response = await context.fetch(davPath(who, path), { method: 'PROPFIND', headers: { Depth: '0' }, data: PROPFIND });
		if (response.status() !== 207) {
			return null;
		}
		const body = await response.text();
		const id = /<oc:fileid>(\d+)<\/oc:fileid>/.exec(body);
		const etag = /<d:getetag>([^<]*)<\/d:getetag>/.exec(body);
		return id === null ? null : { fileId: Number(id[1]), etag: etag?.[1] ?? '' };
	});
}

/** The names in one folder, decoded, exactly as the server stores them. */
export async function davList(who: User, path: string): Promise<string[]> {
	return withApi(who, async (context) => {
		const response = await context.fetch(davPath(who, path), { method: 'PROPFIND', headers: { Depth: '1' }, data: PROPFIND });
		expect(response.status()).toBe(207);
		const body = await response.text();
		const own = decodeURIComponent(davPath(who, path)).replace(/\/$/, '');
		const names: string[] = [];
		for (const match of body.matchAll(/<d:href>([^<]*)<\/d:href>/g)) {
			const href = decodeURIComponent(match[1]).replace(/\/$/, '');
			if (href !== own) {
				names.push(href.slice(href.lastIndexOf('/') + 1));
			}
		}
		return names;
	});
}

/** Uploads one fixture into a folder and returns its file id. */
export async function upload(who: User, folder: string, name: string, bytes: Uint8Array = fixture(name)): Promise<number> {
	await davPut(who, `${folder}/${name}`, bytes);
	const stat = await davStat(who, `${folder}/${name}`);
	expect(stat).not.toBeNull();
	return (stat as { fileId: number }).fileId;
}

/** The working folder of one test in one project; the name stays out of every picture but the file list. */
export function workFolder(testInfo: TestInfo, slug: string): string {
	return `pw-${testInfo.project.name}/${slug}`;
}

// -- shares ---------------------------------------------------------------------

const SHARES = '/ocs/v2.php/apps/files_sharing/api/v1/shares';

export type Share = { id: number; token: string };

/** A user share (type 0) or a public link (type 3); download switch as share attribute. */
export async function share(owner: User, path: string, options: { with?: User; download: boolean }): Promise<Share> {
	return withApi(owner, async (context) => {
		const form: Record<string, string> = {
			path: `/${path}`,
			shareType: options.with === undefined ? '3' : '0',
			permissions: '1',
		};
		if (options.with !== undefined) {
			form.shareWith = options.with.name;
			form.attributes = JSON.stringify([{ scope: 'permissions', key: 'download', value: options.download }]);
		} else if (!options.download) {
			form.hideDownload = 'true';
		}
		const response = await context.post(`${SHARES}?format=json`, { form });
		expect(response.status()).toBe(200);
		const data = (await response.json()).ocs.data;
		return { id: Number(data.id), token: String(data.token ?? '') };
	});
}

export async function setShareDownload(owner: User, shareId: number, download: boolean): Promise<void> {
	await withApi(owner, async (context) => {
		const response = await context.put(`${SHARES}/${shareId}?format=json`, {
			form: { attributes: JSON.stringify([{ scope: 'permissions', key: 'download', value: download }]) },
		});
		expect(response.status()).toBe(200);
	});
}

export async function unshare(owner: User, shareId: number): Promise<void> {
	await withApi(owner, async (context) => {
		const response = await context.delete(`${SHARES}/${shareId}?format=json`);
		expect(response.status()).toBe(200);
	});
}

/** Adds a user to the admin group (the admin pictures in German and French). */
export async function ensureAdmin(who: User): Promise<void> {
	await withApi(users.admin(), async (context) => {
		const response = await context.post(`/ocs/v2.php/cloud/users/${encodeURIComponent(who.name)}/groups?format=json`, { form: { groupid: 'admin' } });
		expect(response.status()).toBe(200);
	});
}

// -- jobs -------------------------------------------------------------------------

export type JobAnswer = { code: number; jobId: number | null; ahead: number | null; reason: string | null };

export async function startJob(who: User, id: number): Promise<JobAnswer> {
	return withApi(who, async (context) => {
		const response = await context.post(`${APP_PATH}/api/v1/jobs`, { data: { fileId: id } });
		const body = await response.json().catch(() => ({}));
		return {
			code: response.status(),
			jobId: typeof body.jobId === 'number' ? body.jobId : null,
			ahead: typeof body.ahead === 'number' ? body.ahead : null,
			reason: typeof body.reason === 'string' ? body.reason : null,
		};
	});
}

export type JobView = { status: JobStatus; stage: string | null; reason: string | null; outputFileId: number | null; outputName: string | null } & Record<string, unknown>;

export async function jobStatus(who: User, jobId: number): Promise<{ code: number; body: JobView | null; cacheControl: string }> {
	return withApi(who, async (context) => {
		const response = await context.get(`${APP_PATH}/api/v1/jobs/${jobId}`);
		const body = response.status() === 200 ? ((await response.json()) as JobView) : null;
		return { code: response.status(), body, cacheControl: response.headers()['cache-control'] ?? '' };
	});
}

/**
 * Polls the status of a job until it reaches one of the targets. With
 * withCron, every poll runs one background job round first (publishing).
 */
export async function waitFor(who: User, jobId: number, targets: JobStatus[], withCron = false): Promise<JobView> {
	let last: JobView | null = null;
	await expect
		.poll(
			async () => {
				if (withCron) {
					cronRound();
				}
				const { code, body } = await jobStatus(who, jobId);
				expect(code).toBe(200);
				last = body;
				return body?.status ?? '';
			},
			{ timeout: 180_000, intervals: [1_000, 2_000] },
		)
		.toMatch(new RegExp(`^(${targets.join('|')})$`));
	return last as unknown as JobView;
}

/** A job of the user on the file, run until review. */
export async function jobInReview(who: User, id: number): Promise<number> {
	const answer = await startJob(who, id);
	expect([200, 201]).toContain(answer.code);
	expect(answer.jobId).not.toBeNull();
	await waitFor(who, answer.jobId as number, ['review']);
	return answer.jobId as number;
}

/** Placeholder copy requested over the API and published by the background job. */
export async function publish(who: User, jobId: number): Promise<JobView> {
	await withApi(who, async (context) => {
		const response = await context.post(`${APP_PATH}/review/${jobId}/placeholder`);
		expect(response.status()).toBe(202);
	});
	return waitFor(who, jobId, ['published'], true);
}

/**
 * A job in review that a test may show in any forged state: one per project
 * user, on a PDF in its own folder. Starting again on the same file and etag
 * returns the open job (200), so every test of the project shares it.
 */
export async function baseJob(who: User, testInfo: TestInfo): Promise<number> {
	const folder = `pw-base-${who.name}`;
	let stat = await davStat(who, `${folder}/${PDF}`);
	if (stat === null) {
		await davFreshFolder(who, folder);
		await upload(who, folder, PDF);
		stat = await davStat(who, `${folder}/${PDF}`);
	}
	expect(stat, `base file of ${testInfo.project.name}`).not.toBeNull();
	return jobInReview(who, (stat as { fileId: number }).fileId);
}

// -- forged answers (closed lists only) -----------------------------------------

function inList<T extends string>(list: readonly T[], value: string | null | undefined, what: string): void {
	if (value !== null && value !== undefined && !list.includes(value as T)) {
		throw new Error(`${what} ${value} is not in the closed list`);
	}
}

export type Forged = {
	status: JobStatus;
	stage?: JobStage | null;
	reason?: JobReason | null;
	ahead?: number | null;
	pagesDone?: number | null;
	pagesTotal?: number | null;
	backendReady?: boolean;
};

function checkForged(forged: Forged): void {
	inList(STATUSES, forged.status, 'status');
	inList(STAGES, forged.stage, 'stage');
	inList(REASONS, forged.reason, 'reason');
}

function decodeBase64Utf8(value: string): string {
	const binary = atob(value);
	return new TextDecoder().decode(Uint8Array.from(binary, (char) => char.charCodeAt(0)));
}

function encodeBase64Utf8(value: string): string {
	let binary = '';
	for (const byte of new TextEncoder().encode(value)) {
		binary += String.fromCharCode(byte);
	}
	return btoa(binary);
}

const INITIAL_STATE = /(id="initial-state-pii_redaction-review"[^>]*value=")([^"]*)(")/;

/** The start state of the review page as the server rendered it. */
export async function initialState(page: Page): Promise<Record<string, unknown>> {
	const value = await page.locator('#initial-state-pii_redaction-review').getAttribute('value');
	expect(value).not.toBeNull();
	return JSON.parse(decodeBase64Utf8(value as string));
}

/**
 * Shows a real job of the user in a forged state: the review page of the
 * server is fetched for real, only the fields of its start state are swapped
 * for values of the closed lists, and the status route answers the same, so
 * the polling of open states holds still. The real path of these states is
 * proven by ci/flow.sh and plan 17 (UI-SPEC, readiness rule 5).
 */
export async function forgeState(page: Page, jobId: number, forged: Forged): Promise<void> {
	checkForged(forged);
	const fields = {
		status: forged.status,
		stage: forged.stage ?? null,
		reason: forged.reason ?? null,
		ahead: forged.ahead ?? null,
		pagesDone: forged.pagesDone ?? null,
		pagesTotal: forged.pagesTotal ?? null,
		backendReady: forged.backendReady ?? true,
	};
	await page.route(new RegExp(`/apps/pii_redaction/review/${jobId}(\\?.*)?$`), async (route) => {
		const response = await route.fetch();
		const html = await response.text();
		expect(html).toMatch(INITIAL_STATE);
		const body = html.replace(INITIAL_STATE, (_all, head: string, value: string, tail: string) => {
			const state = { ...JSON.parse(decodeBase64Utf8(value)), ...fields };
			if (forged.status !== 'review') {
				delete state.image;
			}
			return head + encodeBase64Utf8(JSON.stringify(state)) + tail;
		});
		await route.fulfill({ response, body });
	});
	await forgeStatus(page, jobId, fields);
}

/** The status route answers with fixed fields (or a fixed error code). */
export async function forgeStatus(page: Page, jobId: number, fields: Record<string, unknown> | number): Promise<void> {
	if (typeof fields !== 'number') {
		inList(STATUSES, fields.status as string, 'status');
		inList(STAGES, fields.stage as string | null, 'stage');
		inList(REASONS, fields.reason as string | null, 'reason');
	}
	await page.route(new RegExp(`/apps/pii_redaction/api/v1/jobs/${jobId}$`), async (route) => {
		if (typeof fields === 'number') {
			await route.fulfill({ status: fields, contentType: 'application/json', body: '{}', headers: { 'Cache-Control': 'private, no-store' } });
			return;
		}
		const response = await route.fetch();
		const real = response.ok() ? await response.json() : {};
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			headers: { 'Cache-Control': 'private, no-store' },
			body: JSON.stringify({ ...real, ...fields }),
		});
	});
}

// -- pages -------------------------------------------------------------------------

export function reviewPath(jobId: number): string {
	return `${APP_PATH}/review/${jobId}`;
}

export function folderPath(folder: string): string {
	return `${FILES_PATH}?dir=${encodeURIComponent(`/${folder}`)}`;
}

/** Fill the login form the page shows right now and wait until it is gone. */
export async function submitLogin(page: Page, who: User): Promise<void> {
	await page.locator('#user').fill(who.name);
	await page.locator('#password').fill(who.password);
	await page.locator('form[name="login"] [type="submit"], button[type="submit"]').first().click();
	await expect(page).not.toHaveURL(/\/login(\?|$)/);
}

export async function login(page: Page, who: User): Promise<void> {
	await page.goto('/index.php/login');
	await submitLogin(page, who);
}

/** The text colour a CSS variable resolves to inside an element. */
export async function resolvedColor(scope: Locator, variable: string): Promise<string> {
	return scope.evaluate((element, name) => {
		const probe = document.createElement('span');
		probe.style.color = `var(${name})`;
		element.appendChild(probe);
		const color = getComputedStyle(probe).color;
		probe.remove();
		return color;
	}, variable);
}

export async function color(element: Locator): Promise<string> {
	return element.evaluate((node) => getComputedStyle(node).color);
}

/** Vertical gap between the bottom of one element and the top of another. */
export async function gap(upper: Locator, lower: Locator): Promise<number> {
	const a = await upper.boundingBox();
	const b = await lower.boundingBox();
	expect(a).not.toBeNull();
	expect(b).not.toBeNull();
	return (b as { y: number }).y - ((a as { y: number; height: number }).y + (a as { height: number }).height);
}

/** Spinners the contract allows in a picture; they are masked, never waited out. */
function spinners(page: Page): Locator {
	return page.locator('.loading-icon:visible, .icon-loading:visible, .icon-loading-small:visible');
}

/**
 * Readiness before every picture (UI-SPEC "Bereitschaft"): fonts loaded,
 * every image in #pii-review complete, decoded and not empty, no aria-busy
 * left in the review area. Spinners that belong to the state stay and are
 * masked by screenshot().
 */
export async function ready(page: Page): Promise<void> {
	await page.evaluate(async () => {
		await document.fonts.ready;
	});
	const images = page.locator('#pii-review img');
	for (let i = 0; i < (await images.count()); i++) {
		const image = images.nth(i);
		await expect.poll(() => image.evaluate((element: HTMLImageElement) => element.complete && element.naturalWidth > 0)).toBe(true);
		await image.evaluate((element: HTMLImageElement) => element.decode());
	}
	await expect(page.locator('#pii-review [aria-busy="true"]')).toHaveCount(0);
}

/**
 * One picture per project, surface and state:
 * screenshots/<project>__<surface>__<state>.png.
 */
export async function screenshot(page: Page, surface: string, state: string, testInfo: TestInfo): Promise<void> {
	await ready(page);
	await page.screenshot({
		path: `screenshots/${testInfo.project.name}__${surface}__${state}.png`,
		fullPage: true,
		animations: 'disabled',
		caret: 'hide',
		mask: [spinners(page)],
	});
}

// -- toasts -----------------------------------------------------------------------

// @nextcloud/dialogs 8 (bundled by the app) renders a toast as a Vue
// component: role "alert" for errors (assertive), role "status" otherwise,
// CSS module classes _toast_<type>_<hash> and a close button (NcButton). The
// live regions of its container carry aria-live but no role, so they never
// match. There is no toastify any more.
const TOASTS = ':is([role="alert"], [role="status"])[class*="_toast_"]';

export type ToastKind = 'success' | 'info' | 'warning' | 'error';

function toasts(page: Page): Locator {
	return page.locator(TOASTS);
}

/** The newest toast once it is fully shown. */
export async function toast(page: Page): Promise<Locator> {
	const shown = toasts(page).last();
	await expect(shown).toBeVisible();
	await expect.poll(() => shown.evaluate((element) => getComputedStyle(element).opacity)).toBe('1');
	return shown;
}

/** Type of a toast: the role the library sets and its type class. */
export async function expectToastKind(shown: Locator, kind: ToastKind): Promise<void> {
	await expect(shown).toHaveAttribute('role', kind === 'error' ? 'alert' : 'status');
	await expect(shown).toHaveClass(new RegExp(`(^|\\s)_toast_${kind}_`));
}

/** The close button of a toast; the message itself holds no button. */
export function toastClose(shown: Locator): Locator {
	return shown.getByRole('button');
}

/** Closes every toast, so none reaches into the next picture. */
export async function closeToast(page: Page): Promise<void> {
	const all = toasts(page);
	for (let left = await all.count(); left > 0; left--) {
		await toastClose(all.first()).click();
		await expect(all).toHaveCount(left - 1);
	}
	await expect(all).toHaveCount(0);
}

// -- the Files app -------------------------------------------------------------------

export function row(page: Page, name: string): Locator {
	return page.locator(`[data-cy-files-list-row-name="${name}"]`);
}

/**
 * The toggle of the action menu of one row. Inline actions ("Restore" in the
 * trash bin, "Shared by ..." on a received share) stand in front of it in the
 * same cell, so the first button is not the menu. NcActions marks its trigger
 * with the class action-item__menutoggle.
 */
export function rowMenuToggle(entry: Locator): Locator {
	return entry.locator('[data-cy-files-list-row-actions] .action-item__menutoggle');
}

/** Opens the action menu of one row (UI-SPEC: data-cy-files-list-row-actions). */
export async function openRowMenu(page: Page, name: string): Promise<void> {
	const entry = row(page, name);
	await expect(entry).toBeVisible();
	await rowMenuToggle(entry).click();
	await expect(page.locator('[role="menu"]:visible').first()).toBeVisible();
}

/**
 * The action in the menu that is open now. A closed menu of an earlier row
 * stays in the DOM (hidden), so only the visible entry counts.
 */
export function startAction(page: Page): Locator {
	return page.locator('[data-cy-files-list-row-action="pii_redaction-start"]').filter({ visible: true });
}

/** The action label in the three languages (UI-SPEC area 1). */
export const ACTION_NAME = /^(Redact \/ pseudonymize|Schwärzen \/ Pseudonymisieren|Caviarder \/ pseudonymiser)$/;
