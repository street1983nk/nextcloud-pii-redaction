<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Service;

use OCA\PiiRedaction\Db\Job;
use OCA\PiiRedaction\Db\JobEventMapper;
use OCA\PiiRedaction\Db\JobMapper;
use OCA\PiiRedaction\Db\RetriedTransaction;
use OCA\PiiRedaction\Model\Lang;
use OCA\PiiRedaction\Model\Mode;
use OCA\PiiRedaction\Model\Reason;
use OCA\PiiRedaction\Model\Recheck;
use OCA\PiiRedaction\Model\Stage;
use OCA\PiiRedaction\Model\Status;
use OCA\PiiRedaction\Model\Subject;
use OCA\PiiRedaction\Model\Task;
use OCP\AppFramework\Db\DoesNotExistException;
use OCP\AppFramework\Utility\ITimeFactory;
use OCP\Files\File;
use OCP\IDBConnection;
use OCP\IUserManager;
use OCP\L10N\IFactory as IL10NFactory;
use Psr\Log\LoggerInterface;

/**
 * The user side of a job and the one place that changes its state
 * (01-SKELETON.md "Zustandsübergänge").
 *
 * Every transition checks the state it starts from, stamps updated_at with
 * the one clock, records an event, gives a held lease back, sends the
 * notification of the skeleton and, after an end state, hands the job to
 * the purge task. A job stores the file id, the etag, the initiator, the
 * mode and the language; never a name, a path or a mime type.
 */
final class JobService {
	/** The formats of phase 1, by the mime type Nextcloud reports. */
	public const ALLOWED_MIMES = [
		'application/pdf',
		'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
		'application/vnd.oasis.opendocument.text',
	];

	/** The word the container expects for each allowed mime type (plan 02-15). */
	private const FORMATS = [
		'application/pdf' => 'pdf',
		'application/vnd.openxmlformats-officedocument.wordprocessingml.document' => 'docx',
		'application/vnd.oasis.opendocument.text' => 'odt',
	];

	public function __construct(
		private JobMapper $jobs,
		private JobEventMapper $events,
		private FileAccess $files,
		private ExAppService $exApp,
		private NotificationSender $notifications,
		private IDBConnection $db,
		private ITimeFactory $time,
		private IL10NFactory $l10nFactory,
		private IUserManager $userManager,
		private LoggerInterface $logger,
	) {
	}

	// -- start and view ----------------------------------------------------------

	/**
	 * Starts a job on $fileId for $uid, or returns the open one on the same
	 * file, etag and user. $precheck is the answer of
	 * FileAccess::recheckForStart when the caller already asked it.
	 *
	 * @param array{0: Recheck, 1: ?File}|null $precheck
	 * @return array{job: ?Job, created: bool, ahead: int, reason: ?Reason}
	 */
	public function start(string $uid, int $fileId, ?array $precheck = null): array {
		if (!$this->exApp->startAllowed()) {
			return self::refused(Reason::BackendUnavailable);
		}

		[$verdict, $file] = $precheck ?? $this->files->recheckForStart($uid, $fileId);
		if ($verdict === Recheck::DownloadBlocked) {
			return self::refused(Reason::DownloadBlocked);
		}
		if ($verdict !== Recheck::Ok || $file === null) {
			return self::refused(Reason::NotReadable);
		}

		try {
			$mime = $file->getMimetype();
			$etag = $file->getEtag();
		} catch (\Throwable $e) {
			$this->logger->warning('PII Redaction: file facts not readable at start', ['fileId' => $fileId, 'class' => $e::class]);
			return self::refused(Reason::NotReadable);
		}
		if (!in_array($mime, self::ALLOWED_MIMES, true)) {
			return self::refused(Reason::UnsupportedFormat);
		}
		// The server holds only cipher text below an E2E folder (JOB-05); no
		// notification for a refusal (D-02-02), the toast says it.
		if ($this->files->inE2eFolder($file)) {
			return self::refused(Reason::E2eEncrypted);
		}
		if ($etag === '' || strlen($etag) > 40) {
			// The column holds 40 characters and the container refuses longer
			// ones; a file without a usable etag cannot be bound to a job.
			return self::refused(Reason::NotReadable);
		}

		// The transaction reads first and writes after; on SQLite a writer in
		// between (cron placing a copy, the container claiming work) locks it
		// out at once, so a lock rolls back and runs the whole closure again
		// (CI run 43667132427). findOpenFor answers anew on every attempt.
		$created = false;
		$transaction = new RetriedTransaction($this->db, $this->logger);
		/** @var Job $job */
		$job = $transaction->run(function () use ($fileId, $uid, $etag, &$created): Job {
			$created = false;
			$open = $this->jobs->findOpenFor($fileId, $uid, $etag);
			if ($open !== null) {
				return $open;
			}
			$job = $this->jobs->enqueue($fileId, $uid, $etag, Mode::Redact, $this->languageOf($uid));
			$this->events->record($job->getId(), $uid, Status::Queued->value);
			$created = true;
			return $job;
		});

		$ahead = $job->getStatusEnum() === Status::Queued ? $this->jobs->ahead($job) : 0;
		return ['job' => $job, 'created' => $created, 'ahead' => $ahead, 'reason' => null];
	}

	/**
	 * What the initiator may see of a job, or null when the job is not
	 * there, not theirs, or the file is no longer readable for them. The
	 * three cases are one answer, so nothing can be told apart from outside.
	 *
	 * @return array{jobId: int, fileId: int, status: string, stage: ?string, reason: ?string, ahead: ?int, pagesDone: ?int, pagesTotal: ?int, backendReady: bool, outputFileId: ?int, outputName: ?string, fileName: ?string, createdAt: int, image: ?array{width: int, height: int}, recheck: string, macrosRemoved: bool, signatureConfirmed: bool}|null
	 */
	public function view(int $jobId, string $uid, ?Recheck $known = null): ?array {
		$job = $this->forMember($jobId, $uid);
		if ($job === null) {
			return null;
		}
		$verdict = $known ?? $this->recheckJob($job, $uid);
		if ($verdict === Recheck::Missing) {
			return null;
		}
		$this->catchUpGiveUp($job);

		$status = $job->getStatusEnum();
		$width = $job->getImageWidth();
		$height = $job->getImageHeight();
		$outputFileId = $job->getOutputFileId();

		return [
			'jobId' => $job->getId(),
			'fileId' => $job->getFileId(),
			'status' => $status->value,
			'stage' => $job->getStage(),
			'reason' => $job->getReason(),
			'ahead' => $status === Status::Queued ? $this->jobs->ahead($job) : null,
			'pagesDone' => $job->getPagesDone(),
			'pagesTotal' => $job->getPagesTotal(),
			'backendReady' => $this->exApp->startAllowed(),
			'outputFileId' => $outputFileId,
			'outputName' => $outputFileId !== null ? $this->nameOf($uid, $outputFileId) : null,
			'fileName' => $this->nameOf($uid, $job->getFileId()),
			'createdAt' => $job->getCreatedAt(),
			'image' => $width !== null && $height !== null ? ['width' => $width, 'height' => $height] : null,
			'recheck' => $verdict->value,
			// D-02-12 and D-02-04: both live only as events of the job.
			'macrosRemoved' => $this->events->hasAction($job->getId(), JobEventMapper::ACTION_MACROS_REMOVED),
			'signatureConfirmed' => $this->events->hasAction($job->getId(), JobEventMapper::ACTION_SIGNATURE_CONFIRMED),
		];
	}

	/**
	 * The job when $uid started it, otherwise null (also for an unknown id).
	 */
	public function forMember(int $jobId, string $uid): ?Job {
		if ($jobId <= 0 || $uid === '') {
			return null;
		}
		try {
			$job = $this->jobs->find($jobId);
		} catch (DoesNotExistException) {
			return null;
		}
		return $job->getInitiatorUid() === $uid ? $job : null;
	}

	/**
	 * The recheck of a job for its initiator, with the etag stored at the
	 * start; null when $uid is not the initiator. A changed file turns an
	 * open job stale on the spot.
	 */
	public function recheckMember(int $jobId, string $uid): ?Recheck {
		$job = $this->forMember($jobId, $uid);
		return $job === null ? null : $this->recheckJob($job, $uid);
	}

	/**
	 * The format word of an allowed mime type, or null for any other.
	 */
	public static function formatOf(string $mime): ?string {
		return in_array($mime, self::ALLOWED_MIMES, true) ? self::FORMATS[$mime] : null;
	}

	/**
	 * What the claim of an analyze task tells the container: the format the
	 * file should have (from the mime type Nextcloud reports now, null when
	 * the file is gone or of another type) and whether the initiator already
	 * confirmed the loss of a signature (the event signature_confirmed).
	 *
	 * @return array{expected: ?string, confirmed: bool}
	 */
	public function claimFacts(Job $job): array {
		$file = $this->files->resolve($job->getInitiatorUid(), $job->getFileId());
		$expected = null;
		if ($file !== null) {
			try {
				$expected = self::formatOf($file->getMimetype());
			} catch (\Throwable $e) {
				$this->logger->warning('PII Redaction: mime type not readable at claim', ['jobId' => $job->getId(), 'class' => $e::class]);
			}
		}
		return [
			'expected' => $expected,
			'confirmed' => $this->events->hasAction($job->getId(), JobEventMapper::ACTION_SIGNATURE_CONFIRMED),
		];
	}

	// -- transitions ---------------------------------------------------------------

	public function toReview(Job $job, int $pagesTotal, int $imageWidth, int $imageHeight): void {
		$this->expect($job, Status::Analyzing);
		$job->setStatus(Status::Review->value);
		$job->setReason(null);
		$job->setTask(null);
		$job->setStage(Stage::Done->value);
		$job->setPagesTotal($pagesTotal);
		$job->setPagesDone($pagesTotal);
		$job->setImageWidth($imageWidth);
		$job->setImageHeight($imageHeight);
		// A later apply run counts its own hand-outs (plan 02 note).
		$job->setAttempts(0);
		$this->finish($job, Status::Review, $job->getInitiatorUid(), Subject::ReviewReady);
	}

	/**
	 * The job ends as failed and goes to the purge task. An error sends
	 * job_failed; a refusal of the pre-check sends nothing, the file card
	 * names the reason (D-02-02).
	 */
	public function toFailed(Job $job, Reason $reason): void {
		$this->expectOpen($job);
		$job->setStatus(Status::Failed->value);
		$job->setReason($reason->value);
		$job->setTask(Task::Purge->value);
		$refused = $reason->isPrecheckRefusal();
		$this->finish($job, Status::Failed, $job->getInitiatorUid(), $refused ? null : Subject::JobFailed);
		if ($refused) {
			// As for a cancelled job: no older notification of this job may
			// stay and announce a review that will not come.
			$this->notifications->dismiss($job);
		}
	}

	public function toStale(Job $job): void {
		$this->expectOpen($job);
		$job->setStatus(Status::Stale->value);
		$job->setReason(Reason::OriginalChanged->value);
		$job->setTask(Task::Purge->value);
		$this->finish($job, Status::Stale, $job->getInitiatorUid(), Subject::JobStale);
	}

	public function toCancelled(Job $job, Reason $reason): void {
		$this->expectOpen($job);
		$job->setStatus(Status::Cancelled->value);
		$job->setReason($reason->value);
		$job->setTask(Task::Purge->value);
		$this->finish($job, Status::Cancelled, $job->getInitiatorUid(), null);
		// No notification for a cancelled job, and none of the old ones may
		// point at a review page that no longer has anything to show.
		$this->notifications->dismiss($job);
	}

	/**
	 * The pre-check found a signed PDF (D-02-04): the job leaves the queue
	 * until the initiator confirms that the signature will be lost. No
	 * notification (D-02-02); the file card shows the question.
	 */
	public function toConfirm(Job $job): void {
		$this->expect($job, Status::Analyzing);
		$job->setStatus(Status::Confirm->value);
		$job->setReason(null);
		$job->setTask(null);
		$job->setStage(null);
		$this->finish($job, Status::Confirm, $job->getInitiatorUid(), null);
		$this->events->record($job->getId(), $job->getInitiatorUid(), JobEventMapper::ACTION_SIGNATURE_NOTICE);
	}

	/**
	 * The initiator accepted the loss of the signature: back into the queue
	 * for the analysis. The confirmation is the event signature_confirmed;
	 * the claim reads it from there (plan 02-15).
	 */
	public function confirmSignature(Job $job, string $uid): void {
		$this->expect($job, Status::Confirm);
		$this->expectInitiator($job, $uid);
		$this->events->record($job->getId(), $uid, JobEventMapper::ACTION_SIGNATURE_CONFIRMED);
		$job->setStatus(Status::Queued->value);
		$job->setTask(Task::Analyze->value);
		$job->setStage(Stage::Waiting->value);
		$job->setAttempts(0);
		$this->finish($job, Status::Queued, $uid, null);
	}

	/**
	 * The initiator keeps the signature: the job ends as cancelled with
	 * signature_declined, without a notification.
	 */
	public function declineSignature(Job $job, string $uid): void {
		$this->expect($job, Status::Confirm);
		$this->expectInitiator($job, $uid);
		$this->toCancelled($job, Reason::SignatureDeclined);
	}

	/**
	 * What the pre-check and the sanitizer reported with the ack (plan
	 * 02-15): one event per flag that is set, and none otherwise.
	 */
	public function recordAckFlags(Job $job, bool $macrosRemoved, int $externalLinksRemoved, bool $ownerProtectionDropped): void {
		$uid = $job->getInitiatorUid();
		if ($macrosRemoved) {
			$this->events->record($job->getId(), $uid, JobEventMapper::ACTION_MACROS_REMOVED);
		}
		if ($externalLinksRemoved > 0) {
			$this->events->record($job->getId(), $uid, JobEventMapper::ACTION_EXTERNAL_LINKS_REMOVED);
		}
		if ($ownerProtectionDropped) {
			$this->events->record($job->getId(), $uid, JobEventMapper::ACTION_OWNER_PROTECTION_DROPPED);
		}
	}

	public function toApproved(Job $job, string $uid): void {
		$this->expect($job, Status::Review);
		$job->setStatus(Status::Approved->value);
		$job->setTask(Task::Apply->value);
		$job->setStage(Stage::Waiting->value);
		$job->setAttempts(0);
		$this->finish($job, Status::Approved, $uid, null);
	}

	public function toVerified(Job $job, string $sha256, int $size): void {
		$this->expect($job, Status::Applying);
		if (preg_match('/^[0-9a-f]{64}$/D', $sha256) !== 1 || $size <= 0) {
			throw new \InvalidArgumentException('output checksum or size out of range');
		}
		$job->setStatus(Status::Verified->value);
		$job->setTask(null);
		$job->setStage(Stage::Done->value);
		$job->setOutputSha256($sha256);
		$job->setOutputSize($size);
		$job->setAttempts(0);
		$this->finish($job, Status::Verified, $job->getInitiatorUid(), null);
	}

	public function toPublished(Job $job, int $outputFileId): void {
		$this->expect($job, Status::Verified);
		if ($outputFileId <= 0) {
			throw new \InvalidArgumentException('output file id out of range');
		}
		$job->setStatus(Status::Published->value);
		$job->setOutputFileId($outputFileId);
		$job->setTask(Task::Purge->value);
		$this->finish($job, Status::Published, $job->getInitiatorUid(), Subject::CopyCreated);
	}

	/**
	 * The container confirmed that it deleted everything of this job. The
	 * state stays; only the task ends. There is no event: "purged" is not a
	 * word of the closed lists the event table accepts.
	 */
	public function toPurged(Job $job): void {
		if ($job->getTaskEnum() !== Task::Purge) {
			throw new \LogicException('job is not waiting for purge');
		}
		$this->releaseLease($job);
		$job->setTask(null);
		$job->setUpdatedAt($this->time->getTime());
		$this->jobs->update($job);
	}

	// -- helpers -------------------------------------------------------------------

	private function recheckJob(Job $job, string $uid): Recheck {
		$verdict = $this->files->recheck($uid, $job->getFileId(), $job->getFileEtag());
		if ($verdict === Recheck::Changed && $job->getStatusEnum()->isOpen()) {
			$this->toStale($job);
		}
		return $verdict;
	}

	/**
	 * The mapper fails a job that was handed out three times without an ack
	 * (repeatedly_stuck) and cannot notify. The first reader of such a job
	 * records the event and sends job_failed, once. Only for this one
	 * reason: a refusal of the pre-check already carries its failed event
	 * and never gets a notification afterwards (D-02-02).
	 */
	private function catchUpGiveUp(Job $job): void {
		if ($job->getStatusEnum() !== Status::Failed || $job->getReasonEnum() !== Reason::RepeatedlyStuck) {
			return;
		}
		foreach ($this->events->findForJob($job->getId()) as $event) {
			if ($event->getAction() === Status::Failed->value) {
				return;
			}
		}
		$this->events->record($job->getId(), $job->getInitiatorUid(), Status::Failed->value);
		$this->notifications->notify($job, Subject::JobFailed);
	}

	private function finish(Job $job, Status $status, string $uid, ?Subject $subject): void {
		$this->releaseLease($job);
		$job->setUpdatedAt($this->time->getTime());
		$this->jobs->update($job);
		$this->events->record($job->getId(), $uid, $status->value);
		if ($subject !== null) {
			$this->notifications->notify($job, $subject);
		}
	}

	private function releaseLease(Job $job): void {
		$token = $job->getClaimToken();
		if ($token !== null && $token !== '') {
			$this->jobs->release($job, $token);
		}
	}

	private function expect(Job $job, Status $from): void {
		if ($job->getStatusEnum() !== $from) {
			throw new \LogicException('job state transition not allowed');
		}
	}

	private function expectInitiator(Job $job, string $uid): void {
		if ($uid === '' || $uid !== $job->getInitiatorUid()) {
			throw new \LogicException('only the initiator decides on the signature');
		}
	}

	private function expectOpen(Job $job): void {
		if (!$job->getStatusEnum()->isOpen()) {
			throw new \LogicException('job state transition not allowed');
		}
	}

	private function languageOf(string $uid): Lang {
		return Lang::fromLanguageCode($this->l10nFactory->getUserLanguage($this->userManager->get($uid)));
	}

	private function nameOf(string $uid, int $fileId): ?string {
		$file = $this->files->resolve($uid, $fileId);
		if ($file === null) {
			return null;
		}
		try {
			return $file->getName();
		} catch (\Throwable) {
			return null;
		}
	}

	/**
	 * @return array{job: null, created: false, ahead: 0, reason: Reason}
	 */
	private static function refused(Reason $reason): array {
		return ['job' => null, 'created' => false, 'ahead' => 0, 'reason' => $reason];
	}
}
