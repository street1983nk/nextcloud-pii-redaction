<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Service;

use OCA\PiiRedaction\Db\Job;
use OCA\PiiRedaction\Model\Reason;
use OCA\PiiRedaction\Model\Status;
use OCP\Files\File;
use OCP\Files\NotPermittedException;
use Psr\Log\LoggerInterface;

/**
 * Puts the finished copy of a job next to its original (RESEARCH Entscheid 8).
 *
 * The bytes come from the container, which is outside the trust boundary:
 * they are copied into a temporary stream under a size ceiling while being
 * hashed, and only when sha256 and size are exactly what the container
 * reported in its ack is anything written. The write happens as the
 * initiator, through the user's own folder, so Nextcloud's permissions,
 * versions and quota answer as for an upload of that user. The original must
 * still be the version the job was started on, readable and not under a
 * download block, and its folder must allow creating files. The name comes
 * from Suffix and from the collision rule of the server, so an existing file
 * is never overwritten.
 *
 * backend/tests/test_php_gates.py (rule 18) holds file creation to this file.
 */
final class PublishService {
	/** Ceiling of a copy (provisional, phase 2 hardens it). */
	public const MAX_OUTPUT_BYTES = 33554432;
	/** Above this the temporary stream moves from memory to a file. */
	private const TEMP_IN_MEMORY = 'php://temp/maxmemory:8388608';
	private const CHUNK_BYTES = 1048576;
	private const MAX_IDLE_READS = 1000;

	public function __construct(
		private JobService $jobs,
		private ExAppService $exApp,
		private FileAccess $files,
		private ReaderContext $readerContext,
		private LoggerInterface $logger,
	) {
	}

	public function publish(Job $job): void {
		if ($job->getStatusEnum() !== Status::Verified) {
			$this->logger->info('PII Redaction: publish skipped, job not verified', ['jobId' => $job->getId(), 'status' => $job->getStatus()]);
			return;
		}
		$jobId = $job->getId();
		$uid = $job->getInitiatorUid();

		$response = $this->exApp->output($jobId, $uid);
		if ($response === null) {
			$this->fail($job, Reason::BackendUnavailable);
			return;
		}

		$temp = fopen(self::TEMP_IN_MEMORY, 'w+b');
		if ($temp === false) {
			$this->fail($job, Reason::CheckError);
			return;
		}
		try {
			$copied = self::copyHashed($response->getBody(), $temp);
			if ($copied === null) {
				$this->fail($job, Reason::CheckError);
				return;
			}
			[$sha256, $size] = $copied;
			$expected = $job->getOutputSha256() ?? '';
			if ($expected === '' || !hash_equals($expected, $sha256) || $size !== $job->getOutputSize()) {
				$this->fail($job, Reason::CheckError);
				return;
			}
			rewind($temp);

			$this->place($job, $uid, $temp);
		} finally {
			fclose($temp);
		}
	}

	/**
	 * The checks on the original and the write, as the initiator.
	 *
	 * @param resource $temp
	 */
	private function place(Job $job, string $uid, $temp): void {
		$original = $this->files->resolve($uid, $job->getFileId());
		if ($original === null) {
			$this->jobs->toCancelled($job, Reason::OriginalDeleted);
			return;
		}

		/** @var array{0: ?Reason, 1: bool, 2: ?File} $outcome */
		$outcome = $this->readerContext->actAs($uid, function () use ($job, $original, $temp): array {
			if ($original->getEtag() !== $job->getFileEtag()) {
				return [Reason::OriginalChanged, false, null];
			}
			if ($this->files->downloadBlocked($original)) {
				return [Reason::DownloadBlocked, false, null];
			}
			$folder = $original->getParent();
			if (!$folder->isCreatable()) {
				return [Reason::TargetNotWritable, false, null];
			}
			$name = $folder->getNonExistingName(
				Suffix::outputName($original->getName(), $job->getModeEnum(), $job->getLangEnum()),
			);
			try {
				$created = $folder->newFile($name, $temp);
			} catch (NotPermittedException) {
				return [Reason::TargetNotWritable, false, null];
			}
			return [null, true, $created];
		});

		[$reason, $written, $created] = $outcome;
		if ($reason === Reason::OriginalChanged) {
			$this->jobs->toStale($job);
			return;
		}
		if ($reason !== null || !$written || !$created instanceof File) {
			$this->fail($job, $reason ?? Reason::CheckError);
			return;
		}

		$this->jobs->toPublished($job, $created->getId());
	}

	/**
	 * Copies a body (stream or string) into $temp, at most MAX_OUTPUT_BYTES,
	 * and returns [sha256, size], or null when it is larger or unreadable.
	 *
	 * @param resource $temp
	 * @return array{0: string, 1: int}|null
	 */
	private static function copyHashed(mixed $body, $temp): ?array {
		$hash = hash_init('sha256');
		$size = 0;
		if (is_string($body)) {
			$size = strlen($body);
			if ($size > self::MAX_OUTPUT_BYTES || fwrite($temp, $body) !== $size) {
				return null;
			}
			hash_update($hash, $body);
			return [hash_final($hash), $size];
		}
		if (!is_resource($body)) {
			return null;
		}
		$idle = 0;
		while (!feof($body)) {
			$chunk = fread($body, self::CHUNK_BYTES);
			// A stream that neither ends nor delivers must not spin forever.
			if ($chunk === false || ($chunk === '' && ++$idle > self::MAX_IDLE_READS)) {
				return null;
			}
			$size += strlen($chunk);
			if ($size > self::MAX_OUTPUT_BYTES) {
				return null;
			}
			if ($chunk !== '' && fwrite($temp, $chunk) !== strlen($chunk)) {
				return null;
			}
			hash_update($hash, $chunk);
		}
		return [hash_final($hash), $size];
	}

	private function fail(Job $job, Reason $reason): void {
		$this->logger->warning('PII Redaction: copy not placed', ['jobId' => $job->getId(), 'reason' => $reason->value]);
		$this->jobs->toFailed($job, $reason);
	}
}
