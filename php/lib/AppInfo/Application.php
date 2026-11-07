<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\AppInfo;

use OCA\Files\Event\LoadAdditionalScriptsEvent;
use OCA\PiiRedaction\Listener\FileLifecycleListener;
use OCA\PiiRedaction\Listener\LoadFilesScriptsListener;
use OCA\PiiRedaction\Notification\Notifier;
use OCP\AppFramework\App;
use OCP\AppFramework\Bootstrap\IBootContext;
use OCP\AppFramework\Bootstrap\IBootstrap;
use OCP\AppFramework\Bootstrap\IRegistrationContext;
use OCP\Files\Events\Node\BeforeNodeDeletedEvent;
use OCP\Files\Events\Node\NodeWrittenEvent;

final class Application extends App implements IBootstrap {
	public const APP_ID = 'pii_redaction';

	/**
	 * The ExApp half in the External Apps section of the store. Both ids are
	 * frozen: the app certificates are bound to them.
	 */
	public const BACKEND_APP_ID = 'pii_redaction_backend';

	public function __construct(array $urlParams = []) {
		parent::__construct(self::APP_ID, $urlParams);
	}

	/**
	 * The notifier, the file action in Files and the two file events that end
	 * open jobs. Here and not in boot(), because boot() runs too late for
	 * registrations (Findling finding).
	 */
	public function register(IRegistrationContext $context): void {
		$context->registerNotifierService(Notifier::class);
		$context->registerEventListener(LoadAdditionalScriptsEvent::class, LoadFilesScriptsListener::class);
		$context->registerEventListener(NodeWrittenEvent::class, FileLifecycleListener::class);
		$context->registerEventListener(BeforeNodeDeletedEvent::class, FileLifecycleListener::class);
	}

	public function boot(IBootContext $context): void {
	}
}
