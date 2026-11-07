<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Db;

use OCP\AppFramework\Db\Entity;

/**
 * One row of pii_job_events: who did what to which job, and when. The action
 * is a word from Status, Subject or placeholder_requested (JobEventMapper).
 *
 * @method int getJobId()
 * @method void setJobId(int $jobId)
 * @method string getUid()
 * @method void setUid(string $uid)
 * @method string getAction()
 * @method void setAction(string $action)
 * @method int getAt()
 * @method void setAt(int $at)
 */
final class JobEvent extends Entity {
	protected int $jobId = 0;
	protected string $uid = '';
	protected string $action = '';
	protected int $at = 0;

	public function __construct() {
		$this->addType('jobId', 'integer');
		$this->addType('at', 'integer');
	}
}
