<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Controller;

use OCA\PiiRedaction\AppInfo\Application;
use OCA\PiiRedaction\Model\Reason;
use OCA\PiiRedaction\Model\Recheck;
use OCA\PiiRedaction\Service\FileAccess;
use OCA\PiiRedaction\Service\JobService;
use OCP\AppFramework\Controller;
use OCP\AppFramework\Http;
use OCP\AppFramework\Http\JSONResponse;
use OCP\AppFramework\Http\Response;
use OCP\IRequest;
use OCP\IURLGenerator;
use OCP\IUserSession;
use Psr\Log\LoggerInterface;

/**
 * Start and status of a job for the signed in user (UI-SPEC Fläche 1).
 *
 * Both routes ask FileAccess again on every request; nothing about the file
 * is remembered between two requests. The answers carry ids, numbers and
 * words of the closed lists only. A job that is not there, not the caller's
 * or whose file is gone for the caller answers the same empty 404.
 */
final class JobController extends Controller {
	/** The HTTP status of each refusal (UI-SPEC Fläche 1, Zustände). */
	private const REFUSAL_STATUS = [
		'backend_unavailable' => Http::STATUS_SERVICE_UNAVAILABLE,
		'download_blocked' => Http::STATUS_FORBIDDEN,
		'not_readable' => Http::STATUS_NOT_FOUND,
		'unsupported_format' => Http::STATUS_UNSUPPORTED_MEDIA_TYPE,
	];

	/** The fields of the status answer (01-SKELETON.md, PHP-Routen). */
	private const STATUS_FIELDS = [
		'jobId', 'status', 'stage', 'reason', 'ahead', 'pagesDone', 'pagesTotal',
		'backendReady', 'outputFileId', 'outputName',
	];

	public function __construct(
		IRequest $request,
		private IUserSession $userSession,
		private FileAccess $files,
		private JobService $jobs,
		private IURLGenerator $urlGenerator,
		private LoggerInterface $logger,
	) {
		parent::__construct(Application::APP_ID, $request);
	}

	/**
	 * POST /apps/pii_redaction/api/v1/jobs {fileId}. CSRF stays on: the
	 * request token comes with @nextcloud/axios.
	 */
	#[\OCP\AppFramework\Http\Attribute\NoAdminRequired]
	#[\OCP\AppFramework\Http\Attribute\FrontpageRoute(verb: 'POST', url: '/api/v1/jobs')]
	public function create(int $fileId): JSONResponse {
		$uid = $this->uid();
		if ($uid === null) {
			return self::noStore(new JSONResponse([], Http::STATUS_UNAUTHORIZED));
		}

		$precheck = $this->files->recheckForStart($uid, $fileId);
		$result = $this->jobs->start($uid, $fileId, $precheck);

		$job = $result['job'];
		if ($job === null) {
			$reason = $result['reason'] ?? Reason::NotReadable;
			$this->logger->info('PII Redaction: start refused', ['fileId' => $fileId, 'reason' => $reason->value]);
			return self::noStore(new JSONResponse(
				['reason' => $reason->value],
				self::REFUSAL_STATUS[$reason->value] ?? Http::STATUS_NOT_FOUND,
			));
		}

		return self::noStore(new JSONResponse(
			[
				'jobId' => $job->getId(),
				'status' => $job->getStatus(),
				'ahead' => $result['ahead'],
				'reviewUrl' => $this->urlGenerator->linkToRoute('pii_redaction.review.page', ['jobId' => $job->getId()]),
			],
			$result['created'] ? Http::STATUS_CREATED : Http::STATUS_OK,
		));
	}

	/**
	 * GET /apps/pii_redaction/api/v1/jobs/{jobId}, polled by the review page.
	 */
	#[\OCP\AppFramework\Http\Attribute\NoAdminRequired]
	#[\OCP\AppFramework\Http\Attribute\NoCSRFRequired]
	#[\OCP\AppFramework\Http\Attribute\FrontpageRoute(verb: 'GET', url: '/api/v1/jobs/{jobId}', requirements: ['jobId' => '\d+'])]
	public function show(int $jobId): Response {
		$uid = $this->uid();
		if ($uid === null) {
			return self::noStore(new JSONResponse([], Http::STATUS_UNAUTHORIZED));
		}

		$verdict = $this->jobs->recheckMember($jobId, $uid);
		if ($verdict === null || $verdict === Recheck::Missing) {
			return self::notFound();
		}
		$view = $this->jobs->view($jobId, $uid, $verdict);
		if ($view === null) {
			return self::notFound();
		}

		$body = [];
		foreach (self::STATUS_FIELDS as $field) {
			$body[$field] = $view[$field];
		}
		return self::noStore(new JSONResponse($body));
	}

	private function uid(): ?string {
		$uid = $this->userSession->getUser()?->getUID();
		return is_string($uid) && $uid !== '' ? $uid : null;
	}

	/**
	 * The one 404 of this controller: no body, so no name and no hint
	 * whether the job exists.
	 */
	private static function notFound(): Response {
		$response = new Response();
		$response->setStatus(Http::STATUS_NOT_FOUND);
		return self::noStore($response);
	}

	/**
	 * @template T of Response
	 * @param T $response
	 * @return T
	 */
	private static function noStore(Response $response): Response {
		$response->addHeader('Cache-Control', 'private, no-store');
		return $response;
	}
}
