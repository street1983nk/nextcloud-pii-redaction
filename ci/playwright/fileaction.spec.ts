// Surface 1 of the UI-SPEC: the file action "Redact / pseudonymize" in the
// Files app and the toasts of its start, plus the placeholder copies in the
// file list (surface 4, name per language, collision " (2)").
//
// The action is offered for PDF, DOCX and ODT only, never for TXT, a folder,
// a multiple selection, the trash bin, a share with the download switched off
// or the public share page. Every start answer the server can give comes from
// the server itself where the test can reach it for real (first start, second
// click, download block, unreadable file, wrong format); "n ahead", "backend
// not ready" and the general error are forged with values of the closed list.
import { expect, test, type Page } from '@playwright/test';
import {
	ACTION_NAME,
	DOCX,
	ODT,
	PDF,
	TXT,
	baseJob,
	closeRowMenu,
	closeToast,
	copySuffix,
	davDelete,
	davFreshFolder,
	davList,
	davStat,
	expectToastKind,
	fileId,
	fixture,
	folderPath,
	isFunctional,
	jobInReview,
	login,
	openRowMenu,
	projectUser,
	publish,
	RESPONSE_TIMEOUT,
	row,
	rowMenuToggle,
	screenshot,
	share,
	sharer,
	startAction,
	startJob,
	toast,
	toastClose,
	unshare,
	upload,
	users,
	waitFor,
	workFolder,
} from './helpers';

const START_ROUTE = /\/apps\/pii_redaction\/api\/v1\/jobs$/;
const REVIEW_LINK = /\/apps\/pii_redaction\/review\/\d+$/;
const FILES_ROOT = '/index.php/apps/files/files?dir=/';

/** Opens a folder of the Files app and waits for its rows. */
async function openFolder(page: Page, folder: string, name: string): Promise<void> {
	await page.goto(folderPath(folder));
	await expect(row(page, name)).toBeVisible();
}

/**
 * Clicks the action on a row and returns the answer of the start route. The
 * click goes to the menu item itself (the li around it is presentation only)
 * and the answer has a deadline: a click that sends nothing fails here.
 */
async function clickStart(page: Page, name: string) {
	await openRowMenu(page, name);
	const action = startAction(page).getByRole('menuitem');
	await expect(action).toBeVisible();
	await expect(action).toBeEnabled();
	const answer = page.waitForResponse((response) => START_ROUTE.test(new URL(response.url()).pathname) && response.request().method() === 'POST', {
		timeout: RESPONSE_TIMEOUT,
	});
	await action.click();
	return answer;
}

async function expectNoAction(page: Page): Promise<void> {
	await expect(startAction(page)).toHaveCount(0);
	await expect(page.getByRole('menuitem', { name: ACTION_NAME })).toHaveCount(0);
}

test.describe('Dateiaktion: wo sie angeboten wird', () => {
	test('Menü offen für PDF, sichtbar für DOCX und ODT, nicht für TXT und Ordner', async ({ page }, testInfo) => {
		const who = projectUser(testInfo);
		const folder = workFolder(testInfo, 'menu');
		await davFreshFolder(who, `${folder}/Unterordner`);
		for (const name of [PDF, DOCX, ODT, TXT]) {
			await upload(who, folder, name);
		}
		await login(page, who);
		await openFolder(page, folder, PDF);

		await openRowMenu(page, PDF);
		await expect(startAction(page)).toBeVisible();
		await expect(startAction(page)).toHaveText(ACTION_NAME);
		await screenshot(page, 'dateien', 'menue-pdf', testInfo);
		await closeRowMenu(page);

		for (const name of [DOCX, ODT]) {
			await openRowMenu(page, name);
			await expect(startAction(page)).toBeVisible();
			await closeRowMenu(page);
		}
		for (const name of [TXT, 'Unterordner']) {
			await openRowMenu(page, name);
			await expectNoAction(page);
			await closeRowMenu(page);
		}
	});

	test('Mehrfachauswahl: kein Eintrag im Sammelmenü', async ({ page }, testInfo) => {
		test.skip(!isFunctional(testInfo), 'one functional run is enough');
		const who = projectUser(testInfo);
		const folder = workFolder(testInfo, 'multi');
		await davFreshFolder(who, folder);
		await upload(who, folder, PDF);
		await upload(who, folder, DOCX);
		await login(page, who);
		await openFolder(page, folder, PDF);

		for (const name of [PDF, DOCX]) {
			await row(page, name).locator('[data-cy-files-list-row-checkbox] input, [data-cy-files-list-row-checkbox]').first().click();
		}
		const selection = page.locator('[data-cy-files-list-selection-actions]');
		await expect(selection).toBeVisible();
		await expect(page.locator('[data-cy-files-list-selection-action="pii_redaction-start"]')).toHaveCount(0);
		// The overflow menu of the selection holds the rest of the batch actions.
		const more = selection.locator('button[aria-haspopup="menu"], .action-item__menutoggle').first();
		if ((await more.count()) > 0) {
			await more.click();
		}
		await expect(page.locator('[data-cy-files-list-selection-action="pii_redaction-start"]')).toHaveCount(0);
		await expect(page.getByRole('menuitem', { name: ACTION_NAME })).toHaveCount(0);
	});

	test('Papierkorb: kein Eintrag', async ({ page }, testInfo) => {
		test.skip(!isFunctional(testInfo), 'one functional run is enough');
		const who = projectUser(testInfo);
		const folder = workFolder(testInfo, 'trash');
		await davFreshFolder(who, folder);
		await upload(who, folder, 'Papierkorb.pdf', fixture(PDF));
		await davDelete(who, `${folder}/Papierkorb.pdf`);
		await login(page, who);
		await page.goto('/index.php/apps/files/trashbin');

		const entry = page.locator('[data-cy-files-list-row-name^="Papierkorb.pdf"]').first();
		await expect(entry).toBeVisible();
		await rowMenuToggle(entry).click();
		await expect(page.locator('[role="menu"]:visible').first()).toBeVisible();
		await expectNoAction(page);
	});

	test('Öffentliche Freigabeseite: kein Eintrag', async ({ browser }, testInfo) => {
		test.skip(!isFunctional(testInfo), 'one functional run is enough');
		const who = projectUser(testInfo);
		const folder = workFolder(testInfo, 'public');
		await davFreshFolder(who, folder);
		await upload(who, folder, PDF);
		const link = await share(who, folder, { download: true });
		try {
			// No use options here (plain library call): block the worker like playwright.config.ts.
			const context = await browser.newContext({ serviceWorkers: 'block' });
			const page = await context.newPage();
			await page.goto(`/index.php/s/${link.token}`);
			await expect(row(page, PDF)).toBeVisible();
			await row(page, PDF).locator('[data-cy-files-list-row-actions] button').first().click();
			await expectNoAction(page);
			await expect(page.getByText(ACTION_NAME)).toHaveCount(0);
			await context.close();
		} finally {
			await unshare(who, link.id);
		}
	});

	test('Freigabe ohne Download: Eintrag fehlt im Menü, Start per API ergibt "Download gesperrt"', async ({ page }, testInfo) => {
		const who = projectUser(testInfo);
		const owner = sharer(testInfo);
		const folder = workFolder(testInfo, 'blocked');
		await davFreshFolder(owner, folder);
		const blockedId = await upload(owner, folder, 'Bescheid gesperrt.pdf', fixture(PDF));
		const blocked = await share(owner, `${folder}/Bescheid gesperrt.pdf`, { with: who, download: false });
		const own = workFolder(testInfo, 'blocked-own');
		await davFreshFolder(who, own);
		await upload(who, own, PDF);
		try {
			await login(page, who);
			await page.goto(FILES_ROOT);
			await openRowMenu(page, 'Bescheid gesperrt.pdf');
			await expectNoAction(page);
			await screenshot(page, 'dateien', 'menue-download-gesperrt', testInfo);
			await closeRowMenu(page);

			// The action is hidden there, so the start goes out from the page
			// itself: the action of an own file, its request sent for the
			// blocked file. The server answers for real.
			await openFolder(page, own, PDF);
			await page.route(START_ROUTE, (route) => route.continue({ postData: JSON.stringify({ fileId: blockedId }) }), { times: 1 });
			const answer = await clickStart(page, PDF);
			expect(answer.status()).toBe(403);
			expect((await answer.json()).reason).toBe('download_blocked');
			const shown = await toast(page);
			await expectToastKind(shown, 'error');
			await expect(shown.locator('a')).toHaveCount(0);
			await screenshot(page, 'dateien', 'toast-download-gesperrt', testInfo);
			await closeToast(page);
		} finally {
			await unshare(owner, blocked.id);
		}
	});

	test('bob auf der gesperrten Freigabe aus der Saat: kein Eintrag', async ({ page }, testInfo) => {
		test.skip(!isFunctional(testInfo), 'one functional run is enough');
		await login(page, users.bob());
		await page.goto(FILES_ROOT);
		await openRowMenu(page, 'Bescheid 2026-114 Kopie.pdf');
		await expectNoAction(page);
		// The server refuses as well (fail closed, not only the menu).
		const answer = await startJob(users.bob(), fileId('FILE_SHARED_BLOCKED_BOB'));
		expect(answer.code).toBe(403);
		expect(answer.reason).toBe('download_blocked');
	});
});

test.describe('Start-Rückmeldung', () => {
	test('Toast "als Nächstes" und "läuft schon" aus echten Antworten', async ({ page }, testInfo) => {
		const who = projectUser(testInfo);
		const folder = workFolder(testInfo, 'start');
		await davFreshFolder(who, folder);
		await upload(who, folder, PDF);
		await login(page, who);
		await openFolder(page, folder, PDF);

		const first = await clickStart(page, PDF);
		expect(first.status()).toBe(201);
		const started = await first.json();
		expect(started.ahead).toBe(0);
		let shown = await toast(page);
		await expectToastKind(shown, 'success');
		await expect(toastClose(shown)).toBeVisible();
		await expect(shown.locator('a')).toHaveAttribute('href', REVIEW_LINK);
		await expect(shown).not.toContainText(PDF);
		await screenshot(page, 'dateien', 'toast-als-naechstes', testInfo);
		await closeToast(page);

		const second = await clickStart(page, PDF);
		expect(second.status()).toBe(200);
		expect((await second.json()).jobId).toBe(started.jobId);
		shown = await toast(page);
		await expectToastKind(shown, 'info');
		await expect(shown.locator('a')).toHaveAttribute('href', REVIEW_LINK);
		await screenshot(page, 'dateien', 'toast-laeuft-schon', testInfo);
		await closeToast(page);

		// The queue stays empty for the next test.
		await waitFor(who, started.jobId, ['review']);
	});

	test('Toasts "nicht verfügbar" und "Format" aus echten Antworten', async ({ page }, testInfo) => {
		const who = projectUser(testInfo);
		const folder = workFolder(testInfo, 'refused');
		await davFreshFolder(who, folder);
		await upload(who, folder, PDF);
		const txtId = await upload(who, folder, TXT);
		// A file of somebody else: not readable for the project user.
		const foreign = who.name === 'alice' ? fileId('FILE_PDF_DORA') : fileId('FILE_PDF_ALICE');
		await login(page, who);
		await openFolder(page, folder, PDF);

		const cases = [
			{ state: 'toast-nicht-verfuegbar', id: foreign, code: 404, reason: 'not_readable' },
			{ state: 'toast-format', id: txtId, code: 415, reason: 'unsupported_format' },
		];
		for (const shot of cases) {
			await page.route(START_ROUTE, (route) => route.continue({ postData: JSON.stringify({ fileId: shot.id }) }), { times: 1 });
			const answer = await clickStart(page, PDF);
			expect(answer.status()).toBe(shot.code);
			expect((await answer.json()).reason).toBe(shot.reason);
			const shown = await toast(page);
			await expectToastKind(shown, 'error');
			await screenshot(page, 'dateien', shot.state, testInfo);
			await closeToast(page);
		}
	});

	test('Toasts "n davor", "Backend nicht bereit" und "allgemein" mit Werten der geschlossenen Liste', async ({ page }, testInfo) => {
		const who = projectUser(testInfo);
		const jobId = await baseJob(who, testInfo);
		const folder = workFolder(testInfo, 'forged');
		await davFreshFolder(who, folder);
		await upload(who, folder, PDF);
		// The clock is installed before the page loads, so the error toast
		// can be checked after 12 s without waiting 12 s.
		await page.clock.install();
		await login(page, who);
		await openFolder(page, folder, PDF);

		const cases = [
			{ state: 'toast-n-davor', status: 201, body: { jobId, ahead: 3 }, kind: 'success' as const },
			{ state: 'toast-backend-nicht-bereit', status: 503, body: { reason: 'backend_unavailable' }, kind: 'warning' as const },
			{ state: 'toast-allgemein', status: 500, body: {}, kind: 'error' as const },
		];
		for (const shot of cases) {
			await page.route(START_ROUTE, (route) => route.fulfill({ status: shot.status, contentType: 'application/json', body: JSON.stringify(shot.body) }), { times: 1 });
			const answer = await clickStart(page, PDF);
			expect(answer.status()).toBe(shot.status);
			const shown = await toast(page);
			await expectToastKind(shown, shot.kind);
			await expect(toastClose(shown)).toBeVisible();
			if (shot.status !== 201) {
				// Errors and warnings stay until they are closed (UI-SPEC, 2.2.1).
				await page.clock.fastForward(12_000);
				await expect(shown).toBeVisible();
			}
			await screenshot(page, 'dateien', shot.state, testInfo);
			await closeToast(page);
		}
	});
});

test('Platzhalter-Kopien in der Liste: Name je Sprache in NFC, Kollision (2), Original unverändert', async ({ page }, testInfo) => {
	const who = projectUser(testInfo);
	const folder = workFolder(testInfo, 'copies');
	await davFreshFolder(who, folder);
	const id = await upload(who, folder, PDF);
	const before = await davStat(who, `${folder}/${PDF}`);

	for (let run = 0; run < 2; run++) {
		const jobId = await jobInReview(who, id);
		const done = await publish(who, jobId);
		expect(done.outputFileId).not.toBeNull();
	}

	const stem = PDF.replace(/\.pdf$/, '');
	const first = `${stem}${copySuffix(testInfo)}.pdf`;
	const second = `${stem}${copySuffix(testInfo)} (2).pdf`;
	const names = await davList(who, folder);
	expect(names).toContain(first);
	expect(names).toContain(second);
	for (const name of names) {
		expect(name).toBe(name.normalize('NFC'));
	}
	const after = await davStat(who, `${folder}/${PDF}`);
	expect(after?.etag).toBe(before?.etag);

	await login(page, who);
	await openFolder(page, folder, PDF);
	await expect(row(page, first)).toBeVisible();
	await expect(row(page, second)).toBeVisible();
	await screenshot(page, 'dateien', 'kopie-in-liste', testInfo);
});
