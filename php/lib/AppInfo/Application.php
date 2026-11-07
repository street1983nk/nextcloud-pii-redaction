<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\AppInfo;

use OCP\AppFramework\App;
use OCP\AppFramework\Bootstrap\IBootContext;
use OCP\AppFramework\Bootstrap\IBootstrap;
use OCP\AppFramework\Bootstrap\IRegistrationContext;

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
	 * Empty for now. Plan 14 registers the notifier and the listeners for file
	 * writes and deletions here; register() and not boot(), because boot()
	 * runs too late for registrations (Findling finding).
	 */
	public function register(IRegistrationContext $context): void {
	}

	public function boot(IBootContext $context): void {
	}
}
