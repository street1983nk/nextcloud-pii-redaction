// Surface 3 of the UI-SPEC: the notifications of PII Redaction in the popover
// of the notifications app, one per subject of the closed list:
//   review_ready   a job reached review
//   job_failed     a job failed with a real error: the copy cannot be placed in
//                  a folder shared read-only (target_not_writable)
//   job_stale      the original changed after review (WebDAV PUT)
//   copy_created   the placeholder copy was published (background job)
// All four come from real runs, no page.route. Over OCS notifications/api/v2
// every entry carries neither a file name nor the canary, and its link leads
// to /apps/pii_redaction/review/{id}.
// A file the pre-check refuses (a broken PDF, damaged) fails without any
// notification (D-02-02): its reason stands on the file card only.
import { expect, test } from '@playwright/test';
import {
	APP_PATH,
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
	share,
	sharer,
	startJob,
	unshare,
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
	// The folder for job_failed: somebody else shares it read-only. It comes
	// first, so that clearing the notifications also takes what the share made.
	const owner = sharer(testInfo);
	const readOnly = workFolder(testInfo, 'notify-readonly');
	await davFreshFolder(owner, readOnly);
	const readOnlyId = await upload(owner, readOnly, PDF);
	const readOnlyShare = await share(owner, readOnly, { with: who, download: true });
	try {
		await clearNotifications(who);

		// review_ready
		await davFreshFolder(who, `${base}/ready`);
		const ready = await jobInReview(who, await upload(who, `${base}/ready`, PDF));

		// No notification: a broken PDF is refused by the pre-check. It runs before
		// the three jobs below, so its notification would be there when theirs are.
		await davFreshFolder(who, `${base}/refused`);
		const brokenId = await upload(who, `${base}/refused`, PDF, new TextEncoder().encode('%PDF-1.7\nnot a document\n'));
		const refusedStart = await startJob(who, brokenId);
		expect(refusedStart.code).toBe(201);
		const refused = refusedStart.jobId as number;
		const refusedView = await waitFor(who, refused, ['failed']);
		expect(refusedView.reason).toBe('damaged');

		// job_failed: a real error. The review works on the read-only share and
		// the copy cannot be placed there.
		const failed = await jobInReview(who, readOnlyId);
		await withApi(who, async (context) => {
			const response = await context.post(`${APP_PATH}/review/${failed}/placeholder`);
			expect(response.status()).toBe(202);
		});
		const failedView = await waitFor(who, failed, ['failed', 'published'], true);
		expect(failedView.status).toBe('failed');
		expect(failedView.reason).toBe('target_not_writable');

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
		// The refused job has none, in the same answer that carries the four.
		expect(notified.entries.filter((entry) => entry.object_id === String(refused))).toHaveLength(0);

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
	} finally {
		await unshare(owner, readOnlyShare.id);
	}
});
