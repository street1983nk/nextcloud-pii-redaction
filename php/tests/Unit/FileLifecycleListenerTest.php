<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Listener\FileLifecycleListener;
use OCA\PiiRedaction\Model\Reason;
use OCA\PiiRedaction\Model\Status;
use OCP\EventDispatcher\Event;
use OCP\Files\Events\Node\BeforeNodeDeletedEvent;
use OCP\Files\Events\Node\NodeWrittenEvent;
use OCP\Files\File;
use OCP\Files\Folder;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\TestCase;
use Psr\Log\LoggerInterface;

/**
 * Writes and deletions of the original end its open jobs, with the real
 * JobMapper and JobService against the database of the test instance.
 */
#[CoversClass(FileLifecycleListener::class)]
final class FileLifecycleListenerTest extends TestCase {
	use JobServiceFactory;

	protected function setUp(): void {
		parent::setUp();
		$this->setUpJobService();
	}

	protected function tearDown(): void {
		$this->cleanTables();
		parent::tearDown();
	}

	private function listener(): FileLifecycleListener {
		return new FileLifecycleListener($this->mapper, $this->service, $this->createMock(LoggerInterface::class));
	}

	private function original(int $id = 42): File {
		$file = $this->createMock(File::class);
		$file->method('getId')->willReturn($id);
		return $file;
	}

	/** @return list<int> two open jobs on file 42: one queued, one in review */
	private function twoOpenJobs(): array {
		$first = $this->service->start('alice', 42)['job'];
		self::assertNotNull($first);
		$claim = $this->mapper->claimNext();
		self::assertNotNull($claim);
		$this->service->toReview($claim['job'], 1, 10, 10);
		$this->etag = 'etag-2';
		$second = $this->service->start('alice', 42)['job'];
		self::assertNotNull($second);
		return [$first->getId(), $second->getId()];
	}

	private function statusOf(int $jobId): Status {
		return $this->mapper->find($jobId)->getStatusEnum();
	}

	public function testAWriteMakesEveryOpenJobStale(): void {
		[$review, $queued] = $this->twoOpenJobs();

		$this->listener()->handle(new NodeWrittenEvent($this->original()));

		self::assertSame(Status::Stale, $this->statusOf($review));
		self::assertSame(Status::Stale, $this->statusOf($queued));
		self::assertSame('original_changed', $this->mapper->find($queued)->getReason());
	}

	public function testJobsInAnEndStateStayAsTheyAre(): void {
		$job = $this->service->start('alice', 42)['job'];
		self::assertNotNull($job);
		$this->service->toFailed($job, Reason::RenderFailed);
		$before = count($this->sent);

		$this->listener()->handle(new NodeWrittenEvent($this->original()));

		self::assertSame(Status::Failed, $this->statusOf($job->getId()));
		self::assertSame('render_failed', $this->mapper->find($job->getId())->getReason());
		self::assertCount($before, $this->sent);
	}

	public function testADeletionCancelsWithoutANotification(): void {
		[$review, $queued] = $this->twoOpenJobs();
		$before = count($this->sent);

		$this->listener()->handle(new BeforeNodeDeletedEvent($this->original()));

		foreach ([$review, $queued] as $jobId) {
			$job = $this->mapper->find($jobId);
			self::assertSame(Status::Cancelled, $job->getStatusEnum());
			self::assertSame('original_deleted', $job->getReason());
		}
		self::assertCount($before, $this->sent);
	}

	public function testAnotherFileTouchesNothing(): void {
		[$review, $queued] = $this->twoOpenJobs();

		$this->listener()->handle(new NodeWrittenEvent($this->original(99)));

		self::assertSame(Status::Review, $this->statusOf($review));
		self::assertSame(Status::Queued, $this->statusOf($queued));
	}

	public function testAFolderEventIsIgnored(): void {
		[$review] = $this->twoOpenJobs();
		$folder = $this->createMock(Folder::class);
		$folder->method('getId')->willReturn(42);

		$this->listener()->handle(new NodeWrittenEvent($folder));
		$this->listener()->handle(new BeforeNodeDeletedEvent($folder));

		self::assertSame(Status::Review, $this->statusOf($review));
	}

	public function testAnotherEventIsIgnored(): void {
		[$review] = $this->twoOpenJobs();
		$this->listener()->handle(new Event());
		self::assertSame(Status::Review, $this->statusOf($review));
	}

	public function testAnExceptionIsSwallowed(): void {
		[$review] = $this->twoOpenJobs();
		$file = $this->createMock(File::class);
		$file->method('getId')->willThrowException(new \RuntimeException('/alice/files/Bescheid.pdf'));

		// The file operation of the user goes on: nothing escapes.
		$this->listener()->handle(new NodeWrittenEvent($file));

		self::assertSame(Status::Review, $this->statusOf($review));
	}
}
