<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Model;

/**
 * Redact or pseudonymize, stored in pii_jobs.mode (16 characters). Phase 1
 * only starts redact jobs; the column exists now so no later phase adds one.
 */
enum Mode: string {
	case Redact = 'redact';
	case Pseudonymize = 'pseudonymize';
}
