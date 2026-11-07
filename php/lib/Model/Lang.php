<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Model;

/**
 * The three languages of the app, stored in pii_jobs.lang (8 characters). It
 * decides the suffix of the copy and, from phase 3 on, the language model.
 */
enum Lang: string {
	case De = 'de';
	case En = 'en';
	case Fr = 'fr';

	/**
	 * A Nextcloud language code to one of the three: everything starting with
	 * de is German (de, de_DE, de_CH), with fr French, anything else English.
	 */
	public static function fromLanguageCode(string $code): self {
		$code = strtolower($code);
		if (str_starts_with($code, 'de')) {
			return self::De;
		}
		if (str_starts_with($code, 'fr')) {
			return self::Fr;
		}
		return self::En;
	}
}
