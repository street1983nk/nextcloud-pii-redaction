<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Settings;

use OCA\PiiRedaction\AppInfo\Application;
use OCP\IL10N;
use OCP\IURLGenerator;
use OCP\Settings\IIconSection;

/**
 * The own admin section "PII Redaction" (UI-SPEC Fläche 5, AVS pattern):
 * later phases add their settings here, so the page does not hide under
 * "Additional settings".
 *
 * No Override attribute: it is enforced from PHP 8.3 on, and this app
 * supports PHP 8.2.
 */
final class Section implements IIconSection {
	public function __construct(
		private IL10N $l,
		private IURLGenerator $url,
	) {
	}

	public function getID(): string {
		// The address as well: /settings/admin/pii_redaction.
		return Application::APP_ID;
	}

	public function getName(): string {
		// The app name stays the same in every language (UI-SPEC copy).
		return $this->l->t('PII Redaction');
	}

	public function getPriority(): int {
		// The lower half of the list, where the sections of apps belong.
		return 75;
	}

	public function getIcon(): string {
		// Monochrome, themed by the navigation.
		return $this->url->imagePath(Application::APP_ID, 'app-dark.svg');
	}
}
