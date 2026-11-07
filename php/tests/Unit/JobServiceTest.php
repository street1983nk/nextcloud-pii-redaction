<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Db\Job;
use OCA\PiiRedaction\Model\Lang;
use OCA\PiiRedaction\Model\Mode;
use OCA\PiiRedaction\Model\Reason;
use OCA\PiiRedaction\Model\Stage;
use OCA\PiiRedaction\Model\Status;
use OCA\PiiRedaction\Model\Task;
use OCA\PiiRedaction\Service\JobService;
use OCA\PiiRedaction\Service\NotificationSender;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\TestCase;

/**
 * Start, refusals, idempotence and every transition of JobService, against
 * the real database of the test instance (php.yml enables the app first).
 */
#[CoversClass(JobService::class)]
#[CoversClass(NotificationSender::class)]
final class JobServiceTest extends TestCase {
	use JobServiceFactory;

	protected function setUp(): void {
		parent::setUp();
		$this->setUpJobService();
	}

	protected function tearDown(): void {
		$this->cleanTables();
		parent::tearDown();
	}

	private function started(): Job {
		$result = $this->service->start('alice', 42);
		self::assertNotNull($result['job']);
		return $result['job'];
	}

	private function reload(Job $job): Job {
		return $this->mapper->find($job->getId());
	}

	/** Claims the job like the container does: queued becomes analyzing. */
	private function claimed(): Job {
		$this->started();
		$claim = $this->mapper->claimNext();
		self::assertNotNull($claim);
		return $claim['job'];
	}

	private function inReview(): Job {
		$job = $this->claimed();
		$this->service->toReview($job, 3, 992, 1403);
		return $this->reload($job);
	}

	public function testABackendThatIsNotReadyRefusesTheStart(): void {
		$this->backendReady = false;
		$result = $this->service->start('alice', 42);
		self::assertNull($result['job']);
		self::assertSame(Reason::BackendUnavailable, $result['reason']);
	}

	public function testAnUnreadableFileRefusesTheStart(): void {
		$this->readable = false;
		self::assertSame(Reason::NotReadable, $this->service->start('alice', 42)['reason']);
		self::assertSame(Reason::NotReadable, $this->service->start('bob', 42)['reason']);
		self::assertSame(Reason::NotReadable, $this->service->start('alice', 7)['reason']);
	}

	public function testADownloadBlockRefusesTheStart(): void {
		$this->downloadAllowed = false;
		self::assertSame(Reason::DownloadBlocked, $this->service->start('alice', 42)['reason']);
	}

	public function testAnotherFormatRefusesTheStart(): void {
		$this->mime = 'image/png';
		self::assertSame(Reason::UnsupportedFormat, $this->service->start('alice', 42)['reason']);
	}

	public function testDocxAndOdtAreAccepted(): void {
		$this->mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
		self::assertTrue($this->service->start('alice', 42)['created']);
		$this->etag = 'etag-2';
		$this->mime = 'application/vnd.oasis.opendocument.text';
		self::assertTrue($this->service->start('alice', 42)['created']);
	}

	public function testANewJobStoresIdsEtagModeAndLanguageOnly(): void {
		$result = $this->service->start('alice', 42);
		self::assertTrue($result['created']);
		self::assertNull($result['reason']);
		self::assertSame(0, $result['ahead']);

		$job = $this->reload($result['job']);
		self::assertSame(42, $job->getFileId());
		self::assertSame('alice', $job->getInitiatorUid());
		self::assertSame('etag-1', $job->getFileEtag());
		self::assertSame(Mode::Redact, $job->getModeEnum());
		self::assertSame(Lang::En, $job->getLangEnum());
		self::assertSame(Status::Queued, $job->getStatusEnum());
		self::assertSame([Status::Queued->value], $this->actions($job->getId()));
	}

	public function testASecondStartReturnsTheOpenJob(): void {
		$first = $this->service->start('alice', 42);
		$second = $this->service->start('alice', 42);

		self::assertFalse($second['created']);
		self::assertSame($first['job']?->getId(), $second['job']?->getId());
		self::assertSame([Status::Queued->value], $this->actions($first['job']->getId()));
	}

	public function testAChangedEtagStartsANewJob(): void {
		$first = $this->service->start('alice', 42);
		$this->etag = 'etag-2';
		$second = $this->service->start('alice', 42);

		self::assertTrue($second['created']);
		self::assertNotSame($first['job']?->getId(), $second['job']?->getId());
		self::assertSame(1, $second['ahead']);
	}

	public function testGermanUserLanguageGivesDe(): void {
		$this->languages['alice'] = 'de_DE';
		self::assertSame(Lang::De, $this->reload($this->started())->getLangEnum());
	}

	public function testFrenchUserLanguageGivesFr(): void {
		$this->languages['alice'] = 'fr';
		self::assertSame(Lang::Fr, $this->reload($this->started())->getLangEnum());
	}

	public function testReviewNotifiesAndReleasesTheSlot(): void {
		$job = $this->inReview();

		self::assertSame(Status::Review, $job->getStatusEnum());
		self::assertNull($job->getTaskEnum());
		self::assertSame(Stage::Done, $job->getStageEnum());
		self::assertSame(3, $job->getPagesTotal());
		self::assertSame(992, $job->getImageWidth());
		self::assertSame(0, $job->getAttempts());
		self::assertNull($job->getClaimToken());
		self::assertSame(['review_ready'], $this->subjects());
		self::assertSame('alice', $this->sent[0]['user']);
		self::assertSame('job:' . $job->getId(), $this->sent[0]['object']);

		// The slot is free again: a second job can be claimed at once.
		$this->etag = 'etag-2';
		$this->started();
		self::assertNotNull($this->mapper->claimNext());
	}

	public function testFailedNotifiesAndGoesToPurge(): void {
		$job = $this->claimed();
		$this->service->toFailed($job, Reason::RenderFailed);
		$job = $this->reload($job);

		self::assertSame(Status::Failed, $job->getStatusEnum());
		self::assertSame(Reason::RenderFailed, $job->getReasonEnum());
		self::assertSame(Task::Purge, $job->getTaskEnum());
		self::assertSame(['job_failed'], $this->subjects());
	}

	public function testStaleNotifiesAndGoesToPurge(): void {
		$job = $this->started();
		$this->service->toStale($job);
		$job = $this->reload($job);

		self::assertSame(Status::Stale, $job->getStatusEnum());
		self::assertSame(Reason::OriginalChanged, $job->getReasonEnum());
		self::assertSame(Task::Purge, $job->getTaskEnum());
		self::assertSame(['job_stale'], $this->subjects());
	}

	public function testCancelledSendsNothingAndRemovesOldNotifications(): void {
		$job = $this->inReview();
		$this->sent = [];
		$this->service->toCancelled($job, Reason::OriginalDeleted);
		$job = $this->reload($job);

		self::assertSame(Status::Cancelled, $job->getStatusEnum());
		self::assertSame(Task::Purge, $job->getTaskEnum());
		self::assertSame([], $this->sent);
		self::assertContains('job:' . $job->getId(), $this->dismissed);
	}

	public function testThePlaceholderPathEndsPublishedWithCopyCreated(): void {
		$job = $this->inReview();
		$this->service->toApproved($job, 'alice');
		$job = $this->reload($job);
		self::assertSame(Status::Approved, $job->getStatusEnum());
		self::assertSame(Task::Apply, $job->getTaskEnum());

		$claim = $this->mapper->claimNext();
		self::assertNotNull($claim);
		self::assertSame(Status::Applying, $claim['job']->getStatusEnum());
		$this->service->toVerified($claim['job'], str_repeat('a', 64), 1234);
		$job = $this->reload($job);
		self::assertSame(Status::Verified, $job->getStatusEnum());
		self::assertSame(1234, $job->getOutputSize());

		$this->service->toPublished($job, 99);
		$job = $this->reload($job);
		self::assertSame(Status::Published, $job->getStatusEnum());
		self::assertSame(99, $job->getOutputFileId());
		self::assertSame(Task::Purge, $job->getTaskEnum());
		self::assertSame(['review_ready', 'copy_created'], $this->subjects());
		self::assertSame(
			['queued', 'review', 'approved', 'verified', 'published'],
			$this->actions($job->getId()),
		);

		$this->service->toPurged($job);
		self::assertNull($this->reload($job)->getTaskEnum());
	}

	public function testAForbiddenTransitionThrows(): void {
		$job = $this->started();
		$this->expectException(\LogicException::class);
		$this->service->toPublished($job, 99);
	}

	public function testAnEndStateCannotTurnStale(): void {
		$job = $this->claimed();
		$this->service->toFailed($job, Reason::RenderFailed);
		$this->expectException(\LogicException::class);
		$this->service->toStale($this->reload($job));
	}

	public function testAGivenUpJobIsNotifiedOnceOnTheFirstView(): void {
		$job = $this->started();
		$job->setStatus(Status::Failed->value);
		$job->setReason(Reason::RepeatedlyStuck->value);
		$job->setTask(Task::Purge->value);
		$this->mapper->update($job);

		self::assertSame('failed', $this->service->view($job->getId(), 'alice')['status'] ?? null);
		$this->service->view($job->getId(), 'alice');
		self::assertSame(['job_failed'], $this->subjects());
	}
}
