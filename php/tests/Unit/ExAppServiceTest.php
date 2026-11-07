<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Service\ExAppService;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\TestCase;

/**
 * Page image and output: what the container sends is outside the trust
 * boundary, so only a bounded PNG with status 200 is a page, and the output
 * is asked for as a stream with the long timeout.
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
}
