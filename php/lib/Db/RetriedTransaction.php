<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Db;

use Doctrine\DBAL\Exception\RetryableException;
use OCP\DB\Exception as DbException;
use OCP\IDBConnection;
use Psr\Log\LoggerInterface;

/**
 * Runs one short write transaction and repeats it when the database answers
 * with a lock instead of waiting. SQLite reports "database is locked" at once
 * when the transaction has read and another writer (cron placing a copy, the
 * container claiming work) commits before it writes; MariaDB reports deadlocks
 * and lock wait timeouts the same way. Both arrive as OCP\DB\Exception whose
 * cause Doctrine marks as retryable (CI run 43667132427).
 *
 * The whole closure runs again on every attempt, so it has to be safe to
 * repeat from its first read: the rollback has already undone its writes.
 */
final class RetriedTransaction {
	/** Attempts in total, the first one included. */
	private const ATTEMPTS = 3;
	/** Pause before the second and the third attempt, in milliseconds. */
	private const BACKOFF_MS = [50, 150];
	/** On top of the pause, so colliding writers spread out, in milliseconds. */
	private const JITTER_MS = 50;

	public function __construct(
		private IDBConnection $db,
		private LoggerInterface $logger,
	) {
	}

	/**
	 * The result of $work, committed. A lock on the way rolls back, waits
	 * shortly and runs $work again, at most twice; every other failure and
	 * the last locked attempt roll back and throw unchanged.
	 *
	 * @template T
	 * @param \Closure(): T $work
	 * @return T
	 */
	public function run(\Closure $work): mixed {
		for ($attempt = 1; ; $attempt++) {
			$this->db->beginTransaction();
			try {
				$result = $work();
				$this->db->commit();
				return $result;
			} catch (\Throwable $e) {
				$this->db->rollBack();
				if ($attempt >= self::ATTEMPTS || !self::lockedOut($e)) {
					throw $e;
				}
				$this->logger->warning('PII Redaction: transaction hit a database lock, trying again', ['attempt' => $attempt, 'class' => $e::class]);
				usleep(1000 * (self::BACKOFF_MS[$attempt - 1] + random_int(0, self::JITTER_MS)));
			}
		}
	}

	/**
	 * Whether the chain of $e carries a lock the next attempt can get past.
	 * Nextcloud wraps the driver answer into OCP\DB\Exception with a reason;
	 * the Doctrine exception underneath is checked as well, in case a caller
	 * hands the unwrapped one through.
	 */
	private static function lockedOut(\Throwable $e): bool {
		for ($step = $e; $step !== null; $step = $step->getPrevious()) {
			if ($step instanceof RetryableException) {
				return true;
			}
			if ($step instanceof DbException
				&& in_array($step->getReason(), [DbException::REASON_DEADLOCK, DbException::REASON_LOCK_WAIT_TIMEOUT], true)) {
				return true;
			}
		}
		return false;
	}
}
