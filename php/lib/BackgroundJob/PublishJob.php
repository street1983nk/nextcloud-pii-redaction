<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\BackgroundJob;

use OCA\PiiRedaction\Db\JobMapper;
use OCA\PiiRedaction\Model\Reason;
use OCA\PiiRedaction\Service\JobService;
use OCA\PiiRedaction\Service\PublishService;
use OCP\AppFramework\Db\DoesNotExistException;
use OCP\AppFramework\Utility\ITimeFactory;
use OCP\BackgroundJob\QueuedJob;
use Psr\Log\LoggerInterface;

/**
 * Places the copy of one verified job, queued by QueueController on
 * ack(verified). It runs once in cron, not in the request of the container,
 * so a slow storage never holds the queue (T-01-14-06).
 *
 * Argument: ['jobId' => int]. Anything else is dropped without a trace of
 * its content.
 */
final class PublishJob extends QueuedJob {
	public function __construct(
		ITimeFactory $time,
		private PublishService $publisher,
		private JobMapper $jobs,
		private JobService $service,
		private LoggerInterface $logger,
	) {
		parent::__construct($time);
	}

	/**
	 * @param mixed $argument
	 */
	protected function run($argument): void {
		$jobId = is_array($argument) ? ($argument['jobId'] ?? null) : null;
		if (!is_int($jobId) || $jobId <= 0) {
			$this->logger->warning('PII Redaction: publish job without a usable job id');
			return;
		}

		try {
			$job = $this->jobs->find($jobId);
		} catch (DoesNotExistException) {
			$this->logger->info('PII Redaction: publish job for a job that is gone', ['jobId' => $jobId]);
			return;
		}

		try {
			$this->publisher->publish($job);
		} catch (\Throwable $e) {
			// The class only: a storage message is where a path shows up.
			$this->logger->error('PII Redaction: publishing failed', ['jobId' => $jobId, 'class' => $e::class]);
			$this->failQuietly($jobId);
		}
	}

	/**
	 * The job ends as check_error when it is still open; a second failure
	 * here is logged with its class and left alone.
	 */
	private function failQuietly(int $jobId): void {
		try {
			$job = $this->jobs->find($jobId);
			if ($job->getStatusEnum()->isOpen()) {
				$this->service->toFailed($job, Reason::CheckError);
			}
		} catch (\Throwable $e) {
			$this->logger->error('PII Redaction: failed publish job could not be closed', ['jobId' => $jobId, 'class' => $e::class]);
		}
	}
}
