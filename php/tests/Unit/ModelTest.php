<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Model\Lang;
use OCA\PiiRedaction\Model\Mode;
use OCA\PiiRedaction\Model\Reason;
use OCA\PiiRedaction\Model\Stage;
use OCA\PiiRedaction\Model\Status;
use OCA\PiiRedaction\Model\Subject;
use OCA\PiiRedaction\Model\Task;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

/**
 * The closed lists, held against literal copies of 01-SKELETON.md: adding,
 * renaming or dropping a value turns this test red, so a change to a list is
 * always a deliberate one (the container speaks the same words).
 */
final class ModelTest extends TestCase {
	/**
	 * @param list<\BackedEnum> $cases
	 * @return list<string>
	 */
	private static function values(array $cases): array {
		return array_map(static fn (\BackedEnum $item): string => (string)$item->value, $cases);
	}

	public function testStatusIsTheClosedList(): void {
		self::assertSame(
			['queued', 'analyzing', 'review', 'submitted', 'approved', 'applying', 'verified', 'published', 'failed', 'stale', 'cancelled', 'expired'],
			self::values(Status::cases()),
		);
	}

	public function testReasonIsTheClosedList(): void {
		self::assertSame(
			['encrypted_pdf', 'unsupported_format', 'too_many_pages', 'out_of_memory', 'repeatedly_stuck', 'leak_detected', 'check_error', 'original_changed', 'original_deleted', 'target_not_writable', 'backend_state_lost', 'download_blocked', 'not_readable', 'render_failed', 'backend_unavailable'],
			self::values(Reason::cases()),
		);
	}

	public function testTheSmallListsAreClosed(): void {
		self::assertSame(['waiting', 'fetching', 'converting', 'rendering', 'done'], self::values(Stage::cases()));
		self::assertSame(['analyze', 'apply', 'purge'], self::values(Task::cases()));
		self::assertSame(['redact', 'pseudonymize'], self::values(Mode::cases()));
		self::assertSame(['review_ready', 'job_failed', 'job_stale', 'copy_created'], self::values(Subject::cases()));
		self::assertSame(['de', 'en', 'fr'], self::values(Lang::cases()));
	}

	public function testAnUnknownWordIsNoValue(): void {
		self::assertNull(Status::tryFrom('unknown'));
		self::assertNull(Reason::tryFrom('unknown'));
		self::assertNull(Stage::tryFrom('unknown'));
		self::assertNull(Task::tryFrom('unknown'));
		self::assertNull(Mode::tryFrom('unknown'));
		self::assertNull(Subject::tryFrom('unknown'));
		self::assertNull(Lang::tryFrom('unknown'));
	}

	public function testTerminalAndOpenStates(): void {
		$terminal = array_values(array_filter(Status::cases(), static fn (Status $s): bool => $s->isTerminal()));
		$open = array_values(array_filter(Status::cases(), static fn (Status $s): bool => $s->isOpen()));

		self::assertSame(['published', 'failed', 'stale', 'cancelled', 'expired'], self::values($terminal));
		self::assertSame(['queued', 'analyzing', 'review', 'approved', 'applying', 'verified'], self::values($open));
		self::assertSame(self::values($open), Status::openValues());
	}

	/**
	 * @return iterable<string, array{string, Lang}>
	 */
	public static function languageCodes(): iterable {
		yield 'de' => ['de', Lang::De];
		yield 'de_DE' => ['de_DE', Lang::De];
		yield 'fr' => ['fr', Lang::Fr];
		yield 'fr_FR' => ['fr_FR', Lang::Fr];
		yield 'en' => ['en', Lang::En];
		yield 'es' => ['es', Lang::En];
	}

	#[DataProvider('languageCodes')]
	public function testALanguageCodeMapsToOneOfThree(string $code, Lang $expected): void {
		self::assertSame($expected, Lang::fromLanguageCode($code));
	}

	/**
	 * The column lengths of the migration (Version000100Date20261107000000).
	 *
	 * @return iterable<string, array{list<\BackedEnum>, int}>
	 */
	public static function columnLengths(): iterable {
		yield 'reason' => [Reason::cases(), 32];
		yield 'status' => [Status::cases(), 16];
		yield 'stage' => [Stage::cases(), 16];
		yield 'task' => [Task::cases(), 16];
		yield 'mode' => [Mode::cases(), 16];
		yield 'lang' => [Lang::cases(), 8];
		yield 'event action (status)' => [Status::cases(), 32];
		yield 'event action (subject)' => [Subject::cases(), 32];
	}

	/**
	 * @param list<\BackedEnum> $cases
	 */
	#[DataProvider('columnLengths')]
	public function testEveryValueFitsItsColumn(array $cases, int $length): void {
		foreach (self::values($cases) as $value) {
			self::assertLessThanOrEqual($length, strlen($value), $value);
		}
	}
}
