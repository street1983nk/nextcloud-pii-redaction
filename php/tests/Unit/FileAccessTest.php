<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Model\Recheck;
use OCA\PiiRedaction\Service\FileAccess;
use OCA\PiiRedaction\Service\ReaderContext;
use OCP\Files\File;
use OCP\Files\Folder;
use OCP\Files\IRootFolder;
use OCP\Files\Storage\IStorage;
use OCP\Files\Storage\ISharedStorage;
use OCP\IUserManager;
use OCP\IUserSession;
use OCP\Share\IAttributes;
use OCP\Share\IShare;
use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;
use Psr\Log\LoggerInterface;

/**
 * The recheck every request makes: readable, not download blocked, same etag.
 * The download block fails closed; an exception anywhere is never an "ok".
 */
#[CoversClass(FileAccess::class)]
final class FileAccessTest extends TestCase {
	private IRootFolder&MockObject $rootFolder;
	private Folder&MockObject $userFolder;
	private FileAccess $access;

	protected function setUp(): void {
		parent::setUp();
		$this->rootFolder = $this->createMock(IRootFolder::class);
		$this->userFolder = $this->createMock(Folder::class);
		$this->rootFolder->method('getUserFolder')->with('alice')->willReturn($this->userFolder);

		// Unknown uid in the user manager: actAs runs the work unchanged.
		$readerContext = new ReaderContext(
			$this->createMock(IUserSession::class),
			$this->createMock(IUserManager::class),
		);
		$this->access = new FileAccess($this->rootFolder, $readerContext, $this->createMock(LoggerInterface::class));
	}

	private function file(?IStorage $storage = null, string $etag = 'etag-1', bool $readable = true): File&MockObject {
		$file = $this->createMock(File::class);
		$file->method('isReadable')->willReturn($readable);
		$file->method('getEtag')->willReturn($etag);
		$plain = $this->createMock(IStorage::class);
		$plain->method('instanceOfStorage')->willReturn(false);
		$file->method('getStorage')->willReturn($storage ?? $plain);
		$this->userFolder->method('getFirstNodeById')->with(42)->willReturn($file);
		return $file;
	}

	private function shared(bool $hideDownload = false, ?bool $download = true, bool $throws = false): ISharedStorage&MockObject {
		$storage = $this->createMock(ISharedStorage::class);
		$storage->method('instanceOfStorage')->with(ISharedStorage::class)->willReturn(true);
		if ($throws) {
			$storage->method('getShare')->willThrowException(new \RuntimeException('share gone'));
			return $storage;
		}
		$attributes = $this->createMock(IAttributes::class);
		$attributes->method('getAttribute')->with('permissions', 'download')->willReturn($download);
		$share = $this->createMock(IShare::class);
		$share->method('getHideDownload')->willReturn($hideDownload);
		$share->method('getAttributes')->willReturn($attributes);
		$storage->method('getShare')->willReturn($share);
		return $storage;
	}

	public function testAReadableFileWithTheSameEtagIsOk(): void {
		$this->file();
		self::assertSame(Recheck::Ok, $this->access->recheck('alice', 42, 'etag-1'));
	}

	public function testAnUnreadableFileIsMissing(): void {
		$this->file(readable: false);
		self::assertSame(Recheck::Missing, $this->access->recheck('alice', 42, 'etag-1'));
	}

	public function testAFolderInsteadOfAFileIsMissing(): void {
		$this->userFolder->method('getFirstNodeById')->willReturn($this->createMock(Folder::class));
		self::assertSame(Recheck::Missing, $this->access->recheck('alice', 42, 'etag-1'));
	}

	public function testANodeThatDoesNotExistIsMissing(): void {
		$this->userFolder->method('getFirstNodeById')->willReturn(null);
		self::assertSame(Recheck::Missing, $this->access->recheck('alice', 42, 'etag-1'));
	}

	public function testAShareWithoutDownloadPermissionIsBlocked(): void {
		$this->file($this->shared(download: false));
		self::assertSame(Recheck::DownloadBlocked, $this->access->recheck('alice', 42, 'etag-1'));
	}

	public function testAShareWithHiddenDownloadIsBlocked(): void {
		$this->file($this->shared(hideDownload: true));
		self::assertSame(Recheck::DownloadBlocked, $this->access->recheck('alice', 42, 'etag-1'));
	}

	public function testAShareThatCannotBeAskedIsBlocked(): void {
		$this->file($this->shared(throws: true));
		self::assertSame(Recheck::DownloadBlocked, $this->access->recheck('alice', 42, 'etag-1'));
	}

	public function testAShareWithDownloadAllowedIsOk(): void {
		$this->file($this->shared(download: true));
		self::assertSame(Recheck::Ok, $this->access->recheck('alice', 42, 'etag-1'));
	}

	public function testAnotherEtagIsChanged(): void {
		$this->file(etag: 'etag-2');
		self::assertSame(Recheck::Changed, $this->access->recheck('alice', 42, 'etag-1'));
	}

	public function testAFailingUserFolderIsMissing(): void {
		$root = $this->createMock(IRootFolder::class);
		$root->method('getUserFolder')->willThrowException(new \RuntimeException('no such user'));
		$access = new FileAccess(
			$root,
			new ReaderContext($this->createMock(IUserSession::class), $this->createMock(IUserManager::class)),
			$this->createMock(LoggerInterface::class),
		);
		self::assertSame(Recheck::Missing, $access->recheck('alice', 42, 'etag-1'));
		self::assertNull($access->resolve('alice', 42));
	}

	public function testTheStartCheckReturnsTheFileWhenReadable(): void {
		$file = $this->file(etag: 'any');
		self::assertSame([Recheck::Ok, $file], $this->access->recheckForStart('alice', 42));
	}

	public function testTheStartCheckReturnsNoFileWhenBlocked(): void {
		$this->file($this->shared(download: false));
		self::assertSame([Recheck::DownloadBlocked, null], $this->access->recheckForStart('alice', 42));
	}

	public function testANonPositiveIdIsNeverLookedUp(): void {
		$this->userFolder->expects(self::never())->method('getFirstNodeById');
		self::assertNull(FileAccess::readableFile($this->userFolder, 0));
	}
}
