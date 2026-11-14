<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Db;

use OCA\PiiRedaction\Model\Lang;
use OCA\PiiRedaction\Model\Mode;
use OCA\PiiRedaction\Model\Reason;
use OCA\PiiRedaction\Model\Stage;
use OCA\PiiRedaction\Model\Status;
use OCA\PiiRedaction\Model\Task;
use OCP\AppFramework\Db\QBMapper;
use OCP\AppFramework\Utility\ITimeFactory;
use OCP\DB\Exception as DbException;
use OCP\DB\QueryBuilder\IQueryBuilder;
use OCP\IDBConnection;

/**
 * The job table and the pull queue on top of it (Findling QueueMapper,
 * reduced to one job at a time).
 *
 * The container asks for work; nobody pushes anything into it. A claim is a
 * conditional UPDATE that repeats the "free" condition in its WHERE and sets
 * a random token; whoever reads that token back has won. There is no row lock
 * and no self-referencing subquery (MySQL refuses those in an UPDATE, error
 * 1093), so the same code holds on SQLite, MySQL/MariaDB and PostgreSQL.
 *
 * "One analyze or apply job at a time" is the single row of pii_slot: the
 * first UPDATE of a claim takes the slot only where its lease has run out.
 * Purge jobs only delete container state and do not take the slot.
 *
 * The only clock is ITimeFactory::getTime(), so tests can move it.
 *
 * @template-extends QBMapper<Job>
 */
final class JobMapper extends QBMapper {
	public const TABLE_NAME = 'pii_jobs';
	public const SLOT_TABLE = 'pii_slot';
	public const SLOT_ID = 1;

	// Lease lengths in seconds and the attempt cap: provisional, phase 8 sets
	// the values after measuring (pages times seconds per page plus cold start).
	public const LEASE_ANALYZE = 120;
	public const LEASE_APPLY = 300;
	public const LEASE_PURGE = 60;
	public const MAX_ATTEMPTS = 3;

	/** Upper bound of candidates one claim looks at before it gives up. */
	private const MAX_CANDIDATES = 50;

	public function __construct(
		IDBConnection $db,
		private ITimeFactory $time,
	) {
		parent::__construct($db, self::TABLE_NAME, Job::class);
	}

	public function find(int $id): Job {
		$qb = $this->db->getQueryBuilder();
		$qb->select('*')
			->from(self::TABLE_NAME)
			->where($qb->expr()->eq('id', $qb->createNamedParameter($id, IQueryBuilder::PARAM_INT)));
		return $this->findEntity($qb);
	}

	public function enqueue(int $fileId, string $uid, string $etag, Mode $mode, Lang $lang): Job {
		$now = $this->time->getTime();
		$job = new Job();
		$job->setFileId($fileId);
		$job->setInitiatorUid($uid);
		$job->setFileEtag($etag);
		$job->setMode($mode->value);
		$job->setLang($lang->value);
		$job->setStatus(Status::Queued->value);
		$job->setTask(Task::Analyze->value);
		$job->setStage(Stage::Waiting->value);
		$job->setAttempts(0);
		$job->setLeaseUntil(0);
		$job->setCreatedAt($now);
		$job->setUpdatedAt($now);
		// Phase 1 enforces no retention yet; a later phase only has to start
		// reading the column. 0 equals the entity default, so the INSERT skips
		// it and the database default 0 of the migration fills it.
		$job->setExpiresAt(0);
		return $this->insert($job);
	}

	/**
	 * The open job of this user on this file and this etag, if any: a second
	 * start returns it instead of creating a twin (RESEARCH Pitfall K).
	 */
	public function findOpenFor(int $fileId, string $uid, string $etag): ?Job {
		$qb = $this->db->getQueryBuilder();
		$qb->select('*')
			->from(self::TABLE_NAME)
			->where($qb->expr()->eq('file_id', $qb->createNamedParameter($fileId, IQueryBuilder::PARAM_INT)))
			->andWhere($qb->expr()->eq('initiator_uid', $qb->createNamedParameter($uid)))
			->andWhere($qb->expr()->eq('file_etag', $qb->createNamedParameter($etag)))
			->andWhere($qb->expr()->in('status', $qb->createNamedParameter(Status::openValues(), IQueryBuilder::PARAM_STR_ARRAY)))
			->orderBy('id', 'ASC')
			->setMaxResults(1);
		$jobs = $this->findEntities($qb);
		return $jobs[0] ?? null;
	}

	/**
	 * Every open job on a file, of any user: the file listener marks them
	 * stale or cancelled when the file is written or deleted.
	 *
	 * @return list<Job>
	 */
	public function findOpenByFile(int $fileId): array {
		$qb = $this->db->getQueryBuilder();
		$qb->select('*')
			->from(self::TABLE_NAME)
			->where($qb->expr()->eq('file_id', $qb->createNamedParameter($fileId, IQueryBuilder::PARAM_INT)))
			->andWhere($qb->expr()->in('status', $qb->createNamedParameter(Status::openValues(), IQueryBuilder::PARAM_STR_ARRAY)))
			->orderBy('id', 'ASC');
		return $this->findEntities($qb);
	}

	/**
	 * Inserts the one slot row. A second insert violates the primary key and
	 * is swallowed, so this is safe to call before every claim.
	 */
	public function ensureSlot(): void {
		// Look first: on PostgreSQL a failed statement inside a caller's
		// transaction would abort that transaction, so the insert is the
		// exception, not the rule.
		$probe = $this->db->getQueryBuilder();
		$probe->select($probe->func()->count('id'))
			->from(self::SLOT_TABLE)
			->where($probe->expr()->eq('id', $probe->createNamedParameter(self::SLOT_ID, IQueryBuilder::PARAM_INT)));
		if ($this->countFrom($probe) > 0) {
			return;
		}

		$qb = $this->db->getQueryBuilder();
		$qb->insert(self::SLOT_TABLE)
			->values([
				'id' => $qb->createNamedParameter(self::SLOT_ID, IQueryBuilder::PARAM_INT),
				'lease_until' => $qb->createNamedParameter(0, IQueryBuilder::PARAM_INT),
			]);
		try {
			$qb->executeStatement();
		} catch (DbException $e) {
			if ($e->getReason() !== DbException::REASON_UNIQUE_CONSTRAINT_VIOLATION) {
				throw $e;
			}
		}
	}

	/**
	 * Hands out at most one task: purge first (beside the slot), then apply
	 * before analyze, then jobs whose lease ran out, each in id order.
	 *
	 * @return array{job: Job, token: string, lease: int}|null
	 */
	public function claimNext(): ?array {
		$now = $this->time->getTime();
		$token = self::newToken();

		$purge = $this->claimPurge($now, $token);
		if ($purge !== null) {
			return $purge;
		}

		// Read before any write: the container asks every one to ten
		// seconds, and an empty queue must cost reads only (on SQLite every
		// write competes with the logins of the instance). A candidate that
		// a parallel caller takes meanwhile is handled below as before.
		if ($this->nextCandidate($now) === null) {
			return null;
		}

		$this->ensureSlot();
		if (!$this->takeSlot($now, $token)) {
			return null;
		}

		for ($round = 0; $round < self::MAX_CANDIDATES; $round++) {
			$candidate = $this->nextCandidate($now);
			if ($candidate === null) {
				break;
			}
			if ($candidate->getAttempts() >= self::MAX_ATTEMPTS) {
				$this->giveUp($candidate, $now);
				continue;
			}
			$claimed = $this->claimJob($candidate, $now, $token);
			if ($claimed !== null) {
				return $claimed;
			}
			// Lost to a parallel caller on the job row; that caller cannot
			// hold the slot as well, so the next candidate is tried.
		}

		$this->freeSlot($token);
		return null;
	}

	/**
	 * Extends the lease of a running task, only with the token of the claim
	 * and only while the lease is still alive. An expired lease stays expired:
	 * the job may already belong to the next claim.
	 */
	public function extendLease(Job $job, string $token): bool {
		$now = $this->time->getTime();
		$until = $now + self::leaseFor($job->getTaskEnum());

		$qb = $this->db->getQueryBuilder();
		$qb->update(self::TABLE_NAME)
			->set('lease_until', $qb->createNamedParameter($until, IQueryBuilder::PARAM_INT))
			->set('updated_at', $qb->createNamedParameter($now, IQueryBuilder::PARAM_INT))
			->where($qb->expr()->eq('id', $qb->createNamedParameter($job->getId(), IQueryBuilder::PARAM_INT)))
			->andWhere($qb->expr()->eq('claim_token', $qb->createNamedParameter($token)))
			->andWhere($qb->expr()->gt('lease_until', $qb->createNamedParameter($now, IQueryBuilder::PARAM_INT)));
		if ($qb->executeStatement() !== 1) {
			return false;
		}

		$slot = $this->db->getQueryBuilder();
		$slot->update(self::SLOT_TABLE)
			->set('lease_until', $slot->createNamedParameter($until, IQueryBuilder::PARAM_INT))
			->where($slot->expr()->eq('id', $slot->createNamedParameter(self::SLOT_ID, IQueryBuilder::PARAM_INT)))
			->andWhere($slot->expr()->eq('claim_token', $slot->createNamedParameter($token)))
			->andWhere($slot->expr()->gt('lease_until', $slot->createNamedParameter($now, IQueryBuilder::PARAM_INT)));
		// A purge task holds no slot, so zero rows here is no failure.
		$slot->executeStatement();

		$job->setLeaseUntil($until);
		return true;
	}

	/**
	 * Gives the slot and the job row back, only with the token of the claim:
	 * a foreign token changes nothing.
	 */
	public function release(Job $job, string $token): void {
		$this->freeSlot($token);

		$qb = $this->db->getQueryBuilder();
		$qb->update(self::TABLE_NAME)
			->set('claim_token', $qb->createNamedParameter(null, IQueryBuilder::PARAM_NULL))
			->set('lease_until', $qb->createNamedParameter(0, IQueryBuilder::PARAM_INT))
			->where($qb->expr()->eq('id', $qb->createNamedParameter($job->getId(), IQueryBuilder::PARAM_INT)))
			->andWhere($qb->expr()->eq('claim_token', $qb->createNamedParameter($token)));
		if ($qb->executeStatement() === 1) {
			$job->setClaimToken(null);
			$job->setLeaseUntil(0);
		}
	}

	/**
	 * The real position in the queue: waiting analyze jobs with a smaller id,
	 * plus one when another job holds a live lease on the slot.
	 */
	public function ahead(Job $job): int {
		$now = $this->time->getTime();

		$qb = $this->db->getQueryBuilder();
		$qb->select($qb->func()->count('id'))
			->from(self::TABLE_NAME)
			->where($qb->expr()->eq('status', $qb->createNamedParameter(Status::Queued->value)))
			->andWhere($qb->expr()->eq('task', $qb->createNamedParameter(Task::Analyze->value)))
			->andWhere($qb->expr()->lt('id', $qb->createNamedParameter($job->getId(), IQueryBuilder::PARAM_INT)));
		$count = $this->countFrom($qb);

		$slot = $this->db->getQueryBuilder();
		$slot->select($slot->func()->count('id'))
			->from(self::SLOT_TABLE)
			->where($slot->expr()->eq('id', $slot->createNamedParameter(self::SLOT_ID, IQueryBuilder::PARAM_INT)))
			->andWhere($slot->expr()->gt('lease_until', $slot->createNamedParameter($now, IQueryBuilder::PARAM_INT)))
			->andWhere($slot->expr()->isNotNull('job_id'))
			->andWhere($slot->expr()->neq('job_id', $slot->createNamedParameter($job->getId(), IQueryBuilder::PARAM_INT)));

		return $count + ($this->countFrom($slot) > 0 ? 1 : 0);
	}

	/**
	 * @return array{job: Job, token: string, lease: int}|null
	 */
	private function claimPurge(int $now, string $token): ?array {
		for ($round = 0; $round < self::MAX_CANDIDATES; $round++) {
			$qb = $this->db->getQueryBuilder();
			$qb->select('*')
				->from(self::TABLE_NAME)
				->where($qb->expr()->eq('task', $qb->createNamedParameter(Task::Purge->value)))
				->andWhere($qb->expr()->lte('lease_until', $qb->createNamedParameter($now, IQueryBuilder::PARAM_INT)))
				->orderBy('id', 'ASC')
				->setMaxResults(1);
			$candidates = $this->findEntities($qb);
			if ($candidates === []) {
				return null;
			}
			$candidate = $candidates[0];

			$claim = $this->db->getQueryBuilder();
			$claim->update(self::TABLE_NAME)
				->set('claim_token', $claim->createNamedParameter($token))
				->set('lease_until', $claim->createNamedParameter($now + self::LEASE_PURGE, IQueryBuilder::PARAM_INT))
				->set('updated_at', $claim->createNamedParameter($now, IQueryBuilder::PARAM_INT))
				->where($claim->expr()->eq('id', $claim->createNamedParameter($candidate->getId(), IQueryBuilder::PARAM_INT)))
				->andWhere($claim->expr()->eq('task', $claim->createNamedParameter(Task::Purge->value)))
				->andWhere($claim->expr()->lte('lease_until', $claim->createNamedParameter($now, IQueryBuilder::PARAM_INT)));
			if ($claim->executeStatement() !== 1) {
				continue;
			}
			$won = $this->readBack($candidate->getId(), $token);
			if ($won !== null) {
				return ['job' => $won, 'token' => $token, 'lease' => self::LEASE_PURGE];
			}
		}
		return null;
	}

	/**
	 * The one conditional UPDATE that decides "one at a time".
	 */
	private function takeSlot(int $now, string $token): bool {
		$qb = $this->db->getQueryBuilder();
		$qb->update('pii_slot')
			->set('job_id', $qb->createNamedParameter(null, IQueryBuilder::PARAM_NULL))
			->set('claim_token', $qb->createNamedParameter($token))
			->set('lease_until', $qb->createNamedParameter($now + self::LEASE_APPLY, IQueryBuilder::PARAM_INT))
			->where($qb->expr()->eq('id', $qb->createNamedParameter(self::SLOT_ID, IQueryBuilder::PARAM_INT)))
			->andWhere($qb->expr()->lte('lease_until', $qb->createNamedParameter($now, IQueryBuilder::PARAM_INT)));
		return $qb->executeStatement() === 1;
	}

	private function freeSlot(string $token): void {
		$qb = $this->db->getQueryBuilder();
		$qb->update(self::SLOT_TABLE)
			->set('job_id', $qb->createNamedParameter(null, IQueryBuilder::PARAM_NULL))
			->set('claim_token', $qb->createNamedParameter(null, IQueryBuilder::PARAM_NULL))
			->set('lease_until', $qb->createNamedParameter(0, IQueryBuilder::PARAM_INT))
			->where($qb->expr()->eq('id', $qb->createNamedParameter(self::SLOT_ID, IQueryBuilder::PARAM_INT)))
			->andWhere($qb->expr()->eq('claim_token', $qb->createNamedParameter($token)));
		$qb->executeStatement();
	}

	/**
	 * apply (approved) before analyze (queued), then expired leases of
	 * running jobs; first in id order within each group.
	 */
	private function nextCandidate(int $now): ?Job {
		$groups = [
			[[Task::Apply->value], [Status::Approved->value]],
			[[Task::Analyze->value], [Status::Queued->value]],
			[[Task::Analyze->value, Task::Apply->value], [Status::Analyzing->value, Status::Applying->value]],
		];
		foreach ($groups as [$tasks, $states]) {
			$qb = $this->db->getQueryBuilder();
			$qb->select('*')
				->from(self::TABLE_NAME)
				->where($qb->expr()->in('task', $qb->createNamedParameter($tasks, IQueryBuilder::PARAM_STR_ARRAY)))
				->andWhere($qb->expr()->in('status', $qb->createNamedParameter($states, IQueryBuilder::PARAM_STR_ARRAY)))
				->andWhere($qb->expr()->lte('lease_until', $qb->createNamedParameter($now, IQueryBuilder::PARAM_INT)))
				->orderBy('id', 'ASC')
				->setMaxResults(1);
			$jobs = $this->findEntities($qb);
			if ($jobs !== []) {
				return $jobs[0];
			}
		}
		return null;
	}

	/**
	 * @return array{job: Job, token: string, lease: int}|null
	 */
	private function claimJob(Job $candidate, int $now, string $token): ?array {
		$task = $candidate->getTaskEnum();
		$running = $task === Task::Apply ? Status::Applying : Status::Analyzing;
		$lease = self::leaseFor($task);

		$qb = $this->db->getQueryBuilder();
		$qb->update(self::TABLE_NAME)
			->set('claim_token', $qb->createNamedParameter($token))
			->set('lease_until', $qb->createNamedParameter($now + $lease, IQueryBuilder::PARAM_INT))
			->set('attempts', $qb->createFunction('attempts + 1'))
			->set('status', $qb->createNamedParameter($running->value))
			->set('stage', $qb->createNamedParameter(Stage::Waiting->value))
			->set('updated_at', $qb->createNamedParameter($now, IQueryBuilder::PARAM_INT))
			->where($qb->expr()->eq('id', $qb->createNamedParameter($candidate->getId(), IQueryBuilder::PARAM_INT)))
			->andWhere($qb->expr()->eq('status', $qb->createNamedParameter($candidate->getStatus())))
			->andWhere($qb->expr()->lte('lease_until', $qb->createNamedParameter($now, IQueryBuilder::PARAM_INT)));
		if ($qb->executeStatement() !== 1) {
			return null;
		}

		$won = $this->readBack($candidate->getId(), $token);
		if ($won === null) {
			return null;
		}

		$slot = $this->db->getQueryBuilder();
		$slot->update(self::SLOT_TABLE)
			->set('job_id', $slot->createNamedParameter($won->getId(), IQueryBuilder::PARAM_INT))
			->set('lease_until', $slot->createNamedParameter($now + $lease, IQueryBuilder::PARAM_INT))
			->where($slot->expr()->eq('id', $slot->createNamedParameter(self::SLOT_ID, IQueryBuilder::PARAM_INT)))
			->andWhere($slot->expr()->eq('claim_token', $slot->createNamedParameter($token)));
		$slot->executeStatement();

		return ['job' => $won, 'token' => $token, 'lease' => $lease];
	}

	/**
	 * Three hand-outs without an ack: the job fails as repeatedly_stuck and
	 * goes to purge. The conditions repeat the candidate state, so a job a
	 * parallel caller just claimed is left alone.
	 */
	private function giveUp(Job $candidate, int $now): void {
		$qb = $this->db->getQueryBuilder();
		$qb->update(self::TABLE_NAME)
			->set('status', $qb->createNamedParameter(Status::Failed->value))
			->set('reason', $qb->createNamedParameter(Reason::RepeatedlyStuck->value))
			->set('task', $qb->createNamedParameter(Task::Purge->value))
			->set('claim_token', $qb->createNamedParameter(null, IQueryBuilder::PARAM_NULL))
			->set('lease_until', $qb->createNamedParameter(0, IQueryBuilder::PARAM_INT))
			->set('updated_at', $qb->createNamedParameter($now, IQueryBuilder::PARAM_INT))
			->where($qb->expr()->eq('id', $qb->createNamedParameter($candidate->getId(), IQueryBuilder::PARAM_INT)))
			->andWhere($qb->expr()->eq('status', $qb->createNamedParameter($candidate->getStatus())))
			->andWhere($qb->expr()->lte('lease_until', $qb->createNamedParameter($now, IQueryBuilder::PARAM_INT)));
		$qb->executeStatement();
	}

	private function readBack(int $id, string $token): ?Job {
		$qb = $this->db->getQueryBuilder();
		$qb->select('*')
			->from(self::TABLE_NAME)
			->where($qb->expr()->eq('id', $qb->createNamedParameter($id, IQueryBuilder::PARAM_INT)))
			->andWhere($qb->expr()->eq('claim_token', $qb->createNamedParameter($token)));
		$jobs = $this->findEntities($qb);
		return $jobs[0] ?? null;
	}

	private static function leaseFor(?Task $task): int {
		return match ($task) {
			Task::Apply => self::LEASE_APPLY,
			Task::Purge => self::LEASE_PURGE,
			default => self::LEASE_ANALYZE,
		};
	}

	/** 128 random bits as hex: the claim token of job row and slot. */
	private static function newToken(): string {
		return bin2hex(random_bytes(16));
	}

	private function countFrom(IQueryBuilder $qb): int {
		$result = $qb->executeQuery();
		$count = $result->fetchOne();
		$result->closeCursor();
		return is_numeric($count) ? (int)$count : 0;
	}
}
