// Surface 2 of the UI-SPEC: the review page /apps/pii_redaction/review/{jobId}
// in every state of its state table, plus the first page of the placeholder
// copy, fetched over WebDAV and rendered in the backend container (surface 4).
//
// Real runs for ready (PDF, DOCX, ODT), copy being created and created, file
// changed, file deleted, download blocked afterwards and every "not
// available" (stranger, group folder ACL, share taken back). The queue, run,
// failure, expired and polling states are forged on a real job with values of
// the closed lists only (helpers.forgeState); their real path is ci/flow.sh
// and plan 17.
//
// Mandatory assertions: no file name in DOM, title and start state for "not
// available" and "deleted"; no-store on image and status, nosniff on the
// image; focus in #pii-review-state after "Create placeholder copy"; the
// canary PIIKANARIE7Q4XZ9 nowhere in the DOM; card text in
// var(--color-main-text); 16 px from status card to the next block; no
// horizontal scrolling at 320 px.
import { expect, test, type Page, type TestInfo } from '@playwright/test';
import {
	CANARY,
	DOCX,
	FILE_STEMS,
	ODT,
	PDF,
	baseJob,
	color,
	davDelete,
	davFreshFolder,
	davGet,
	davPut,
	fileId,
	fixture,
	forgeState,
	forgeStatus,
	gap,
	initialState,
	isEnglish,
	isFunctional,
	jobInReview,
	jobStatus,
	login,
	occ,
	projectUser,
	renderFirstPage,
	resolvedColor,
	reviewPath,
	screenshot,
	setShareDownload,
	share,
	showPng,
	sharer,
	unshare,
	upload,
	users,
	waitFor,
	workFolder,
	type Forged,
	type User,
} from './helpers';

const NEUTRAL_HEADING = /^(Review|Prüfung|Vérification)$/;
const STATE = '#pii-review-state';
const BACKEND_NOT_READY = /^(PII Redaction is not ready|PII Redaction ist gerade nicht bereit|PII Redaction n'est pas prêt)$/;

async function openReview(page: Page, jobId: number): Promise<number> {
	const response = await page.goto(reviewPath(jobId));
	await expect(page.locator('#pii-review h2')).toBeVisible();
	return response?.status() ?? 0;
}

/** The canary of the fixtures is never on the page: only the image shows content. */
async function expectNoCanary(page: Page): Promise<void> {
	expect(await page.content()).not.toContain(CANARY);
}

/** No file name in the DOM, the document title or the start state. */
async function expectNoFileName(page: Page): Promise<void> {
	const content = await page.content();
	const title = await page.evaluate(() => document.title);
	const state = JSON.stringify(await initialState(page));
	for (const stem of FILE_STEMS) {
		expect(content).not.toContain(stem);
		expect(title).not.toContain(stem);
		expect(state).not.toContain(stem);
	}
	expect(await initialState(page)).not.toHaveProperty('fileName');
	await expect(page.locator('#pii-review h2')).toHaveText(NEUTRAL_HEADING);
}

/** Text in the cards keeps the main text colour, never the muted grey. */
async function expectCardText(page: Page): Promise<void> {
	const root = page.locator('#pii-review');
	const main = await resolvedColor(root, '--color-main-text');
	const muted = await resolvedColor(root, '--color-text-maxcontrast');
	const texts = page.locator('#pii-review .pii-note__title:visible, #pii-review .pii-note__text:visible');
	const count = await texts.count();
	expect(count).toBeGreaterThan(0);
	for (let i = 0; i < count; i++) {
		expect(await color(texts.nth(i))).toBe(main);
		if (main !== muted) {
			expect(await color(texts.nth(i))).not.toBe(muted);
		}
	}
}

// -- forged states (closed lists) ---------------------------------------------

type ForgedShot = { state: string; forged: Forged; check?: (page: Page) => Promise<void> };

// One picture per reason of the UI-SPEC table; check_error stands for
// "any other reason" (it has no sentence of its own).
const FAILURE_REASONS = [
	'render_failed',
	'out_of_memory',
	'repeatedly_stuck',
	'backend_state_lost',
	'target_not_writable',
	'check_error',
] as const;

const FORGED: ForgedShot[] = [
	{ state: 'warteschlange-als-naechstes', forged: { status: 'queued', stage: 'waiting', ahead: 0 } },
	{ state: 'warteschlange-n-davor', forged: { status: 'queued', stage: 'waiting', ahead: 3 } },
	{
		state: 'warteschlange-backend-nicht-bereit',
		forged: { status: 'queued', stage: 'waiting', ahead: 0, backendReady: false },
		check: async (page) => {
			// 16 px from the status area to the next block (UI-SPEC, spacing md).
			const next = page.locator(`${STATE} + *`);
			await expect(next).toBeVisible();
			expect(Math.abs((await gap(page.locator(STATE), next)) - 16)).toBeLessThanOrEqual(1);
		},
	},
	{ state: 'lauf-waiting', forged: { status: 'analyzing', stage: 'waiting' } },
	{ state: 'lauf-fetching', forged: { status: 'analyzing', stage: 'fetching' } },
	{ state: 'lauf-converting', forged: { status: 'analyzing', stage: 'converting' } },
	{
		state: 'lauf-rendering',
		forged: { status: 'analyzing', stage: 'rendering', pagesDone: 1, pagesTotal: 2 },
		check: async (page) => {
			await expect(page.locator('#pii-review [role="progressbar"], #pii-review progress').first()).toBeVisible();
		},
	},
	...FAILURE_REASONS.map((reason) => ({
		state: `fehlgeschlagen-${reason}`,
		forged: { status: 'failed', reason } as Forged,
		check: expectCardText,
	})),
	{ state: 'abgelaufen', forged: { status: 'expired', reason: null }, check: expectCardText },
	{
		state: 'bereit-backend-nicht-bereit',
		forged: { status: 'review', backendReady: false },
		check: async (page) => {
			await expect(page.getByText(BACKEND_NOT_READY)).toBeVisible();
			await expect(page.locator('#pii-placeholder')).toBeDisabled();
			await expect(page.locator('#pii-review img')).toHaveCount(0);
		},
	},
];

test('Prüfseite: Warteschlange, Lauf, Fehlgründe und Abgelaufen (geschlossene Liste)', async ({ page }, testInfo) => {
	const who = projectUser(testInfo);
	const jobId = await baseJob(who, testInfo);
	await login(page, who);

	for (const shot of FORGED) {
		await page.unrouteAll({ behavior: 'wait' });
		await forgeState(page, jobId, shot.forged);
		expect(await openReview(page, jobId)).toBe(200);
		if (shot.forged.status === 'review') {
			// UI-SPEC Fläche 2, Aufbau: in "ready" the status area holds neither
			// a line nor a card; the backend warning (5) and the placeholder
			// card (6) follow it.
			await expect(page.locator(STATE)).toBeEmpty();
		} else {
			await expect(page.locator(STATE)).not.toBeEmpty();
		}
		await shot.check?.(page);
		await expectNoCanary(page);
		await screenshot(page, 'pruefseite', shot.state, testInfo);
	}
});

test('Prüfseite: Stand nicht aktualisiert (503) und Sitzung abgelaufen (401)', async ({ page }, testInfo) => {
	const who = projectUser(testInfo);
	const jobId = await baseJob(who, testInfo);
	await login(page, who);

	await forgeState(page, jobId, { status: 'queued', stage: 'waiting', ahead: 0 });
	await forgeStatus(page, jobId, 503);
	await openReview(page, jobId);
	await expect(page.getByText(/Status not updated|Stand nicht aktualisiert|État non mis à jour/)).toBeVisible();
	await screenshot(page, 'pruefseite', 'stand-nicht-aktualisiert', testInfo);

	await page.unrouteAll({ behavior: 'wait' });
	await forgeState(page, jobId, { status: 'queued', stage: 'waiting', ahead: 0 });
	await forgeStatus(page, jobId, 401);
	await openReview(page, jobId);
	await expect(page.getByText(/session has expired|Sitzung ist abgelaufen|session a expiré/)).toBeVisible();
	await expect(page.getByRole('button', { name: /Reload page|Seite neu laden|Recharger la page/ })).toBeVisible();
	await screenshot(page, 'pruefseite', 'sitzung-abgelaufen', testInfo);
});

// -- real runs ---------------------------------------------------------------------

test('Prüfseite bereit mit Seite 1 für PDF, DOCX und ODT', async ({ page }, testInfo) => {
	const who = projectUser(testInfo);
	const folder = workFolder(testInfo, 'ready');
	await davFreshFolder(who, folder);
	const jobs: Array<[string, number]> = [['pdf', await baseJob(who, testInfo)]];
	for (const [kind, name] of [['docx', DOCX], ['odt', ODT]] as const) {
		jobs.push([kind, await jobInReview(who, await upload(who, folder, name))]);
	}
	await login(page, who);

	for (const [kind, jobId] of jobs) {
		expect(await openReview(page, jobId)).toBe(200);
		const image = page.locator('#pii-review img');
		await expect(image).toBeVisible();
		const alt = (await image.getAttribute('alt')) ?? '';
		for (const stem of FILE_STEMS) {
			expect(alt).not.toContain(stem);
		}
		await expect(page.locator('#pii-placeholder')).toBeEnabled();
		await expectNoCanary(page);
		await expectCardText(page);
		await screenshot(page, 'pruefseite', `bereit-${kind}`, testInfo);
	}

	if (isFunctional(testInfo)) {
		const jobId = jobs[0][1];
		// Status and image: private, no-store; the image also nosniff.
		const status = await jobStatus(who, jobId);
		expect(status.cacheControl).toContain('no-store');
		const picture = await page.request.get(`${reviewPath(jobId)}/page/1`);
		expect(picture.status()).toBe(200);
		expect(picture.headers()['cache-control'] ?? '').toContain('no-store');
		expect(picture.headers()['x-content-type-options']).toBe('nosniff');
		expect(picture.headers()['content-type']).toContain('image/png');

		// 320 px (400 % zoom): no horizontal scrolling besides the image.
		await openReview(page, jobId);
		await page.setViewportSize({ width: 320, height: 900 });
		await expect(page.locator('#pii-review img')).toBeVisible();
		const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
		expect(overflow).toBeLessThanOrEqual(0);
	}
});

test('Prüfseite: Seite 1 nicht abrufbar (Bild 502)', async ({ page }, testInfo) => {
	const who = projectUser(testInfo);
	const jobId = await baseJob(who, testInfo);
	await login(page, who);
	await page.route(new RegExp(`/apps/pii_redaction/review/${jobId}/page/1(\\?.*)?$`), (route) => route.fulfill({ status: 502, body: '' }));

	await openReview(page, jobId);
	await expect(page.getByRole('button', { name: /Load again|Erneut laden|Recharger$/ })).toBeVisible();
	await expect(page.locator('#pii-review img')).toHaveCount(0);
	await expectCardText(page);
	await screenshot(page, 'pruefseite', 'seite-nicht-abrufbar', testInfo);
});

test('Prüfseite: Kopie wird angelegt, Kopie angelegt, erste Seite der Kopie', async ({ page }, testInfo) => {
	const who = projectUser(testInfo);
	const folder = workFolder(testInfo, 'copy');
	await davFreshFolder(who, folder);
	const jobId = await jobInReview(who, await upload(who, folder, PDF));
	await login(page, who);
	await openReview(page, jobId);

	await page.locator('#pii-placeholder').click();
	// Focus moves to the new status line (UI-SPEC, Fokuspunkte).
	await expect(page.locator(STATE)).toBeFocused();
	await expect(page.locator(`${STATE} .pii-review__line`)).toBeVisible();
	await expect(page.locator('#pii-placeholder')).toHaveCount(0);
	await screenshot(page, 'pruefseite', 'kopie-wird-angelegt', testInfo);

	const done = await waitFor(who, jobId, ['published'], true);
	await expect(page.locator(`${STATE} .pii-note__title`)).toBeVisible({ timeout: 30_000 });
	await expect(page.locator(STATE)).toContainText(done.outputName ?? '');
	await expectCardText(page);
	await expectNoCanary(page);
	await screenshot(page, 'pruefseite', 'kopie-angelegt', testInfo);

	// The first page of the copy: fetched over WebDAV as the user, rendered in
	// the backend container (the CI instance has no PDF preview provider).
	expect(done.outputFileId).not.toBeNull();
	expect(done.outputName).not.toBeNull();
	const copy = await davGet(who, `${folder}/${done.outputName as string}`);
	expect(new TextDecoder().decode(copy.subarray(0, 5))).toBe('%PDF-');
	expect(new TextDecoder('latin1').decode(copy)).not.toContain(CANARY);
	await showPng(page, renderFirstPage(copy));
	await screenshot(page, 'kopie', 'erste-seite', testInfo);
});

test('Prüfseite: Original geändert (WebDAV-PUT nach review)', async ({ page }, testInfo) => {
	const who = projectUser(testInfo);
	const folder = workFolder(testInfo, 'stale');
	await davFreshFolder(who, folder);
	const jobId = await jobInReview(who, await upload(who, folder, PDF));
	const changed = new Uint8Array([...fixture(PDF), ...new TextEncoder().encode('%changed\n')]);
	await davPut(who, `${folder}/${PDF}`, changed);
	await waitFor(who, jobId, ['stale']);

	await login(page, who);
	expect(await openReview(page, jobId)).toBe(200);
	await expect(page.locator('#pii-review img')).toHaveCount(0);
	await expectCardText(page);
	await screenshot(page, 'pruefseite', 'original-geaendert', testInfo);
	if (isFunctional(testInfo)) {
		expect((await page.request.get(`${reviewPath(jobId)}/page/1`)).status()).toBe(409);
	}
});

test('Prüfseite: Original gelöscht (WebDAV-DELETE), kein Dateiname', async ({ page }, testInfo) => {
	const who = projectUser(testInfo);
	const folder = workFolder(testInfo, 'deleted');
	await davFreshFolder(who, folder);
	const jobId = await jobInReview(who, await upload(who, folder, PDF));
	await davDelete(who, `${folder}/${PDF}`);
	// The status route cannot tell "deleted" from "not allowed" and answers
	// 404 once the file is gone (JobController::show, Recheck::Missing); only
	// the review page shows the initiator cancelled(original_deleted) with 200.
	const status = await jobStatus(who, jobId);
	expect(status.code).toBe(404);
	expect(status.cacheControl).toContain('no-store');

	await login(page, who);
	// 404 until the delete listener has ended the job, then 200.
	await expect.poll(async () => (await page.request.get(reviewPath(jobId))).status()).toBe(200);
	expect(await openReview(page, jobId)).toBe(200);
	const start = await initialState(page);
	expect(start.status).toBe('cancelled');
	expect(start.reason).toBe('original_deleted');
	await expectNoFileName(page);
	await expectCardText(page);
	await screenshot(page, 'pruefseite', 'original-geloescht', testInfo);
});

test('Prüfseite: Download nachträglich gesperrt', async ({ page }, testInfo) => {
	const who = projectUser(testInfo);
	const owner = sharer(testInfo);
	const folder = workFolder(testInfo, 'later-blocked');
	await davFreshFolder(owner, folder);
	const id = await upload(owner, folder, PDF);
	const shared = await share(owner, `${folder}/${PDF}`, { with: who, download: true });
	try {
		const jobId = await jobInReview(who, id);
		await setShareDownload(owner, shared.id, false);

		await login(page, who);
		expect(await openReview(page, jobId)).toBe(200);
		await expect(page.locator('#pii-review img')).toHaveCount(0);
		await expect(page.locator('#pii-placeholder')).toHaveCount(0);
		await expectCardText(page);
		await screenshot(page, 'pruefseite', 'download-gesperrt', testInfo);
		if (isFunctional(testInfo)) {
			expect((await page.request.get(`${reviewPath(jobId)}/page/1`)).status()).toBe(403);
		}
	} finally {
		await unshare(owner, shared.id);
	}
});

// -- not available ---------------------------------------------------------------------

/** The viewer of a job of alice that is not alice: bob in the alice projects, else the project user. */
function viewerOfForeign(testInfo: TestInfo): User {
	const who = projectUser(testInfo);
	return who.name === 'alice' ? users.bob() : who;
}

async function expectUnavailable(page: Page, jobId: number, testInfo: TestInfo, state: string): Promise<void> {
	expect(await openReview(page, jobId)).toBe(404);
	await expectNoFileName(page);
	await expect(page.locator('#pii-review time')).toHaveCount(0);
	await expectCardText(page);
	await screenshot(page, 'pruefseite', state, testInfo);
}

test('Prüfseite nicht verfügbar: fremder Nutzer', async ({ page }, testInfo) => {
	const jobId = await baseJob(users.alice(), testInfo);
	await login(page, viewerOfForeign(testInfo));
	await expectUnavailable(page, jobId, testInfo, 'nicht-verfuegbar-fremd');
	if (isFunctional(testInfo)) {
		// Status and image refuse the stranger as well, without a name.
		const status = await jobStatus(users.bob(), jobId);
		expect(status.code).toBe(404);
		expect((await page.request.get(`${reviewPath(jobId)}/page/1`)).status()).toBe(404);
	}
});

test('Prüfseite nicht verfügbar: Freigabe entzogen', async ({ page }, testInfo) => {
	const who = projectUser(testInfo);
	const owner = sharer(testInfo);
	const folder = workFolder(testInfo, 'revoked');
	await davFreshFolder(owner, folder);
	const id = await upload(owner, folder, PDF);
	const shared = await share(owner, `${folder}/${PDF}`, { with: who, download: true });
	let open = true;
	try {
		const jobId = await jobInReview(who, id);
		await unshare(owner, shared.id);
		open = false;
		await login(page, who);
		await expectUnavailable(page, jobId, testInfo, 'nicht-verfuegbar-freigabe-entzogen');
	} finally {
		if (open) {
			await unshare(owner, shared.id);
		}
	}
});

test('Prüfseite nicht verfügbar: carol nach ACL -read im Gruppenordner', async ({ page }, testInfo) => {
	// carol's language is English; the German and French projects show the
	// same page through "stranger" and "share taken back".
	test.skip(!isEnglish(testInfo), 'carol is an English user');
	const alice = users.alice();
	const carol = users.carol();
	const sub = `pw-${testInfo.project.name}`;
	await davFreshFolder(alice, `Akten/${sub}`);
	// carol reads the file through the group folder, starts and reaches review;
	// then the ACL takes read away from her on that subfolder.
	const jobId = await jobInReview(carol, await upload(alice, `Akten/${sub}`, PDF));
	occ('groupfolders:permissions', String(fileId('GROUP_FOLDER_ID')), '--user', 'carol', sub, '--', '-read');

	await login(page, carol);
	await expectUnavailable(page, jobId, testInfo, 'nicht-verfuegbar-acl');
});
