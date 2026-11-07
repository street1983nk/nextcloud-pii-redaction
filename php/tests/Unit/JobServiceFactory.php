<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Tests\Unit;

use OCA\PiiRedaction\Db\JobEventMapper;
use OCA\PiiRedaction\Db\JobMapper;
use OCA\PiiRedaction\Service\ExAppService;
use OCA\PiiRedaction\Service\FileAccess;
use OCA\PiiRedaction\Service\JobService;
use OCA\PiiRedaction\Service\NotificationSender;
use OCA\PiiRedaction\Service\ReaderContext;
use OCP\AppFramework\Utility\ITimeFactory;
use OCP\Files\File;
use OCP\Files\Folder;
use OCP\Files\IRootFolder;
use OCP\Files\Storage\IStorage;
use OCP\Http\Client\IResponse;
use OCP\IDBConnection;
use OCP\IUser;
use OCP\IUserManager;
use OCP\IUserSession;
use OCP\L10N\IFactory as IL10NFactory;
use OCP\Notification\IManager;
use OCP\Notification\INotification;
use OCP\Server;
use Psr\Log\LoggerInterface;

/**
 * Builds a JobService against the real database of the test instance (like
 * QueueMapperTest) with the edges doubled: the file tree, the state of the
 * backend, the user language and the notification manager.
 *
 * The file tree knows one file, id 42, owned by alice. Its etag, mime type,
 * readability and the share download switch are fields the tests change.
 * Every notification that is sent or removed lands in $sent and $dismissed.
 */
trait JobServiceFactory {
	private IDBConnection $db;
	private int $clock = 1_800_000_000;
	private JobMapper $mapper;
	private JobEventMapper $events;
	private JobService $service;
	private FileAccess $access;

	private bool $backendReady = true;
	private string $etag = 'etag-1';
	private string $mime = 'application/pdf';
	private bool $readable = true;
	private bool $downloadAllowed = true;
	/** @var array<string, string> */
	private array $languages = ['alice' => 'en'];
	/** What fopen() of file 42 returns: a stream the test made, or false. */
	private mixed $content = false;
	/** @var list<string> the modes fopen() of file 42 was called with */
	private array $openedAs = [];
	/** What ExAppService::page() returns: PNG bytes or null. */
	private ?string $pagePng = null;
	/** @var list<array{0: int, 1: int, 2: string}> the page calls (job, page, uid) */
	private array $pageCalls = [];
	private ExAppService $exApp;
	/** What ExAppService::output() returns. */
	private ?IResponse $outputResponse = null;
	/** The folder of file 42: writable, names already taken, files created. */
	private bool $folderWritable = true;
	/** @var list<string> */
	private array $takenNames = [];
	/** @var list<array{name: string, bytes: string}> */
	private array $created = [];
	private ?\Throwable $newFileFails = null;

	/** @var list<array{user: string, object: string, subject: string}> */
	private array $sent = [];
	/** @var list<string> */
	private array $dismissed = [];

	private function setUpJobService(): void {
		$this->db = Server::get(IDBConnection::class);
		$this->cleanTables();

		$time = $this->createMock(ITimeFactory::class);
		$time->method('getTime')->willReturnCallback(fn (): int => $this->clock);
		$time->method('getDateTime')->willReturnCallback(fn (): \DateTime => new \DateTime('@' . $this->clock));
		$this->mapper = new JobMapper($this->db, $time);
		$this->events = new JobEventMapper($this->db, $time);

		$this->access = new FileAccess(
			$this->rootFolder(),
			new ReaderContext($this->createMock(IUserSession::class), $this->createMock(IUserManager::class)),
			$this->createMock(LoggerInterface::class),
		);

		$exApp = $this->createMock(ExAppService::class);
		$exApp->method('startAllowed')->willReturnCallback(fn (): bool => $this->backendReady);
		$exApp->method('page')->willReturnCallback(function (int $jobId, int $n, string $uid): ?string {
			$this->pageCalls[] = [$jobId, $n, $uid];
			return $this->pagePng;
		});
		$exApp->method('output')->willReturnCallback(fn (int $jobId, string $uid): ?IResponse => $this->outputResponse);
		$this->exApp = $exApp;

		$users = $this->createMock(IUserManager::class);
		$users->method('get')->willReturnCallback(function (string $uid): IUser {
			$user = $this->createMock(IUser::class);
			$user->method('getUID')->willReturn($uid);
			return $user;
		});
		$l10n = $this->createMock(IL10NFactory::class);
		$l10n->method('getUserLanguage')->willReturnCallback(
			fn (?IUser $user = null): string => $this->languages[$user?->getUID() ?? ''] ?? 'en',
		);

		$sender = new NotificationSender($this->notificationManager(), $time, $this->createMock(LoggerInterface::class));

		$this->service = new JobService(
			$this->mapper,
			$this->events,
			$this->access,
			$exApp,
			$sender,
			$this->db,
			$time,
			$l10n,
			$users,
			$this->createMock(LoggerInterface::class),
		);
	}

	private function cleanTables(): void {
		foreach (['pii_jobs', 'pii_job_events', 'pii_slot'] as $table) {
			self::assertTrue(
				$this->db->tableExists($table),
				"table {$table} is missing: php.yml has to enable the app before the suite",
			);
			$this->db->getQueryBuilder()->delete($table)->executeStatement();
		}
	}

	private function rootFolder(): IRootFolder {
		$root = $this->createMock(IRootFolder::class);
		$root->method('getUserFolder')->willReturnCallback(function (string $uid): Folder {
			$folder = $this->createMock(Folder::class);
			$folder->method('getFirstNodeById')->willReturnCallback(
				fn (int $id): ?File => ($uid === 'alice' && $id === 42) ? $this->file() : null,
			);
			return $folder;
		});
		return $root;
	}

	private function file(): File {
		$file = $this->createMock(File::class);
		$file->method('isReadable')->willReturnCallback(fn (): bool => $this->readable);
		$file->method('getEtag')->willReturnCallback(fn (): string => $this->etag);
		$file->method('getMimetype')->willReturnCallback(fn (): string => $this->mime);
		$file->method('getName')->willReturn('Bescheid.pdf');
		$file->method('getId')->willReturn(42);
		$file->method('getParent')->willReturnCallback(fn (): Folder => $this->parentFolder());
		$file->method('fopen')->willReturnCallback(function (string $mode): mixed {
			$this->openedAs[] = $mode;
			return $this->content;
		});

		if ($this->downloadAllowed) {
			$storage = $this->createMock(IStorage::class);
			$storage->method('instanceOfStorage')->willReturn(false);
		} else {
			$share = $this->createMock(\OCP\Share\IShare::class);
			$share->method('getHideDownload')->willReturn(true);
			$storage = $this->createMock(\OCP\Files\Storage\ISharedStorage::class);
			$storage->method('instanceOfStorage')->willReturn(true);
			$storage->method('getShare')->willReturn($share);
		}
		$file->method('getStorage')->willReturn($storage);
		return $file;
	}

	/**
	 * The folder of file 42. getNonExistingName answers like the server: a
	 * taken name gets " (2)" before the extension.
	 */
	private function parentFolder(): Folder {
		$folder = $this->createMock(Folder::class);
		$folder->method('isCreatable')->willReturnCallback(fn (): bool => $this->folderWritable);
		$folder->method('getNonExistingName')->willReturnCallback(function (string $name): string {
			if (!in_array($name, $this->takenNames, true)) {
				return $name;
			}
			$dot = strrpos($name, '.');
			return $dot === false ? $name . ' (2)' : substr($name, 0, $dot) . ' (2)' . substr($name, $dot);
		});
		$folder->method('newFile')->willReturnCallback(function (string $name, mixed $content = null): File {
			if ($this->newFileFails !== null) {
				throw $this->newFileFails;
			}
			$this->created[] = ['name' => $name, 'bytes' => is_resource($content) ? (string)stream_get_contents($content) : (string)$content];
			$copy = $this->createMock(File::class);
			$copy->method('getId')->willReturn(99);
			return $copy;
		});
		return $folder;
	}

	private function notificationManager(): IManager {
		$manager = $this->createMock(IManager::class);
		$manager->method('createNotification')->willReturnCallback(fn (): INotification => $this->notification());
		$manager->method('notify')->willReturnCallback(function (INotification $notification): void {
			$this->sent[] = [
				'user' => $notification->getUser(),
				'object' => $notification->getObjectType() . ':' . $notification->getObjectId(),
				'subject' => $notification->getSubject(),
			];
		});
		$manager->method('markProcessed')->willReturnCallback(function (INotification $notification): void {
			$this->dismissed[] = $notification->getObjectType() . ':' . $notification->getObjectId();
		});
		return $manager;
	}

	/**
	 * A notification double that remembers what the sender set on it.
	 */
	private function notification(): INotification {
		$fields = new \ArrayObject(['app' => '', 'user' => '', 'type' => '', 'id' => '', 'subject' => '', 'params' => []]);
		$notification = $this->createMock(INotification::class);
		$notification->method('setApp')->willReturnCallback(function (string $app) use ($fields, &$notification): INotification {
			$fields['app'] = $app;
			return $notification;
		});
		$notification->method('setUser')->willReturnCallback(function (string $user) use ($fields, &$notification): INotification {
			$fields['user'] = $user;
			return $notification;
		});
		$notification->method('setObject')->willReturnCallback(function (string $type, string $id) use ($fields, &$notification): INotification {
			$fields['type'] = $type;
			$fields['id'] = $id;
			return $notification;
		});
		$notification->method('setSubject')->willReturnCallback(function (string $subject, array $params = []) use ($fields, &$notification): INotification {
			$fields['subject'] = $subject;
			$fields['params'] = $params;
			return $notification;
		});
		$notification->method('setDateTime')->willReturnCallback(fn (\DateTime $at): INotification => $notification);
		$notification->method('getApp')->willReturnCallback(fn (): string => $fields['app']);
		$notification->method('getUser')->willReturnCallback(fn (): string => $fields['user']);
		$notification->method('getObjectType')->willReturnCallback(fn (): string => $fields['type']);
		$notification->method('getObjectId')->willReturnCallback(fn (): string => $fields['id']);
		$notification->method('getSubject')->willReturnCallback(function () use ($fields): string {
			// The subject never carries parameters: a name could hide there.
			self::assertSame([], $fields['params']);
			return $fields['subject'];
		});
		return $notification;
	}

	/** @return list<string> */
	private function subjects(): array {
		return array_map(static fn (array $sent): string => $sent['subject'], $this->sent);
	}

	/** @return list<string> */
	private function actions(int $jobId): array {
		return array_map(static fn ($event): string => $event->getAction(), $this->events->findForJob($jobId));
	}
}
