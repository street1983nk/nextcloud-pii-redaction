<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Controller;

use OCA\PiiRedaction\AppInfo\Application;
use OCA\PiiRedaction\BackgroundJob\PublishJob;
use OCA\PiiRedaction\Db\Job;
use OCA\PiiRedaction\Db\JobMapper;
use OCA\PiiRedaction\Model\Reason;
use OCA\PiiRedaction\Model\Recheck;
use OCA\PiiRedaction\Model\Stage;
use OCA\PiiRedaction\Model\Status;
use OCA\PiiRedaction\Model\Task;
use OCA\PiiRedaction\Service\FileAccess;
use OCA\PiiRedaction\Service\JobService;
use OCP\AppFramework\Db\DoesNotExistException;
use OCP\AppFramework\Http;
use OCP\AppFramework\Http\DataResponse;
use OCP\AppFramework\OCSController;
use OCP\AppFramework\Utility\ITimeFactory;
use OCP\BackgroundJob\IJobList;
use OCP\IRequest;
use Psr\Log\LoggerInterface;

/**
 * The pull queue of the container: claim, progress and ack (Findling
 * QueueController, reduced to one job at a time).
 *
 * The container is outside the trust boundary even though AppAPI signed its
 * request. Every value it sends is checked against a closed list or a range
 * before anything is stored, and nothing it says reaches a log: only the job
 * id, a status, a reason and class names. A report with a value outside its
 * list or range is a 400; a report for a job that is no longer the caller's
 * (unknown job, foreign token, wrong state, lease run out) is a 409, so the
 * container stops working on it.
 *
 * Every state change goes through JobService, which also gives the lease
 * back. The copy is not written here: ack(verified) queues a PublishJob, so a
 * slow storage never holds the request of the container (plan 14).
 */
final class QueueController extends OCSController {
	/** The ceiling of a page count the container may report. */
	public const MAX_PAGES = 100000;
	/** The ceiling of a side of the page image in pixels. */
	public const MAX_IMAGE_SIDE = 20000;
	/** Mirror of PublishService::MAX_OUTPUT_BYTES (32 MiB, 01-SKELETON.md). */
	public const MAX_OUTPUT_BYTES = 33554432;

	/** The results of an ack (01-SKELETON.md, AckResult). */
	private const RESULTS = ['review', 'verified', 'purged', 'failed'];

	public function __construct(
		IRequest $request,
		private JobMapper $jobs,
		private JobService $service,
		private FileAccess $files,
		private IJobList $jobList,
		private ITimeFactory $time,
		private LoggerInterface $logger,
	) {
		parent::__construct(Application::APP_ID, $request);
	}

	/**
	 * POST /ocs/v2.php/apps/pii_redaction/api/v1/queue/claim
	 *
	 * At most one task, or an empty object when there is nothing to do or
	 * another analyze or apply task holds the slot.
	 */
	#[\OCP\AppFramework\Http\Attribute\ExAppRequired]
	#[\OCP\AppFramework\Http\Attribute\NoCSRFRequired]
	#[\OCP\AppFramework\Http\Attribute\ApiRoute(verb: 'POST', url: '/api/v1/queue/claim')]
	public function claim(): DataResponse {
		$foreign = $this->rejectForeignCaller();
		if ($foreign !== null) {
			return $foreign;
		}

		// claimNext creates the slot row itself, only when there is a task.
		$claim = $this->jobs->claimNext();
		if ($claim === null) {
			return new DataResponse([]);
		}

		$job = $claim['job'];
		return new DataResponse([
			'jobId' => $job->getId(),
			'task' => $job->getTask(),
			'token' => $claim['token'],
			'fileId' => $job->getFileId(),
			'userId' => $job->getInitiatorUid(),
			'etag' => $job->getFileEtag(),
			'leaseSeconds' => $claim['lease'],
		]);
	}

	/**
	 * POST /ocs/v2.php/apps/pii_redaction/api/v1/queue/{jobId}/progress
	 *
	 * The stage and the page counters of a running task; extends the lease.
	 */
	#[\OCP\AppFramework\Http\Attribute\ExAppRequired]
	#[\OCP\AppFramework\Http\Attribute\NoCSRFRequired]
	#[\OCP\AppFramework\Http\Attribute\ApiRoute(verb: 'POST', url: '/api/v1/queue/{jobId}/progress', requirements: ['jobId' => '\d+'])]
	public function progress(int $jobId, string $token = '', string $stage = '', ?int $pagesDone = null, ?int $pagesTotal = null): DataResponse {
		$foreign = $this->rejectForeignCaller();
		if ($foreign !== null) {
			return $foreign;
		}

		$stageValue = Stage::tryFrom($stage);
		if ($stageValue === null || !self::countsInRange($pagesDone, $pagesTotal)) {
			return self::badRequest();
		}

		$job = $this->running($jobId, $token);
		if ($job === null || !in_array($job->getStatusEnum(), [Status::Analyzing, Status::Applying], true)
			|| $job->getLeaseUntil() <= $this->time->getTime()) {
			return $this->conflict($jobId);
		}
		if (!$this->jobs->extendLease($job, $token)) {
			return $this->conflict($jobId);
		}

		$job->setStage($stageValue->value);
		$job->setPagesDone($pagesDone);
		$job->setPagesTotal($pagesTotal);
		$job->setUpdatedAt($this->time->getTime());
		$this->jobs->update($job);

		return new DataResponse(['ok' => true]);
	}

	/**
	 * POST /ocs/v2.php/apps/pii_redaction/api/v1/queue/{jobId}/ack
	 *
	 * The end of a task. The token alone decides whether the caller still
	 * holds the job: once a lease runs out, the next claim replaces it, so an
	 * old token can no longer finish the job of somebody else.
	 *
	 * @param array<mixed>|null $image
	 * @param array<mixed>|null $output
	 */
	#[\OCP\AppFramework\Http\Attribute\ExAppRequired]
	#[\OCP\AppFramework\Http\Attribute\NoCSRFRequired]
	#[\OCP\AppFramework\Http\Attribute\ApiRoute(verb: 'POST', url: '/api/v1/queue/{jobId}/ack', requirements: ['jobId' => '\d+'])]
	public function ack(
		int $jobId,
		string $token = '',
		string $result = '',
		?string $reason = null,
		?int $pagesTotal = null,
		?string $etagSeen = null,
		?array $image = null,
		?array $output = null,
	): DataResponse {
		$foreign = $this->rejectForeignCaller();
		if ($foreign !== null) {
			return $foreign;
		}
		if (!in_array($result, self::RESULTS, true)) {
			return self::badRequest();
		}

		$job = $this->running($jobId, $token);
		if ($job === null) {
			return $this->conflict($jobId);
		}

		return match ($result) {
			'review' => $this->ackReview($job, $pagesTotal, $etagSeen, $image),
			'verified' => $this->ackVerified($job, $output),
			'failed' => $this->ackFailed($job, $reason),
			default => $this->ackPurged($job),
		};
	}

	// -- the four results -----------------------------------------------------

	/**
	 * @param array<mixed>|null $image
	 */
	private function ackReview(Job $job, ?int $pagesTotal, ?string $etagSeen, ?array $image): DataResponse {
		$width = self::side($image['width'] ?? null);
		$height = self::side($image['height'] ?? null);
		if ($pagesTotal === null || $pagesTotal < 1 || $pagesTotal > self::MAX_PAGES
			|| $width === null || $height === null || $etagSeen === null || $etagSeen === '') {
			return self::badRequest();
		}
		if ($job->getStatusEnum() !== Status::Analyzing || $job->getTaskEnum() !== Task::Analyze) {
			return $this->conflict($job->getId());
		}

		// The container read a different version than the job was started on.
		if (!hash_equals($job->getFileEtag(), $etagSeen)) {
			$this->service->toStale($job);
			return $this->notTaken($job, Reason::OriginalChanged);
		}

		// And the file has to be what it was, for the initiator, right now.
		$verdict = $this->files->recheck($job->getInitiatorUid(), $job->getFileId(), $job->getFileEtag());
		if ($verdict === Recheck::Changed) {
			$this->service->toStale($job);
			return $this->notTaken($job, Reason::OriginalChanged);
		}
		if ($verdict !== Recheck::Ok) {
			$why = $verdict === Recheck::DownloadBlocked ? Reason::DownloadBlocked : Reason::NotReadable;
			$this->service->toFailed($job, $why);
			return $this->notTaken($job, $why);
		}

		$this->service->toReview($job, $pagesTotal, $width, $height);
		return new DataResponse(['ok' => true]);
	}

	/**
	 * @param array<mixed>|null $output
	 */
	private function ackVerified(Job $job, ?array $output): DataResponse {
		$sha256 = $output['sha256'] ?? null;
		$size = $output['size'] ?? null;
		if (!is_string($sha256) || preg_match('/^[0-9a-f]{64}$/D', $sha256) !== 1
			|| !is_int($size) || $size < 1 || $size > self::MAX_OUTPUT_BYTES) {
			return self::badRequest();
		}
		if ($job->getStatusEnum() !== Status::Applying || $job->getTaskEnum() !== Task::Apply) {
			return $this->conflict($job->getId());
		}

		$this->service->toVerified($job, $sha256, $size);
		// The copy is written by a background job, never in this request.
		$this->jobList->add(PublishJob::class, ['jobId' => $job->getId()]);
		return new DataResponse(['ok' => true]);
	}

	private function ackFailed(Job $job, ?string $reason): DataResponse {
		$why = Reason::tryFrom($reason ?? '');
		if ($why === null) {
			return self::badRequest();
		}
		if (!in_array($job->getStatusEnum(), [Status::Analyzing, Status::Applying], true)) {
			return $this->conflict($job->getId());
		}

		$this->service->toFailed($job, $why);
		return new DataResponse(['ok' => true]);
	}

	private function ackPurged(Job $job): DataResponse {
		if ($job->getTaskEnum() !== Task::Purge) {
			return $this->conflict($job->getId());
		}

		$this->service->toPurged($job);
		return new DataResponse(['ok' => true]);
	}

	// -- helpers --------------------------------------------------------------

	/**
	 * The job when $token is the token of its current claim, otherwise null
	 * (also for an unknown id). The comparison takes constant time.
	 */
	private function running(int $jobId, string $token): ?Job {
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
		return $job;
	}

	/** Not negative, done not above total, total not above the ceiling. */
	private static function countsInRange(?int $done, ?int $total): bool {
		if (($done !== null && $done < 0) || ($total !== null && ($total < 0 || $total > self::MAX_PAGES))) {
			return false;
		}
		return $done === null || $total === null || $done <= $total;
	}

	/** A side of the page image as a whole number in range, or null. */
	private static function side(mixed $value): ?int {
		return is_int($value) && $value >= 1 && $value <= self::MAX_IMAGE_SIDE ? $value : null;
	}

	private static function badRequest(): DataResponse {
		return new DataResponse([], Http::STATUS_BAD_REQUEST);
	}

	private function conflict(int $jobId): DataResponse {
		$this->logger->info('PII Redaction: queue report refused', ['jobId' => $jobId]);
		return new DataResponse([], Http::STATUS_CONFLICT);
	}

	/**
	 * The ack was read, but the job did not take the result the container
	 * reported: the container stops, the purge task cleans up after it.
	 */
	private function notTaken(Job $job, Reason $reason): DataResponse {
		$this->logger->info('PII Redaction: review result not taken', ['jobId' => $job->getId(), 'reason' => $reason->value]);
		return new DataResponse(['reason' => $reason->value], Http::STATUS_CONFLICT);
	}

	/**
	 * ExAppRequired admits every registered ExApp; only the backend of this
	 * app may use the queue. AppAPI puts the authenticated app id into this
	 * header (residual risk as at the content gateway).
	 */
	private function rejectForeignCaller(): ?DataResponse {
		$callerAppId = $this->request->getHeader('EX-APP-ID');
		if ($callerAppId === Application::BACKEND_APP_ID) {
			return null;
		}

		$this->logger->warning('PII Redaction: queue called by a foreign ExApp', ['app' => $callerAppId]);

		return new DataResponse(
			['error' => 'This route is reserved for the PII Redaction backend.'],
			Http::STATUS_FORBIDDEN,
		);
	}
}
