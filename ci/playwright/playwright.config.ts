// End-to-end acceptance suite of PII Redaction (UI-SPEC, "Prüfvertrag für die
// Abnahme"), against the throwaway Nextcloud of deploy-harp.yml after
// ci/seed.sh and ci/flow.sh. The instance, its passwords and the fixtures
// exist only inside the CI run: NC_URL, ADMIN_PASS, CI_PASS and NC_ROOT as
// job variables, the file ids in ci/out/fileids.env, the fixtures in
// ci/out/fixtures (the script contract of plan 15).
//
// The projects are the screenshot grid of the UI-SPEC, twelve in all:
//   English, user alice: 375, 768 and 1280 px, light and dark, and the high
//     contrast project at 1280 px as dora (admin, theme light-highcontrast).
//   German de_DE (elke) and French (fleur): 375 px light and 1280 px dark.
//   German "de", the du catalogue (greta): 375 px light.
// Every surface and state takes a picture in every project; language, width
// and theme are in the project name and so in every file name.
//
// One worker, nothing in parallel: the tests share one instance and its one
// job queue, and the CI runner carries Nextcloud, HaRP and the backend
// container beside the browser.
import { defineConfig, devices } from '@playwright/test';

type Shot = { name: string; language: 'en' | 'de' | 'fr' | 'de-du'; width: 375 | 768 | 1280; scheme: 'light' | 'dark' | 'contrast'; user: string };

const SHOTS: Shot[] = [
	{ name: 'en-w375-light', language: 'en', width: 375, scheme: 'light', user: 'alice' },
	{ name: 'en-w375-dark', language: 'en', width: 375, scheme: 'dark', user: 'alice' },
	{ name: 'en-w768-light', language: 'en', width: 768, scheme: 'light', user: 'alice' },
	{ name: 'en-w768-dark', language: 'en', width: 768, scheme: 'dark', user: 'alice' },
	{ name: 'en-w1280-light', language: 'en', width: 1280, scheme: 'light', user: 'alice' },
	{ name: 'en-w1280-dark', language: 'en', width: 1280, scheme: 'dark', user: 'alice' },
	{ name: 'en-w1280-contrast', language: 'en', width: 1280, scheme: 'contrast', user: 'dora' },
	{ name: 'de-w375-light', language: 'de', width: 375, scheme: 'light', user: 'elke' },
	{ name: 'de-w1280-dark', language: 'de', width: 1280, scheme: 'dark', user: 'elke' },
	{ name: 'fr-w375-light', language: 'fr', width: 375, scheme: 'light', user: 'fleur' },
	{ name: 'fr-w1280-dark', language: 'fr', width: 1280, scheme: 'dark', user: 'fleur' },
	{ name: 'de-du-w375-light', language: 'de-du', width: 375, scheme: 'light', user: 'greta' },
];

export default defineConfig({
	testDir: '.',
	testMatch: '*.spec.ts',
	outputDir: 'test-results',
	retries: 0,
	workers: 1,
	fullyParallel: false,
	forbidOnly: !!process.env.CI,
	// Real jobs run through the backend (render, LibreOffice for DOCX/ODT).
	// The longest passing test of run 43600377522 took 40 s; waitFor() in
	// helpers.ts polls up to 180 s, so 240 s stays the frame of one test.
	timeout: 240_000,
	// The whole main step: twelve projects at about 4.2 minutes each (run
	// 43600377522 without its hangs) is about 50 minutes. Past 75 minutes the
	// run stops by itself, names the test in progress and still writes the
	// report, well before the job timeout of 120 minutes (setup and the drift
	// steps need the rest).
	globalTimeout: 75 * 60_000,
	expect: { timeout: 15_000 },
	reporter: [['list'], ['html', { open: 'never' }]],
	use: {
		baseURL: process.env.NC_URL ?? 'http://localhost:8080',
		// Without these, a click on an element that never becomes clickable
		// (a toast outside the viewport, run 43600377522) retries until the
		// test timeout of 240 s. With them it fails after 15 s by name.
		actionTimeout: 15_000,
		navigationTimeout: 30_000,
		screenshot: 'only-on-failure',
		trace: 'retain-on-failure',
		// The Files app of Nextcloud 33+ registers preview-service-worker.js.
		// Once it controls the page, requests go through the worker, and
		// page.route and the response events of the page no longer see them
		// (Playwright docs of page.route, issue 1090: "We recommend disabling
		// Service Workers when using request interception"). Run 43615560742:
		// the forged start of fileaction.spec.ts reached the server unchanged
		// (201 on the real file id) and waitForResponse ran into its 30 s
		// deadline, depending on when the worker took over. No test needs the
		// worker: the CI instance has no PDF preview provider anyway.
		// Contexts opened by hand with browser.newContext() do not inherit
		// this option and set it themselves.
		serviceWorkers: 'block',
	},
	projects: SHOTS.map((shot) => ({
		name: shot.name,
		use: {
			...devices['Desktop Chrome'],
			viewport: { width: shot.width, height: 900 },
			// The high contrast theme is a user setting of dora (ci/seed.sh);
			// the browser itself stays light for it.
			colorScheme: shot.scheme === 'dark' ? 'dark' : 'light',
		},
		metadata: {
			language: shot.language,
			user: shot.user,
			highContrast: shot.scheme === 'contrast',
			// The English 1280 px light project carries the checks that need no
			// picture per project (rights as bob and carol, headers, menus).
			functional: shot.language === 'en' && shot.width === 1280 && shot.scheme === 'light',
		},
	})),
});
