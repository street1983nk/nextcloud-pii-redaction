<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Db\Job;
use OCA\PiiRedaction\Model\Status;
use OCA\PiiRedaction\Service\PublishService;
use OCA\PiiRedaction\Service\ReaderContext;
use OCP\Files\NotPermittedException;
use OCP\Http\Client\IResponse;
use OCP\IUserManager;
use OCP\IUserSession;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\TestCase;
use Psr\Log\LoggerInterface;

/**
 * Placing the copy: checksum and size against the ack, the checks on the
 * original as its initiator, the name rule and the collision rule, with the
 * real JobService against the database of the test instance.
 */
#[CoversClass(PublishService::class)]
final class PublishServiceTest extends TestCase {
	use JobServiceFactory;

	private const BYTES = '%PDF-1.7 placeholder without any original content';

	protected function setUp(): void {
		parent::setUp();
		$this->setUpJobService();
	}

	protected function tearDown(): void {
		$this->cleanTables();
		parent::tearDown();
	}

	private function publisher(): PublishService {
		return new PublishService(
			$this->service,
			$this->exApp,
			$this->access,
			new ReaderContext($this->createMock(IUserSession::class), $this->createMock(IUserManager::class)),
			$this->createMock(LoggerInterface::class),
		);
	}

	/** A job that went the whole way to verified with the given ack values. */
	private function verified(?string $sha256 = null, ?int $size = null): Job {
		self::assertNotNull($this->service->start('alice', 42)['job']);
		$claim = $this->mapper->claimNext();
		self::assertNotNull($claim);
		$this->service->toReview($claim['job'], 1, 992, 1403);
		$this->service->toApproved($this->mapper->find($claim['job']->getId()), 'alice');
		$apply = $this->mapper->claimNext();
		self::assertNotNull($apply);
		$this->service->toVerified($apply['job'], $sha256 ?? hash('sha256', self::BYTES), $size ?? strlen(self::BYTES));
		return $this->mapper->find($apply['job']->getId());
	}

	/** The container answers with $bytes as a stream. */
	private function serving(string $bytes): void {
		$stream = fopen('php://temp', 'w+b');
		self::assertIsResource($stream);
		fwrite($stream, $bytes);
		rewind($stream);
		$response = $this->createMock(IResponse::class);
		$response->method('getStatusCode')->willReturn(200);
		$response->method('getBody')->willReturn($stream);
		$this->outputResponse = $response;
	}

	private function reloaded(Job $job): Job {
		return $this->mapper->find($job->getId());
	}

	public function testTheCopyIsPlacedNextToTheOriginalAndTheJobIsPublished(): void {
		$job = $this->verified();
		$this->serving(self::BYTES);

		$this->publisher()->publish($job);

		self::assertSame([['name' => 'Bescheid_redacted.pdf', 'bytes' => self::BYTES]], $this->created);
		$after = $this->reloaded($job);
		self::assertSame(Status::Published, $after->getStatusEnum());
		self::assertSame(99, $after->getOutputFileId());
		self::assertContains('copy_created', $this->subjects());
	}

	public function testTheNameFollowsTheLanguageOfTheInitiator(): void {
		$this->languages['alice'] = 'de_DE';
		$job = $this->verified();
		$this->serving(self::BYTES);

		$this->publisher()->publish($job);

		self::assertSame("Bescheid_geschw\u{00E4}rzt.pdf", $this->created[0]['name'] ?? null);
	}

	public function testATakenNameGetsTheNameOfTheServerInstead(): void {
		$job = $this->verified();
		$this->serving(self::BYTES);
		$this->takenNames = ['Bescheid_redacted.pdf'];

		$this->publisher()->publish($job);

		self::assertSame('Bescheid_redacted (2).pdf', $this->created[0]['name'] ?? null);
		self::assertSame(Status::Published, $this->reloaded($job)->getStatusEnum());
	}

	public function testAnotherChecksumFailsTheJobAndWritesNothing(): void {
		$job = $this->verified();
		$this->serving(self::BYTES . 'X');

		$this->publisher()->publish($job);

		self::assertSame([], $this->created);
		$after = $this->reloaded($job);
		self::assertSame(Status::Failed, $after->getStatusEnum());
		self::assertSame('check_error', $after->getReason());
	}

	public function testAnotherSizeFailsTheJob(): void {
		$job = $this->verified(null, strlen(self::BYTES) + 1);
		$this->serving(self::BYTES);

		$this->publisher()->publish($job);

		self::assertSame([], $this->created);
		self::assertSame('check_error', $this->reloaded($job)->getReason());
	}

	public function testAStreamAboveTheCeilingFailsTheJob(): void {
		$job = $this->verified();
		$this->serving(str_repeat('a', PublishService::MAX_OUTPUT_BYTES + 1));

		$this->publisher()->publish($job);

		self::assertSame([], $this->created);
		self::assertSame('check_error', $this->reloaded($job)->getReason());
	}

	public function testAChangedOriginalMakesTheJobStale(): void {
		$job = $this->verified();
		$this->serving(self::BYTES);
		$this->etag = 'etag-2';

		$this->publisher()->publish($job);

		self::assertSame([], $this->created);
		self::assertSame(Status::Stale, $this->reloaded($job)->getStatusEnum());
	}

	public function testADeletedOriginalCancelsTheJob(): void {
		$job = $this->verified();
		$this->serving(self::BYTES);
		$this->readable = false;

		$this->publisher()->publish($job);

		$after = $this->reloaded($job);
		self::assertSame(Status::Cancelled, $after->getStatusEnum());
		self::assertSame('original_deleted', $after->getReason());
		self::assertNotContains('copy_created', $this->subjects());
	}

	public function testAFolderThatIsNotWritableFailsTheJob(): void {
		$job = $this->verified();
		$this->serving(self::BYTES);
		$this->folderWritable = false;

		$this->publisher()->publish($job);

		self::assertSame([], $this->created);
		self::assertSame('target_not_writable', $this->reloaded($job)->getReason());
	}

	public function testARefusedWriteFailsTheJobAsNotWritable(): void {
		$job = $this->verified();
		$this->serving(self::BYTES);
		$this->newFileFails = new NotPermittedException('/alice/files/Bescheid_redacted.pdf');

		$this->publisher()->publish($job);

		self::assertSame('target_not_writable', $this->reloaded($job)->getReason());
	}

	public function testADownloadBlockFailsTheJob(): void {
		$job = $this->verified();
		$this->serving(self::BYTES);
		$this->downloadAllowed = false;

		$this->publisher()->publish($job);

		self::assertSame([], $this->created);
		self::assertSame('download_blocked', $this->reloaded($job)->getReason());
	}

	public function testAContainerWithoutAnAnswerFailsTheJob(): void {
		$job = $this->verified();
		$this->outputResponse = null;

		$this->publisher()->publish($job);

		self::assertSame([], $this->created);
		self::assertSame('backend_unavailable', $this->reloaded($job)->getReason());
	}

	public function testAJobThatIsNotVerifiedIsLeftAlone(): void {
		$job = $this->service->start('alice', 42)['job'];
		self::assertNotNull($job);
		$this->serving(self::BYTES);

		$this->publisher()->publish($job);

		self::assertSame([], $this->created);
		self::assertSame(Status::Queued, $this->reloaded($job)->getStatusEnum());
	}
}
