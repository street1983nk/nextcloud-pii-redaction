<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Model\Lang;
use OCA\PiiRedaction\Model\Mode;
use OCA\PiiRedaction\Service\Suffix;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

/**
 * The name rule of the copy (UI-SPEC Fläche 4).
 */
#[CoversClass(Suffix::class)]
final class SuffixTest extends TestCase {
	/** @return array<string, array{string, Mode, Lang, string}> */
	public static function names(): array {
		return [
			'docx de' => ['Bescheid 2026-114.docx', Mode::Redact, Lang::De, 'Bescheid 2026-114_geschwärzt.pdf'],
			'pdf en' => ['report.pdf', Mode::Redact, Lang::En, 'report_redacted.pdf'],
			'odt fr' => ['note.odt', Mode::Redact, Lang::Fr, 'note_caviardé.pdf'],
			'pseudonymize de' => ['Akte.pdf', Mode::Pseudonymize, Lang::De, 'Akte_pseudonymisiert.pdf'],
			'pseudonymize en' => ['file.pdf', Mode::Pseudonymize, Lang::En, 'file_pseudonymized.pdf'],
			'pseudonymize fr' => ['dossier.pdf', Mode::Pseudonymize, Lang::Fr, 'dossier_pseudonymisé.pdf'],
			'only the last extension' => ['archiv.tar.docx', Mode::Redact, Lang::En, 'archiv.tar_redacted.pdf'],
			'leading dot is no extension' => ['.hidden', Mode::Redact, Lang::En, '.hidden_redacted.pdf'],
			'no extension' => ['ohne_endung', Mode::Redact, Lang::De, 'ohne_endung_geschwärzt.pdf'],
		];
	}

	#[DataProvider('names')]
	public function testTheCopyIsNamedStemSuffixPdf(string $original, Mode $mode, Lang $lang, string $expected): void {
		self::assertSame($expected, Suffix::outputName($original, $mode, $lang));
	}

	public function testADecomposedNameComesOutComposed(): void {
		// "Müller" with a combining diaeresis (NFD) and the French suffix.
		$name = Suffix::outputName("Mu\u{0308}ller.pdf", Mode::Redact, Lang::Fr);

		self::assertSame("M\u{00FC}ller_caviard\u{00E9}.pdf", $name);
		self::assertStringNotContainsString("\u{0308}", $name);
		self::assertStringNotContainsString("\u{0301}", $name);
	}

	public function testTheSuffixesAreComposedCharacters(): void {
		self::assertSame("Bericht_geschw\u{00E4}rzt.pdf", Suffix::outputName('Bericht.pdf', Mode::Redact, Lang::De));
	}
}
