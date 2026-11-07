<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Service\ExAppService;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

/**
 * The seven states of the other half and the rule when a job may start.
 */
#[CoversClass(ExAppService::class)]
final class BackendStateTest extends TestCase {
	use ExAppServiceFactory;

	private const ENABLED = ['appid' => 'pii_redaction_backend', 'version' => '0.1.0', 'enabled' => true];

	public function testWithoutAppApiTheStateIsNoAppApi(): void {
		$service = $this->service(self::ENABLED, fn () => null, appApi: false);
		self::assertSame(ExAppService::STATE_NO_APP_API, $service->backendState(true)['state']);
	}

	public function testUnresolvableAppApiIsNoAppApi(): void {
		$service = $this->service(false, fn () => null);
		self::assertSame(ExAppService::STATE_NO_APP_API, $service->backendState(true)['state']);
	}

	public function testAnUnregisteredBackendIsMissing(): void {
		$service = $this->service(null, fn () => null);
		self::assertSame(ExAppService::STATE_BACKEND_MISSING, $service->backendState(true)['state']);
	}

	public function testADisabledBackendIsDisabled(): void {
		$service = $this->service(['enabled' => 0] + self::ENABLED, fn () => null);
		self::assertSame(ExAppService::STATE_BACKEND_DISABLED, $service->backendState(true)['state']);
	}

	public function testARegisteredMinorDriftIsDriftAndTheContainerIsNotAsked(): void {
		$service = $this->service(['version' => '0.2.0'] + self::ENABLED, fn () => $this->statusAnswer([]));
		self::assertSame(ExAppService::STATE_VERSION_DRIFT, $service->backendState(true)['state']);
		self::assertSame([], $this->calls);
	}

	public function testAReportedMinorDriftIsDrift(): void {
		$service = $this->service(self::ENABLED, fn () => $this->statusAnswer(['version' => '0.2.0']));
		self::assertSame(ExAppService::STATE_VERSION_DRIFT, $service->backendState(true)['state']);
	}

	public function testNoAnswerIsUnreachable(): void {
		$service = $this->service(self::ENABLED, fn () => ['error' => 'connection refused']);
		self::assertSame(ExAppService::STATE_BACKEND_UNREACHABLE, $service->backendState(true)['state']);
		self::assertSame('/status', $this->calls[0]['route']);
		self::assertSame(ExAppService::STATUS_TIMEOUT_SECONDS, $this->calls[0]['timeout']);
	}

	public function testAPatchDifferenceIsPatchDiffers(): void {
		$service = $this->service(self::ENABLED, fn () => $this->statusAnswer(['version' => '0.1.1']));
		self::assertSame(ExAppService::STATE_VERSION_PATCH_DIFFERS, $service->backendState(true)['state']);
	}

	public function testTheSameVersionIsOk(): void {
		$service = $this->service(self::ENABLED, fn () => $this->statusAnswer(['companion' => 'ok']));
		$state = $service->backendState(true);
		self::assertSame(ExAppService::STATE_OK, $state['state']);
		self::assertSame('0.1.0', $state['backendVersion']);
		self::assertSame('ok', $state['companion']);
	}

	public function testAFreshVerdictIsReusedAndAnOldOneIsNot(): void {
		$service = $this->service(self::ENABLED, fn () => $this->statusAnswer([]));
		$service->backendState();
		$service->backendState();
		self::assertCount(1, $this->calls);

		$this->now += ExAppService::STATE_MAX_AGE_SECONDS + 1;
		$service->backendState();
		self::assertCount(2, $this->calls);
	}

	/**
	 * @return iterable<string, array{array<string, mixed>, ?string, bool}>
	 */
	public static function startCases(): iterable {
		yield 'ok, companion ok' => [[], 'ok', true];
		yield 'ok, companion unknown' => [[], 'unknown', true];
		yield 'ok, companion missing' => [[], 'missing', false];
		yield 'patch differs' => [['version' => '0.1.1'], 'ok', true];
		yield 'patch differs, companion missing' => [['version' => '0.1.1'], 'missing', false];
		yield 'drift' => [['version' => '0.2.0'], 'ok', false];
	}

	/**
	 * @param array<string, mixed> $status
	 */
	#[DataProvider('startCases')]
	public function testStartIsAllowedOnlyInTheTwoStatesWithoutAMissingCompanion(array $status, ?string $companion, bool $allowed): void {
		$service = $this->service(self::ENABLED, fn () => $this->statusAnswer($status + ['companion' => $companion]));
		self::assertSame($allowed, $service->startAllowed());
	}

	public function testStartIsRefusedInEveryOtherState(): void {
		self::assertFalse($this->service(null, fn () => null)->startAllowed());
		$this->stored = [];
		self::assertFalse($this->service(['enabled' => false] + self::ENABLED, fn () => null)->startAllowed());
		$this->stored = [];
		self::assertFalse($this->service(self::ENABLED, fn () => null)->startAllowed());
		$this->stored = [];
		self::assertFalse($this->service(self::ENABLED, fn () => null, appApi: false)->startAllowed());
	}

	public function testStatusDropsWhatIsOutsideTheContract(): void {
		$service = $this->service(self::ENABLED, fn () => $this->statusAnswer([
			'companion' => 'perhaps',
			'ready' => 'yes',
			'lastChild' => ['kind' => 'shell', 'rssKb' => 1, 'ms' => 2],
		]));
		$status = $service->status('root');
		self::assertNotNull($status);
		self::assertNull($status['companion']);
		self::assertFalse($status['ready']);
		self::assertNull($status['lastChild']);

		$service = $this->service(self::ENABLED, fn () => $this->statusAnswer(['lastChild' => ['kind' => 'render', 'rssKb' => 2048, 'ms' => 90]]));
		self::assertSame(['kind' => 'render', 'rssKb' => 2048, 'ms' => 90], $service->status('root')['lastChild'] ?? null);
	}
}
