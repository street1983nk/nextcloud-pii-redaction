<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Service\ExAppService;
use OCP\App\IAppManager;
use OCP\AppFramework\Utility\ITimeFactory;
use OCP\Http\Client\IResponse;
use OCP\IAppConfig;
use OCP\IGroup;
use OCP\IGroupManager;
use OCP\IUser;
use OCP\IUserManager;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;
use Psr\Log\LoggerInterface;

/**
 * Builds an ExAppService with two seams doubled, as in Audio & Video Search:
 * exAppInfo (the registration in AppAPI) and proxyRequest (the one call into
 * the container). Both belong to AppAPI, which is absent from the autoload
 * space of this suite. Everything else is the real code.
 */
trait ExAppServiceFactory {
	/** @var array<string, string> */
	private array $stored = [];
	private int $now = 1_800_000_000;
	/** @var list<array{route: string, method: string, timeout: float, options: array<string, mixed>}> */
	private array $calls = [];

	/**
	 * @param array<mixed>|false|null $info what AppAPI knows about the backend
	 * @param \Closure(string): (array<mixed>|IResponse|null) $transport answer per route
	 */
	private function service(array|false|null $info, \Closure $transport, string $ownVersion = '0.1.0', bool $appApi = true): ExAppService&MockObject {
		$appConfig = $this->createMock(IAppConfig::class);
		$appConfig->method('getValueString')->willReturnCallback(
			fn (string $app, string $key, string $default = ''): string => $this->stored[$key] ?? $default,
		);
		$appConfig->method('setValueString')->willReturnCallback(
			function (string $app, string $key, string $value): bool {
				$this->stored[$key] = $value;
				return true;
			},
		);

		$appManager = $this->createMock(IAppManager::class);
		$appManager->method('getAppVersion')->willReturn($ownVersion);
		$appManager->method('isEnabledForUser')->willReturnCallback(static fn (string $app): bool => $app === 'app_api' && $appApi);

		$user = $this->createMock(IUser::class);
		$user->method('getUID')->willReturn('root');
		$user->method('isEnabled')->willReturn(true);
		$userManager = $this->createMock(IUserManager::class);
		$userManager->method('get')->willReturn($user);

		$group = $this->createMock(IGroup::class);
		$group->method('getUsers')->willReturn([$user]);
		$groupManager = $this->createMock(IGroupManager::class);
		$groupManager->method('get')->willReturn($group);

		$time = $this->createMock(ITimeFactory::class);
		$time->method('getTime')->willReturnCallback(fn (): int => $this->now);

		$service = $this->getMockBuilder(ExAppService::class)
			->setConstructorArgs([$appManager, $userManager, $appConfig, $this->createMock(LoggerInterface::class), $groupManager, $time])
			->onlyMethods(['proxyRequest', 'exAppInfo'])
			->getMock();
		$service->method('exAppInfo')->willReturn($info);
		$service->method('proxyRequest')->willReturnCallback(
			function (string $route, string $userId, string $method, array $params, float $timeout, array $options = []) use ($transport): array|IResponse|null {
				$this->calls[] = ['route' => $route, 'method' => $method, 'timeout' => $timeout, 'options' => $options];
				return $transport($route);
			},
		);

		return $service;
	}

	/**
	 * @param string|resource $body
	 */
	private function response(int $status, mixed $body): IResponse&MockObject {
		$response = $this->createMock(IResponse::class);
		$response->method('getStatusCode')->willReturn($status);
		$response->method('getBody')->willReturn($body);
		return $response;
	}

	/**
	 * @param array<string, mixed> $fields
	 */
	private function statusAnswer(array $fields): IResponse&MockObject {
		return $this->response(200, (string)json_encode($fields + ['version' => '0.1.0', 'ready' => true, 'busy' => false, 'lastChild' => null]));
	}
}
