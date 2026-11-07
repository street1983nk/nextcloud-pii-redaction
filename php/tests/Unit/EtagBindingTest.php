<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Model\Reason;
use OCA\PiiRedaction\Model\Recheck;
use OCA\PiiRedaction\Model\Status;
use OCA\PiiRedaction\Model\Task;
use OCA\PiiRedaction\Service\JobService;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\TestCase;

/**
 * A job is bound to the file id and the etag of its start (JOB-04). Every
 * look at the job asks again, and a changed file ends an open job as stale.
 */
#[CoversClass(JobService::class)]
final class EtagBindingTest extends TestCase {
	use JobServiceFactory;

	protected function setUp(): void {
		parent::setUp();
		$this->setUpJobService();
	}

	protected function tearDown(): void {
		$this->cleanTables();
		parent::tearDown();
	}

	private function startedId(): int {
		$job = $this->service->start('alice', 42)['job'];
		self::assertNotNull($job);
		return $job->getId();
	}

	public function testTheStartStoresTheEtagOfTheFile(): void {
		$this->etag = 'W/abc123';
		$id = $this->startedId();
		self::assertSame('W/abc123', $this->mapper->find($id)->getFileEtag());
	}

	public function testAnUnchangedFileShowsTheJob(): void {
		$id = $this->startedId();
		$view = $this->service->view($id, 'alice');

		self::assertNotNull($view);
		self::assertSame('queued', $view['status']);
		self::assertSame(0, $view['ahead']);
		self::assertSame('ok', $view['recheck']);
		self::assertSame('Bescheid.pdf', $view['fileName']);
		self::assertSame([], $this->sent);
	}

	public function testAChangedEtagTurnsTheJobStale(): void {
		$id = $this->startedId();
		$this->etag = 'etag-2';
		$view = $this->service->view($id, 'alice');

		self::assertNotNull($view);
		self::assertSame('stale', $view['status']);
		self::assertSame('original_changed', $view['reason']);
		self::assertSame('changed', $view['recheck']);
		$job = $this->mapper->find($id);
		self::assertSame(Status::Stale, $job->getStatusEnum());
		self::assertSame(Reason::OriginalChanged, $job->getReasonEnum());
		self::assertSame(Task::Purge, $job->getTaskEnum());
		self::assertSame(['job_stale'], $this->subjects());

		// A second look sends nothing new.
		$this->service->view($id, 'alice');
		self::assertSame(['job_stale'], $this->subjects());
	}

	public function testRecheckMemberAlsoTurnsTheJobStale(): void {
		$id = $this->startedId();
		$this->etag = 'etag-2';
		self::assertSame(Recheck::Changed, $this->service->recheckMember($id, 'alice'));
		self::assertSame(Status::Stale, $this->mapper->find($id)->getStatusEnum());
	}

	public function testAForeignUserSeesNothing(): void {
		$id = $this->startedId();
		self::assertNull($this->service->view($id, 'bob'));
		self::assertNull($this->service->recheckMember($id, 'bob'));
		self::assertNull($this->service->view($id + 1000, 'alice'));
	}

	public function testALostReadPermissionHidesTheJob(): void {
		$id = $this->startedId();
		$this->readable = false;
		self::assertNull($this->service->view($id, 'alice'));
		self::assertSame(Recheck::Missing, $this->service->recheckMember($id, 'alice'));
		// Losing the permission is no change of the file: the job stays open.
		self::assertSame(Status::Queued, $this->mapper->find($id)->getStatusEnum());
	}
}
