<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Service\ExAppService;
use OCA\PiiRedaction\Settings\Admin;
use OCA\PiiRedaction\Settings\Section;
use OCP\AppFramework\Http\TemplateResponse;
use OCP\AppFramework\Utility\ITimeFactory;
use OCP\IDateTimeFormatter;
use OCP\IL10N;
use OCP\IURLGenerator;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;
use Psr\Log\LoggerInterface;

/**
 * The admin section: its section values, the form parameters, and the
 * template itself, rendered with a doubled URL generator. "Open Apps" sits in
 * the five error banners and in no other; the fallback route counts only where
 * the first one is unknown (orchestrator decision 3).
 */
#[CoversClass(Admin::class)]
#[CoversClass(Section::class)]
final class AdminSettingsTest extends TestCase {
	private const FIRST = '/index.php/apps/appstore';
	private const SECOND = '/index.php/settings/apps';
	private const ERROR_STATES = ['version_drift', 'backend_missing', 'backend_disabled', 'backend_unreachable', 'no_app_api'];

	/**
	 * The template as the settings page renders it, as a DOM.
	 */
	private function renderTemplate(string $state, string $first = self::FIRST): \DOMXPath {
		if (!function_exists('p')) {
			require_once \OC::$SERVERROOT . '/lib/private/Template/functions.php';
		}
		$urls = $this->createMock(IURLGenerator::class);
		$urls->method('linkToRoute')->willReturnCallback(
			static fn (string $route): string => match ($route) {
				'appstore.page.viewApps' => $first,
				'settings.AppSettings.viewApps' => self::SECOND,
				default => '',
			},
		);
		$l = $this->createMock(IL10N::class);
		$l->method('t')->willReturnCallback(
			static fn (string $text, array|string $parameters = []): string => vsprintf($text, (array)$parameters),
		);
		$_ = [
			'state' => $state,
			'ownVersion' => '0.1.0',
			'backendVersion' => '0.1.0',
			'checkedAtText' => '14:00:00',
			'checkedAtIso' => '2026-11-07T14:00:00Z',
			'urlGenerator' => $urls,
		];

		ob_start();
		try {
			include __DIR__ . '/../../templates/admin.php';
		} finally {
			$html = (string)ob_get_clean();
		}

		$document = new \DOMDocument();
		self::assertTrue($document->loadHTML('<?xml encoding="utf-8"?>' . $html, LIBXML_NOERROR | LIBXML_NOWARNING));
		return new \DOMXPath($document);
	}

	private static function actionOf(\DOMXPath $dom, string $state): ?string {
		$links = $dom->query("//div[@data-state='{$state}']//a[contains(@class, 'pii-banner__action')]");
		if ($links === false || $links->length === 0) {
			return null;
		}
		$link = $links->item(0);
		return $link instanceof \DOMElement ? $link->getAttribute('href') : null;
	}

	/**
	 * @return array<string, array{string}>
	 */
	public static function errorStates(): array {
		$cases = [];
		foreach (self::ERROR_STATES as $state) {
			$cases[$state] = [$state];
		}
		return $cases;
	}

	#[DataProvider('errorStates')]
	public function testEveryErrorBannerOffersTheAppManagement(string $state): void {
		$dom = $this->renderTemplate($state);
		self::assertSame(self::FIRST, self::actionOf($dom, $state));

		$visible = $dom->query("//div[@data-state='{$state}' and not(@hidden)]");
		self::assertNotFalse($visible);
		self::assertSame(1, $visible->length);
	}

	public function testTheCalmStatesOfferNoLink(): void {
		$dom = $this->renderTemplate('ok');
		self::assertNull(self::actionOf($dom, 'ok'));
		self::assertNull(self::actionOf($dom, 'version_patch_differs'));
	}

	public function testTheFallbackRouteCountsOnlyWhereTheFirstIsUnknown(): void {
		$dom = $this->renderTemplate('backend_missing', '');
		self::assertSame(self::SECOND, self::actionOf($dom, 'backend_missing'));
	}

	public function testOnlyTheCurrentBannerIsVisibleAndTheStateAreaIsAnnounced(): void {
		$dom = $this->renderTemplate('version_patch_differs');
		$visible = $dom->query('//div[@data-state and not(@hidden)]');
		self::assertNotFalse($visible);
		self::assertSame(1, $visible->length);

		$area = $dom->query("//div[@id='pii-backend-state' and @role='status' and @aria-live='polite' and @tabindex='-1']");
		self::assertNotFalse($area);
		self::assertSame(1, $area->length);
		$failed = $dom->query("//div[@id='pii-recheck-failed' and @hidden]");
		self::assertNotFalse($failed);
		self::assertSame(1, $failed->length);
		$button = $dom->query("//button[@id='pii-recheck']//span[@id='pii-recheck-label']");
		self::assertNotFalse($button);
		self::assertSame(1, $button->length);
	}

	public function testAnUnknownStateRendersAsUnreachable(): void {
		$dom = $this->renderTemplate('something_else');
		$visible = $dom->query("//div[@data-state='backend_unreachable' and not(@hidden)]");
		self::assertNotFalse($visible);
		self::assertSame(1, $visible->length);
	}

	public function testTheFormPassesCodesVersionsAndTimeOnly(): void {
		$exApp = $this->createMock(ExAppService::class);
		$exApp->method('backendState')->willReturn([
			'state' => 'ok',
			'ownVersion' => '0.1.0',
			'backendVersion' => '0.1.1',
			'checkedAt' => 1_800_000_000,
			'companion' => 'ok',
		]);
		$formatter = $this->createMock(IDateTimeFormatter::class);
		$formatter->method('formatTime')->willReturn('14:00:00');
		$urls = $this->createMock(IURLGenerator::class);

		$admin = new Admin($exApp, $formatter, $urls, $this->createMock(ITimeFactory::class), $this->createMock(LoggerInterface::class));
		$form = $admin->getForm();

		self::assertSame('admin', $form->getTemplateName());
		self::assertSame(TemplateResponse::RENDER_AS_BLANK, $form->getRenderAs());
		$parameters = $form->getParams();
		self::assertSame('ok', $parameters['state']);
		self::assertSame('0.1.1', $parameters['backendVersion']);
		self::assertSame('14:00:00', $parameters['checkedAtText']);
		self::assertSame($urls, $parameters['urlGenerator']);
		self::assertSame('pii_redaction', $admin->getSection());
		self::assertSame(50, $admin->getPriority());
	}

	public function testAThrowingStateRendersAsUnreachable(): void {
		$exApp = $this->createMock(ExAppService::class);
		$exApp->method('backendState')->willThrowException(new \RuntimeException('down'));
		$exApp->method('ownVersion')->willReturn('0.1.0');
		$time = $this->createMock(ITimeFactory::class);
		$time->method('getTime')->willReturn(1_800_000_000);

		$admin = new Admin($exApp, $this->createMock(IDateTimeFormatter::class), $this->createMock(IURLGenerator::class), $time, $this->createMock(LoggerInterface::class));

		self::assertSame('backend_unreachable', $admin->getForm()->getParams()['state']);
	}

	public function testTheSectionValues(): void {
		$l = $this->createMock(IL10N::class);
		$l->method('t')->willReturnArgument(0);
		$urls = $this->createMock(IURLGenerator::class);
		$urls->method('imagePath')->with('pii_redaction', 'app-dark.svg')->willReturn('/apps/pii_redaction/img/app-dark.svg');

		$section = new Section($l, $urls);

		self::assertSame('pii_redaction', $section->getID());
		self::assertSame('PII Redaction', $section->getName());
		self::assertSame(75, $section->getPriority());
		self::assertSame('/apps/pii_redaction/img/app-dark.svg', $section->getIcon());
	}
}
