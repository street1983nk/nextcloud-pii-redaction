<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit\AppInfo;

use OCA\PiiRedaction\AppInfo\Application;
use PHPUnit\Framework\TestCase;

/**
 * The two app ids are frozen (the app certificates are bound to them), and the
 * PHP half names the backend by the id backend/appinfo/info.xml carries
 * (backend/tests/test_lockstep_versions.py compares the manifests).
 */
final class ApplicationTest extends TestCase {
	public function testTheAppIdsAreTheFrozenOnes(): void {
		$this->assertSame('pii_redaction', Application::APP_ID);
		$this->assertSame('pii_redaction_backend', Application::BACKEND_APP_ID);
	}
}
