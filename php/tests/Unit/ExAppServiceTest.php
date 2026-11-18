<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Service\ExAppService;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

/**
 * Page image and output: what the container sends is outside the trust
 * boundary, so only a bounded PNG with status 200 is a page, and the output
 * is asked for as a stream with the long timeout. The protection state of
 * /status (plan 02-20) comes through as fixed words only, and the state of the
 * other half names the missing layers as a list of fixed words.
 */
#[CoversClass(ExAppService::class)]
final class ExAppServiceTest extends TestCase {
	use ExAppServiceFactory;

	private const PNG = "\x89PNG\r\n\x1a\n" . 'rest-of-image';
	private const INFO = ['appid' => 'pii_redaction_backend', 'version' => '0.1.0', 'enabled' => true];

	public function testAValidPngIsThePage(): void {
		$service = $this->service(self::INFO, fn () => $this->response(200, self::PNG));
		self::assertSame(self::PNG, $service->page(7, 1, 'alice'));
		self::assertSame('/jobs/7/pages/1.png', $this->calls[0]['route']);
		self::assertSame('GET', $this->calls[0]['method']);
		self::assertSame(ExAppService::PAGE_TIMEOUT_SECONDS, $this->calls[0]['timeout']);
	}

	public function testAStreamedPngIsReadToo(): void {
		$stream = fopen('php://memory', 'r+');
		self::assertIsResource($stream);
		fwrite($stream, self::PNG);
		rewind($stream);
		$service = $this->service(self::INFO, fn () => $this->response(200, $stream));
		self::assertSame(self::PNG, $service->page(7, 1, 'alice'));
	}

	public function testSomethingElseThanAPngIsRefused(): void {
		$service = $this->service(self::INFO, fn () => $this->response(200, '<html>not an image</html>'));
		self::assertNull($service->page(7, 1, 'alice'));
	}

	public function testAnOversizedPageIsRefused(): void {
		$service = $this->service(self::INFO, fn () => $this->response(200, self::PNG . str_repeat('x', ExAppService::MAX_PAGE_BYTES)));
		self::assertNull($service->page(7, 1, 'alice'));
	}

	public function testANotFoundPageIsRefused(): void {
		$service = $this->service(self::INFO, fn () => $this->response(404, self::PNG));
		self::assertNull($service->page(7, 1, 'alice'));
	}

	public function testATransportFailureIsNoPage(): void {
		$service = $this->service(self::INFO, fn () => ['error' => 'timeout']);
		self::assertNull($service->page(7, 1, 'alice'));
	}

	public function testANonPositivePageIsNeverAsked(): void {
		$service = $this->service(self::INFO, fn () => $this->response(200, self::PNG));
		self::assertNull($service->page(7, 0, 'alice'));
		self::assertSame([], $this->calls);
	}

	public function testTheOutputIsAskedAsAStreamWithTheLongTimeout(): void {
		$response = $this->response(200, 'pdf-bytes');
		$service = $this->service(self::INFO, fn () => $response);
		self::assertSame($response, $service->output(9, 'alice'));
		self::assertSame('/jobs/9/output', $this->calls[0]['route']);
		self::assertSame(['stream' => true], $this->calls[0]['options']);
		self::assertSame(120.0, $this->calls[0]['timeout']);
	}

	public function testAFailedOutputIsNull(): void {
		self::assertNull($this->service(self::INFO, fn () => $this->response(404, ''))->output(9, 'alice'));
		self::assertNull($this->service(self::INFO, fn () => ['error' => 'refused'])->output(9, 'alice'));
	}

	public function testAListInsteadOfAnObjectIsNoStatus(): void {
		$service = $this->service(self::INFO, fn () => $this->response(200, '[1, 2]'));
		self::assertNull($service->status('root'));
	}

	// -- the protection state of the container (plan 02-20, D-02-11) -------------

	private const SANDBOX = ['seccomp' => 'active', 'landlock' => 'unavailable', 'landlockAbi' => 0, 'jail' => 'ok'];

	public function testASandboxOfFixedWordsIsTakenOver(): void {
		$service = $this->service(self::INFO, fn () => $this->statusAnswer(['sandbox' => self::SANDBOX]));
		self::assertSame(self::SANDBOX, $service->status('root')['sandbox'] ?? null);
	}

	/**
	 * @return iterable<string, array{mixed}>
	 */
	public static function foreignSandboxes(): iterable {
		yield 'seccomp maybe' => [['seccomp' => 'maybe'] + self::SANDBOX];
		yield 'landlock as bool' => [['landlock' => true] + self::SANDBOX];
		yield 'jail broken' => [['jail' => 'broken'] + self::SANDBOX];
		yield 'abi as string' => [['landlockAbi' => '4'] + self::SANDBOX];
		yield 'abi as bool' => [['landlockAbi' => true] + self::SANDBOX];
		yield 'abi negative' => [['landlockAbi' => -1] + self::SANDBOX];
		yield 'abi too high' => [['landlockAbi' => 65] + self::SANDBOX];
		yield 'jail missing' => [['seccomp' => 'active', 'landlock' => 'active', 'landlockAbi' => 4]];
		yield 'a list' => [['active', 'active', 4, 'ok']];
		yield 'a word' => ['active'];
	}

	#[DataProvider('foreignSandboxes')]
	public function testASandboxOutsideTheContractIsNull(mixed $sandbox): void {
		$service = $this->service(self::INFO, fn () => $this->statusAnswer(['sandbox' => $sandbox]));
		$status = $service->status('root');
		self::assertNotNull($status);
		self::assertArrayHasKey('sandbox', $status);
		self::assertNull($status['sandbox']);
	}

	public function testTheHighestLandlockAbiIsStillAWord(): void {
		// array_replace keeps the key order of the contract; assertSame on
		// arrays compares the order too.
		$sandbox = array_replace(self::SANDBOX, ['landlockAbi' => 64]);
		$service = $this->service(self::INFO, fn () => $this->statusAnswer(['sandbox' => $sandbox]));
		self::assertSame($sandbox, $service->status('root')['sandbox'] ?? null);
	}

	public function testTheCheckChildrenAreKindsAndARocketIsNot(): void {
		foreach (['precheck', 'sanitize'] as $kind) {
			$child = ['kind' => $kind, 'rssKb' => 4096, 'ms' => 120];
			$service = $this->service(self::INFO, fn () => $this->statusAnswer(['lastChild' => $child]));
			self::assertSame($child, $service->status('root')['lastChild'] ?? null, $kind);
		}
		$service = $this->service(self::INFO, fn () => $this->statusAnswer(['lastChild' => ['kind' => 'rocket', 'rssKb' => 1, 'ms' => 1]]));
		$status = $service->status('root');
		self::assertNotNull($status);
		self::assertArrayHasKey('lastChild', $status);
		self::assertNull($status['lastChild']);
	}

	/**
	 * @return iterable<string, array{array<string, mixed>, list<string>}>
	 */
	public static function degradations(): iterable {
		yield 'full isolation' => [['seccomp' => 'active', 'landlock' => 'active', 'landlockAbi' => 4, 'jail' => 'ok'], []];
		yield 'no seccomp' => [['seccomp' => 'unavailable', 'landlock' => 'active', 'landlockAbi' => 4, 'jail' => 'ok'], ['seccomp']];
		yield 'no landlock' => [self::SANDBOX, ['landlock']];
		yield 'jail failed' => [['seccomp' => 'active', 'landlock' => 'active', 'landlockAbi' => 4, 'jail' => 'failed'], ['jail']];
		yield 'everything gone' => [['seccomp' => 'unavailable', 'landlock' => 'unavailable', 'landlockAbi' => 0, 'jail' => 'failed'], ['seccomp', 'landlock', 'jail']];
	}

	/**
	 * @param array<string, mixed> $sandbox
	 * @param list<string> $expected
	 */
	#[DataProvider('degradations')]
	public function testTheStateNamesEveryMissingLayer(array $sandbox, array $expected): void {
		$service = $this->service(self::INFO, fn () => $this->statusAnswer(['companion' => 'ok', 'sandbox' => $sandbox]));
		self::assertSame($expected, $service->backendState(true)['sandboxDegraded']);
	}

	public function testAnUnknownSandboxIsNoListAtAll(): void {
		$service = $this->service(self::INFO, fn () => $this->statusAnswer(['companion' => 'ok', 'sandbox' => null]));
		self::assertNull($service->backendState(true)['sandboxDegraded']);

		$this->stored = [];
		$service = $this->service(self::INFO, fn () => $this->statusAnswer(['companion' => 'ok', 'sandbox' => ['seccomp' => 'maybe'] + self::SANDBOX]));
		self::assertNull($service->backendState(true)['sandboxDegraded']);

		$this->stored = [];
		$service = $this->service(self::INFO, fn () => ['error' => 'refused']);
		self::assertNull($service->backendState(true)['sandboxDegraded']);
	}

	public function testAJailThatFailsInOperationShowsOnTheNextCheck(): void {
		// Exit 71 in a child: the container turns jail to failed for good
		// (probe.mark_jail_failed, plan 02-19). The next fresh check shows it.
		$jail = 'ok';
		$service = $this->service(self::INFO, function () use (&$jail) {
			return $this->statusAnswer(['companion' => 'ok', 'sandbox' => ['seccomp' => 'active', 'landlock' => 'active', 'landlockAbi' => 4, 'jail' => $jail]]);
		});
		self::assertSame([], $service->backendState(true)['sandboxDegraded']);

		$jail = 'failed';
		self::assertSame(['jail'], $service->backendState(true)['sandboxDegraded']);
	}

	public function testARememberedVerdictKeepsTheListAndDropsForeignWords(): void {
		$service = $this->service(self::INFO, fn () => $this->statusAnswer(['companion' => 'ok', 'sandbox' => self::SANDBOX]));
		$service->backendState(true);
		self::assertSame(['landlock'], $service->backendState()['sandboxDegraded']);
		self::assertCount(1, $this->calls);

		$decoded = json_decode($this->stored[ExAppService::KEY_BACKEND_STATE], true);
		self::assertIsArray($decoded);
		$decoded['sandboxDegraded'] = ['landlock', '<b>x</b>'];
		$this->stored[ExAppService::KEY_BACKEND_STATE] = (string)json_encode($decoded);
		self::assertNull($service->backendState()['sandboxDegraded']);
	}
}
