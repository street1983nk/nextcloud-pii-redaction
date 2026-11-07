<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Controller\SettingsController;
use OCA\PiiRedaction\Service\ExAppService;
use OCP\AppFramework\Http;
use OCP\IDateTimeFormatter;
use OCP\IRequest;
use OCP\IURLGenerator;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;
use Psr\Log\LoggerInterface;

/**
 * "Check again" of the admin section: a fresh state, the last child only when
 * the container answers, the app management address, and a 503 without any
 * message text when the check throws. The last test reads the attributes and
 * holds that the route stays an administrator route.
 */
#[CoversClass(SettingsController::class)]
final class SettingsControllerTest extends TestCase {
	private string $firstRoute = '/index.php/apps/appstore';

	/**
	 * @param array<string, mixed> $state
	 */
	private function exApp(array $state, ?array $answer = null): ExAppService&MockObject {
		$exApp = $this->createMock(ExAppService::class);
		$exApp->method('backendState')->with(true)->willReturn($state + [
			'ownVersion' => '0.1.0',
			'backendVersion' => '0.1.0',
			'checkedAt' => 1_800_000_000,
			'companion' => 'ok',
		]);
		$exApp->method('status')->willReturn($answer);
		return $exApp;
	}

	private function controller(ExAppService $exApp, ?LoggerInterface $logger = null): SettingsController {
		$urls = $this->createMock(IURLGenerator::class);
		$urls->method('linkToRoute')->willReturnCallback(
			fn (string $route): string => match ($route) {
				'appstore.page.viewApps' => $this->firstRoute,
				'settings.AppSettings.viewApps' => '/index.php/settings/apps',
				default => '',
			},
		);
		$formatter = $this->createMock(IDateTimeFormatter::class);
		$formatter->method('formatTime')->willReturn('14:00:00');

		return new SettingsController(
			$this->createMock(IRequest::class),
			$exApp,
			$urls,
			$formatter,
			$logger ?? $this->createMock(LoggerInterface::class),
		);
	}

	public function testAFreshStateComesBackWithTheLastChild(): void {
		$child = ['kind' => 'render', 'rssKb' => 51200, 'ms' => 840];
		$exApp = $this->exApp(['state' => 'ok'], ['version' => '0.1.0', 'ready' => true, 'companion' => 'ok', 'busy' => false, 'lastChild' => $child]);

		$response = $this->controller($exApp)->state();

		self::assertSame(Http::STATUS_OK, $response->getStatus());
		$data = $response->getData();
		self::assertSame('ok', $data['state']);
		self::assertSame('0.1.0', $data['ownVersion']);
		self::assertSame(1_800_000_000, $data['checkedAt']);
		self::assertSame('14:00:00', $data['checkedAtText']);
		self::assertSame($child, $data['lastChild']);
		self::assertSame('/index.php/apps/appstore', $data['appsUrl']);
	}

	public function testAnErrorStateAsksTheContainerNothingMore(): void {
		$exApp = $this->exApp(['state' => 'backend_unreachable']);
		$exApp->expects(self::never())->method('status');

		$data = $this->controller($exApp)->state()->getData();

		self::assertSame('backend_unreachable', $data['state']);
		self::assertNull($data['lastChild']);
	}

	public function testTheSettingsRouteServesWhereTheAppstoreIsUnknown(): void {
		$this->firstRoute = '';
		$data = $this->controller($this->exApp(['state' => 'backend_missing']))->state()->getData();
		self::assertSame('/index.php/settings/apps', $data['appsUrl']);
	}

	public function testAThrowingCheckAnswers503WithACodeOnly(): void {
		$exApp = $this->createMock(ExAppService::class);
		$exApp->method('backendState')->willThrowException(new \RuntimeException('secret detail /home/alice/x.pdf'));
		$logger = $this->createMock(LoggerInterface::class);
		$logger->expects(self::once())->method('error')->with(
			self::stringStartsWith('PII Redaction: '),
			['class' => \RuntimeException::class],
		);

		$response = $this->controller($exApp, $logger)->state();

		self::assertSame(Http::STATUS_SERVICE_UNAVAILABLE, $response->getStatus());
		self::assertSame(['state' => 'recheck_failed'], $response->getData());
	}

	public function testTheRouteStaysAnAdministratorRoute(): void {
		$method = new \ReflectionMethod(SettingsController::class, 'state');
		$names = array_map(static fn (\ReflectionAttribute $attribute): string => $attribute->getName(), $method->getAttributes());

		self::assertContains(\OCP\AppFramework\Http\Attribute\FrontpageRoute::class, $names);
		foreach ([
			\OCP\AppFramework\Http\Attribute\NoAdminRequired::class,
			\OCP\AppFramework\Http\Attribute\PublicPage::class,
			\OCP\AppFramework\Http\Attribute\NoCSRFRequired::class,
			\OCP\AppFramework\Http\Attribute\ExAppRequired::class,
		] as $forbidden) {
			self::assertNotContains($forbidden, $names);
		}

		$route = $method->getAttributes(\OCP\AppFramework\Http\Attribute\FrontpageRoute::class)[0]->getArguments();
		self::assertSame('GET', $route['verb']);
		self::assertSame('/admin/state', $route['url']);
	}
}
