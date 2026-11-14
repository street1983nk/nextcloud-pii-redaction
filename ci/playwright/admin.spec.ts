// Surface 5 of the UI-SPEC: the admin section "PII Redaction", connection to
// the backend. Audio & Video Search admin.spec.ts with the pii- ids, without
// the debug block.
//
// The main run of deploy-harp.yml sees the state ok. The error states need an
// instance the workflow rebuilt beforehand (plan 18, drift steps); each runs
// on its own with --grep and the main run leaves them out with --grep-invert:
//   @patch       backend registered a patch apart       version_patch_differs
//   @drift       backend registered a minor apart       version_drift
//   @missing     backend not registered                 backend_missing
//   @disabled    backend disabled                       backend_disabled
//   @unreachable backend container stopped              backend_unreachable
//   @noappapi    app_api disabled                       no_app_api
// PII_BACKEND_VERSION names the version a drift step registered.
//
// In each of the five error states the link "Open Apps" exists, is reached
// with Tab and its href answers 200 for dora (orchestrator decision 3, no
// version check). Banner text is the text tone of its status pair, never the
// muted grey; 16 px from banner to version line; focus on #pii-backend-state
// after "Check again"; the button is disabled with "Checking…" meanwhile.
import { expect, test, type Page, type TestInfo } from '@playwright/test';
import {
	ADMIN_PATH,
	color,
	ensureAdmin,
	gap,
	login,
	projectUser,
	resolvedColor,
	screenshot,
	users,
	type User,
} from './helpers';

const VERSION = '0.1.0';
const STATE_ROUTE = /\/apps\/pii_redaction\/admin\/state$/;
const CHECKING = /^(Checking…|Wird geprüft…|Vérification…)$/;
const STATUS_TEXT: Record<string, string> = {
	error: '--color-error-text',
	warning: '--color-warning-text',
	info: '--color-info-text',
	success: '--color-success-text',
};

/**
 * The admin of a project: dora in high contrast, the German and French users
 * (made admin here, so the section shows in their language), the instance
 * admin for the English alice projects.
 */
async function adminOf(testInfo: TestInfo): Promise<User> {
	const who = projectUser(testInfo);
	if (who.name === 'alice') {
		return users.admin();
	}
	if (who.name !== 'dora') {
		await ensureAdmin(who);
	}
	return who;
}

async function openSection(page: Page, testInfo: TestInfo): Promise<void> {
	await login(page, await adminOf(testInfo));
	await page.goto(ADMIN_PATH);
	await expect(page.locator('#pii-admin')).toBeVisible();
}

function banner(page: Page, state: string) {
	return page.locator(`#pii-backend-state [data-state="${state}"]`);
}

/** "Check again", so the banner shows the state of right now. */
async function recheck(page: Page): Promise<void> {
	const answer = page.waitForResponse((response) => STATE_ROUTE.test(new URL(response.url()).pathname));
	await page.locator('#pii-recheck').click();
	await answer;
	await expect(page.locator('#pii-backend-state')).not.toHaveAttribute('aria-busy', 'true');
}

/** Text tone of the status pair, not the muted grey; no version inside the banner. */
async function expectBannerText(page: Page, state: string): Promise<void> {
	const shown = banner(page, state);
	await expect(shown).toBeVisible();
	const kind = /pii-banner--(error|warning|info|success)/.exec((await shown.getAttribute('class')) ?? '')?.[1];
	expect(kind).toBeDefined();
	const expected = await resolvedColor(shown, STATUS_TEXT[kind as string]);
	const muted = await resolvedColor(shown, '--color-text-maxcontrast');
	const texts = shown.locator('.pii-banner__title, .pii-banner__text');
	expect(await texts.count()).toBeGreaterThan(0);
	for (let i = 0; i < (await texts.count()); i++) {
		expect(await color(texts.nth(i))).toBe(expected);
		expect(await color(texts.nth(i))).not.toBe(muted);
	}
	expect(await shown.innerText()).not.toMatch(/\d+\.\d+\.\d+/);
	// 16 px from the banner to the version line (AVS acceptance 07.11.).
	expect(Math.abs((await gap(shown, page.locator('.pii-admin__line').first())) - 16)).toBeLessThanOrEqual(1);
}

async function expectVersionLine(own: string, backend: string, page: Page): Promise<void> {
	await expect(page.locator('.pii-admin__line .pii-version-own')).toHaveText(own);
	await expect(page.locator('.pii-admin__line .pii-version-backend')).toHaveText(backend);
}

/**
 * The one action of an error banner: present, reached with Tab from the
 * state area, and its href answers 200 for the logged in admin and for dora.
 */
async function expectAppsLink(page: Page, state: string, testInfo: TestInfo): Promise<void> {
	const link = banner(page, state).locator('.pii-banner__action');
	await expect(link).toBeVisible();
	await expect(link).toHaveText(/^(Open Apps|Apps öffnen|Ouvrir Applications)$/);
	const href = await link.getAttribute('href');
	expect(href).toMatch(/\/settings\/apps|\/apps\/appstore/);

	await page.locator('#pii-backend-state').focus();
	await page.keyboard.press('Tab');
	await expect(link).toBeFocused();

	expect((await page.request.get(href as string)).status()).toBe(200);
	if (projectUser(testInfo).name !== 'dora') {
		const browser = page.context().browser();
		expect(browser).not.toBeNull();
		const context = await browser!.newContext({ baseURL: process.env.NC_URL ?? 'http://localhost:8080' });
		try {
			const dora = await context.newPage();
			await login(dora, users.dora());
			expect((await context.request.get(href as string)).status()).toBe(200);
		} finally {
			await context.close();
		}
	}
}

/** The backend version the drift step of the workflow registered. */
function registeredBackendVersion(): string {
	const value = process.env.PII_BACKEND_VERSION;
	if (value === undefined || value === '') {
		throw new Error('PII_BACKEND_VERSION is not set; the drift tests run in the drift steps of deploy-harp.yml only');
	}
	return value;
}

// -- main run ----------------------------------------------------------------------

test('Admin: Zustand ok mit beiden Versionen', async ({ page }, testInfo) => {
	await openSection(page, testInfo);

	await expect(banner(page, 'ok')).toBeVisible();
	await expect(banner(page, 'ok').locator('.pii-banner__action')).toHaveCount(0);
	await expectVersionLine(VERSION, VERSION, page);
	await expectBannerText(page, 'ok');
	await expect(page.locator('#pii-recheck-failed')).toBeHidden();
	await screenshot(page, 'admin', 'ok', testInfo);
});

test('Admin: Erneut prüfen, Knopf während der Prüfung, danach Fokus auf dem Zustand', async ({ page }, testInfo) => {
	await openSection(page, testInfo);

	// The answer is held back until the busy state is seen; no fixed wait.
	let release: () => void = () => {};
	const held = new Promise<void>((resolve) => {
		release = resolve;
	});
	await page.route(STATE_ROUTE, async (route) => {
		await held;
		await route.continue();
	});

	const button = page.locator('#pii-recheck');
	const stateArea = page.locator('#pii-backend-state');
	await button.click();
	await expect(button).toBeDisabled();
	await expect(page.locator('#pii-recheck-label')).toHaveText(CHECKING);
	await expect(stateArea).toHaveAttribute('aria-busy', 'true');
	await screenshot(page, 'admin', 'pruefung-laeuft', testInfo);
	release();

	await expect(stateArea).not.toHaveAttribute('aria-busy', 'true');
	await expect(stateArea).toBeFocused();
	await expect(button).toBeEnabled();
	await expect(banner(page, 'ok')).toBeVisible();
});

test('Admin: Neuprüfung gescheitert, letzter Stand bleibt', async ({ page }, testInfo) => {
	await openSection(page, testInfo);
	// The answer of SettingsController::state() when the check throws.
	await page.route(STATE_ROUTE, (route) => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ state: 'recheck_failed' }) }));

	await page.locator('#pii-recheck').click();
	const warning = page.locator('#pii-recheck-failed');
	await expect(warning).toBeVisible();
	await expect(banner(page, 'ok')).toBeVisible();
	await expect(page.locator('#pii-backend-state')).toBeFocused();
	const expected = await resolvedColor(warning, '--color-warning-text');
	expect(await color(warning.locator('.pii-banner__text'))).toBe(expected);
	await screenshot(page, 'admin', 'neupruefung-gescheitert', testInfo);
});

// -- drift steps (plan 18) ------------------------------------------------------------

test('Admin: nur der Patch-Teil weicht ab, Hinweis ohne Aktion @patch', async ({ page }, testInfo) => {
	await openSection(page, testInfo);
	await recheck(page);

	await expectBannerText(page, 'version_patch_differs');
	await expect(banner(page, 'version_patch_differs').locator('.pii-banner__action')).toHaveCount(0);
	await expectVersionLine(VERSION, registeredBackendVersion(), page);
	await screenshot(page, 'admin', 'version_patch_differs', testInfo);
});

test('Admin: Versionen weichen in Major.Minor ab @drift', async ({ page }, testInfo) => {
	await openSection(page, testInfo);
	await recheck(page);

	await expectBannerText(page, 'version_drift');
	await expectVersionLine(VERSION, registeredBackendVersion(), page);
	await expectAppsLink(page, 'version_drift', testInfo);
	await screenshot(page, 'admin', 'version_drift', testInfo);
});

const ERROR_STATES = [
	{ state: 'backend_missing', tag: '@missing' },
	{ state: 'backend_disabled', tag: '@disabled' },
	{ state: 'backend_unreachable', tag: '@unreachable' },
	{ state: 'no_app_api', tag: '@noappapi' },
] as const;

for (const { state, tag } of ERROR_STATES) {
	test(`Admin: Fehlerzustand ${state} mit "Apps öffnen" ${tag}`, async ({ page }, testInfo) => {
		await openSection(page, testInfo);
		await recheck(page);

		await expectBannerText(page, state);
		await expectAppsLink(page, state, testInfo);
		await screenshot(page, 'admin', state, testInfo);
	});
}
