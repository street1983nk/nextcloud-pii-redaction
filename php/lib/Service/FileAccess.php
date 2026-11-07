<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Service;

use OCA\PiiRedaction\Model\Recheck;
use OCP\Files\File;
use OCP\Files\Folder;
use OCP\Files\IRootFolder;
use OCP\Files\Node;
use OCP\Files\Storage\ISharedStorage;
use Psr\Log\LoggerInterface;

/**
 * The one place that asks whether a user may read a file (taken over from
 * Audio & Video Search, sharpened for PII Redaction).
 *
 * Start, status, review page, page image, placeholder, gateway and publishing
 * all ask recheck() here on every request; nothing remembers a permission.
 * backend/tests/test_php_gates.py holds the node lookup by id to this file
 * (rule 4) and the recheck call to every route (rule 12).
 *
 * There is no answer "reachable, but closed": the ACL wrapper of groupfolders
 * hides a node entirely, and then the lookup answers what it answers for a
 * file that does not exist. Both become Recheck::Missing.
 *
 * The download block fails closed (orchestrator decision 6): a share without
 * download permission, a share with hidden download and any exception while
 * asking count as blocked. There is no exception for the server setting that
 * allows viewing without download: this app hands the content to a program,
 * which is a download in all but name.
 */
final class FileAccess {
	public function __construct(
		private IRootFolder $rootFolder,
		private ReaderContext $readerContext,
		private LoggerInterface $logger,
	) {
	}

	/**
	 * The file behind $fileId in the tree of $userFolder, or null when it does
	 * not exist there, is not a file, or is not readable for that user.
	 */
	public static function readableFile(Folder $userFolder, int $fileId): ?File {
		if ($fileId <= 0) {
			return null;
		}

		return self::readableNode($userFolder->getFirstNodeById($fileId));
	}

	/**
	 * The same question for a node the caller already holds.
	 */
	public static function readableNode(?Node $node): ?File {
		if (!$node instanceof File) {
			return null;
		}

		return $node->isReadable() ? $node : null;
	}

	/**
	 * True when the node lies in a share that forbids downloading, and true
	 * whenever that cannot be decided.
	 */
	public function downloadBlocked(Node $node): bool {
		try {
			$storage = $node->getStorage();
			if (!$storage->instanceOfStorage(ISharedStorage::class)) {
				return false;
			}
			/** @var ISharedStorage $storage */
			$share = $storage->getShare();
			if ($share->getHideDownload()) {
				return true;
			}
			return $share->getAttributes()?->getAttribute('permissions', 'download') === false;
		} catch (\Throwable $e) {
			$this->logger->warning('PII Redaction: download permission unclear, treated as blocked', ['class' => $e::class]);
			return true;
		}
	}

	/**
	 * Readable, not blocked and still the version of the job, asked as $uid.
	 */
	public function recheck(string $uid, int $fileId, string $etag): Recheck {
		[$verdict, $file] = $this->recheckForStart($uid, $fileId);
		if ($verdict !== Recheck::Ok || $file === null) {
			return $verdict;
		}
		try {
			return $file->getEtag() === $etag ? Recheck::Ok : Recheck::Changed;
		} catch (\Throwable $e) {
			$this->logger->warning('PII Redaction: etag not readable, treated as missing', ['fileId' => $fileId, 'class' => $e::class]);
			return Recheck::Missing;
		}
	}

	/**
	 * The check before a job exists: readable and not blocked, no etag yet.
	 * Returns the file for etag and mime only when the answer is Ok.
	 *
	 * @return array{0: Recheck, 1: ?File}
	 */
	public function recheckForStart(string $uid, int $fileId): array {
		$file = $this->resolve($uid, $fileId);
		if ($file === null) {
			return [Recheck::Missing, null];
		}
		$blocked = $this->readerContext->actAs($uid, fn (): bool => $this->downloadBlocked($file));
		if ($blocked) {
			return [Recheck::DownloadBlocked, null];
		}
		return [Recheck::Ok, $file];
	}

	/**
	 * The readable file behind $fileId for $uid, or null. Every exception is
	 * "not there": nothing about the file leaks through an error.
	 */
	public function resolve(string $uid, int $fileId): ?File {
		try {
			return $this->readerContext->actAs(
				$uid,
				fn (): ?File => self::readableFile($this->rootFolder->getUserFolder($uid), $fileId),
			);
		} catch (\Throwable $e) {
			$this->logger->warning('PII Redaction: file lookup failed, treated as missing', ['fileId' => $fileId, 'class' => $e::class]);
			return null;
		}
	}
}
