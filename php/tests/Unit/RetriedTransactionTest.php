<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use Doctrine\DBAL\Exception\RetryableException;
use OCA\PiiRedaction\Db\RetriedTransaction;
use OCP\DB\Exception as DbException;
use OCP\IDBConnection;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\TestCase;
use Psr\Log\LoggerInterface;

/**
 * The repeat of one short write transaction when the database answers with a
 * lock (CI run 43667132427: "database is locked" at the job start while cron
 * and the container wrote in the same second).
 */
#[CoversClass(RetriedTransaction::class)]
final class RetriedTransactionTest extends TestCase {
	private int $begun = 0;
	private int $committed = 0;
	private int $rolledBack = 0;

	private function transaction(): RetriedTransaction {
		$db = $this->createMock(IDBConnection::class);
		$db->method('beginTransaction')->willReturnCallback(function (): void {
			$this->begun++;
		});
		$db->method('commit')->willReturnCallback(function (): void {
			$this->committed++;
		});
		$db->method('rollBack')->willReturnCallback(function (): void {
			$this->rolledBack++;
		});
		return new RetriedTransaction($db, $this->createMock(LoggerInterface::class));
	}

	/** What Doctrine throws underneath: a lock marked as worth another try. */
	private static function lock(): \RuntimeException {
		return new class ('database is locked') extends \RuntimeException implements RetryableException {
		};
	}

	public function testTheSecondAttemptCarriesTheResult(): void {
		$calls = 0;
		$result = $this->transaction()->run(function () use (&$calls): string {
			if (++$calls === 1) {
				throw self::lock();
			}
			return 'done';
		});

		self::assertSame('done', $result);
		self::assertSame(2, $calls);
		self::assertSame(2, $this->begun);
		self::assertSame(1, $this->rolledBack);
		self::assertSame(1, $this->committed);
	}

	public function testTheThirdLockedAttemptThrowsUnchanged(): void {
		$lock = self::lock();
		$calls = 0;
		try {
			$this->transaction()->run(function () use (&$calls, $lock): string {
				$calls++;
				throw $lock;
			});
			self::fail('the lock of the last attempt has to surface');
		} catch (\RuntimeException $caught) {
			self::assertSame($lock, $caught);
		}

		self::assertSame(3, $calls);
		self::assertSame(3, $this->begun);
		self::assertSame(3, $this->rolledBack);
		self::assertSame(0, $this->committed);
	}

	public function testAnyOtherFailureIsNotRepeated(): void {
		$failure = new \RuntimeException('not a lock');
		$calls = 0;
		try {
			$this->transaction()->run(function () use (&$calls, $failure): string {
				$calls++;
				throw $failure;
			});
			self::fail('the failure has to surface unchanged');
		} catch (\RuntimeException $caught) {
			self::assertSame($failure, $caught);
		}

		self::assertSame(1, $calls);
		self::assertSame(1, $this->begun);
		self::assertSame(1, $this->rolledBack);
		self::assertSame(0, $this->committed);
	}

	public function testTheWrappedLockOfTheServerCountsAsALock(): void {
		// The app receives OCP\DB\Exception: the server wraps the Doctrine
		// lock and keeps it only as the reason.
		$wrapped = new class ('database is locked') extends DbException {
			public function getReason(): ?int {
				return self::REASON_LOCK_WAIT_TIMEOUT;
			}
		};
		$calls = 0;
		$result = $this->transaction()->run(function () use (&$calls, $wrapped): string {
			if (++$calls === 1) {
				throw $wrapped;
			}
			return 'done';
		});

		self::assertSame('done', $result);
		self::assertSame(2, $calls);
		self::assertSame(1, $this->rolledBack);
		self::assertSame(1, $this->committed);
	}
}
