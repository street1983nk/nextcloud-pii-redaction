<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Notification;

use OCA\PiiRedaction\AppInfo\Application;
use OCA\PiiRedaction\Model\Subject;
use OCA\PiiRedaction\Service\NotificationSender;
use OCP\IURLGenerator;
use OCP\L10N\IFactory;
use OCP\Notification\INotification;
use OCP\Notification\INotifier;
use OCP\Notification\UnknownNotificationException;

/**
 * The texts of the four notifications of a job (UI-SPEC Fläche 3).
 *
 * A notification leaves the server through the push proxy, and file names of
 * public authorities often carry the names of people. So subject and message
 * are fixed sentences of the catalog, chosen by the subject word alone: no
 * file name, no path, no parameter, no finding (owner decision 07.11.2026).
 * The link is the review page of the job, nothing else. Nothing here reads a
 * node; backend/tests/test_php_gates.py (rule 17) holds that.
 */
final class Notifier implements INotifier {
	public function __construct(
		private IFactory $l10nFactory,
		private IURLGenerator $urlGenerator,
	) {
	}

	public function getID(): string {
		return Application::APP_ID;
	}

	/** The app name stays the same in every language. */
	public function getName(): string {
		return 'PII Redaction';
	}

	public function prepare(INotification $notification, string $languageCode): INotification {
		if ($notification->getApp() !== Application::APP_ID) {
			throw new UnknownNotificationException();
		}
		$subject = Subject::tryFrom($notification->getSubject());
		if ($subject === null) {
			throw new UnknownNotificationException();
		}

		$l = $this->l10nFactory->get(Application::APP_ID, $languageCode);
		[$title, $sentence] = match ($subject) {
			Subject::ReviewReady => [$l->t('A review is ready'), $l->t('Open the review page.')],
			Subject::JobFailed => [$l->t('An analysis failed'), $l->t('The review page shows why.')],
			Subject::JobStale => [$l->t('An analysis was stopped'), $l->t('The file changed. Analyse it again.')],
			Subject::CopyCreated => [$l->t('A copy was created'), $l->t('It is next to the original.')],
		};
		$notification->setParsedSubject($title);
		$notification->setParsedMessage($sentence);

		$objectId = $notification->getObjectId();
		if ($notification->getObjectType() === NotificationSender::OBJECT_TYPE
			&& preg_match('/^[1-9]\d{0,18}$/D', $objectId) === 1) {
			$notification->setLink($this->urlGenerator->linkToRouteAbsolute(
				'pii_redaction.review.page',
				['jobId' => (int)$objectId],
			));
		}
		$notification->setIcon($this->urlGenerator->getAbsoluteURL(
			$this->urlGenerator->imagePath(Application::APP_ID, 'app-dark.svg'),
		));

		return $notification;
	}
}
