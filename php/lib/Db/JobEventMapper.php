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

	/** The placeholder PDF was asked for (phase 1). */
	public const ACTION_PLACEHOLDER_REQUESTED = 'placeholder_requested';
	/** A signed PDF was found and the user was told the signature is lost (D-02-04). */
	public const ACTION_SIGNATURE_NOTICE = 'signature_notice';
	/** The user confirmed the loss of the signature (D-02-04). */
	public const ACTION_SIGNATURE_CONFIRMED = 'signature_confirmed';
	/** Macros were removed from the copy LibreOffice reads (D-02-12). */
	public const ACTION_MACROS_REMOVED = 'macros_removed';
	/** External links were removed from that copy (D-02-12). */
	public const ACTION_EXTERNAL_LINKS_REMOVED = 'external_links_removed';
	/** The owner password of a PDF was dropped for the copy (D-02-10). */
	public const ACTION_OWNER_PROTECTION_DROPPED = 'owner_protection_dropped';

	/**
	 * The actions that are neither a state nor a notification subject. Only
	 * words, never a name or a message.
	 */
	private const ACTIONS = [
		self::ACTION_PLACEHOLDER_REQUESTED,
		self::ACTION_SIGNATURE_NOTICE,
		self::ACTION_SIGNATURE_CONFIRMED,
		self::ACTION_MACROS_REMOVED,
		self::ACTION_EXTERNAL_LINKS_REMOVED,
		self::ACTION_OWNER_PROTECTION_DROPPED,
	];

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
		return in_array($action, self::ACTIONS, true)
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
