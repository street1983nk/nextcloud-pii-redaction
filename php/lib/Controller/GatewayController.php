<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Controller;

use OCA\PiiRedaction\AppInfo\Application;
use OCA\PiiRedaction\Db\Job;
use OCA\PiiRedaction\Db\JobMapper;
use OCA\PiiRedaction\Model\Reason;
use OCA\PiiRedaction\Model\Recheck;
use OCA\PiiRedaction\Model\Status;
use OCA\PiiRedaction\Service\FileAccess;
use OCA\PiiRedaction\Service\JobService;
use OCP\AppFramework\Db\DoesNotExistException;
use OCP\AppFramework\Http;
use OCP\AppFramework\Http\DataResponse;
use OCP\AppFramework\Http\StreamResponse;
use OCP\AppFramework\OCSController;
use OCP\AppFramework\Utility\ITimeFactory;
use OCP\IRequest;
use Psr\Log\LoggerInterface;

/**
 * The read only channel of the container to the content of a file, bound to
 * one job (RESEARCH Entscheid 5; AVS gateway, narrowed).
 *
 * The container names a job and the token of its claim, never a file or a
 * user. The file is the one of that job, read as its initiator, and only
 * while the job is being analysed under a live lease and the file is still
 * the version the job was started on. A container that is taken over can
 * therefore read nothing but the file it was just handed, and only once the
 * initiator may still read it:
 *
 *   404  job unknown, token foreign, lease run out, job not analysing, or the
 *        file gone for the initiator (all the same answer)
 *   403  the share forbids downloading; the job fails as download_blocked
 *   409  the file changed; the job becomes stale
 *   503  the file could not be opened right now; the lease decides the retry
 *
 * The answer names the etag it served in a header, so the ack can prove which
 * version the container saw (JOB-04). No header carries a file name.
 */
final class GatewayController extends OCSController {
	/** The header that names the etag of the delivered version. */
	public const ETAG_HEADER = 'X-Pii-Etag';

	public function __construct(
		IRequest $request,
		private JobMapper $jobs,
		private JobService $service,
		private FileAccess $files,
		private ITimeFactory $time,
		private LoggerInterface $logger,
	) {
		parent::__construct(Application::APP_ID, $request);
	}

	/**
	 * GET /ocs/v2.php/apps/pii_redaction/api/v1/files/{jobId}?token=
	 */
	#[\OCP\AppFramework\Http\Attribute\ExAppRequired]
	#[\OCP\AppFramework\Http\Attribute\NoCSRFRequired]
	#[\OCP\AppFramework\Http\Attribute\ApiRoute(verb: 'GET', url: '/api/v1/files/{jobId}', requirements: ['jobId' => '\d+'])]
	public function file(int $jobId, string $token = ''): DataResponse|StreamResponse {
		$foreign = $this->rejectForeignCaller();
		if ($foreign !== null) {
			return $foreign;
		}

		$job = $this->leased($jobId, $token);
		if ($job === null) {
			return self::notFound();
		}

		$uid = $job->getInitiatorUid();
		$fileId = $job->getFileId();
		$etag = $job->getFileEtag();
		$verdict = $this->files->recheck($uid, $fileId, $etag);
		if ($verdict === Recheck::Missing) {
			$this->service->toFailed($job, Reason::NotReadable);
			$this->logger->info('PII Redaction: gateway refused, file not readable', ['jobId' => $jobId, 'reason' => Reason::NotReadable->value]);
			return self::notFound();
		}
		if ($verdict === Recheck::DownloadBlocked) {
			$this->service->toFailed($job, Reason::DownloadBlocked);
			$this->logger->info('PII Redaction: gateway refused, download blocked', ['jobId' => $jobId, 'reason' => Reason::DownloadBlocked->value]);
			return self::noStore(new DataResponse([], Http::STATUS_FORBIDDEN));
		}
		if ($verdict === Recheck::Changed) {
			$this->service->toStale($job);
			$this->logger->info('PII Redaction: gateway refused, file changed', ['jobId' => $jobId, 'reason' => Reason::OriginalChanged->value]);
			return self::noStore(new DataResponse([], Http::STATUS_CONFLICT));
		}

		try {
			$file = $this->files->resolve($uid, $fileId);
			if ($file === null) {
				$this->service->toFailed($job, Reason::NotReadable);
				return self::notFound();
			}
			// Read only: 'rb' is the whole guarantee at this spot.
			$stream = $file->fopen('rb');
		} catch (\Throwable $e) {
			// The class only: a library message is where a path shows up.
			$this->logger->warning('PII Redaction: gateway could not open a file', ['jobId' => $jobId, 'fileId' => $fileId, 'class' => $e::class]);
			return self::noStore(new DataResponse([], Http::STATUS_SERVICE_UNAVAILABLE));
		}
		if (!is_resource($stream)) {
			$this->logger->warning('PII Redaction: gateway could not open a file', ['jobId' => $jobId, 'fileId' => $fileId]);
			return self::noStore(new DataResponse([], Http::STATUS_SERVICE_UNAVAILABLE));
		}

		$response = new StreamResponse($stream);
		$response->addHeader('Content-Type', 'application/octet-stream');
		$response->addHeader(self::ETAG_HEADER, $etag);
		return self::noStore($response);
	}

	/**
	 * The job when it is being analysed under a live lease and $token is the
	 * token of that claim; null in every other case.
	 */
	private function leased(int $jobId, string $token): ?Job {
		if ($jobId <= 0 || $token === '') {
			return null;
		}
		try {
			$job = $this->jobs->find($jobId);
		} catch (DoesNotExistException) {
			return null;
		}
		$held = $job->getClaimToken();
		if ($held === null || $held === '' || !hash_equals($held, $token)) {
			return null;
		}
		if ($job->getStatusEnum() !== Status::Analyzing || $job->getLeaseUntil() <= $this->time->getTime()) {
			return null;
		}
		return $job;
	}

	private static function notFound(): DataResponse {
		return self::noStore(new DataResponse([], Http::STATUS_NOT_FOUND));
	}

	/**
	 * @template T of DataResponse|StreamResponse
	 * @param T $response
	 * @return T
	 */
	private static function noStore(DataResponse|StreamResponse $response): DataResponse|StreamResponse {
		$response->addHeader('Cache-Control', 'no-store');
		return $response;
	}

	/**
	 * ExAppRequired admits every registered ExApp; without this comparison
	 * any other container of the instance could read the job files. AppAPI
	 * puts the authenticated app id into this header; whoever can forge it
	 * has broken the AppAPI trust model itself.
	 */
	private function rejectForeignCaller(): ?DataResponse {
		$callerAppId = $this->request->getHeader('EX-APP-ID');
		if ($callerAppId === Application::BACKEND_APP_ID) {
			return null;
		}

		$this->logger->warning('PII Redaction: content gateway called by a foreign ExApp', ['app' => $callerAppId]);

		return new DataResponse(
			['error' => 'This route is reserved for the PII Redaction backend.'],
			Http::STATUS_FORBIDDEN,
		);
	}
}
