<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Service;

use OCA\PiiRedaction\AppInfo\Application;
use OCA\PiiRedaction\Db\Job;
use OCA\PiiRedaction\Model\Subject;
use OCP\AppFramework\Utility\ITimeFactory;
use OCP\Notification\IManager;
use OCP\Notification\INotification;
use Psr\Log\LoggerInterface;

/**
 * Sends and removes the one notification a job has at a time.
 *
 * A notification carries the app, the initiator, the object ('job', id) and
 * a subject from the closed list, nothing else: no file name, no path, no
 * parameter (owner decision 07.11.2026). The notifier of plan 14 builds the
 * text and the link to the review page from these words alone.
 *
 * A notification is a courtesy. A failure to send one is logged with the
 * class only and never stops the state change that asked for it.
 */
final class NotificationSender {
	public const OBJECT_TYPE = 'job';

	public function __construct(
		private IManager $manager,
		private ITimeFactory $time,
		private LoggerInterface $logger,
	) {
	}

	/**
	 * Replaces the notification of this job by one with $subject.
	 */
	public function notify(Job $job, Subject $subject): void {
		$this->dismiss($job);
		try {
			$notification = $this->base($job);
			$notification->setDateTime($this->time->getDateTime())
				->setSubject($subject->value);
			$this->manager->notify($notification);
		} catch (\Throwable $e) {
			$this->logger->warning('PII Redaction: notification not sent', ['jobId' => $job->getId(), 'class' => $e::class]);
		}
	}

	/**
	 * Removes every notification of this job for its initiator.
	 */
	public function dismiss(Job $job): void {
		try {
			$this->manager->markProcessed($this->base($job));
		} catch (\Throwable $e) {
			$this->logger->warning('PII Redaction: notification not removed', ['jobId' => $job->getId(), 'class' => $e::class]);
		}
	}

	private function base(Job $job): INotification {
		$notification = $this->manager->createNotification();
		$notification->setApp(Application::APP_ID)
			->setUser($job->getInitiatorUid())
			->setObject(self::OBJECT_TYPE, (string)$job->getId());
		return $notification;
	}
}
