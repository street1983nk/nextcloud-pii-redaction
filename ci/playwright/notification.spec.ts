// Surface 3 of the UI-SPEC: the notifications of PII Redaction in the popover
// of the notifications app, one per subject of the closed list:
//   review_ready   a job reached review
//   job_failed     a job failed (a broken PDF, real render_failed)
//   job_stale      the original changed after review (WebDAV PUT)
//   copy_created   the placeholder copy was published (background job)
// All four come from real runs, no page.route. Over OCS notifications/api/v2
// every entry carries neither a file name nor the canary, and its link leads
// to /apps/pii_redaction/review/{id}.
import { expect, test } from '@playwright/test';
import {
	CANARY,
	FILE_STEMS,
	PDF,
	davFreshFolder,
	davPut,
	fixture,
	jobInReview,
	login,
	projectUser,
	publish,
	screenshot,
	startJob,
	upload,
	waitFor,
	withApi,
	workFolder,
	type User,
} from './helpers';

const NOTIFICATIONS = '/ocs/v2.php/apps/notifications/api/v2/notifications';

/** The closed list of subjects (php/lib/Notification/Subject.php). */
const SUBJECTS = ['review_ready', 'job_failed', 'job_stale', 'copy_created'] as const;

type Entry = { app: string; object_type: string; object_id: string; link: string; subject: string; message: string };

async function clearNotifications(who: User): Promise<void> {
	await withApi(who, async (context) => {
		const response = await context.delete(`${NOTIFICATIONS}?format=json`);
		expect([200, 404]).toContain(response.status());
	});
}

async function ownNotifications(who: User): Promise<{ raw: string; entries: Entry[] }> {
	return withApi(who, async (context) => {
		const response = await context.get(`${NOTIFICATIONS}?format=json`);
		expect(response.status()).toBe(200);
		const raw = await response.text();
		const entries = (JSON.parse(raw).ocs.data as Entry[]).filter((entry) => entry.app === 'pii_redaction');
		return { raw, entries };
	});
}

test('Benachrichtigungen review_ready, job_failed, job_stale, copy_created im Popover', async ({ page }, testInfo) => {
	const who = projectUser(testInfo);
	const base = workFolder(testInfo, 'notify');
	await clearNotifications(who);

	// review_ready
	await davFreshFolder(who, `${base}/ready`);
	const ready = await jobInReview(who, await upload(who, `${base}/ready`, PDF));

	// job_failed: a PDF the backend cannot render.
	await davFreshFolder(who, `${base}/failed`);
	const brokenId = await upload(who, `${base}/failed`, PDF, new TextEncoder().encode('%PDF-1.7\nnot a document\n'));
	const failedStart = await startJob(who, brokenId);
	expect(failedStart.code).toBe(201);
	const failed = failedStart.jobId as number;
	const failedView = await waitFor(who, failed, ['failed']);
	expect(failedView.reason).toBe('render_failed');

	// job_stale
	await davFreshFolder(who, `${base}/stale`);
	const stale = await jobInReview(who, await upload(who, `${base}/stale`, PDF));
	await davPut(who, `${base}/stale/${PDF}`, new Uint8Array([...fixture(PDF), ...new TextEncoder().encode('%changed\n')]));
	await waitFor(who, stale, ['stale']);

	// copy_created
	await davFreshFolder(who, `${base}/copy`);
	const copy = await jobInReview(who, await upload(who, `${base}/copy`, PDF));
	await publish(who, copy);

	// Over OCS: one entry per job, no file name, no canary, link to the review page.
	const jobs = [ready, failed, stale, copy];
	let notified: Awaited<ReturnType<typeof ownNotifications>> = { raw: '', entries: [] };
	await expect
		.poll(async () => {
			notified = await ownNotifications(who);
			return jobs.filter((job) => notified.entries.some((entry) => entry.object_type === 'job' && entry.object_id === String(job))).length;
		})
		.toBe(SUBJECTS.length);
	for (const stem of FILE_STEMS) {
		expect(notified.raw).not.toContain(stem);
	}
	expect(notified.raw).not.toContain(CANARY);
	for (const job of jobs) {
		const entries = notified.entries.filter((entry) => entry.object_id === String(job));
		// A new subject of the same job replaces the old one.
		expect(entries).toHaveLength(1);
		expect(entries[0].link).toMatch(new RegExp(`/apps/pii_redaction/review/${job}$`));
		expect(entries[0].subject).not.toBe('');
	}

	// The popover of the notifications app.
	await login(page, who);
	await page.goto('/index.php/apps/files/');
	const bell = page.locator('#notifications button, .notifications-button, header [aria-label="Notifications"], header [aria-label="Benachrichtigungen"]').first();
	await expect(bell).toBeVisible();
	await bell.click();
	const items = page.locator('.notification[data-object-type="job"], .notification-wrapper .notification');
	await expect(items.first()).toBeVisible();
	await expect.poll(() => items.count()).toBeGreaterThanOrEqual(SUBJECTS.length);
	await screenshot(page, 'benachrichtigung', 'popover', testInfo);

	// The link of an entry leads to the review page of its job.
	const link = page.locator(`.notification a[href*="/apps/pii_redaction/review/${ready}"]`).first();
	await expect(link).toBeVisible();
	await link.click();
	await expect(page).toHaveURL(new RegExp(`/apps/pii_redaction/review/${ready}$`));
});
