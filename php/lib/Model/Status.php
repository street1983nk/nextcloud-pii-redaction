<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Model;

/**
 * The closed list of job states (01-SKELETON.md "Geschlossene Listen").
 *
 * The values are stored in pii_jobs.status (16 characters) and are the same
 * words the container uses in model.py. Anything outside this list read from
 * the database is an error, never passed through (Job::getStatusEnum).
 */
enum Status: string {
	case Queued = 'queued';
	case Analyzing = 'analyzing';
	case Review = 'review';
	case Submitted = 'submitted';
	case Approved = 'approved';
	case Applying = 'applying';
	case Verified = 'verified';
	case Published = 'published';
	case Failed = 'failed';
	case Stale = 'stale';
	case Cancelled = 'cancelled';
	case Expired = 'expired';

	/**
	 * A job in one of these states is finished; JobService then hands it to
	 * the purge task (except review, which waits for the user).
	 */
	public function isTerminal(): bool {
		return match ($this) {
			self::Published, self::Failed, self::Stale, self::Cancelled, self::Expired => true,
			default => false,
		};
	}

	/**
	 * A job in one of these states still holds the file: a second start on the
	 * same file and etag returns it instead of creating a new one.
	 */
	public function isOpen(): bool {
		return match ($this) {
			self::Queued, self::Analyzing, self::Review, self::Approved, self::Applying, self::Verified => true,
			default => false,
		};
	}

	/**
	 * The values of isOpen() as strings, for an IN condition of a query.
	 *
	 * @return list<string>
	 */
	public static function openValues(): array {
		$values = [];
		foreach (self::cases() as $status) {
			if ($status->isOpen()) {
				$values[] = $status->value;
			}
		}
		return $values;
	}
}
