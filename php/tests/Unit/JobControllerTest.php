<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Controller\JobController;
use OCP\AppFramework\Http;
use OCP\AppFramework\Http\JSONResponse;
use OCP\AppFramework\Http\Response;
use OCP\IRequest;
use OCP\IURLGenerator;
use OCP\IUser;
use OCP\IUserSession;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\TestCase;
use Psr\Log\LoggerInterface;

/**
 * Every HTTP answer of UI-SPEC Fläche 1 and of the status route, with the
 * real JobService and FileAccess behind the controller.
 */
#[CoversClass(JobController::class)]
final class JobControllerTest extends TestCase {
	use JobServiceFactory;

	private ?string $signedIn = 'alice';

	protected function setUp(): void {
		parent::setUp();
		$this->setUpJobService();
	}

	protected function tearDown(): void {
		$this->cleanTables();
		parent::tearDown();
	}

	private function controller(): JobController {
		$session = $this->createMock(IUserSession::class);
		$session->method('getUser')->willReturnCallback(function (): ?IUser {
			if ($this->signedIn === null) {
				return null;
			}
			$user = $this->createMock(IUser::class);
			$user->method('getUID')->willReturn($this->signedIn);
			return $user;
		});
		$urls = $this->createMock(IURLGenerator::class);
		$urls->method('linkToRoute')->willReturnCallback(
			static fn (string $route, array $parameters = []): string => '/apps/pii_redaction/review/' . $parameters['jobId'],
		);
		return new JobController(
			$this->createMock(IRequest::class),
			$session,
			$this->access,
			$this->service,
			$urls,
			$this->createMock(LoggerInterface::class),
		);
	}

	/**
	 * @return array<string, mixed>
	 */
	private function body(JSONResponse $response): array {
		$data = $response->getData();
		self::assertIsArray($data);
		return $data;
	}

	private static function assertNoStore(Response $response): void {
		self::assertSame('private, no-store', $response->getHeaders()['Cache-Control'] ?? null);
	}

	public function testANewJobAnswers201WithPositionAndReviewUrl(): void {
		$response = $this->controller()->create(42);
		$body = $this->body($response);

		self::assertSame(Http::STATUS_CREATED, $response->getStatus());
		self::assertSame('queued', $body['status']);
		self::assertSame(0, $body['ahead']);
		self::assertSame('/apps/pii_redaction/review/' . $body['jobId'], $body['reviewUrl']);
		self::assertArrayNotHasKey('fileName', $body);
		self::assertNoStore($response);
	}

	public function testASecondStartAnswers200WithTheSameJob(): void {
		$first = $this->body($this->controller()->create(42));
		$response = $this->controller()->create(42);

		self::assertSame(Http::STATUS_OK, $response->getStatus());
		self::assertSame($first['jobId'], $this->body($response)['jobId']);
	}

	public function testABackendThatIsNotReadyAnswers503(): void {
		$this->backendReady = false;
		$response = $this->controller()->create(42);
		self::assertSame(Http::STATUS_SERVICE_UNAVAILABLE, $response->getStatus());
		self::assertSame(['reason' => 'backend_unavailable'], $this->body($response));
	}

	public function testADownloadBlockAnswers403(): void {
		$this->downloadAllowed = false;
		$response = $this->controller()->create(42);
		self::assertSame(Http::STATUS_FORBIDDEN, $response->getStatus());
		self::assertSame(['reason' => 'download_blocked'], $this->body($response));
	}

	public function testAnUnreadableFileAnswers404(): void {
		$this->signedIn = 'bob';
		$response = $this->controller()->create(42);
		self::assertSame(Http::STATUS_NOT_FOUND, $response->getStatus());
		self::assertSame(['reason' => 'not_readable'], $this->body($response));
	}

	public function testAnotherFormatAnswers415(): void {
		$this->mime = 'text/plain';
		$response = $this->controller()->create(42);
		self::assertSame(Http::STATUS_UNSUPPORTED_MEDIA_TYPE, $response->getStatus());
		self::assertSame(['reason' => 'unsupported_format'], $this->body($response));
	}

	public function testWithoutASessionTheStartAnswers401(): void {
		$this->signedIn = null;
		self::assertSame(Http::STATUS_UNAUTHORIZED, $this->controller()->create(42)->getStatus());
		self::assertSame([], $this->sent);
	}

	public function testTheStatusOfTheOwnJobCarriesCodesOnly(): void {
		$jobId = $this->body($this->controller()->create(42))['jobId'];
		$response = $this->controller()->show($jobId);

		self::assertInstanceOf(JSONResponse::class, $response);
		self::assertSame(Http::STATUS_OK, $response->getStatus());
		$body = $this->body($response);
		self::assertSame(
			['jobId', 'status', 'stage', 'reason', 'ahead', 'pagesDone', 'pagesTotal', 'backendReady', 'outputFileId', 'outputName'],
			array_keys($body),
		);
		self::assertSame('queued', $body['status']);
		self::assertTrue($body['backendReady']);
		self::assertNoStore($response);
	}

	public function testAForeignJobAnswersAnEmpty404(): void {
		$jobId = $this->body($this->controller()->create(42))['jobId'];
		$this->signedIn = 'bob';
		$response = $this->controller()->show($jobId);

		self::assertSame(Http::STATUS_NOT_FOUND, $response->getStatus());
		self::assertNotInstanceOf(JSONResponse::class, $response);
		self::assertSame('', $response->render());
		self::assertNoStore($response);
	}

	public function testAnUnknownJobAnswersTheSame404(): void {
		$response = $this->controller()->show(987654);
		self::assertSame(Http::STATUS_NOT_FOUND, $response->getStatus());
		self::assertSame('', $response->render());
	}

	public function testAChangedFileShowsStaleWithoutAName(): void {
		$jobId = $this->body($this->controller()->create(42))['jobId'];
		$this->etag = 'etag-2';
		$response = $this->controller()->show($jobId);

		self::assertInstanceOf(JSONResponse::class, $response);
		$body = $this->body($response);
		self::assertSame('stale', $body['status']);
		self::assertSame('original_changed', $body['reason']);
		self::assertStringNotContainsString('Bescheid', (string)json_encode($body));
	}
}
