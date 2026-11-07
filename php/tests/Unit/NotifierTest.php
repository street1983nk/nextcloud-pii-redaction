<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Notification\Notifier;
use OCP\IL10N;
use OCP\IURLGenerator;
use OCP\L10N\IFactory;
use OCP\Notification\INotification;
use OCP\Notification\UnknownNotificationException;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

/**
 * The notifier with the real catalogs of php/l10n: every subject in de,
 * de_DE, en and fr, and never a file name in what leaves through push.
 */
#[CoversClass(Notifier::class)]
final class NotifierTest extends TestCase {
	private const FILE_NAME = 'Bescheid Müller 2026-114.docx';

	/** @var array<string, mixed> what prepare() set on the notification */
	private array $parsed = [];

	private function notifier(): Notifier {
		$factory = $this->createMock(IFactory::class);
		$factory->method('get')->willReturnCallback(function (string $app, ?string $lang = null): IL10N {
			self::assertSame('pii_redaction', $app);
			return $this->catalog($lang ?? 'en');
		});
		$urls = $this->createMock(IURLGenerator::class);
		$urls->method('linkToRouteAbsolute')->willReturnCallback(
			static fn (string $route, array $parameters = []): string => 'https://cloud.example/index.php/apps/pii_redaction/review/' . $parameters['jobId'],
		);
		$urls->method('imagePath')->willReturn('/apps/pii_redaction/img/app-dark.svg');
		$urls->method('getAbsoluteURL')->willReturnCallback(static fn (string $url): string => 'https://cloud.example' . $url);
		return new Notifier($factory, $urls);
	}

	/** A translator over the real catalog of $lang. */
	private function catalog(string $lang): IL10N {
		$path = dirname(__DIR__, 2) . '/l10n/' . $lang . '.json';
		$translations = [];
		if (is_file($path)) {
			$decoded = json_decode((string)file_get_contents($path), true);
			self::assertIsArray($decoded);
			$translations = $decoded['translations'];
		}
		$l = $this->createMock(IL10N::class);
		$l->method('t')->willReturnCallback(static function (string $text, mixed $parameters = []) use ($translations): string {
			self::assertSame([], $parameters, 'a notification text has no parameters');
			$translated = $translations[$text] ?? $text;
			return is_string($translated) ? $translated : $text;
		});
		return $l;
	}

	private function notification(string $app, string $subject, string $objectId = '7'): INotification {
		$this->parsed = [];
		$notification = $this->createMock(INotification::class);
		$notification->method('getApp')->willReturn($app);
		$notification->method('getSubject')->willReturn($subject);
		// A name smuggled into the parameters must not reach the text.
		$notification->method('getSubjectParameters')->willReturn(['name' => self::FILE_NAME]);
		$notification->method('getObjectType')->willReturn('job');
		$notification->method('getObjectId')->willReturn($objectId);
		foreach (['setParsedSubject', 'setParsedMessage', 'setLink', 'setIcon'] as $setter) {
			$notification->method($setter)->willReturnCallback(function (string $value) use ($setter, $notification): INotification {
				$this->parsed[$setter] = $value;
				return $notification;
			});
		}
		return $notification;
	}

	/** @return array<string, array{string, string, string, string}> */
	public static function texts(): array {
		return [
			'review_ready de' => ['review_ready', 'de', 'Eine Prüfung ist bereit', 'Die Prüfseite öffnen.'],
			'review_ready de_DE' => ['review_ready', 'de_DE', 'Eine Prüfung ist bereit', 'Die Prüfseite öffnen.'],
			'review_ready en' => ['review_ready', 'en', 'A review is ready', 'Open the review page.'],
			'review_ready fr' => ['review_ready', 'fr', 'Une vérification est prête', 'Ouvrez la page de vérification.'],
			'job_failed de' => ['job_failed', 'de', 'Eine Analyse ist fehlgeschlagen', 'Den Grund nennt die Prüfseite.'],
			'job_failed de_DE' => ['job_failed', 'de_DE', 'Eine Analyse ist fehlgeschlagen', 'Den Grund nennt die Prüfseite.'],
			'job_failed en' => ['job_failed', 'en', 'An analysis failed', 'The review page shows why.'],
			'job_failed fr' => ['job_failed', 'fr', 'Une analyse a échoué', 'La page de vérification indique pourquoi.'],
			'job_stale de' => ['job_stale', 'de', 'Eine Analyse wurde beendet', 'Die Datei wurde geändert. Neu analysieren.'],
			'job_stale de_DE' => ['job_stale', 'de_DE', 'Eine Analyse wurde beendet', 'Die Datei wurde geändert. Neu analysieren.'],
			'job_stale en' => ['job_stale', 'en', 'An analysis was stopped', 'The file changed. Analyse it again.'],
			'job_stale fr' => ['job_stale', 'fr', 'Une analyse a été arrêtée', "Le fichier a été modifié. Relancez l'analyse."],
			'copy_created de' => ['copy_created', 'de', 'Eine Kopie ist angelegt', 'Sie liegt neben dem Original.'],
			'copy_created de_DE' => ['copy_created', 'de_DE', 'Eine Kopie ist angelegt', 'Sie liegt neben dem Original.'],
			'copy_created en' => ['copy_created', 'en', 'A copy was created', 'It is next to the original.'],
			'copy_created fr' => ['copy_created', 'fr', 'Une copie a été créée', "Elle se trouve à côté de l'original."],
		];
	}

	#[DataProvider('texts')]
	public function testEachSubjectHasItsFixedSentenceInTheLanguageOfTheRecipient(string $subject, string $lang, string $title, string $sentence): void {
		$this->notifier()->prepare($this->notification('pii_redaction', $subject), $lang);

		self::assertSame($title, $this->parsed['setParsedSubject']);
		self::assertSame($sentence, $this->parsed['setParsedMessage']);
		$text = $this->parsed['setParsedSubject'] . ' ' . $this->parsed['setParsedMessage'];
		foreach (['.pdf', '.docx', '.odt', 'Bescheid', 'Müller'] as $needle) {
			self::assertStringNotContainsString($needle, $text);
		}
	}

	public function testTheLinkIsTheReviewPageAndTheIconIsAbsolute(): void {
		$this->notifier()->prepare($this->notification('pii_redaction', 'review_ready', '7'), 'en');

		self::assertSame('https://cloud.example/index.php/apps/pii_redaction/review/7', $this->parsed['setLink']);
		self::assertSame('https://cloud.example/apps/pii_redaction/img/app-dark.svg', $this->parsed['setIcon']);
	}

	public function testAnObjectIdThatIsNoNumberGetsNoLink(): void {
		$this->notifier()->prepare($this->notification('pii_redaction', 'review_ready', '../7'), 'en');
		self::assertArrayNotHasKey('setLink', $this->parsed);
	}

	public function testAnUnknownSubjectThrows(): void {
		$this->expectException(UnknownNotificationException::class);
		$this->notifier()->prepare($this->notification('pii_redaction', 'reminder-due'), 'en');
	}

	public function testANotificationOfAnotherAppThrows(): void {
		$this->expectException(UnknownNotificationException::class);
		$this->notifier()->prepare($this->notification('files_reminders', 'review_ready'), 'en');
	}

	public function testIdAndNameAreFixed(): void {
		$notifier = $this->notifier();
		self::assertSame('pii_redaction', $notifier->getID());
		self::assertSame('PII Redaction', $notifier->getName());
	}
}
