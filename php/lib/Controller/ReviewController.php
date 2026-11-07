<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Controller;

use OCA\PiiRedaction\AppInfo\Application;
use OCA\PiiRedaction\Db\JobEventMapper;
use OCA\PiiRedaction\Model\Reason;
use OCA\PiiRedaction\Model\Recheck;
use OCA\PiiRedaction\Model\Status;
use OCA\PiiRedaction\Service\ExAppService;
use OCA\PiiRedaction\Service\JobService;
use OCA\PiiRedaction\Service\NotificationSender;
use OCP\AppFramework\Controller;
use OCP\AppFramework\Http;
use OCP\AppFramework\Http\DataDisplayResponse;
use OCP\AppFramework\Http\JSONResponse;
use OCP\AppFramework\Http\Response;
use OCP\AppFramework\Http\TemplateResponse;
use OCP\AppFramework\Services\IInitialState;
use OCP\IL10N;
use OCP\IRequest;
use OCP\IUserSession;
use OCP\Util;
use Psr\Log\LoggerInterface;

/**
 * The review page of a job, its page image and the placeholder action
 * (UI-SPEC Fläche 2, RESEARCH Pattern 3).
 *
 * Every route asks JobService::recheckMember first: the caller started the
 * job, the file is still readable for them, the share does not forbid
 * downloading and the file is the version of the job. Nothing about a
 * permission is remembered between two requests. A job that is not there,
 * not the caller's or whose file is gone for the caller is one answer, 404,
 * without a name in the markup, the title or the start state.
 *
 * The page image comes from the container through ExAppService, never from
 * the browser to the container. Every answer of the image route carries
 * private, no-store and nosniff, the refusals as well.
 */
final class ReviewController extends Controller {
	public const STATE_JOB = 'job';
	public const STATE_BLOCKED = 'blocked';
	public const STATE_UNAVAILABLE = 'unavailable';

	public function __construct(
		IRequest $request,
		private IUserSession $userSession,
		private JobService $jobs,
		private ExAppService $exApp,
		private NotificationSender $notifications,
		private JobEventMapper $events,
		private IInitialState $initialState,
		private IL10N $l10n,
		private LoggerInterface $logger,
	) {
		parent::__construct(Application::APP_ID, $request);
	}

	/**
	 * GET /apps/pii_redaction/review/{jobId}
	 *
	 * Without a session the framework sends the caller to the login page and
	 * back here afterwards.
	 */
	#[\OCP\AppFramework\Http\Attribute\NoAdminRequired]
	#[\OCP\AppFramework\Http\Attribute\NoCSRFRequired]
	#[\OCP\AppFramework\Http\Attribute\FrontpageRoute(verb: 'GET', url: '/review/{jobId}', requirements: ['jobId' => '\d+'])]
	public function page(int $jobId): TemplateResponse {
		$uid = $this->uid();
		$verdict = $uid === null ? null : $this->jobs->recheckMember($jobId, $uid);
		if ($uid === null || $verdict === null) {
			return $this->unavailable($jobId);
		}
		if ($verdict === Recheck::Missing) {
			return $this->deletedOrUnavailable($jobId, $uid);
		}
		$view = $this->jobs->view($jobId, $uid, $verdict);
		$job = $this->jobs->forMember($jobId, $uid);
		if ($view === null || $job === null) {
			return $this->unavailable($jobId);
		}

		// Opening the page is reading the notification.
		$this->notifications->dismiss($job);

		$blocked = $verdict === Recheck::DownloadBlocked;
		$deleted = $view['status'] === Status::Cancelled->value;
		$name = $deleted ? null : $view['fileName'];
		$ready = !$blocked && $view['status'] === Status::Review->value;

		$state = [
			'state' => $blocked ? self::STATE_BLOCKED : self::STATE_JOB,
			'jobId' => $view['jobId'],
			'fileId' => $view['fileId'],
			'status' => $view['status'],
			'stage' => $view['stage'],
			'reason' => $view['reason'],
			'ahead' => $view['ahead'],
			'pagesDone' => $view['pagesDone'],
			'pagesTotal' => $view['pagesTotal'],
			'createdAt' => $view['createdAt'],
			'backendReady' => $view['backendReady'],
			'outputFileId' => $view['outputFileId'],
			'outputName' => $view['outputName'],
			'recheck' => $view['recheck'],
		];
		if ($name !== null) {
			$state['fileName'] = $name;
		}
		if ($ready && $view['image'] !== null) {
			$state['image'] = $view['image'];
		}

		return $this->render(
			$state,
			$name !== null ? $this->l10n->t('Review: %s', [$name]) : $this->l10n->t('Review'),
		);
	}

	/**
	 * GET /apps/pii_redaction/review/{jobId}/page/{n}
	 *
	 * Page 1 of a job in review as PNG. 404 for everything that is not the
	 * caller's or not there, 409 when the file changed (the job turns stale
	 * on the spot), 403 under a download block, 502 when the container gives
	 * no usable image.
	 */
	#[\OCP\AppFramework\Http\Attribute\NoAdminRequired]
	#[\OCP\AppFramework\Http\Attribute\NoCSRFRequired]
	#[\OCP\AppFramework\Http\Attribute\FrontpageRoute(verb: 'GET', url: '/review/{jobId}/page/{n}', requirements: ['jobId' => '\d+', 'n' => '\d{1,3}'])]
	public function pageImage(int $jobId, int $n): Response {
		$uid = $this->uid();
		$verdict = $uid === null ? null : $this->jobs->recheckMember($jobId, $uid);
		if ($uid === null || $verdict === null || $verdict === Recheck::Missing) {
			return self::refusal(Http::STATUS_NOT_FOUND);
		}
		if ($verdict === Recheck::Changed) {
			return self::refusal(Http::STATUS_CONFLICT);
		}
		if ($verdict === Recheck::DownloadBlocked) {
			return self::refusal(Http::STATUS_FORBIDDEN);
		}
		$job = $this->jobs->forMember($jobId, $uid);
		if ($job === null || $job->getStatusEnum() !== Status::Review || $n !== 1) {
			return self::refusal(Http::STATUS_NOT_FOUND);
		}

		$png = $this->exApp->page($jobId, 1, $uid);
		if ($png === null) {
			$this->logger->info('PII Redaction: page image not available', ['jobId' => $jobId]);
			return self::refusal(Http::STATUS_BAD_GATEWAY);
		}

		return self::secured(new DataDisplayResponse($png, Http::STATUS_OK, ['Content-Type' => 'image/png']));
	}

	/**
	 * POST /apps/pii_redaction/review/{jobId}/placeholder
	 *
	 * CSRF stays on: the request token comes with @nextcloud/axios.
	 */
	#[\OCP\AppFramework\Http\Attribute\NoAdminRequired]
	#[\OCP\AppFramework\Http\Attribute\FrontpageRoute(verb: 'POST', url: '/review/{jobId}/placeholder', requirements: ['jobId' => '\d+'])]
	public function placeholder(int $jobId): JSONResponse {
		$uid = $this->uid();
		$verdict = $uid === null ? null : $this->jobs->recheckMember($jobId, $uid);
		if ($uid === null || $verdict === null || $verdict === Recheck::Missing) {
			return self::secured(new JSONResponse([], Http::STATUS_NOT_FOUND));
		}
		if ($verdict === Recheck::Changed) {
			return self::conflict(Reason::OriginalChanged);
		}
		if ($verdict === Recheck::DownloadBlocked) {
			return self::conflict(Reason::DownloadBlocked);
		}
		$job = $this->jobs->forMember($jobId, $uid);
		if ($job === null) {
			return self::secured(new JSONResponse([], Http::STATUS_NOT_FOUND));
		}
		if ($job->getStatusEnum() !== Status::Review) {
			return self::secured(new JSONResponse(['status' => $job->getStatus()], Http::STATUS_CONFLICT));
		}
		if (!$this->exApp->startAllowed()) {
			return self::conflict(Reason::BackendUnavailable);
		}

		$this->jobs->toApproved($job, $uid);
		$this->events->record($jobId, $uid, JobEventMapper::ACTION_PLACEHOLDER_REQUESTED);
		return self::secured(new JSONResponse(['status' => Status::Approved->value], Http::STATUS_ACCEPTED));
	}

	// -- helpers --------------------------------------------------------------

	private function uid(): ?string {
		$uid = $this->userSession->getUser()?->getUID();
		return is_string($uid) && $uid !== '' ? $uid : null;
	}

	/**
	 * A file that is gone for the initiator: the job ended as
	 * cancelled(original_deleted) by the file listener shows its card
	 * (UI-SPEC: 200, no name), every other job is "not available". Only the
	 * initiator gets here (recheckMember), and the card says nothing but
	 * that the file was deleted.
	 */
	private function deletedOrUnavailable(int $jobId, string $uid): TemplateResponse {
		$job = $this->jobs->forMember($jobId, $uid);
		if ($job === null || $job->getStatusEnum() !== Status::Cancelled
			|| $job->getReasonEnum() !== Reason::OriginalDeleted) {
			return $this->unavailable($jobId);
		}
		$this->notifications->dismiss($job);

		return $this->render([
			'state' => self::STATE_JOB,
			'jobId' => $job->getId(),
			'fileId' => $job->getFileId(),
			'status' => $job->getStatus(),
			'stage' => $job->getStage(),
			'reason' => $job->getReason(),
			'ahead' => null,
			'pagesDone' => $job->getPagesDone(),
			'pagesTotal' => $job->getPagesTotal(),
			'createdAt' => $job->getCreatedAt(),
			'backendReady' => $this->exApp->startAllowed(),
			'outputFileId' => null,
			'outputName' => null,
			'recheck' => Recheck::Missing->value,
		], $this->l10n->t('Review'));
	}

	/**
	 * The one "not available" page: 404, no name anywhere, no job data.
	 */
	private function unavailable(int $jobId): TemplateResponse {
		$this->logger->debug('PII Redaction: review page not available', ['jobId' => $jobId]);
		$response = $this->render(['state' => self::STATE_UNAVAILABLE], $this->l10n->t('Review'));
		$response->setStatus(Http::STATUS_NOT_FOUND);
		return $response;
	}

	/**
	 * @param array<string, mixed> $state
	 */
	private function render(array $state, string $title): TemplateResponse {
		$this->initialState->provideInitialState('review', $state);
		Util::addScript(Application::APP_ID, 'pii_redaction-review');
		Util::addStyle(Application::APP_ID, 'review');

		$response = new TemplateResponse(Application::APP_ID, 'review', [
			'pageTitle' => $title,
			// The page has no app navigation; the skip link of the layout
			// must not point at one (AVS).
			'id-app-navigation' => null,
		], TemplateResponse::RENDER_AS_USER);
		return self::secured($response);
	}

	private static function refusal(int $status): Response {
		$response = new Response();
		$response->setStatus($status);
		return self::secured($response);
	}

	private static function conflict(Reason $reason): JSONResponse {
		return self::secured(new JSONResponse(['reason' => $reason->value], Http::STATUS_CONFLICT));
	}

	/**
	 * @template T of Response
	 * @param T $response
	 * @return T
	 */
	private static function secured(Response $response): Response {
		$response->addHeader('Cache-Control', 'private, no-store');
		$response->addHeader('X-Content-Type-Options', 'nosniff');
		return $response;
	}
}
