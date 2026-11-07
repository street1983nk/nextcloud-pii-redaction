<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\AppInfo\Application;
use OCA\PiiRedaction\Controller\GatewayController;
use OCA\PiiRedaction\Model\Status;
use OCP\AppFramework\Http;
use OCP\AppFramework\Http\DataResponse;
use OCP\AppFramework\Http\StreamResponse;
use OCP\AppFramework\Utility\ITimeFactory;
use OCP\IRequest;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\TestCase;
use Psr\Log\LoggerInterface;

/**
 * The job bound gateway with the real JobMapper, JobService and FileAccess
 * against the database of the test instance. File 42 of alice is a double;
 * its content is an in-memory stream.
 */
#[CoversClass(GatewayController::class)]
final class GatewayControllerTest extends TestCase {
	use JobServiceFactory;

	protected function setUp(): void {
		parent::setUp();
		$this->setUpJobService();
	}

	protected function tearDown(): void {
		if (is_resource($this->content)) {
			fclose($this->content);
		}
		$this->cleanTables();
		parent::tearDown();
	}

	private function controller(string $callerAppId = Application::BACKEND_APP_ID): GatewayController {
		$request = $this->createMock(IRequest::class);
		$request->method('getHeader')->willReturnCallback(
			static fn (string $name): string => $name === 'EX-APP-ID' ? $callerAppId : '',
		);
		$time = $this->createMock(ITimeFactory::class);
		$time->method('getTime')->willReturnCallback(fn (): int => $this->clock);

		return new GatewayController(
			$request,
			$this->mapper,
			$this->service,
			$this->access,
			$time,
			$this->createMock(LoggerInterface::class),
		);
	}

	/**
	 * A started job on file 42, claimed like the container does.
	 *
	 * @return array{jobId: int, token: string}
	 */
	private function claimed(): array {
		self::assertNotNull($this->service->start('alice', 42)['job']);
		$claim = $this->mapper->claimNext();
		self::assertNotNull($claim);
		return ['jobId' => $claim['job']->getId(), 'token' => $claim['token']];
	}

	private function withContent(): void {
		$stream = fopen('php://memory', 'rb+');
		self::assertIsResource($stream);
		fwrite($stream, '%PDF-1.7 PIIKANARIE7Q4XZ9');
		rewind($stream);
		$this->content = $stream;
	}

	private function jobStatus(int $jobId): Status {
		return $this->mapper->find($jobId)->getStatusEnum();
	}

	public function testAForeignExAppGets403(): void {
		$claim = $this->claimed();
		$this->withContent();

		$response = $this->controller('other_app')->file($claim['jobId'], $claim['token']);

		self::assertInstanceOf(DataResponse::class, $response);
		self::assertSame(Http::STATUS_FORBIDDEN, $response->getStatus());
		self::assertSame([], $this->openedAs);
	}

	public function testAForeignTokenGets404(): void {
		$claim = $this->claimed();
		$this->withContent();

		$response = $this->controller()->file($claim['jobId'], str_repeat('0', 32));

		self::assertSame(Http::STATUS_NOT_FOUND, $response->getStatus());
		self::assertSame([], $this->openedAs);
		self::assertSame(Status::Analyzing, $this->jobStatus($claim['jobId']));
	}

	public function testAnUnknownJobGets404(): void {
		$claim = $this->claimed();
		self::assertSame(Http::STATUS_NOT_FOUND, $this->controller()->file($claim['jobId'] + 1000, $claim['token'])->getStatus());
	}

	public function testALeaseThatRanOutGets404(): void {
		$claim = $this->claimed();
		$this->withContent();
		$this->clock += 10_000;

		self::assertSame(Http::STATUS_NOT_FOUND, $this->controller()->file($claim['jobId'], $claim['token'])->getStatus());
		self::assertSame([], $this->openedAs);
	}

	public function testAJobInReviewGets404(): void {
		$claim = $this->claimed();
		$this->withContent();
		$job = $this->mapper->find($claim['jobId']);
		// The token stays on the row here, so only the state can refuse.
		$job->setStatus(Status::Review->value);
		$this->mapper->update($job);

		self::assertSame(Http::STATUS_NOT_FOUND, $this->controller()->file($claim['jobId'], $claim['token'])->getStatus());
		self::assertSame([], $this->openedAs);
	}

	public function testAFileGoneForTheInitiatorGets404AndFailsTheJob(): void {
		$claim = $this->claimed();
		$this->readable = false;

		$response = $this->controller()->file($claim['jobId'], $claim['token']);

		self::assertSame(Http::STATUS_NOT_FOUND, $response->getStatus());
		$job = $this->mapper->find($claim['jobId']);
		self::assertSame(Status::Failed, $job->getStatusEnum());
		self::assertSame('not_readable', $job->getReason());
	}

	public function testADownloadBlockGets403AndFailsTheJob(): void {
		$claim = $this->claimed();
		$this->downloadAllowed = false;

		$response = $this->controller()->file($claim['jobId'], $claim['token']);

		self::assertSame(Http::STATUS_FORBIDDEN, $response->getStatus());
		self::assertSame('download_blocked', $this->mapper->find($claim['jobId'])->getReason());
		self::assertSame([], $this->openedAs);
	}

	public function testAChangedFileGets409AndMakesTheJobStale(): void {
		$claim = $this->claimed();
		$this->etag = 'etag-2';

		$response = $this->controller()->file($claim['jobId'], $claim['token']);

		self::assertSame(Http::STATUS_CONFLICT, $response->getStatus());
		self::assertSame(Status::Stale, $this->jobStatus($claim['jobId']));
		self::assertSame(['job_stale'], $this->subjects());
		self::assertSame([], $this->openedAs);
	}

	public function testTheJobFileIsStreamedWithItsEtagAndWithoutAName(): void {
		$claim = $this->claimed();
		$this->withContent();

		$response = $this->controller()->file($claim['jobId'], $claim['token']);

		self::assertInstanceOf(StreamResponse::class, $response);
		self::assertSame(Http::STATUS_OK, $response->getStatus());
		self::assertSame(['rb'], $this->openedAs);
		$headers = $response->getHeaders();
		self::assertSame('etag-1', $headers['X-Pii-Etag'] ?? null);
		self::assertSame('application/octet-stream', $headers['Content-Type'] ?? null);
		self::assertSame('no-store', $headers['Cache-Control'] ?? null);
		self::assertArrayNotHasKey('Content-Disposition', $headers);
		foreach ($headers as $name => $value) {
			self::assertStringNotContainsString('Bescheid', $name . ': ' . (is_string($value) ? $value : (string)json_encode($value)));
		}
		self::assertSame(Status::Analyzing, $this->jobStatus($claim['jobId']));
	}

	public function testAFileThatCannotBeOpenedGets503AndKeepsTheJob(): void {
		$claim = $this->claimed();
		$this->content = false;

		$response = $this->controller()->file($claim['jobId'], $claim['token']);

		self::assertSame(Http::STATUS_SERVICE_UNAVAILABLE, $response->getStatus());
		self::assertSame(Status::Analyzing, $this->jobStatus($claim['jobId']));
	}
}
