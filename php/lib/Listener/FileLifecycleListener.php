<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Listener;

use OCA\PiiRedaction\Db\JobMapper;
use OCA\PiiRedaction\Model\Reason;
use OCA\PiiRedaction\Service\JobService;
use OCP\EventDispatcher\Event;
use OCP\EventDispatcher\IEventListener;
use OCP\Files\Events\Node\BeforeNodeDeletedEvent;
use OCP\Files\Events\Node\NodeWrittenEvent;
use OCP\Files\File;
use Psr\Log\LoggerInterface;

/**
 * Ends the open jobs of a file when the file changes under them (JOB-04).
 *
 * A write turns every open job on the file stale(original_changed); the
 * review would otherwise show a version that no longer exists. A deletion
 * cancels them as original_deleted, without a notification (the user did it
 * themselves). The deletion is caught before it happens, while the file id
 * is still readable (Findling pattern). The copy this app writes has its own
 * file id and touches no job.
 *
 * A file operation of the user must never fail because of this app: every
 * exception is logged with its class and swallowed.
 *
 * @template-implements IEventListener<NodeWrittenEvent|BeforeNodeDeletedEvent>
 */
final class FileLifecycleListener implements IEventListener {
	public function __construct(
		private JobMapper $jobs,
		private JobService $service,
		private LoggerInterface $logger,
	) {
	}

	public function handle(Event $event): void {
		$deleted = $event instanceof BeforeNodeDeletedEvent;
		if (!$deleted && !$event instanceof NodeWrittenEvent) {
			return;
		}

		try {
			$node = $event->getNode();
			if (!$node instanceof File) {
				return;
			}
			$fileId = $node->getId();
			if ($fileId <= 0) {
				return;
			}
			$open = $this->jobs->findOpenByFile($fileId);
		} catch (\Throwable $e) {
			$this->logger->warning('PII Redaction: file event not handled', ['class' => $e::class]);
			return;
		}

		foreach ($open as $job) {
			try {
				if ($deleted) {
					$this->service->toCancelled($job, Reason::OriginalDeleted);
				} else {
					$this->service->toStale($job);
				}
			} catch (\Throwable $e) {
				$this->logger->warning('PII Redaction: job not ended after a file event', ['jobId' => $job->getId(), 'class' => $e::class]);
			}
		}
	}
}
