<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\AppInfo\Application;
use OCA\PiiRedaction\Controller\QueueController;
use OCA\PiiRedaction\Db\Job;
use OCA\PiiRedaction\Model\Status;
use OCA\PiiRedaction\Model\Task;
use OCP\AppFramework\Http;
use OCP\AppFramework\Http\DataResponse;
use OCP\AppFramework\Utility\ITimeFactory;
use OCP\BackgroundJob\IJobList;
use OCP\IRequest;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\TestCase;
use Psr\Log\LoggerInterface;

/**
 * claim, progress and ack with the real JobMapper and JobService against
 * the database of the test instance. The container is played by the test:
 * it claims through the controller and reports with the token it got.
 */
#[CoversClass(QueueController::class)]
final class QueueControllerTest extends TestCase {
	use JobServiceFactory;

	private const SHA = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

	/** @var list<array{0: mixed, 1: mixed}> */
	private array $queued = [];

	protected function setUp(): void {
		parent::setUp();
		$this->setUpJobService();
		$this->queued = [];
	}

	protected function tearDown(): void {
		$this->cleanTables();
		parent::tearDown();
	}

	private function controller(string $callerAppId = Application::BACKEND_APP_ID): QueueController {
		$request = $this->createMock(IRequest::class);
		$request->method('getHeader')->willReturnCallback(
			static fn (string $name): string => $name === 'EX-APP-ID' ? $callerAppId : '',
		);
		$time = $this->createMock(ITimeFactory::class);
		$time->method('getTime')->willReturnCallback(fn (): int => $this->clock);
		$jobList = $this->createMock(IJobList::class);
		$jobList->method('add')->willReturnCallback(function (mixed $job, mixed $argument = null): void {
			$this->queued[] = [$job, $argument];
		});

		return new QueueController(
			$request,
			$this->mapper,
			$this->service,
			$this->access,
			$jobList,
			$time,
			$this->createMock(LoggerInterface::class),
		);
	}

	/** @return array<string, mixed> */
	private static function data(DataResponse $response): array {
		$data = $response->getData();
		self::assertIsArray($data);
		return $data;
	}

	/**
	 * Starts a job on file 42 and claims it like the container.
	 *
	 * @return array{jobId: int, token: string}
	 */
	private function claimedAnalyze(): array {
		self::assertNotNull($this->service->start('alice', 42)['job']);
		$data = self::data($this->controller()->claim());
		self::assertSame('analyze', $data['task']);
		return ['jobId' => $data['jobId'], 'token' => $data['token']];
	}

	/**
	 * A job that went through review and approval and was claimed for apply.
	 *
	 * @return array{jobId: int, token: string}
	 */
	private function claimedApply(): array {
		$claim = $this->claimedAnalyze();
		$this->ackReview($claim);
		$this->service->toApproved($this->job($claim['jobId']), 'alice');
		$data = self::data($this->controller()->claim());
		self::assertSame('apply', $data['task']);
		return ['jobId' => $data['jobId'], 'token' => $data['token']];
	}

	/**
	 * @param array{jobId: int, token: string} $claim
	 * @param array<string, mixed>|null $image
	 */
	private function ackReview(array $claim, string $etagSeen = 'etag-1', ?array $image = ['width' => 992, 'height' => 1403]): DataResponse {
		return $this->controller()->ack($claim['jobId'], $claim['token'], 'review', null, 3, $etagSeen, $image, null);
	}

	private function job(int $jobId): Job {
		return $this->mapper->find($jobId);
	}

	public function testAForeignExAppGets403OnClaim(): void {
		self::assertNotNull($this->service->start('alice', 42)['job']);
		$response = $this->controller('other_app')->claim();
		self::assertSame(Http::STATUS_FORBIDDEN, $response->getStatus());
		// Nothing was handed out: the backend itself still gets the task.
		self::assertSame('analyze', self::data($this->controller()->claim())['task']);
	}

	public function testAForeignExAppGets403OnProgress(): void {
		$claim = $this->claimedAnalyze();
		$response = $this->controller('other_app')->progress($claim['jobId'], $claim['token'], 'fetching', null, null);
		self::assertSame(Http::STATUS_FORBIDDEN, $response->getStatus());
		self::assertSame('waiting', $this->job($claim['jobId'])->getStage());
	}

	public function testAForeignExAppGets403OnAck(): void {
		$claim = $this->claimedAnalyze();
		$response = $this->controller('other_app')->ack($claim['jobId'], $claim['token'], 'review', null, 3, 'etag-1', ['width' => 10, 'height' => 10], null);
		self::assertSame(Http::STATUS_FORBIDDEN, $response->getStatus());
		self::assertSame(Status::Analyzing, $this->job($claim['jobId'])->getStatusEnum());
	}

	public function testAnEmptyQueueAnswersAnEmptyObject(): void {
		$response = $this->controller()->claim();
		self::assertSame(Http::STATUS_OK, $response->getStatus());
		self::assertSame([], self::data($response));
	}

	public function testAClaimHandsOutOneTaskWithItsFields(): void {
		$job = $this->service->start('alice', 42)['job'];
		self::assertNotNull($job);

		$data = self::data($this->controller()->claim());

		self::assertSame(['jobId', 'task', 'token', 'fileId', 'userId', 'etag', 'leaseSeconds'], array_keys($data));
		self::assertSame($job->getId(), $data['jobId']);
		self::assertSame(42, $data['fileId']);
		self::assertSame('alice', $data['userId']);
		self::assertSame('etag-1', $data['etag']);
		self::assertMatchesRegularExpression('/^[0-9a-f]{32}$/', $data['token']);
		self::assertSame(Status::Analyzing, $this->job($job->getId())->getStatusEnum());
		// One at a time: a second claim gets nothing while the lease lives.
		self::assertSame([], self::data($this->controller()->claim()));
	}

	public function testProgressWithAForeignTokenIs409(): void {
		$claim = $this->claimedAnalyze();
		$response = $this->controller()->progress($claim['jobId'], str_repeat('0', 32), 'fetching', null, null);
		self::assertSame(Http::STATUS_CONFLICT, $response->getStatus());
	}

	public function testProgressWithAnUnknownStageIs400(): void {
		$claim = $this->claimedAnalyze();
		$response = $this->controller()->progress($claim['jobId'], $claim['token'], 'uploading', null, null);
		self::assertSame(Http::STATUS_BAD_REQUEST, $response->getStatus());
	}

	public function testProgressWithCountsOutOfRangeIs400(): void {
		$claim = $this->claimedAnalyze();
		$controller = $this->controller();
		self::assertSame(Http::STATUS_BAD_REQUEST, $controller->progress($claim['jobId'], $claim['token'], 'rendering', -1, 3)->getStatus());
		self::assertSame(Http::STATUS_BAD_REQUEST, $controller->progress($claim['jobId'], $claim['token'], 'rendering', 4, 3)->getStatus());
		self::assertSame(Http::STATUS_BAD_REQUEST, $controller->progress($claim['jobId'], $claim['token'], 'rendering', 0, 100001)->getStatus());
	}

	public function testProgressStoresStageAndCountsAndExtendsTheLease(): void {
		$claim = $this->claimedAnalyze();
		$before = $this->job($claim['jobId'])->getLeaseUntil();
		$this->clock += 30;

		$response = $this->controller()->progress($claim['jobId'], $claim['token'], 'rendering', 1, 3);

		self::assertSame(Http::STATUS_OK, $response->getStatus());
		$job = $this->job($claim['jobId']);
		self::assertSame('rendering', $job->getStage());
		self::assertSame(1, $job->getPagesDone());
		self::assertSame(3, $job->getPagesTotal());
		self::assertGreaterThan($before, $job->getLeaseUntil());
	}

	public function testProgressAfterTheLeaseRanOutIs409(): void {
		$claim = $this->claimedAnalyze();
		$this->clock += 10_000;
		$response = $this->controller()->progress($claim['jobId'], $claim['token'], 'fetching', null, null);
		self::assertSame(Http::STATUS_CONFLICT, $response->getStatus());
	}

	public function testAckReviewWithTheSameEtagMovesTheJobToReview(): void {
		$claim = $this->claimedAnalyze();

		$response = $this->ackReview($claim);

		self::assertSame(Http::STATUS_OK, $response->getStatus());
		$job = $this->job($claim['jobId']);
		self::assertSame(Status::Review, $job->getStatusEnum());
		self::assertSame(992, $job->getImageWidth());
		self::assertSame(1403, $job->getImageHeight());
		self::assertSame(3, $job->getPagesTotal());
		self::assertNull($job->getClaimToken());
		self::assertSame(['review_ready'], $this->subjects());
	}

	public function testAckReviewWithAnotherSeenEtagMakesTheJobStale(): void {
		$claim = $this->claimedAnalyze();

		$response = $this->ackReview($claim, 'etag-0');

		self::assertSame(Http::STATUS_CONFLICT, $response->getStatus());
		self::assertSame(['reason' => 'original_changed'], self::data($response));
		self::assertSame(Status::Stale, $this->job($claim['jobId'])->getStatusEnum());
		self::assertNotContains('review_ready', $this->subjects());
	}

	public function testAckReviewWhenTheFileChangedMeanwhileMakesTheJobStale(): void {
		$claim = $this->claimedAnalyze();
		$this->etag = 'etag-2';

		$response = $this->ackReview($claim);

		self::assertSame(Http::STATUS_CONFLICT, $response->getStatus());
		self::assertSame(Status::Stale, $this->job($claim['jobId'])->getStatusEnum());
		self::assertSame(['job_stale'], $this->subjects());
	}

	public function testAckReviewWithAnImageOutOfRangeIs400(): void {
		$claim = $this->claimedAnalyze();
		self::assertSame(Http::STATUS_BAD_REQUEST, $this->ackReview($claim, 'etag-1', ['width' => 0, 'height' => 10])->getStatus());
		self::assertSame(Http::STATUS_BAD_REQUEST, $this->ackReview($claim, 'etag-1', ['width' => 20001, 'height' => 10])->getStatus());
		self::assertSame(Http::STATUS_BAD_REQUEST, $this->ackReview($claim, 'etag-1', ['width' => '992', 'height' => 10])->getStatus());
		self::assertSame(Http::STATUS_BAD_REQUEST, $this->ackReview($claim, 'etag-1', null)->getStatus());
		self::assertSame(Status::Analyzing, $this->job($claim['jobId'])->getStatusEnum());
	}

	public function testAckFailedWithoutOrWithAnUnknownReasonIs400(): void {
		$claim = $this->claimedAnalyze();
		$controller = $this->controller();
		self::assertSame(Http::STATUS_BAD_REQUEST, $controller->ack($claim['jobId'], $claim['token'], 'failed', null, null, null, null, null)->getStatus());
		self::assertSame(Http::STATUS_BAD_REQUEST, $controller->ack($claim['jobId'], $claim['token'], 'failed', 'disk full at /tmp', null, null, null, null)->getStatus());
		self::assertSame(Status::Analyzing, $this->job($claim['jobId'])->getStatusEnum());

		self::assertSame(Http::STATUS_OK, $controller->ack($claim['jobId'], $claim['token'], 'failed', 'render_failed', null, null, null, null)->getStatus());
		$job = $this->job($claim['jobId']);
		self::assertSame(Status::Failed, $job->getStatusEnum());
		self::assertSame('render_failed', $job->getReason());
		self::assertSame(Task::Purge, $job->getTaskEnum());
	}

	public function testAnUnknownResultIs400(): void {
		$claim = $this->claimedAnalyze();
		$response = $this->controller()->ack($claim['jobId'], $claim['token'], 'published', null, null, null, null, null);
		self::assertSame(Http::STATUS_BAD_REQUEST, $response->getStatus());
	}

	public function testAckWithAForeignTokenIs409(): void {
		$claim = $this->claimedAnalyze();
		$response = $this->ackReview(['jobId' => $claim['jobId'], 'token' => str_repeat('f', 32)]);
		self::assertSame(Http::STATUS_CONFLICT, $response->getStatus());
		self::assertSame(Status::Analyzing, $this->job($claim['jobId'])->getStatusEnum());
	}

	public function testAckVerifiedWithABrokenChecksumIs400AndQueuesNothing(): void {
		$claim = $this->claimedApply();
		$controller = $this->controller();
		foreach ([['sha256' => 'abc', 'size' => 10], ['sha256' => strtoupper(self::SHA), 'size' => 10], ['sha256' => self::SHA, 'size' => 0], ['sha256' => self::SHA, 'size' => 33554433], null] as $output) {
			$response = $controller->ack($claim['jobId'], $claim['token'], 'verified', null, null, null, null, $output);
			self::assertSame(Http::STATUS_BAD_REQUEST, $response->getStatus());
		}
		self::assertSame([], $this->queued);
		self::assertSame(Status::Applying, $this->job($claim['jobId'])->getStatusEnum());
	}

	public function testAckVerifiedQueuesThePublishJob(): void {
		$claim = $this->claimedApply();

		$response = $this->controller()->ack($claim['jobId'], $claim['token'], 'verified', null, null, null, null, ['sha256' => self::SHA, 'size' => 2048]);

		self::assertSame(Http::STATUS_OK, $response->getStatus());
		$job = $this->job($claim['jobId']);
		self::assertSame(Status::Verified, $job->getStatusEnum());
		self::assertSame(self::SHA, $job->getOutputSha256());
		self::assertSame(2048, $job->getOutputSize());
		self::assertSame([['OCA\\PiiRedaction\\BackgroundJob\\PublishJob', ['jobId' => $claim['jobId']]]], $this->queued);
	}

	public function testAckPurgedEndsThePurgeTask(): void {
		$claim = $this->claimedAnalyze();
		$this->controller()->ack($claim['jobId'], $claim['token'], 'failed', 'render_failed', null, null, null, null);
		$purge = self::data($this->controller()->claim());
		self::assertSame('purge', $purge['task']);

		$response = $this->controller()->ack($purge['jobId'], $purge['token'], 'purged', null, null, null, null, null);

		self::assertSame(Http::STATUS_OK, $response->getStatus());
		$job = $this->job($claim['jobId']);
		self::assertNull($job->getTask());
		self::assertSame(Status::Failed, $job->getStatusEnum());
	}
}
