<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Service;

use OCA\PiiRedaction\Model\Lang;
use OCA\PiiRedaction\Model\Mode;

/**
 * The name of the copy next to the original (UI-SPEC Fläche 4):
 * {stem}{suffix}.pdf, stem = the name without its last extension, suffix by
 * mode and the language of the initiator, always .pdf, in NFC.
 *
 * The suffixes are not catalog entries: they are part of a file name and
 * must not change when a translation changes.
 */
final class Suffix {
	private const REDACT = [
		'de' => '_geschwärzt',
		'en' => '_redacted',
		'fr' => '_caviardé',
	];

	private const PSEUDONYMIZE = [
		'de' => '_pseudonymisiert',
		'en' => '_pseudonymized',
		'fr' => '_pseudonymisé',
	];

	public static function outputName(string $original, Mode $mode, Lang $lang): string {
		$suffixes = $mode === Mode::Redact ? self::REDACT : self::PSEUDONYMIZE;
		$name = self::stem($original) . $suffixes[$lang->value] . '.pdf';

		$normalized = class_exists(\Normalizer::class) ? \Normalizer::normalize($name, \Normalizer::FORM_C) : false;
		return is_string($normalized) ? $normalized : $name;
	}

	/**
	 * The name without its last extension. A name without a dot stays
	 * whole, and a leading dot (".hidden") is no extension.
	 */
	private static function stem(string $name): string {
		$dot = strrpos($name, '.');
		return $dot === false || $dot === 0 ? $name : substr($name, 0, $dot);
	}
}
