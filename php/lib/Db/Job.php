<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Db;

use OCA\PiiRedaction\Model\Lang;
use OCA\PiiRedaction\Model\Mode;
use OCA\PiiRedaction\Model\Reason;
use OCA\PiiRedaction\Model\Stage;
use OCA\PiiRedaction\Model\Status;
use OCA\PiiRedaction\Model\Task;
use OCP\AppFramework\Db\Entity;

/**
 * One row of pii_jobs: ids, the etag, numbers and words from closed lists.
 * There is no field for a file name, a path, a mime type or text.
 *
 * @method int getFileId()
 * @method void setFileId(int $fileId)
 * @method string getInitiatorUid()
 * @method void setInitiatorUid(string $initiatorUid)
 * @method string getFileEtag()
 * @method void setFileEtag(string $fileEtag)
 * @method string getMode()
 * @method void setMode(string $mode)
 * @method string getLang()
 * @method void setLang(string $lang)
 * @method string getStatus()
 * @method void setStatus(string $status)
 * @method string|null getReason()
 * @method void setReason(?string $reason)
 * @method string|null getTask()
 * @method void setTask(?string $task)
 * @method string|null getStage()
 * @method void setStage(?string $stage)
 * @method int|null getPagesDone()
 * @method void setPagesDone(?int $pagesDone)
 * @method int|null getPagesTotal()
 * @method void setPagesTotal(?int $pagesTotal)
 * @method string|null getClaimToken()
 * @method void setClaimToken(?string $claimToken)
 * @method int getLeaseUntil()
 * @method void setLeaseUntil(int $leaseUntil)
 * @method int getAttempts()
 * @method void setAttempts(int $attempts)
 * @method int|null getRevision()
 * @method void setRevision(?int $revision)
 * @method string|null getRevisionHash()
 * @method void setRevisionHash(?string $revisionHash)
 * @method string|null getOutputSha256()
 * @method void setOutputSha256(?string $outputSha256)
 * @method int|null getOutputSize()
 * @method void setOutputSize(?int $outputSize)
 * @method int|null getOutputFileId()
 * @method void setOutputFileId(?int $outputFileId)
 * @method int|null getImageWidth()
 * @method void setImageWidth(?int $imageWidth)
 * @method int|null getImageHeight()
 * @method void setImageHeight(?int $imageHeight)
 * @method int getCreatedAt()
 * @method void setCreatedAt(int $createdAt)
 * @method int getUpdatedAt()
 * @method void setUpdatedAt(int $updatedAt)
 * @method int getExpiresAt()
 * @method void setExpiresAt(int $expiresAt)
 */
final class Job extends Entity {
	protected int $fileId = 0;
	protected string $initiatorUid = '';
	protected string $fileEtag = '';
	protected string $mode = '';
	protected string $lang = '';
	protected string $status = '';
	protected ?string $reason = null;
	protected ?string $task = null;
	protected ?string $stage = null;
	protected ?int $pagesDone = null;
	protected ?int $pagesTotal = null;
	protected ?string $claimToken = null;
	protected int $leaseUntil = 0;
	protected int $attempts = 0;
	protected ?int $revision = null;
	protected ?string $revisionHash = null;
	protected ?string $outputSha256 = null;
	protected ?int $outputSize = null;
	protected ?int $outputFileId = null;
	protected ?int $imageWidth = null;
	protected ?int $imageHeight = null;
	protected int $createdAt = 0;
	protected int $updatedAt = 0;
	protected int $expiresAt = 0;

	public function __construct() {
		$this->addType('fileId', 'integer');
		$this->addType('pagesDone', 'integer');
		$this->addType('pagesTotal', 'integer');
		$this->addType('leaseUntil', 'integer');
		$this->addType('attempts', 'integer');
		$this->addType('revision', 'integer');
		$this->addType('outputSize', 'integer');
		$this->addType('outputFileId', 'integer');
		$this->addType('imageWidth', 'integer');
		$this->addType('imageHeight', 'integer');
		$this->addType('createdAt', 'integer');
		$this->addType('updatedAt', 'integer');
		$this->addType('expiresAt', 'integer');
	}

	/**
	 * A stored word outside the closed list is an error, never passed on.
	 * The messages are static: the stored value itself is not repeated.
	 */
	public function getStatusEnum(): Status {
		return Status::tryFrom($this->status)
			?? throw new \UnexpectedValueException('pii_jobs.status holds a value outside the closed list');
	}

	public function getReasonEnum(): ?Reason {
		if ($this->reason === null) {
			return null;
		}
		return Reason::tryFrom($this->reason)
			?? throw new \UnexpectedValueException('pii_jobs.reason holds a value outside the closed list');
	}

	public function getTaskEnum(): ?Task {
		if ($this->task === null) {
			return null;
		}
		return Task::tryFrom($this->task)
			?? throw new \UnexpectedValueException('pii_jobs.task holds a value outside the closed list');
	}

	public function getStageEnum(): ?Stage {
		if ($this->stage === null) {
			return null;
		}
		return Stage::tryFrom($this->stage)
			?? throw new \UnexpectedValueException('pii_jobs.stage holds a value outside the closed list');
	}

	public function getModeEnum(): Mode {
		return Mode::tryFrom($this->mode)
			?? throw new \UnexpectedValueException('pii_jobs.mode holds a value outside the closed list');
	}

	public function getLangEnum(): Lang {
		return Lang::tryFrom($this->lang)
			?? throw new \UnexpectedValueException('pii_jobs.lang holds a value outside the closed list');
	}
}
