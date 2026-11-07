<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Controller\ReviewController;
use OCA\PiiRedaction\Db\Job;
use OCA\PiiRedaction\Model\Reason;
use OCA\PiiRedaction\Model\Status;
use OCA\PiiRedaction\Service\NotificationSender;
use OCP\AppFramework\Http;
use OCP\AppFramework\Http\DataDisplayResponse;
use OCP\AppFramework\Http\JSONResponse;
use OCP\AppFramework\Http\Response;
use OCP\AppFramework\Http\TemplateResponse;
use OCP\AppFramework\Services\IInitialState;
use OCP\AppFramework\Utility\ITimeFactory;
use OCP\IL10N;
use OCP\IRequest;
use OCP\IUser;
use OCP\IUserSession;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\TestCase;
use Psr\Log\LoggerInterface;

/**
 * Every state of the review page (UI-SPEC Fläche 2) with its HTTP status,
 * the page image proxy and the placeholder action, with the real JobService
 * and FileAccess against the database of the test instance.
 */
#[CoversClass(ReviewController::class)]
final class ReviewControllerTest extends TestCase {
	use JobServiceFactory;

	private const PNG = "\x89PNG\r\n\x1a\nPIXELS";

	private ?string $signedIn = 'alice';
	/** @var array<string, mixed>|null */
	private ?array $initial = null;

	protected function setUp(): void {
		parent::setUp();
		$this->setUpJobService();
		$this->initial = null;
	}

	protected function tearDown(): void {
		$this->cleanTables();
		parent::tearDown();
	}

	private function controller(): ReviewController {
		$session = $this->createMock(IUserSession::class);
		$session->method('getUser')->willReturnCallback(function (): ?IUser {
			if ($this->signedIn === null) {
				return null;
			}
			$user = $this->createMock(IUser::class);
			$user->method('getUID')->willReturn($this->signedIn);
			return $user;
		});
		$initialState = $this->createMock(IInitialState::class);
		$initialState->method('provideInitialState')->willReturnCallback(function (string $key, mixed $data): void {
			self::assertSame('review', $key);
			$this->initial = $data;
		});
		$l10n = $this->createMock(IL10N::class);
		$l10n->method('t')->willReturnCallback(
			static fn (string $text, mixed $parameters = []): string => vsprintf($text, is_array($parameters) ? $parameters : [$parameters]),
		);
		$time = $this->createMock(ITimeFactory::class);
		$time->method('getTime')->willReturnCallback(fn (): int => $this->clock);
		$time->method('getDateTime')->willReturnCallback(fn (): \DateTime => new \DateTime('@' . $this->clock));

		return new ReviewController(
			$this->createMock(IRequest::class),
			$session,
			$this->service,
			$this->exApp,
			new NotificationSender($this->notificationManager(), $time, $this->createMock(LoggerInterface::class)),
			$this->events,
			$initialState,
			$l10n,
			$this->createMock(LoggerInterface::class),
		);
	}

	private function started(): Job {
		$job = $this->service->start('alice', 42)['job'];
		self::assertNotNull($job);
		return $job;
	}

	private function inReview(): Job {
		$this->started();
		$claim = $this->mapper->claimNext();
		self::assertNotNull($claim);
		$this->service->toReview($claim['job'], 3, 992, 1403);
		return $this->mapper->find($claim['job']->getId());
	}

	/** @return array<string, mixed> */
	private function initial(): array {
		self::assertIsArray($this->initial);
		return $this->initial;
	}

	private static function assertGuarded(Response $response): void {
		$headers = $response->getHeaders();
		self::assertSame('private, no-store', $headers['Cache-Control'] ?? null);
		self::assertSame('nosniff', $headers['X-Content-Type-Options'] ?? null);
	}

	private static function title(TemplateResponse $response): string {
		$title = $response->getParams()['pageTitle'] ?? null;
		self::assertIsString($title);
		return $title;
	}

	// -- the page ---------------------------------------------------------------

	public function testAQueuedJobShowsItsStateAndNameWithoutAnImage(): void {
		$job = $this->started();

		$response = $this->controller()->page($job->getId());

		self::assertSame(Http::STATUS_OK, $response->getStatus());
		self::assertSame('review', $response->getTemplateName());
		$initial = $this->initial();
		self::assertSame('job', $initial['state']);
		self::assertSame('queued', $initial['status']);
		self::assertSame('Bescheid.pdf', $initial['fileName']);
		self::assertSame(42, $initial['fileId']);
		self::assertArrayNotHasKey('image', $initial);
		self::assertSame('Review: Bescheid.pdf', self::title($response));
	}

	public function testAJobInReviewCarriesTheImageSize(): void {
		$job = $this->inReview();

		$this->controller()->page($job->getId());

		$initial = $this->initial();
		self::assertSame('review', $initial['status']);
		self::assertSame(['width' => 992, 'height' => 1403], $initial['image']);
		self::assertSame(3, $initial['pagesTotal']);
	}

	public function testAForeignUserGetsA404WithoutAnyName(): void {
		$job = $this->started();
		$this->signedIn = 'bob';

		$response = $this->controller()->page($job->getId());

		self::assertSame(Http::STATUS_NOT_FOUND, $response->getStatus());
		self::assertSame(['state' => 'unavailable'], $this->initial());
		self::assertSame('Review', self::title($response));
		self::assertStringNotContainsString('Bescheid', (string)json_encode($response->getParams()));
	}

	public function testAnUnknownJobGetsTheSame404(): void {
		$response = $this->controller()->page(987654);
		self::assertSame(Http::STATUS_NOT_FOUND, $response->getStatus());
		self::assertSame(['state' => 'unavailable'], $this->initial());
	}

	public function testAFileNoLongerReadableGetsTheSame404(): void {
		$job = $this->started();
		$this->readable = false;

		$response = $this->controller()->page($job->getId());

		self::assertSame(Http::STATUS_NOT_FOUND, $response->getStatus());
		self::assertSame(['state' => 'unavailable'], $this->initial());
	}

	public function testADeletedOriginalShowsTheCancelledStateWithoutAName(): void {
		$job = $this->started();
		$this->service->toCancelled($job, Reason::OriginalDeleted);
		$this->readable = false;

		$response = $this->controller()->page($job->getId());

		self::assertSame(Http::STATUS_OK, $response->getStatus());
		$initial = $this->initial();
		self::assertSame('cancelled', $initial['status']);
		self::assertSame('original_deleted', $initial['reason']);
		self::assertArrayNotHasKey('fileName', $initial);
		self::assertSame('Review', self::title($response));
		self::assertStringNotContainsString('Bescheid', (string)json_encode([$initial, $response->getParams()]));
	}

	public function testADownloadBlockShowsTheBlockedStateWithoutAnImage(): void {
		$job = $this->inReview();
		$this->downloadAllowed = false;

		$response = $this->controller()->page($job->getId());

		self::assertSame(Http::STATUS_OK, $response->getStatus());
		$initial = $this->initial();
		self::assertSame('blocked', $initial['state']);
		self::assertSame('download_blocked', $initial['recheck']);
		self::assertArrayNotHasKey('image', $initial);
	}

	public function testAChangedFileShowsTheJobAsStale(): void {
		$job = $this->inReview();
		$this->etag = 'etag-2';

		$response = $this->controller()->page($job->getId());

		self::assertSame(Http::STATUS_OK, $response->getStatus());
		self::assertSame('stale', $this->initial()['status']);
		self::assertSame('original_changed', $this->initial()['reason']);
		self::assertArrayNotHasKey('image', $this->initial());
	}

	public function testOpeningThePageDismissesTheNotification(): void {
		$job = $this->inReview();
		$before = count($this->dismissed);

		$this->controller()->page($job->getId());

		self::assertSame(['job:' . $job->getId()], array_slice($this->dismissed, $before));
	}

	// -- the page image ---------------------------------------------------------

	public function testThePageImageIsAGuardedPng(): void {
		$job = $this->inReview();
		$this->pagePng = self::PNG;

		$response = $this->controller()->pageImage($job->getId(), 1);

		self::assertInstanceOf(DataDisplayResponse::class, $response);
		self::assertSame(Http::STATUS_OK, $response->getStatus());
		self::assertSame(self::PNG, $response->getData());
		self::assertSame('image/png', $response->getHeaders()['Content-Type'] ?? null);
		self::assertGuarded($response);
		self::assertSame([[$job->getId(), 1, 'alice']], $this->pageCalls);
	}

	public function testAChangedFileAnswersTheImageWith409AndMakesTheJobStale(): void {
		$job = $this->inReview();
		$this->pagePng = self::PNG;
		$this->etag = 'etag-2';

		$response = $this->controller()->pageImage($job->getId(), 1);

		self::assertSame(Http::STATUS_CONFLICT, $response->getStatus());
		self::assertGuarded($response);
		self::assertSame(Status::Stale, $this->mapper->find($job->getId())->getStatusEnum());
		self::assertSame([], $this->pageCalls);
	}

	public function testADownloadBlockAnswersTheImageWith403(): void {
		$job = $this->inReview();
		$this->pagePng = self::PNG;
		$this->downloadAllowed = false;

		$response = $this->controller()->pageImage($job->getId(), 1);

		self::assertSame(Http::STATUS_FORBIDDEN, $response->getStatus());
		self::assertGuarded($response);
		self::assertSame([], $this->pageCalls);
	}

	public function testTheImageAnswers404ForAForeignUserAnotherPageOrAnotherState(): void {
		$queued = $this->started();
		$this->pagePng = self::PNG;
		$response = $this->controller()->pageImage($queued->getId(), 1);
		self::assertSame(Http::STATUS_NOT_FOUND, $response->getStatus());
		self::assertGuarded($response);

		$this->cleanTables();
		$job = $this->inReview();
		self::assertSame(Http::STATUS_NOT_FOUND, $this->controller()->pageImage($job->getId(), 2)->getStatus());
		$this->signedIn = 'bob';
		self::assertSame(Http::STATUS_NOT_FOUND, $this->controller()->pageImage($job->getId(), 1)->getStatus());
		self::assertSame([], $this->pageCalls);
	}

	public function testNoUsableImageFromTheContainerAnswers502(): void {
		$job = $this->inReview();
		$this->pagePng = null;

		$response = $this->controller()->pageImage($job->getId(), 1);

		self::assertSame(Http::STATUS_BAD_GATEWAY, $response->getStatus());
		self::assertGuarded($response);
	}

	// -- the placeholder action -------------------------------------------------

	public function testThePlaceholderApprovesAJobInReview(): void {
		$job = $this->inReview();

		$response = $this->controller()->placeholder($job->getId());

		self::assertSame(Http::STATUS_ACCEPTED, $response->getStatus());
		self::assertSame(['status' => 'approved'], $response->getData());
		self::assertSame(Status::Approved, $this->mapper->find($job->getId())->getStatusEnum());
		self::assertContains('placeholder_requested', $this->actions($job->getId()));
		self::assertGuarded($response);
	}

	public function testThePlaceholderIsRefusedOutsideReview(): void {
		$job = $this->started();

		$response = $this->controller()->placeholder($job->getId());

		self::assertInstanceOf(JSONResponse::class, $response);
		self::assertSame(Http::STATUS_CONFLICT, $response->getStatus());
		self::assertSame(Status::Queued, $this->mapper->find($job->getId())->getStatusEnum());
	}

	public function testThePlaceholderWaitsForTheBackend(): void {
		$job = $this->inReview();
		$this->backendReady = false;

		$response = $this->controller()->placeholder($job->getId());

		self::assertSame(Http::STATUS_CONFLICT, $response->getStatus());
		self::assertSame(['reason' => 'backend_unavailable'], $response->getData());
		self::assertSame(Status::Review, $this->mapper->find($job->getId())->getStatusEnum());
	}

	public function testThePlaceholderIsRefusedUnderABlockOrAfterAChange(): void {
		$job = $this->inReview();
		$this->downloadAllowed = false;
		self::assertSame(['reason' => 'download_blocked'], $this->controller()->placeholder($job->getId())->getData());

		$this->downloadAllowed = true;
		$this->etag = 'etag-2';
		$response = $this->controller()->placeholder($job->getId());
		self::assertSame(Http::STATUS_CONFLICT, $response->getStatus());
		self::assertSame(['reason' => 'original_changed'], $response->getData());
		self::assertSame(Status::Stale, $this->mapper->find($job->getId())->getStatusEnum());
	}

	public function testThePlaceholderOfAForeignJobIs404(): void {
		$job = $this->inReview();
		$this->signedIn = 'bob';

		$response = $this->controller()->placeholder($job->getId());

		self::assertSame(Http::STATUS_NOT_FOUND, $response->getStatus());
		self::assertSame(Status::Review, $this->mapper->find($job->getId())->getStatusEnum());
	}
}
