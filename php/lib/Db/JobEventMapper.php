<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Db;

use OCA\PiiRedaction\Model\Status;
use OCA\PiiRedaction\Model\Subject;
use OCP\AppFramework\Db\QBMapper;
use OCP\AppFramework\Utility\ITimeFactory;
use OCP\DB\QueryBuilder\IQueryBuilder;
use OCP\IDBConnection;

/**
 * @template-extends QBMapper<JobEvent>
 */
final class JobEventMapper extends QBMapper {
	public const TABLE_NAME = 'pii_job_events';

	/** The one action that is neither a state nor a notification subject. */
	public const ACTION_PLACEHOLDER_REQUESTED = 'placeholder_requested';

	public function __construct(
		IDBConnection $db,
		private ITimeFactory $time,
	) {
		parent::__construct($db, self::TABLE_NAME, JobEvent::class);
	}

	/**
	 * Records one event. Only words of the closed lists get in, so the column
	 * can never carry a name or a message.
	 */
	public function record(int $jobId, string $uid, string $action): void {
		if (!self::isAllowedAction($action)) {
			throw new \InvalidArgumentException('job event action outside the closed lists');
		}
		$event = new JobEvent();
		$event->setJobId($jobId);
		$event->setUid($uid);
		$event->setAction($action);
		$event->setAt($this->time->getTime());
		$this->insert($event);
	}

	public static function isAllowedAction(string $action): bool {
		return $action === self::ACTION_PLACEHOLDER_REQUESTED
			|| Status::tryFrom($action) !== null
			|| Subject::tryFrom($action) !== null;
	}

	/**
	 * @return list<JobEvent>
	 */
	public function findForJob(int $jobId): array {
		$qb = $this->db->getQueryBuilder();
		$qb->select('*')
			->from(self::TABLE_NAME)
			->where($qb->expr()->eq('job_id', $qb->createNamedParameter($jobId, IQueryBuilder::PARAM_INT)))
			->orderBy('id', 'ASC');
		return $this->findEntities($qb);
	}
}
