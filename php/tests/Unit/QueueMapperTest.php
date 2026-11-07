<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Db\Job;
use OCA\PiiRedaction\Db\JobEventMapper;
use OCA\PiiRedaction\Db\JobMapper;
use OCA\PiiRedaction\Model\Lang;
use OCA\PiiRedaction\Model\Mode;
use OCA\PiiRedaction\Model\Reason;
use OCA\PiiRedaction\Model\Status;
use OCA\PiiRedaction\Model\Task;
use OCP\AppFramework\Utility\ITimeFactory;
use OCP\IDBConnection;
use OCP\Server;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\TestCase;

/**
 * The pull queue against the real database of the test instance.
 *
 * php.yml enables the app before the suite, so its migration has created the
 * pii_* tables (on SQLite there; the MariaDB leg of deploy-harp.yml covers
 * MySQL semantics end to end). Every test starts from empty tables and a clock
 * it moves itself: the mapper reads no other clock than ITimeFactory.
 */
#[CoversClass(JobMapper::class)]
#[CoversClass(JobEventMapper::class)]
final class QueueMapperTest extends TestCase {
	private IDBConnection $db;
	private int $now = 1_800_000_000;
	private JobMapper $mapper;
	private JobEventMapper $events;

	protected function setUp(): void {
		parent::setUp();
		$this->db = Server::get(IDBConnection::class);
		foreach (['pii_jobs', 'pii_job_events', 'pii_slot'] as $table) {
			self::assertTrue(
				$this->db->tableExists($table),
				"table {$table} is missing: php.yml has to enable the app before the suite",
			);
			$this->db->getQueryBuilder()->delete($table)->executeStatement();
		}

		$time = $this->createMock(ITimeFactory::class);
		$time->method('getTime')->willReturnCallback(fn (): int => $this->now);
		$this->mapper = new JobMapper($this->db, $time);
		$this->events = new JobEventMapper($this->db, $time);
	}

	protected function tearDown(): void {
		foreach (['pii_jobs', 'pii_job_events', 'pii_slot'] as $table) {
			$this->db->getQueryBuilder()->delete($table)->executeStatement();
		}
		parent::tearDown();
	}

	private function waiting(int $fileId, string $etag = 'etag-1'): Job {
		return $this->mapper->enqueue($fileId, 'alice', $etag, Mode::Redact, Lang::En);
	}

	private function reload(Job $job): Job {
		return $this->mapper->find($job->getId());
	}

	public function testANewJobWaitsWithoutLease(): void {
		$job = $this->reload($this->waiting(10));

		self::assertSame(Status::Queued, $job->getStatusEnum());
		self::assertSame(Task::Analyze, $job->getTaskEnum());
		self::assertSame(0, $job->getAttempts());
		self::assertSame(0, $job->getLeaseUntil());
		self::assertSame($this->now, $job->getCreatedAt());
	}

	public function testTwoWaitingJobsYieldExactlyOneClaimThenNothing(): void {
		$first = $this->waiting(10);
		$this->waiting(11);

		$claim = $this->mapper->claimNext();
		self::assertNotNull($claim);
		self::assertSame($first->getId(), $claim['job']->getId());
		self::assertSame(Status::Analyzing, $claim['job']->getStatusEnum());
		self::assertSame(JobMapper::LEASE_ANALYZE, $claim['lease']);
		self::assertSame(32, strlen($claim['token']));
		self::assertSame(1, $claim['job']->getAttempts());

		self::assertNull($this->mapper->claimNext(), 'a second job ran while the first held the slot');
	}

	public function testAnExpiredLeaseFreesTheJobAndCountsAnAttempt(): void {
		$job = $this->waiting(10);
		$first = $this->mapper->claimNext();
		self::assertNotNull($first);

		$this->now += JobMapper::LEASE_ANALYZE;
		$second = $this->mapper->claimNext();

		self::assertNotNull($second);
		self::assertSame($job->getId(), $second['job']->getId());
		self::assertSame(2, $second['job']->getAttempts());
		self::assertNotSame($first['token'], $second['token']);
	}

	public function testTheThirdHandOutWithoutAckEndsInRepeatedlyStuck(): void {
		$job = $this->waiting(10);
		for ($i = 1; $i <= JobMapper::MAX_ATTEMPTS; $i++) {
			$claim = $this->mapper->claimNext();
			self::assertNotNull($claim, "hand-out {$i} was refused");
			$this->now += JobMapper::LEASE_ANALYZE + 1;
		}

		self::assertNull($this->mapper->claimNext());

		$failed = $this->reload($job);
		self::assertSame(Status::Failed, $failed->getStatusEnum());
		self::assertSame(Reason::RepeatedlyStuck, $failed->getReasonEnum());
		self::assertSame(Task::Purge, $failed->getTaskEnum());

		// The slot is free again: the stuck job does not block the queue.
		$next = $this->waiting(11);
		$claim = $this->mapper->claimNext();
		self::assertNotNull($claim);
		// The stuck job now waits for its purge, which comes first.
		self::assertSame($job->getId(), $claim['job']->getId());
		self::assertSame(JobMapper::LEASE_PURGE, $claim['lease']);
		$claim = $this->mapper->claimNext();
		self::assertNotNull($claim);
		self::assertSame($next->getId(), $claim['job']->getId());
	}

	public function testApplyGoesBeforeAnalyze(): void {
		$this->waiting(10);
		$approved = $this->waiting(11);
		$approved->setStatus(Status::Approved->value);
		$approved->setTask(Task::Apply->value);
		$this->mapper->update($approved);

		$claim = $this->mapper->claimNext();

		self::assertNotNull($claim);
		self::assertSame($approved->getId(), $claim['job']->getId());
		self::assertSame(Status::Applying, $claim['job']->getStatusEnum());
		self::assertSame(JobMapper::LEASE_APPLY, $claim['lease']);
	}

	public function testPurgeRunsWhileTheSlotIsTaken(): void {
		$this->waiting(10);
		self::assertNotNull($this->mapper->claimNext());

		$done = $this->waiting(11);
		$done->setStatus(Status::Failed->value);
		$done->setTask(Task::Purge->value);
		$this->mapper->update($done);

		$purge = $this->mapper->claimNext();
		self::assertNotNull($purge);
		self::assertSame($done->getId(), $purge['job']->getId());
		self::assertSame(Task::Purge, $purge['job']->getTaskEnum());

		self::assertNull($this->mapper->claimNext(), 'the leased purge was handed out twice');
	}

	public function testReleaseWithAForeignTokenChangesNothing(): void {
		$this->waiting(10);
		$this->waiting(11);
		$claim = $this->mapper->claimNext();
		self::assertNotNull($claim);

		$this->mapper->release($claim['job'], str_repeat('0', 32));

		self::assertNull($this->mapper->claimNext());
		self::assertSame($claim['token'], $this->reload($claim['job'])->getClaimToken());
	}

	public function testReleaseWithTheOwnTokenFreesTheSlot(): void {
		$this->waiting(10);
		$second = $this->waiting(11);
		$claim = $this->mapper->claimNext();
		self::assertNotNull($claim);

		$this->mapper->release($claim['job'], $claim['token']);

		$next = $this->mapper->claimNext();
		self::assertNotNull($next);
		// The released job still says analyzing with an expired lease, but a
		// queued job comes before the expired-lease group.
		self::assertSame($second->getId(), $next['job']->getId());
	}

	public function testExtendLeaseNeedsTheOwnTokenAndALiveLease(): void {
		$this->waiting(10);
		$claim = $this->mapper->claimNext();
		self::assertNotNull($claim);

		self::assertFalse($this->mapper->extendLease($claim['job'], str_repeat('f', 32)));

		$this->now += 60;
		self::assertTrue($this->mapper->extendLease($claim['job'], $claim['token']));
		self::assertSame($this->now + JobMapper::LEASE_ANALYZE, $this->reload($claim['job'])->getLeaseUntil());

		// The extended slot lease holds a second job off past the first end.
		$this->waiting(11);
		$this->now += JobMapper::LEASE_ANALYZE - 1;
		self::assertNull($this->mapper->claimNext());

		$this->now += 2;
		self::assertFalse($this->mapper->extendLease($claim['job'], $claim['token']), 'an expired lease came back');
	}

	public function testAheadCountsWaitingJobsAndTheRunningOne(): void {
		$a = $this->waiting(10);
		$b = $this->waiting(11);
		$c = $this->waiting(12);

		self::assertSame(0, $this->mapper->ahead($a));
		self::assertSame(1, $this->mapper->ahead($b));
		self::assertSame(2, $this->mapper->ahead($c));

		self::assertNotNull($this->mapper->claimNext());

		self::assertSame(0, $this->mapper->ahead($a), 'the running job counted itself');
		self::assertSame(1, $this->mapper->ahead($b));
		self::assertSame(2, $this->mapper->ahead($c));
	}

	public function testFindOpenForMatchesOnlyTheSameEtag(): void {
		$job = $this->waiting(10, 'etag-1');

		$same = $this->mapper->findOpenFor(10, 'alice', 'etag-1');
		self::assertNotNull($same);
		self::assertSame($job->getId(), $same->getId());
		self::assertNull($this->mapper->findOpenFor(10, 'alice', 'etag-2'));
		self::assertNull($this->mapper->findOpenFor(10, 'bob', 'etag-1'));

		$job->setStatus(Status::Published->value);
		$this->mapper->update($job);
		self::assertNull($this->mapper->findOpenFor(10, 'alice', 'etag-1'), 'a finished job counted as open');
		self::assertSame([], $this->mapper->findOpenByFile(10));
	}

	public function testEnsureSlotIsIdempotent(): void {
		$this->mapper->ensureSlot();
		$this->mapper->ensureSlot();

		$qb = $this->db->getQueryBuilder();
		$qb->select($qb->func()->count('id'))->from('pii_slot');
		$result = $qb->executeQuery();
		$count = (int)$result->fetchOne();
		$result->closeCursor();
		self::assertSame(1, $count);
	}

	public function testAStoredWordOutsideTheListIsAnError(): void {
		$job = $this->waiting(10);
		$job->setStatus('unknown');
		$this->mapper->update($job);

		$this->expectException(\UnexpectedValueException::class);
		$this->reload($job)->getStatusEnum();
	}

	public function testEventsTakeOnlyWordsOfTheClosedLists(): void {
		$job = $this->waiting(10);
		$this->events->record($job->getId(), 'alice', Status::Queued->value);
		$this->events->record($job->getId(), 'alice', JobEventMapper::ACTION_PLACEHOLDER_REQUESTED);

		$recorded = $this->events->findForJob($job->getId());
		self::assertSame(['queued', 'placeholder_requested'], array_map(static fn ($e): string => $e->getAction(), $recorded));
		self::assertSame($this->now, $recorded[0]->getAt());

		$this->expectException(\InvalidArgumentException::class);
		$this->events->record($job->getId(), 'alice', 'secret.pdf');
	}
}
