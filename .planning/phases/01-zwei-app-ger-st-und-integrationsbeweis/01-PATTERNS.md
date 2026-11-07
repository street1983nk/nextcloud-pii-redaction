# Phase 1: Zwei-App-Gerüst und Integrationsbeweis - Pattern Map

**Mapped:** 2026-11-07
**Files analyzed:** 74 neue oder geänderte Dateien (in 14 Gruppen)
**Analogs found:** 63 / 74 (Rest siehe "No Analog Found")

Hauptquelle ist Audio & Video Search (AVS), `C:/Users/Student/nextcloud-audio-video-search`, Zweig `main`, Stand `1fb003d` (enthält 4291faa "Apps öffnen" ab NC 34, 3d07c81 Bannertext im Statuspaar und md-Abstände, fed53b4 `expectMediaSettled`, 1fb003d DE/FR-Screenshots mit elke/fleur). Zweitquelle für Warteschlange mit Lease, Migration, Listener, QueuedJob, RAM-Wächter und Kindprozess ist Findling, `C:/Users/Student/nextcloud-search`. Für Dateiaktion, `LoadAdditionalScriptsEvent`, `INotifier` und Vue-Mount gibt es in keinem eigenen Repo ein Vorbild; dafür dient der lokale Server-Checkout `C:/Users/Student/.cache/findling-phpunit/server` (Zweig `stable34`, Stand 04.11.2026), App `files_reminders` und `encryption`.

Das PII-Repo ist nicht leer: an der Wurzel liegt das Skeleton (`appinfo/info.xml` mit ID `pii_redaction`, `src/pii_redaction/{config,logs,main,nc,settings}.py`, `Dockerfile`, `docker/`, `tests/`, `.github/workflows/`, `scripts/release/store-archive.sh`, `scripts/l10n_js.py`, `l10n/`). Diese Dateien werden nach `backend/` verschoben und umbenannt (Entscheid 1), nicht neu geschrieben.

## File Classification

Abkürzungen: AVS = `C:/Users/Student/nextcloud-audio-video-search`, FIN = `C:/Users/Student/nextcloud-search`, SRV = `C:/Users/Student/.cache/findling-phpunit/server`.

### PHP-App `php/` (Namespace `OCA\PiiRedaction`)

| Neue/geänderte Datei | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `php/appinfo/info.xml` | config | n. a. | `AVS/php/appinfo/info.xml` | exact |
| `php/appinfo/routes.php` | config | n. a. | `AVS/php/appinfo/routes.php` | exact |
| `php/composer.json` | config | n. a. | `AVS/php/composer.json` | exact |
| `php/phpunit.xml` | config | n. a. | `AVS/php/phpunit.xml` | exact |
| `php/tests/bootstrap.php` | test | n. a. | `AVS/php/tests/bootstrap.php` | exact |
| `php/lib/AppInfo/Application.php` | provider | event-driven | `AVS/php/lib/AppInfo/Application.php` + `FIN/php/lib/AppInfo/Application.php` (Listener-Schleife) + `SRV/apps/files_reminders/lib/AppInfo/Application.php` (Notifier) | role-match |
| `php/lib/Controller/JobController.php` | controller | request-response (CRUD) | `AVS/php/lib/Controller/PageController.php` (Recheck) + `AVS/php/lib/Controller/SettingsController.php` (DataResponse, Fehlerform) | role-match |
| `php/lib/Controller/ReviewController.php` | controller | request-response | `AVS/php/lib/Controller/PageController.php` | exact (Seite), role-match (Bild-Proxy) |
| `php/lib/Controller/QueueController.php` | controller | request-response (Pull-Queue) | `FIN/php/lib/Controller/QueueController.php` | exact |
| `php/lib/Controller/GatewayController.php` | controller | streaming | `AVS/php/lib/Controller/GatewayController.php` | exact (plus Auftragsbindung neu) |
| `php/lib/Controller/HandshakeController.php` | controller | request-response | `AVS/php/lib/Controller/HandshakeController.php` | exact |
| `php/lib/Controller/SettingsController.php` | controller | request-response | `AVS/php/lib/Controller/SettingsController.php` | exact (ohne `setSample`) |
| `php/lib/Service/ExAppService.php` | service | request-response + streaming | `AVS/php/lib/Service/ExAppService.php` | exact (Transport), neu: `page()`, `output()` |
| `php/lib/Service/FileAccess.php` | utility | request-response | `AVS/php/lib/Service/FileAccess.php` | exact (plus `downloadBlocked`) |
| `php/lib/Service/ReaderContext.php` | utility | request-response | `AVS/php/lib/Service/ReaderContext.php` | exact (1:1) |
| `php/lib/Service/JobService.php` | service | CRUD | `FIN/php/lib/Db/QueueMapper.php` (`enqueue`, Konfliktweg) | partial |
| `php/lib/Service/PublishService.php` | service | file-I/O | keine; Muster RESEARCH "Ausgabe holen und ablegen" | no analog |
| `php/lib/Db/Job.php`, `JobEvent.php` | model | CRUD | `FIN/php/lib/Db/QueueFile.php` | exact |
| `php/lib/Db/JobMapper.php` | model | CRUD + Lease-Claim | `FIN/php/lib/Db/QueueMapper.php` | exact |
| `php/lib/Db/JobEventMapper.php` | model | CRUD | `FIN/php/lib/Db/QueueMapper.php` (nur Insert/Select) | role-match |
| `php/lib/Model/{Status,Reason,Stage,Task}.php` | model | transform | `FIN/php/lib/Db/QueueMapper.php` `KINDS` (Z. 56 bis 82), `AVS ExAppService::STATES` (Z. 80 bis 96) | role-match (Konstantenliste statt `enum`) |
| `php/lib/Notification/Notifier.php` | provider | event-driven | `SRV/apps/files_reminders/lib/Notification/Notifier.php` | role-match (ohne Dateiname) |
| `php/lib/BackgroundJob/PublishJob.php` | service | batch | `FIN/php/lib/BackgroundJobs/SubtreeExpandJob.php` | role-match |
| `php/lib/Listener/LoadFilesScriptsListener.php` | middleware | event-driven | `SRV/apps/files_reminders/lib/Listener/LoadAdditionalScriptsListener.php` | exact |
| `php/lib/Listener/FileLifecycleListener.php` | middleware | event-driven | `FIN/php/lib/Listener/FileEventListener.php` | exact (Rahmen) |
| `php/lib/Migration/Version000100Date20261107000000.php` | migration | n. a. | `FIN/php/lib/Migration/Version001000Date20260816000000.php` | exact |
| `php/lib/Settings/Admin.php` | provider | request-response | `AVS/php/lib/Settings/Admin.php` | exact (ohne Debug) |
| `php/lib/Settings/Section.php` | provider | n. a. | `AVS/php/lib/Settings/Section.php` | exact |
| `php/templates/admin.php` | component | n. a. | `AVS/php/templates/admin.php` | exact (ohne Debug-Block) |
| `php/templates/review.php` | component | n. a. | `SRV/apps/encryption/templates/settings.php` (nur Mount-Div) | role-match |
| `php/css/admin.css`, `php/css/review.css` | config (Stil) | n. a. | `AVS/php/css/play.css` Z. 65 bis 167, `AVS/php/css/admin.css` Z. 118 bis 128 | exact |
| `php/src/admin.ts` | component | request-response | `AVS/php/js/admin.js` (Vanilla, ohne Vue) | exact |
| `php/src/init.ts` | component | request-response | `SRV/apps/files_reminders/src/files-init.ts` + `.../files_actions/clearReminderAction.ts` | exact |
| `php/src/review.ts` | component | n. a. | `SRV/apps/encryption/src/settings-admin.ts` | exact |
| `php/src/ReviewPlaceholder.vue` | component | polling | `SRV/apps/encryption/src/views/SettingsAdmin.vue` (loadState, NcNoteCard) | partial |
| `php/src/icon.svg` | config | n. a. | Icon-Pfade in `AVS/php/templates/admin.php` Z. 34 bis 40 | role-match |
| `php/package.json`, `package-lock.json`, `vite.config.ts`, `tsconfig.json` | config | n. a. | `SRV/build/frontend/vite.config.ts` (nur `createAppConfig`-Form) | partial |
| `php/l10n/{de,de_DE,en,fr}.{json,js}` | config | n. a. | `AVS/php/l10n/*` | exact |
| `php/img/app.svg`, `app-dark.svg` | config | n. a. | `AVS/php/img/*` | exact |
| `php/tests/Unit/*Test.php` (BackendState, ExAppService, Gateway, Handshake, Settings, JobController, QueueController, QueueMapper, Notifier, FileAccess, EtagBinding, Suffix) | test | n. a. | `AVS/php/tests/Unit/GatewayControllerTest.php` u. a. | exact (Gerüst) |

### Backend `backend/` (ExApp `pii_redaction_backend`)

| Neue/geänderte Datei | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/appinfo/info.xml` | config | n. a. | `AVS/backend/appinfo/info.xml` + heutiges `appinfo/info.xml` | exact, aber `<routes/>` leer |
| `backend/Dockerfile` | config | n. a. | `AVS/backend/Dockerfile` | exact (plus LibreOffice) |
| `backend/pyproject.toml`, `uv.lock` | config | n. a. | heutiges `pyproject.toml` + `AVS/backend/pyproject.toml` | exact |
| `backend/docker/{entrypoint,start,healthcheck}.sh` | config | n. a. | heutiges `docker/*` | exact (Verschiebung) |
| `backend/l10n/*` | config | n. a. | `AVS/backend/l10n/*` | exact |
| `backend/src/pii_redaction_backend/main.py` | provider | event-driven | `AVS/backend/src/audio_video_search_backend/main.py` | exact |
| `.../config.py` | config | n. a. | `AVS/backend/src/audio_video_search_backend/config.py` | exact |
| `.../settings.py` | config | n. a. | heutiges `src/pii_redaction/settings.py` | exact |
| `.../logs.py` | utility | transform | `AVS/backend/src/audio_video_search_backend/logs.py` | role-match (strenger: Allowlist, kein Traceback) |
| `.../nc.py` | service | streaming | `AVS/backend/src/audio_video_search_backend/nc.py` | exact (plus Job, Token, Etag) |
| `.../companion.py` | service | event-driven | `AVS/backend/src/audio_video_search_backend/companion.py` | exact (1:1) |
| `.../tasks/client.py` | service | request-response (Pull) | `FIN/backend/src/findling/nc/queue.py` (`DocumentQueue`, Z. 541 bis 656) | exact |
| `.../tasks/fetch.py` | service | streaming | `AVS nc.py` `_hash_stream` (Z. 144 bis 184) | exact |
| `.../runner/runner.py` | service | batch | `AVS main.py` `start_background`/`stop_background` (Z. 46 bis 67) + `companion.run_periodic` (Z. 126 bis 133) | partial |
| `.../resources/hardware.py`, `memory_guard.py` | utility | file-I/O | `FIN/backend/src/findling/hardware.py`, `memory_guard.py` | exact (Kopie) |
| `.../workers/child.py` | utility | batch | `FIN/backend/src/findling/extract/sandbox.py` (`_kill_child_tree`, Z. 150 bis 169) | partial |
| `.../workers/render.py`, `soffice.py`, `placeholder.py` | utility | file-I/O | keine (PyMuPDF/soffice neu) | no analog |
| `.../store/schema.sql`, `repo.py` | model | CRUD | `AVS/backend/src/audio_video_search_backend/store/{schema.sql,repo.py}` | role-match |
| `.../api/__init__.py` | route | request-response | `AVS/backend/src/audio_video_search_backend/api/__init__.py` | exact |
| `.../api/status.py` | route | request-response | `AVS/backend/src/audio_video_search_backend/api/status.py` | exact |
| `.../api/pages.py`, `output.py` | route | streaming | `AVS api/status.py` (Router-Form) | partial |
| `backend/tests/test_lockstep_versions.py` | test | n. a. | `AVS/backend/tests/test_lockstep_versions.py` | exact |
| `backend/tests/test_php_gates.py` | test | n. a. | `AVS/backend/tests/test_php_gates.py` | exact (plus neue Regeln) |
| `backend/tests/test_release_archives.py` | test | n. a. | `AVS/backend/tests/test_release_archives.py` | exact |
| `backend/tests/test_boundary.py` | test | n. a. | `AVS/backend/tests/test_boundary.py` | exact |
| `backend/tests/test_handshake.py`, `test_companion.py` | test | n. a. | `AVS/backend/tests/test_handshake.py` | exact |
| `backend/tests/test_trilingual.py`, `test_public_texts.py` | test | n. a. | `AVS/backend/tests/test_trilingual.py`, `test_public_texts.py` | exact (plus `php/src`) |
| `backend/tests/test_logs.py`, `test_log_calls.py` | test | n. a. | heutiges `tests/test_logs.py`; AST-Muster aus `AVS/backend/tests/test_boundary.py` | role-match |
| `backend/tests/test_memory_guard.py`, `test_runner.py`, `test_child.py` | test | n. a. | Findling-Tests zu `memory_guard`/`sandbox` | role-match |
| übrige heutige `tests/*` | test | n. a. | Verschiebung nach `backend/tests/` | exact |

### CI, Workflows, Skripte

| Neue/geänderte Datei | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `.github/workflows/deploy-harp.yml` | config | batch | `AVS/.github/workflows/deploy-harp.yml` | exact (plus MariaDB-Bein, notifications, Node-Build) |
| `.github/workflows/php.yml` | config | batch | `AVS/.github/workflows/php.yml` | exact (plus `npm ci && npm run build`) |
| `.github/workflows/{python,docker,release,store-submit}.yml` | config | batch | AVS gleichnamige Dateien | exact |
| `.github/dependabot.yml` | config | n. a. | `AVS/.github/dependabot.yml` | exact (plus npm, vite-Major ignorieren) |
| `scripts/release/store-archive.sh` | utility | file-I/O | `AVS/scripts/release/store-archive.sh` | exact (plus `js/`-Prüfung) |
| `ci/seed.sh` | utility | batch | `AVS/ci/seed.sh` | exact (Fixtures statt Medien) |
| `ci/redeploy.sh`, `ci/admin-state.sh` | utility | batch | AVS gleichnamig | exact |
| `ci/playwright/{playwright.config.ts,helpers.ts,admin.spec.ts}` | test | n. a. | `AVS/ci/playwright/*` | exact |
| `ci/playwright/fileaction.spec.ts`, `review.spec.ts` | test | n. a. | `AVS/ci/playwright/play.spec.ts` | role-match |
| `ci/make_fixtures.py` | utility | file-I/O | `AVS/ci/make-testmedia.sh` (nur Rolle) | partial |
| `ci/measure.sh` | utility | batch | keine | no analog |

## Pattern Assignments

### `php/lib/AppInfo/Application.php` (provider, event-driven)

**Analog:** `AVS/php/lib/AppInfo/Application.php` (Z. 1 bis 37) für Kopf und Konstanten; Listener-Schleife aus `FIN/php/lib/AppInfo/Application.php` (Z. 76 bis 90); Notifier-Registrierung aus `SRV/apps/files_reminders/lib/AppInfo/Application.php`.

**Kopf und IDs** (AVS Z. 13 bis 24):
```php
class Application extends App implements IBootstrap {
	public const APP_ID = 'audio_video_search';

	/**
	 * The ExApp half in the External Apps section of the store. Both ids are
	 * frozen: the app certificates are bound to them.
	 */
	public const BACKEND_APP_ID = 'audio_video_search_backend';

	public function __construct(array $urlParams = []) {
		parent::__construct(self::APP_ID, $urlParams);
	}
```
IDs tauschen: `pii_redaction`, `pii_redaction_backend`.

**Registrierung nur in `register()`** (AVS Z. 26 bis 33, Kommentar "boot() runs too late"). Listener als zählbare Schleife (FIN Z. 76 bis 90):
```php
foreach ([
	\OCP\Files\Events\Node\NodeCreatedEvent::class,
	\OCP\Files\Events\Node\NodeWrittenEvent::class,
	...
	\OCP\Files\Events\Node\NodeDeletedEvent::class,
] as $event) {
	$context->registerEventListener($event, FileEventListener::class);
}
```
Für PII nur `NodeWrittenEvent` und `NodeDeletedEvent` auf `FileLifecycleListener`, dazu (SRV files_reminders):
```php
$context->registerNotifierService(Notifier::class);
$context->registerEventListener(LoadAdditionalScriptsEvent::class, LoadAdditionalScriptsListener::class);
```
**Nicht übernehmen:** `#[\Override]` aus dem Server-Code; AVS `Section.php` Z. 15 bis 18 begründet, warum es auf PHP 8.2 fehlt.

---

### `php/lib/Controller/GatewayController.php` (controller, streaming)

**Analog:** `AVS/php/lib/Controller/GatewayController.php` (ganze Datei, 126 Zeilen).

**Imports** (Z. 7 bis 17):
```php
use OCA\AudioVideoSearch\AppInfo\Application;
use OCA\AudioVideoSearch\Service\FileAccess;
use OCA\AudioVideoSearch\Service\ReaderContext;
use OCP\AppFramework\Http;
use OCP\AppFramework\Http\DataResponse;
use OCP\AppFramework\Http\StreamResponse;
use OCP\AppFramework\OCSController;
use OCP\Files\File;
use OCP\Files\IRootFolder;
use OCP\IRequest;
use Psr\Log\LoggerInterface;
```

**Attribute und Wächter** (Z. 51 bis 58):
```php
#[\OCP\AppFramework\Http\Attribute\ExAppRequired]
#[\OCP\AppFramework\Http\Attribute\NoCSRFRequired]
#[\OCP\AppFramework\Http\Attribute\ApiRoute(verb: 'GET', url: '/files/{fileId}', requirements: ['fileId' => '\d+'])]
public function getFileContents(int $fileId, string $userId): DataResponse|StreamResponse {
	$foreign = $this->rejectForeignCaller();
	if ($foreign !== null) {
		return $foreign;
	}
```
PII: URL `/api/v1/files/{jobId}` mit `requirements: ['jobId' => '\d+']`, Parameter `int $jobId, string $token`. `userId` kommt NICHT mehr vom Container, sondern aus `initiator_uid` der Auftragszeile (Entscheid 5).

**Kern: Recheck als Nutzer, dann `fopen('r')`** (Z. 60 bis 85):
```php
$file = $this->readerContext->actAs(
	$userId,
	fn (): ?File => FileAccess::readableFile($this->rootFolder->getUserFolder($userId), $fileId),
);
if ($file === null) {
	return new DataResponse(['error' => 'Node is not a file or could not be found.'], Http::STATUS_NOT_FOUND);
}
$stream = $file->fopen('r');
...
return new StreamResponse($stream);
```
Neu davor: Token = `claim_token` (`hash_equals`), `lease_until > now`, Status `analyzing`; danach `downloadBlocked($file)` und `$file->getEtag() !== $job->getFileEtag()` -> 409 plus `stale(original_changed)`. Header `X-Pii-Etag` per `$response->addHeader(...)`.

**Fehlerbehandlung** (Z. 86 bis 99): `NoUserException` gibt wortgleich die 404-Antwort; `\Throwable` -> 500 mit statischem Satz und `['exception' => $e]`.

**`rejectForeignCaller`** (Z. 113 bis 125) 1:1, Satz "reserved for the PII Redaction backend".

---

### `php/lib/Controller/HandshakeController.php` (controller, request-response)

**Analog:** `AVS/php/lib/Controller/HandshakeController.php` 1:1 (Z. 40 bis 50 Route, Z. 57 bis 69 Wächter):
```php
#[\OCP\AppFramework\Http\Attribute\ExAppRequired]
#[\OCP\AppFramework\Http\Attribute\NoCSRFRequired]
#[\OCP\AppFramework\Http\Attribute\ApiRoute(verb: 'GET', url: '/api/v1/handshake')]
public function handshake(): DataResponse {
	$foreign = $this->rejectForeignCaller();
	if ($foreign !== null) {
		return $foreign;
	}
	return new DataResponse(['companionVersion' => $this->appManager->getAppVersion(Application::APP_ID)]);
}
```

---

### `php/lib/Controller/QueueController.php` (controller, Pull-Queue)

**Analog:** `FIN/php/lib/Controller/QueueController.php` (607 Zeilen; relevant Z. 115 bis 148 Claim, Z. 206 bis 239 Ack, Z. 414 bis 425 Wächter, Z. 466 bis 490 Grund-Validierung gegen geschlossene Liste).

**Claim-Route** (Z. 115 bis 148):
```php
#[\OCP\AppFramework\Http\Attribute\ExAppRequired]
#[\OCP\AppFramework\Http\Attribute\NoCSRFRequired]
#[\OCP\AppFramework\Http\Attribute\ApiRoute(verb: 'GET', url: '/queues/documents')]
public function getDocuments(int $n = self::DEFAULT_BATCH_FILES, ...): DataResponse {
	$foreign = $this->rejectForeignCaller();
	if ($foreign !== null) {
		return $foreign;
	}
	if (!in_array($lane, QueueService::LANES, true)) {
		return $this->badLane();
	}
	try {
		$files = $this->queueService->claim($limit, $budget, $lane);
	} catch (\Throwable $e) {
		$this->logger->error('Findling: could not hand out a batch', ['exception' => $e]);
		return new DataResponse(['error' => 'Queue is not available.'], Http::STATUS_INTERNAL_SERVER_ERROR);
	}
	return new DataResponse(['files' => $files, 'lane' => $lane]);
}
```
PII-Routen laut RESEARCH Entscheid 4: `POST /api/v1/queue/claim`, `POST /api/v1/queue/{jobId}/progress`, `POST /api/v1/queue/{jobId}/ack`. Jede Methode beginnt mit dem Wächter (Gate-Regel 1). `stage`, `result`, `reason` mit `in_array(..., Stage::VALUES, true)` prüfen wie FIN Z. 479 (`in_array($reason, FileStateService::REASONS, true)`), sonst 400 ohne Schreiben.

**Kommentar zur Parameterbindung übernehmen** (FIN Z. 196 bis 200): Nextcloud bindet OCS-Parameter aus Query und JSON-Körper gleich.

---

### `php/lib/Db/JobMapper.php` (model, CRUD + Lease-Claim)

**Analog:** `FIN/php/lib/Db/QueueMapper.php` (977 Zeilen; relevant Z. 12 bis 34 Kopfkommentar, Z. 194 bis 199 Konstruktor, Z. 341 bis 417 `claimBatch`, Z. 925 bis 956 Hilfen).

**Klassenkopf** (Z. 34 bis 35, 194 bis 199):
```php
class QueueMapper extends QBMapper {
	public const TABLE_NAME = 'findling_queue';
	...
	public function __construct(
		IDBConnection $db,
		private ITimeFactory $timeFactory,
	) {
		parent::__construct($db, self::TABLE_NAME, QueueFile::class);
	}
```

**Claim als bedingte Aktualisierung mit Token-Rücklesen** (Z. 396 bis 416):
```php
$token = bin2hex(random_bytes(16));
$claim = $this->db->getQueryBuilder();
$claim->update(self::TABLE_NAME)
	->set('locked_at', $claim->createNamedParameter($now, IQueryBuilder::PARAM_DATE))
	->set('claim_token', $claim->createNamedParameter($token))
	->set('retries', $claim->createFunction('retries + 1'))
	->where($claim->expr()->in('id', $claim->createNamedParameter($wanted, IQueryBuilder::PARAM_INT_ARRAY)))
	->andWhere($this->freeRowCondition($claim, $cutoff))
	->andWhere($claim->expr()->eq('kind', $claim->createNamedParameter($kind)));
if ($claim->executeStatement() === 0) {
	return [];
}
$won = $this->db->getQueryBuilder();
$won->select('*')
	->from(self::TABLE_NAME)
	->where($won->expr()->eq('claim_token', $won->createNamedParameter($token)))
	->orderBy('id', 'ASC');
return $this->findEntities($won);
```
Unterschied PII: eine Zeile statt Band; Lease als `lease_until BIGINT` (Unix-Sekunden über `ITimeFactory::getTime()`) statt `locked_at DATETIME`; "ein Auftrag zur Zeit" als zusätzliche Prüfung (RESEARCH Pattern 2, Z. 436 bis 439: in MySQL kein `NOT EXISTS` mit Selbstbezug, also Transaktion mit vorheriger Zählung oder Sperrzeile). Reihenfolge der Arten wie FIN `KINDS` (Z. 75 bis 82) als Konstantenliste `purge, apply, analyze`, Schleife statt `ORDER BY`. Lease je Art wie `LOCK_TIMEOUTS` (Z. 143 bis 150): `analyze` 120, `apply` 300.

**Zeitbasis** (Z. 944 bis 956): immer `ITimeFactory`, nie `time()`, damit phpunit die Uhr steuern kann.

**Zählen** (Z. 970 bis 976) für die Warteschlangenposition:
```php
private function countFrom(IQueryBuilder $qb): int {
	$result = $qb->executeQuery();
	$count = $result->fetchOne();
	$result->closeCursor();
	return is_numeric($count) ? (int)$count : 0;
}
```

---

### `php/lib/Db/Job.php`, `JobEvent.php` (model)

**Analog:** `FIN/php/lib/Db/QueueFile.php`:
```php
class QueueFile extends Entity {
	protected int $fileId = 0;
	protected int $retries = 0;
	protected string $kind = QueueMapper::KIND_CONTENT;
	protected ?string $claimToken = null;
	protected ?string $lockedAt = null;

	public function __construct() {
		$this->addType('fileId', 'integer');
		$this->addType('retries', 'integer');
	}
}
```
Felder laut RESEARCH Entscheid 3 (`fileId, initiatorUid, fileEtag, mode, status, reason, task, stage, pagesDone, pagesTotal, claimToken, leaseUntil, attempts, revision, revisionHash, outputFileId, createdAt, updatedAt, expiresAt`, dazu Sprachkürzel aus UI-SPEC Fläche 4). Kein Feld für Name, Pfad, Mime.

---

### `php/lib/Model/{Status,Reason,Stage,Task}.php` (model, transform)

**Analog:** geschlossene Listen als Konstanten mit einer Liste `VALUES`, wie `FIN QueueMapper::KINDS` (Z. 56 bis 82) und `AVS ExAppService::STATES` (Z. 80 bis 96):
```php
public const STATE_NO_APP_API = 'no_app_api';
...
public const STATES = [
	self::STATE_NO_APP_API,
	...
	self::STATE_OK,
];
```
RESEARCH empfiehlt string-backed `enum`; beides läuft auf PHP 8.2. Wenn `enum`, dann `Status::tryFrom($raw)` als einzige Prüfung, Werte wortgleich zur Python-Seite (`Literal`/`StrEnum`).

---

### `php/lib/Migration/Version000100Date20261107000000.php` (migration)

**Analog:** `FIN/php/lib/Migration/Version001000Date20260816000000.php` (131 Zeilen).

**Gerüst** (Z. 32 bis 47, 99 bis 130):
```php
class Version001000Date20260816000000 extends SimpleMigrationStep {
	public function changeSchema(IOutput $output, Closure $schemaClosure, array $options): ?ISchemaWrapper {
		/** @var ISchemaWrapper $schema */
		$schema = $schemaClosure();
		$changed = false;

		if (!$schema->hasTable('findling_queue')) {
			$table = $schema->createTable('findling_queue');
			$table->addColumn('id', Types::BIGINT, ['autoincrement' => true, 'notnull' => true, 'length' => 64]);
			$table->addColumn('file_id', Types::BIGINT, ['notnull' => true, 'length' => 64]);
			...
			$table->setPrimaryKey(['id'], 'findling_q_id');
			$table->addIndex(['locked_at'], 'findling_q_locked');
			$changed = true;
		}
		return $changed ? $schema : null;
	}
}
```
**Regeln daraus:** Dateiname = Klassenname (Z. 27 bis 30); `hasTable()`-Schutz (Z. 34 bis 38); `BOOLEAN` nur `notnull => false` (Z. 56 bis 65); Grund-Spalte `STRING length 32`, "no path fits in 32 characters" (Z. 114 bis 117); Status `length 16` (Z. 110 bis 112); kurze Index-Namen mit Präfix (`pii_j_...`). Keine eindeutigen Teilindizes (RESEARCH Pitfall K).

---

### `php/lib/Service/FileAccess.php` (utility)

**Analog:** `AVS/php/lib/Service/FileAccess.php` (Z. 33 bis 50) 1:1:
```php
public static function readableFile(Folder $userFolder, int $fileId): ?File {
	if ($fileId <= 0) {
		return null;
	}
	return self::readableNode($userFolder->getFirstNodeById($fileId));
}

public static function readableNode(?Node $node): ?File {
	if (!$node instanceof File) {
		return null;
	}
	return $node->isReadable() ? $node : null;
}
```
`relativePath` und `ownerOf` entfallen (keine WebDAV-URL, kein occ-Befehl). Neu `downloadBlocked(Node $node): bool`; Vorlage im eigenen Haus ist `AVS/php/lib/Controller/PageController.php` Z. 213 bis 230:
```php
$storage = $file->getStorage();
if (!$storage->instanceOfStorage(ISharedStorage::class)) {
	return true;
}
/** @var ISharedStorage $storage */
return $storage->getShare()->getAttributes()?->getAttribute('permissions', 'download') !== false;
```
Abweichungen für PII (RESEARCH Code-Beispiel "Download-Sperre"): zusätzlich `getHideDownload()`; im `catch` nicht "erlauben" wie AVS, sondern fail-safe "gesperrt"; keine Ausnahme `shareapi_allow_view_without_download` (Owner-Entscheid 5, ohne Admin-Ausnahme).

---

### `php/lib/Service/ReaderContext.php` (utility)

**Analog:** `AVS/php/lib/Service/ReaderContext.php` 1:1, nur Namespace (Z. 48 bis 65):
```php
public function actAs(string $uid, \Closure $work): mixed {
	$previous = $this->userSession->getUser();
	if ($previous !== null && $previous->getUID() === $uid) {
		return $work();
	}
	$member = $this->userManager->get($uid);
	if ($member === null) {
		return $work();
	}
	$this->userSession->setVolatileActiveUser($member);
	try {
		return $work();
	} finally {
		$this->userSession->setVolatileActiveUser($previous);
	}
}
```

---

### `php/lib/Service/ExAppService.php` (service, request-response + streaming)

**Analog:** `AVS/php/lib/Service/ExAppService.php` (758 Zeilen). Übernehmen: Z. 58 bis 142 (Konstanten, sieben Zustände, Versionsmuster, Konstruktor), Z. 355 bis 580 (`backendState`, `exAppInfo`, `determineState`, `drifts`, `appApiEnabledFor`, `rememberState`, `rememberedState`, `ownVersion`, `majorMinor`), Z. 582 bis 697 (Transport). Entfallen: `search`, `excerpt`, `sample`, `removeSample`, `filterHits`, `sampleCount`.

**Transport, einzige Stelle mit `exAppRequest`** (Z. 596 bis 610):
```php
protected function proxyRequest(string $route, string $userId, string $method, array $params, float $timeout): array|IResponse|null {
	$appApi = $this->publicFunctions($userId);
	if ($appApi === null) {
		return null;
	}
	return $appApi->exAppRequest(
		Application::BACKEND_APP_ID,
		$route,
		$userId,
		$method,
		$params,
		['timeout' => $timeout],
	);
}
```
PII-Änderung: Signatur um `array $options = []` erweitern und `['timeout' => $timeout] + $options` übergeben, damit `page()` (10 s, gepuffert) und `output()` (`['stream' => true]`, 120 s) denselben einzigen Aufruf nutzen. So bleibt Gate-Regel 3 ("exAppRequest( in ExAppService.php only, and there once") grün.

**Vier stille Fehlerfälle** (Z. 646 bis 697): Array von AppAPI, Status >= 400, Körper nicht begrenzt, kein JSON-Objekt; jeder Fall `null`, Log nur mit `route`, `status`, `innerMs`. Für `page()` statt JSON-Prüfung: Größendeckel 16 MiB und PNG-Magic `"\x89PNG\r\n\x1a\n"`.

**Zustandsermittlung** (Z. 392 bis 484) 1:1, nur `sampleCount` streichen. Zusätzlich eine Methode wie `searchAllowed()` (Z. 329) als `startAllowed()`: nur `ok` und `version_patch_differs` (`SEARCHABLE_STATES`, Z. 99) plus `companion !== 'missing'`; sonst `POST /jobs` -> 503 `backend_unavailable`.

---

### `php/lib/Controller/JobController.php` (controller, CRUD)

**Analog:** Recheck-Weg `AVS/php/lib/Controller/PageController.php` Z. 183 bis 205 (`resolve`), Antwortform `AVS/php/lib/Controller/SettingsController.php` Z. 53 bis 65.

**Auflösen als angemeldeter Nutzer** (PageController Z. 184 bis 204):
```php
$uid = $this->userSession->getUser()?->getUID();
if (!is_string($uid) || $uid === '') {
	return null;
}
try {
	return $this->readerContext->actAs($uid, function () use ($uid, $fileId): ?array {
		$userFolder = $this->rootFolder->getUserFolder($uid);
		$file = FileAccess::readableFile($userFolder, $fileId);
		return $file === null ? null : [$userFolder, $file, $uid];
	});
} catch (\Throwable $e) {
	// Class name only: a library message is where a path shows up.
	$this->logger->warning('Audio & Video Search: a file for the playback page could not be resolved', [
		'fileId' => $fileId,
		'class' => $e::class,
	]);
	return null;
}
```
**Attribute:** `POST /api/v1/jobs` mit `#[NoAdminRequired]` und `#[FrontpageRoute(verb: 'POST', url: '/api/v1/jobs')]`, CSRF bleibt an (Request-Token über `@nextcloud/axios`). `GET /api/v1/jobs/{id}` mit `#[NoAdminRequired]`, `requirements: ['id' => '\d+']`, Antwort mit `Cache-Control: private, no-store` (Pitfall J). Antwortkörper nur Codes: `{jobId, status, stage, reason, ahead, pagesDone, pagesTotal}`; HTTP-Codes laut UI-SPEC Fläche 1 (201/200/503/403/404/415).

---

### `php/lib/Controller/ReviewController.php` (controller, request-response)

**Analog:** `AVS/php/lib/Controller/PageController.php`.

**Seiten-Route** (Z. 83 bis 86):
```php
#[\OCP\AppFramework\Http\Attribute\NoAdminRequired]
#[\OCP\AppFramework\Http\Attribute\NoCSRFRequired]
#[\OCP\AppFramework\Http\Attribute\FrontpageRoute(verb: 'GET', url: '/play/{fileId}', requirements: ['fileId' => '\d+'])]
public function play(int $fileId): TemplateResponse {
```
**404 ohne Namen** (Z. 274 bis 292) und **Rendern ohne App-Navigation** (Z. 295 bis 307):
```php
$response = $this->render([... 'fileName' => '', 'pageTitle' => $this->l10n->t('Playback'), ...], $startMs);
$response->setStatus(Http::STATUS_NOT_FOUND);
...
$params += ['id-app-navigation' => null];
return new TemplateResponse(Application::APP_ID, 'play', $params, TemplateResponse::RENDER_AS_USER);
```
PII: Startzustand nicht als Template-Parameter, sondern über `IInitialState::provideInitialState('review', [...])` (UI-SPEC Fläche 2; Muster `AVS/php/lib/Settings/Admin.php` Z. 52); Template nur Mount-Div. `markProcessed` der Benachrichtigung beim Öffnen (Muster `SRV/apps/comments/lib/Controller/NotificationsController.php` Z. 98 bis 105, siehe Notifier).

**Seitenbild:** RESEARCH Pattern 3 (Z. 441 bis 457) ist die Vorlage, `DataDisplayResponse` mit `Cache-Control: private, no-store` und `X-Content-Type-Options: nosniff`. `POST /review/{id}/placeholder` mit CSRF, setzt `approved`/`apply`.

---

### `php/lib/Controller/SettingsController.php` (controller)

**Analog:** `AVS/php/lib/Controller/SettingsController.php` Z. 35 bis 65 und 110 bis 113 (nur `state()`; `setSample` entfällt, kein Debug-Weg). Schutz durch fehlende Attribute (Z. 26 bis 30): Admin plus Request-Token.

---

### `php/lib/Settings/Admin.php`, `Section.php` (provider)

**Analog:** `AVS/php/lib/Settings/Admin.php` Z. 44 bis 92, ohne `debug`/`sampleVisible`:
```php
public function getForm(): TemplateResponse {
	$state = $this->state();
	$this->initialState->provideInitialState('bootstrap', $state);
	return new TemplateResponse(Application::APP_ID, 'admin', $state + [
		'checkedAtText' => $this->dateTimeFormatter->formatTime($state['checkedAt'], 'medium'),
		'checkedAtIso' => gmdate('Y-m-d\TH:i:s\Z', $state['checkedAt']),
	], TemplateResponse::RENDER_AS_BLANK);
}
```
`Section.php` 1:1 (`getID` = APP_ID, Priorität 75, `app-dark.svg`), Name "PII Redaction".

---

### `php/templates/admin.php` + `php/css/admin.css` (component)

**Analog:** `AVS/php/templates/admin.php` (177 Zeilen) ohne Debug-Block (ab ca. Z. 150); `AVS/php/css/admin.css` und Banner-Regeln aus `AVS/php/css/play.css` Z. 65 bis 167 (bei PII in `admin.css`/`review.css` mit Präfix `pii-`).

**Skripte im Template, nicht in `getForm()`** (Z. 28 bis 32):
```php
\OCP\Util::addScript('audio_video_search', 'admin');
\OCP\Util::addStyle('audio_video_search', 'play');
\OCP\Util::addStyle('audio_video_search', 'admin');
```
PII: `addScript('pii_redaction', 'pii_redaction-admin')` (Vite-Ausgabe), Stil `admin`.

**"Apps öffnen" mit Routen-Rückfall (AVS 4291faa)** (Z. 50 bis 58):
```php
$urlGenerator = \OCP\Server::get(\OCP\IURLGenerator::class);
$appsUrl = $urlGenerator->linkToRoute('appstore.page.viewApps');
if ($appsUrl === '') {
	$appsUrl = $urlGenerator->linkToRoute('settings.AppSettings.viewApps');
}
```
Hinweis für den Planer: UI-SPEC sagt "Auswahl über die Serverversion"; AVS wählt über "unbekannte Route ergibt leeren String" und ist damit in CI auf 33/34/35 grün. Eines festlegen; die AVS-Form ist belegt.

**Banner-Markup** (Z. 110 bis 125): Zustandscontainer `role="status" aria-live="polite" tabindex="-1"`, alle sieben Banner gerendert, nur der aktuelle ohne `hidden`, Icon als Inline-SVG mit `aria-hidden="true" focusable="false"`, Text über `p($l->t(...))`.

**Bannertext im Statuspaar (AVS 3d07c81)** (play.css Z. 77 bis 95, 133 bis 148):
```css
.avs-banner--error {
	background-color: var(--color-error);
	color: var(--color-error-text);
}
...
.avs-banner .avs-banner__title,
.avs-banner .avs-banner__text {
	max-width: none;
	margin: 0;
	color: inherit;
	line-height: var(--default-line-height);
	overflow-wrap: anywhere;
}
```
**`[hidden]` an ID** (admin.css Z. 122 bis 128):
```css
#avs-admin [hidden] {
	display: none;
}
```

---

### `php/lib/Notification/Notifier.php` (provider, event-driven)

**Analog:** `SRV/apps/files_reminders/lib/Notification/Notifier.php` (Rahmen), aber **ohne** `getFirstNodeById`, ohne Dateinamen und ohne `setRichSubject`-Parameter (Owner 07.11.).

**Rahmen** (übernehmen):
```php
class Notifier implements INotifier {
	public function __construct(
		protected IFactory $l10nFactory,
		protected IURLGenerator $urlGenerator,
	) {
	}

	public function getID(): string {
		return Application::APP_ID;
	}

	public function prepare(INotification $notification, string $languageCode): INotification {
		$l = $this->l10nFactory->get(Application::APP_ID, $languageCode);
		if ($notification->getApp() !== Application::APP_ID) {
			throw new UnknownNotificationException();
		}
		switch ($notification->getSubject()) {
			case 'reminder-due':
				...
				$notification->setRichSubject($subject, [...])->setLink($link);
				break;
			default:
				throw new UnknownNotificationException();
		}
		return $notification;
	}
}
```
PII: `getName()` gibt "PII Redaction" unübersetzt; Fälle `review_ready`, `job_failed`, `job_stale`, `copy_created` mit `setParsedSubject($l->t(...))` und `setParsedMessage(...)` ohne Parameter; `setLink($this->urlGenerator->linkToRouteAbsolute('pii_redaction.review.page', ['jobId' => ...]))`; `setIcon` absolut auf `app-dark.svg`; keine Aktionen. `#[\Override]` weglassen (PHP 8.2).

**Senden** (Vorlage `SRV/apps/files_reminders/lib/Service/ReminderService.php` Z. 180 bis 192):
```php
$notification = $this->notificationManager->createNotification();
$notification
	->setApp(Application::APP_ID)
	->setIcon($this->urlGenerator->getAbsoluteURL($this->urlGenerator->imagePath('files', 'folder.svg')))
	->setUser($user->getUID())
	->setObject('reminder', (string)$reminder->getId())
	->setSubject('reminder-due', [...])
	->setDateTime($reminder->getDueDate());
$this->notificationManager->notify($notification);
```
PII: `setObject('job', (string)$jobId)`, `setSubject('review_ready')` ohne Parameter. Im `catch` NICHT wie das Original `$th->getMessage()` loggen, sondern statischer Satz plus `['exception' => $e]`.

**Erledigt markieren** (`SRV/apps/comments/lib/Controller/NotificationsController.php` Z. 98 bis 105):
```php
$notification = $this->notificationManager->createNotification();
$notification->setApp('comments')
	->setObject('comment', $comment->getId())
	->setSubject('mention')
	->setUser($currentUser->getUID());
$this->notificationManager->markProcessed($notification);
```

---

### `php/lib/Listener/LoadFilesScriptsListener.php` (middleware, event-driven)

**Analog:** `SRV/apps/files_reminders/lib/Listener/LoadAdditionalScriptsListener.php`:
```php
use OCA\Files\Event\LoadAdditionalScriptsEvent;
use OCP\EventDispatcher\Event;
use OCP\EventDispatcher\IEventListener;
use OCP\Util;

/** @template-implements IEventListener<LoadAdditionalScriptsEvent> */
class LoadAdditionalScriptsListener implements IEventListener {
	public function handle(Event $event): void {
		if (!($event instanceof LoadAdditionalScriptsEvent)) {
			return;
		}
		...
		Util::addInitScript(Application::APP_ID, 'init');
	}
}
```
PII: `Util::addInitScript(Application::APP_ID, 'pii_redaction-init')` (der App-Build heißt `js/pii_redaction-init.mjs`; Server-Apps heißen `init`, weil der Server-Build anders benennt). Kein `addStyle` (UI-SPEC: kein eigenes CSS in Dateien). Zweite Vorlage für "nur Skript laden, sonst nichts": `FIN/php/lib/Listener/LoadUnifiedSearchFiltersListener.php`.

---

### `php/lib/Listener/FileLifecycleListener.php` (middleware, event-driven)

**Analog:** `FIN/php/lib/Listener/FileEventListener.php` Z. 56 bis 80 und 149 bis 156.

**Alles in einem Schutz, nur Klassenname loggen**:
```php
public function handle(Event $event): void {
	try {
		if ($event instanceof NodeWrittenEvent) {
			...
			return;
		}
		if ($event instanceof NodeDeletedEvent) {
			...
			return;
		}
	} catch (\Throwable $e) {
		// The type name and nothing else. The message of a filesystem
		// exception carries the path of the file it failed on.
		$this->logger->warning('Findling: an event could not be turned into queued work', [
			'error' => get_class($e),
		]);
	}
}
```
Begründung im Kopfkommentar (Z. 68 bis 75): der Listener läuft im Schreibvorgang des Nutzers, eine Ausnahme ließe den Upload scheitern. PII: offene Aufträge mit `file_id` auf `stale(original_changed)` bzw. `cancelled(original_deleted)` und `task = purge` setzen; nur Ordner-freie Dateiknoten.

---

### `php/lib/BackgroundJob/PublishJob.php` (service, batch)

**Analog:** `FIN/php/lib/BackgroundJobs/SubtreeExpandJob.php` Z. 39, 108 bis 138:
```php
class SubtreeExpandJob extends QueuedJob {
	public function __construct(
		ITimeFactory $time,
		...
		private LoggerInterface $logger,
	) {
		parent::__construct($time);
	}

	protected function run($argument): void {
		$storageId = (int)($argument['storage_id'] ?? 0);
		...
		if ($storageId <= 0 || ...) {
			$this->logger->warning('Findling: dropped a subtree job without a usable argument', [
				'storage_id' => $storageId,
			]);
			return;
		}
```
PII: Argument nur `['jobId' => int]`; ungültiges Argument verwerfen wie oben. Kern (Strom, sha256, `newFile`) aus RESEARCH Code-Beispiel "Ausgabe holen und ablegen" (Z. 598 bis 626); der Strom kommt über `ExAppService::output()`, nicht über einen eigenen Aufruf.

---

### `php/src/init.ts` (component, Dateiaktion)

**Analog:** `SRV/apps/files_reminders/src/files-init.ts` und `.../files_actions/clearReminderAction.ts`.

**Registrierung**:
```ts
import { registerFileAction } from '@nextcloud/files'
import { action as clearAction } from './files_actions/clearReminderAction.ts'
registerFileAction(clearAction)
```
**Aktionsobjekt**:
```ts
import type { IFileAction } from '@nextcloud/files'
import AlarmOffSvg from '@mdi/svg/svg/alarm-off.svg?raw'
import { t } from '@nextcloud/l10n'

export const action: IFileAction = {
	id: 'clear-reminder',
	displayName: () => t('files_reminders', 'Clear reminder'),
	iconSvgInline: () => AlarmOffSvg,
	enabled: ({ nodes }) => {
		if (nodes.length !== 1) {
			return false
		}
		...
	},
	async exec({ nodes }) {
		const node = nodes.at(0)!
		...
		return null
	},
	order: 19,
}
```
PII: `id: 'pii_redaction-start'`, `order: 60`, Icon `eye-off-outline` (UI-SPEC: Pfaddaten als eigene `src/icon.svg` mit `?raw`, oder `@mdi/svg` nur wenn exakt gepinnt). `enabled()` nach RESEARCH Pattern 1; `downloadable()` ist wortgleich zu `SRV/apps/files/src/utils/permissions.ts` Z. 17 bis 38 (`isDownloadable`). Toasts nach UI-SPEC Fläche 1 über `showMessage(node, {type, timeout, close})` mit per `document.createElement` gebautem Knoten, nie `isHTML`.

---

### `php/src/review.ts`, `php/src/ReviewPlaceholder.vue`, `php/templates/review.php` (component, polling)

**Analog Mount:** `SRV/apps/encryption/src/settings-admin.ts`:
```ts
import { createApp } from 'vue'
import SettingsAdmin from './views/SettingsAdmin.vue'

const app = createApp(SettingsAdmin)
app.mount('#encryption-settings-section')
```
**Template nur Mount-Div** (`SRV/apps/encryption/templates/settings.php`): `<div id="encryption-settings-section"></div>`. PII: `<div id="pii-review" class="pii-review"></div>`, Skript über `\OCP\Util::addScript('pii_redaction', 'pii_redaction-review')` im Template wie AVS `templates/play.php` Z. 25 bis 26.

**Startzustand und Nc-Komponenten** (`SRV/apps/encryption/src/views/SettingsAdmin.vue` Z. 6 bis 22, 26 bis 30):
```vue
<script setup lang="ts">
import { loadState } from '@nextcloud/initial-state'
import { t } from '@nextcloud/l10n'
import { NcNoteCard } from '@nextcloud/vue'
import { ref } from 'vue'

const adminSettings = loadState<{ ... }>('encryption', 'adminSettings')
</script>
<template>
	<NcNoteCard v-if="..." type="warning">
		{{ t('encryption', '...') }}
	</NcNoteCard>
</template>
```
UI-SPEC-Abweichungen: `NcNoteCard` ohne `heading`-Prop, Titel und Satz als `<p class="pii-note__title|text">`; Polling 3 s mit Pause bei `visibilityState === 'hidden'` und Rückoff 3/6/12/30 s ohne Vorbild (eigene Logik, nur Textinterpolation, nie `v-html`).

---

### `php/src/admin.ts` (component)

**Analog:** `AVS/php/js/admin.js` (185 Zeilen) als TypeScript-Port: liest `bootstrap` aus dem Startzustand, schaltet `hidden`-Attribute und ersetzt Textknoten, baut kein Markup; Fokus nach "Erneut prüfen" auf `#pii-backend-state`. Debug-Teil entfällt.

---

### `php/appinfo/info.xml`, `routes.php`, `composer.json`, `phpunit.xml`, `tests/bootstrap.php` (config, test)

**Analoga:** AVS gleichnamig.
- `info.xml` (AVS Z. 16 bis 63): Kopfkommentar zu Lockstep; `<namespace>PiiRedaction</namespace>`; `<nextcloud min-version="33" max-version="35"/>`; Einstellungen auf einer Zeile (Z. 62). Neu: `<background-jobs>` nicht nötig (PublishJob ist `QueuedJob`), kein `<commands>`.
- `routes.php` (AVS) 1:1: beide Arrays leer, alle Routen über Attribute.
- `composer.json` (AVS): `"OCA\\PiiRedaction\\": "lib/"`, `"OCA\\PiiRedaction\\Tests\\": "tests/"`; doppelte Backslashes erhalten (RESEARCH Pitfall 1, Gate-Regel 9).
- `phpunit.xml` 1:1.
- `tests/bootstrap.php` (AVS Z. 23 bis 74): `rtrim($serverRoot, '/\\')` mit beiden Backslashes; Texte "PII Redaction test bootstrap", Pfad `apps/pii_redaction`.

**phpunit-Testgerüst** (`AVS/php/tests/Unit/GatewayControllerTest.php` Z. 1 bis 80): `#[CoversClass(...)]`, `final class ... extends TestCase`, zustandsbehaftete `IUserSession`-Mock mit `setVolatileActiveUser`, `BACKEND_APP_ID` per Reflection gelesen. Keine Hilfsmethode namens `status()` o. ä. (Gate-Regel 10).

---

### `php/package.json`, `vite.config.ts`, `tsconfig.json` (config)

**Analog (nur Form):** `SRV/build/frontend/vite.config.ts` Z. 6, 43 bis 44, 92:
```ts
import { createAppConfig } from '@nextcloud/vite-config'
...
	files_reminders: {
		init: resolve(import.meta.dirname, 'apps/files_reminders/src', 'files-init.ts'),
...
export default createAppConfig(Object.fromEntries(viteModuleEntries), {
```
PII-Fassung: `createAppConfig({ init: 'src/init.ts', review: 'src/review.ts', admin: 'src/admin.ts' })` (Ausgabe `js/pii_redaction-<name>.mjs`). Versionen exakt nach RESEARCH Standard Stack, `vite` 7.3.7. `php/js/` in `.gitignore`.

---

### `backend/src/pii_redaction_backend/main.py` (provider)

**Analog:** `AVS/backend/src/audio_video_search_backend/main.py`.

**Hintergrundaufgaben mit Abschaltfrist** (Z. 46 bis 67):
```python
_TASKS: set[asyncio.Task[None]] = set()

def start_background(coroutine: Coroutine[Any, Any, None], name: str) -> asyncio.Task[None]:
    task = asyncio.get_running_loop().create_task(coroutine, name=name)
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return task
```
**Lifespan** (Z. 117 bis 140): `logs.configure`, `set_handlers` nur einmal, Store öffnen in `asyncio.to_thread`, `start_background(companion.run_periodic(), "companion")`, im `finally` abbrechen. PII: zusätzlich `start_background(runner.run(...), "runner")`.
**App** (Z. 143 bis 146): `FastAPI(..., docs_url=None, redoc_url=None, openapi_url=None)`, `AppAPIAuthMiddleware`, `build_router()`.
**Logs:** AVS Z. 78 und 112 rufen `LOGGER.exception(...)`; das verbietet RESEARCH Entscheid 10 (AST-Gate "kein `logger.exception`"). Ersetzen durch `LOGGER.error("...", extra={"exc_type": type(exc).__name__})`.

---

### `backend/src/pii_redaction_backend/companion.py` (service)

**Analog:** `AVS/backend/src/audio_video_search_backend/companion.py` 1:1 (133 Zeilen); `_judge` (Z. 86 bis 102) mit 412 als "unknown", nicht als Fehler (AVS-Fix 7e423e1). Einzige Änderung: `LOGGER.exception` in Z. 132 wie oben ersetzen.

---

### `backend/src/pii_redaction_backend/nc.py`, `tasks/fetch.py`, `tasks/client.py` (service, streaming/Pull)

**Analog:** `AVS/backend/src/audio_video_search_backend/nc.py` (208 Zeilen) und `FIN/backend/src/findling/nc/queue.py`.

**Grenzregel** (`AVS/backend/tests/test_boundary.py`): nur `nc.py` darf `nc_py_api`, `httpx`, `niquests` usw. importieren. RESEARCH skizziert `tasks/client.py` und `tasks/fetch.py`; entweder liegen die HTTP-Aufrufe in `nc.py` und `tasks/` ruft nur dessen Funktionen, oder `test_boundary.py` bekommt eine zweite erlaubte Datei. Empfehlung: in `nc.py` lassen (eine lesbare Datei für "was darf der Container in Nextcloud").

**Signierte Kopfzeilen** (Z. 112 bis 121):
```python
def app_api_headers(header_user: str = "") -> dict[str, str]:
    secret = os.environ.get("APP_SECRET", "")
    return {
        "AA-VERSION": os.environ.get("AA_VERSION", _DEFAULT_AA_VERSION),
        "EX-APP-ID": os.environ.get("APP_ID", ""),
        "EX-APP-VERSION": os.environ.get("APP_VERSION", ""),
        "AUTHORIZATION-APP-API": b64encode(f"{header_user}:{secret}".encode()).decode(),
        "OCS-APIRequest": "true",
    }
```
**Gateway-Strom mit sha256** (Z. 144 bis 164):
```python
async with client.stream(
    "GET", gateway_url(file_id), params={"userId": user_id}, headers=app_api_headers()
) as response:
    if response.status_code in _DENIED_STATUS:
        return FetchResult(sha256=None, size=0, error=GATEWAY_DENIED)
    if response.status_code >= _FIRST_ERROR_STATUS:
        return _failed(file_id, "status", status=response.status_code)
    async for chunk in response.aiter_bytes(CHUNK_SIZE):
        size += len(chunk)
        if size > max_bytes:
            return _failed(file_id, "too_large")
        digest.update(chunk)
```
PII-Änderungen (RESEARCH Code-Beispiel "Gateway-Strom mit Etag"): Pfad `/ocs/v2.php/apps/pii_redaction/api/v1/files/{job_id}`, Query `token`, 409 -> `stale`, Bytes nach `work/<job>/src` schreiben, `X-Pii-Etag` zurückgeben. `new_gateway_client()` (Z. 134 bis 136) mit `follow_redirects=False` 1:1.

**Handshake** (Z. 188 bis 208) 1:1 mit neuem Pfad.

**Claim/Ack-Client** (`FIN/backend/src/findling/nc/queue.py` Z. 541 bis 601, 603 bis 656): eine Klasse an einen Client gebunden; jede Ausnahme bei Claim -> `ClaimResult(unavailable=True)` mit `LOGGER.debug` (Begründung Z. 561 bis 576: der Aufrufer zählt Fehlrunden und entscheidet über Log und Rückoff); Antwort feldweise prüfen (`_mapping`, `_positive_int`, Z. 364 bis 400). Findling nutzt `LOGGER.warning("discarded %d ...", n)` mit `%d`; das verbietet das PII-AST-Gate (Literal ohne Platzhalter), also Zahl in `extra=`.

---

### `backend/src/pii_redaction_backend/logs.py` (utility)

**Analog:** heutiges `src/pii_redaction/logs.py` = `AVS/.../logs.py` (Z. 28 bis 60). Zu ändern laut Entscheid 10:
```python
for key, value in vars(record).items():
    if key not in _STANDARD_ATTRIBUTES and not key.startswith("_"):
        line[key] = value if isinstance(value, str | int | float | bool | None) else repr(value)
if record.exc_info:
    line["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
    line["exc"] = self.formatException(record.exc_info)
```
wird zu: nur Schlüssel aus einer `Final`-Allowlist (`job_id, task, stage, status, reason, pages, bytes, duration_ms, attempt, http_status, exc_type, child, rss_kb`), `exc`/`formatException` entfällt, statt dessen `module:lineno` des innersten eigenen Rahmens. `uvicorn.access` abschalten statt umleiten.

---

### `backend/src/pii_redaction_backend/config.py` (config)

**Analog:** `AVS/.../config.py` (72 Zeilen) 1:1; Präfix bleibt `PII_REDACTION_` (RESEARCH Runtime State), `FALLBACK_STORAGE_DIRNAME = "pii_redaction_backend"`.

---

### `backend/src/pii_redaction_backend/api/__init__.py`, `api/status.py`, `api/pages.py`, `api/output.py` (route)

**Analog:** `AVS/.../api/__init__.py` (Z. 29 bis 70: `Services` mit Lock, `services()` -> 503 vor dem Öffnen, `run_locked`, `build_router`) und `AVS/.../api/status.py` (Z. 40 bis 56). `status` liefert zusätzlich `lastChild: {kind, rssKb, ms}` (Entscheid 12); `sampleCount` entfällt. Kommentar in status.py Z. 3 ("Route access level ADMIN in appinfo/info.xml") ändern: es gibt keine Route mehr, nur der signierte Weg erreicht sie. `pages.py` liefert `FileResponse` von `work/<job>/page-1.png`, `output.py` die Ausgabe-PDF; beide nur im passenden Status.

---

### `backend/src/pii_redaction_backend/resources/hardware.py`, `memory_guard.py` (utility)

**Analog:** `FIN/backend/src/findling/hardware.py`, `memory_guard.py` als Kopie (Importpfad `findling.hardware` -> `pii_redaction_backend.resources.hardware`).

**Kern** (memory_guard Z. 71 bis 94):
```python
def headroom_bytes(*, cgroup_root: Path = CGROUP_ROOT, meminfo: Path = MEMINFO) -> int | None:
    available = meminfo_bytes(meminfo, "MemAvailable")
    limit = memory_limit(cgroup_root)
    if limit is None:
        return available
    anon = anon_bytes(cgroup_root)
    if anon is None:
        return available
    within_limit = max(0, limit - anon)
    return within_limit if available is None else min(within_limit, available)


def admits(headroom: int | None, *, need: int) -> bool:
    """True when a readable headroom covers ``need``; unreadable is never admitted."""
    return headroom is not None and headroom >= need
```
Bedarfskonstanten `render` 512 MiB, `soffice` 1 GiB mit Vermerk "vorläufig".

---

### `backend/src/pii_redaction_backend/workers/child.py` (utility)

**Analog (teilweise):** `FIN/backend/src/findling/extract/sandbox.py` Z. 150 bis 169 (Gruppen-Kill):
```python
def _kill_child_tree(process: SpawnProcess) -> None:
    if sys.platform != "win32" and process.pid is not None:
        import signal

        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    process.kill()
```
und Z. 105 bis 118 (rlimit nur auf Linux, Windows-Tests laufen ohne). Findling nutzt einen dauerhaften `multiprocessing`-Spawn-Kind; PII Phase 1 nimmt die einfachere Form aus RESEARCH Pattern 4 (`asyncio.create_subprocess_exec`, `env=SAFE_ENV`, `start_new_session=True`, stdout/stderr `DEVNULL`).

---

### `backend/src/pii_redaction_backend/store/schema.sql`, `repo.py` (model)

**Analog:** `AVS/.../store/schema.sql` Z. 1 bis 18 (Kopf, `meta`-Tabelle, alles `IF NOT EXISTS`) und `AVS/.../store/repo.py` Z. 1 bis 60 (SQL nur als `Final`-Konstanten mit Platzhaltern, geschlossene Grundliste `STATE_REASONS`, `_STATE_CODE`-Regex, `SCHEMA_VERSION`). Phase 1 speichert keinen Text; Tabelle `jobs(job_id, task, stage, sha256, size, etag_seen, created_at)` ohne Namen.

---

### `backend/appinfo/info.xml`, `backend/Dockerfile` (config)

**Analog:** `AVS/backend/appinfo/info.xml` Z. 60 bis 117 und `AVS/backend/Dockerfile`.
- `<routes>`-Block (AVS Z. 71 bis 107, heutiges PII Z. 69 bis 77) wird zu leerem `<routes/>` (Entscheid 9). Hinweis aus `AVS/scripts/release/store-archive.sh` Z. 55 bis 60: die Store-Transformation verwirft den Routes-Block, AppAPI liest ihn aus dem Archiv; `stage-backend` kopiert `info.xml` byteidentisch (`cmp`), also bleibt `<routes/>` im Archiv erhalten.
- `environment-variables` wie AVS Z. 108 bis 115 mit `PII_REDACTION_LOG_LEVEL`.
- Dockerfile: Laufzeit-Stufe AVS Z. 53 bis 61 (Label, `hadolint ignore=DL3008`, `--no-install-recommends`, `rm -rf /var/lib/apt/lists/*`), gepinnte Zusatzpakete wie Z. 69 bis 75 (`wngerman=...` plus `test -s`-Prüfung). PII: `libreoffice-writer-nogui` ungepinnt, Schriften laut RESEARCH Standard Stack; uid 10001 und Datenverzeichnis `/nc_app_pii_redaction_backend_data` wie Z. 76 bis 82.

---

### Backend-Tests (test)

- `test_lockstep_versions.py`: AVS 1:1 (Z. 1 bis 40 Kopf, vier Werte plus Serverfenster plus Matrix, jede Regel mit Selbsttest).
- `test_php_gates.py`: AVS (Z. 9 bis 32 Regelliste, Konstanten Z. 44 bis 64) mit neuen Werten; zusätzliche Regeln laut RESEARCH Validation: jede Prüfseiten-Route ruft den Recheck, Migrationsspalten ohne `name|path|text|value|snippet|title|comment`, Log-Kontext-Allowlist `jobId, fileId, status, reason, app, exception`. Jede neue Regel mit mutiertem Beispiel, das sie auslöst (AVS Z. 349 bis 445).
- `test_release_archives.py`: AVS 1:1 plus Prüfung `js/pii_redaction-init.mjs` im Begleit-Archiv.
- `test_trilingual.py`: AVS (`german_twin_findings`, `french_spacing_findings`, `placeholder_findings`, `js_twin_findings`, Z. 92 bis 145) erweitert um `php/src/**/*.{ts,vue}`.
- `test_boundary.py`: AVS 1:1 (siehe nc.py).

---

### `.github/workflows/deploy-harp.yml` (config, batch)

**Analog:** `AVS/.github/workflows/deploy-harp.yml` (887 Zeilen).
- Matrix als `include`-Liste (Z. 77 bis 101), sechs Beine, PHP 8.2/8.2/8.3. Neu: siebtes Bein `stable35`/`ubuntu-24.04` mit MariaDB-Dienstcontainer (Owner 07.11.); `test_lockstep_versions.py` liest die Matrix (`test_the_matrix_expression_reads_the_include_list_and_nothing_else`) und muss das Zusatzfeld (z. B. `database`) tolerieren.
- Checkout-Reihenfolge Server, app_api, App (Z. 103 bis 121); zusätzlich `nextcloud/notifications` im selben Zweig nach `apps/notifications` (Pitfall A).
- Installation (Z. 130 bis 147): `composer run serve` mit `NEXTCLOUD_WORKERS=8` (Pitfall B); Debug-Schalter entfällt (Owner: ohne Debug).
- PHP-App (Z. 149 bis 153): vorher `npm ci && npm run build` in `app-src/php`, dann `mv app-src/php apps/pii_redaction`.
- Schritt "No test file name in the Nextcloud log or the container log" (Z. 516) wird zum Kanarien-Schritt mit Positivkontrolle.
- "The settings form is registered and the status answers through HaRP" (Z. 259) wird Negativprüfung "No browser route".
- Job `upgrade` ab Z. 577 inkl. viewer-Checkout (Z. 618 bis 627), `occ upgrade` (Z. 818), `app_api:app:update` (Z. 832), Volume-Abgleich (Z. 845).

### `ci/seed.sh`, `ci/playwright/*` (utility, test)

**Analog:** `AVS/ci/seed.sh` (Nutzer per `OC_PASS=... occ user:add --password-from-env`, Z. 51; Sprache vor dem ersten Login Z. 71 bis 74; groupfolders aus Store oder Tarball Z. 80 bis 95; Freigabe mit Download-Sperre über OCS mit `attributes=[{"scope":"permissions","key":"download","value":false}]`, Z. 129 bis 135; `fileids.env`). PII: zusätzlich ACL `-read` für carol, `occ user:setting <de-Nutzer> core lang de` für das `de`-Projekt.

`AVS/ci/playwright/playwright.config.ts` 1:1 (Raster Z. 23 bis 54, Projekte Z. 67 bis 82); zusätzlich ein Projekt `de-du-w375-light` (UI-SPEC Raster). `helpers.ts` Z. 20 bis 95 (`users`, `reviewer`, `gridOnly`, `login`, `screenshot`) 1:1; `expectMediaSettled` (Z. 124) wird zu einer Bild-Bereitschaft nach UI-SPEC (`img.complete`, `decode()`, kein `aria-busy`).

### `scripts/release/store-archive.sh` (utility, file-I/O)

**Analog:** `AVS/scripts/release/store-archive.sh` Z. 42 bis 70:
```sh
stage_companion() {
	stage="$1"
	app="${stage}/audio_video_search"
	mkdir -p "${app}"
	for d in appinfo lib templates js css img l10n; do
		cp -R "php/${d}" "${app}/${d}"
	done
	cp LICENSE CHANGELOG.md "${app}/"
	find "${app}" -name '.gitkeep' -delete
```
PII: `js` kommt aus dem Build; danach `test -s "${app}/js/pii_redaction-init.mjs"`.

## Shared Patterns

### Fremd-ExApp-Wächter
**Source:** `AVS/php/lib/Controller/GatewayController.php` Z. 113 bis 125
**Apply to:** jede Methode mit `#[ExAppRequired]` (Gateway, Handshake, Queue claim/progress/ack); Gate-Regel 1 verlangt `$foreign = $this->rejectForeignCaller();` als erste Anweisung.
```php
private function rejectForeignCaller(): ?DataResponse {
	$callerAppId = $this->request->getHeader('EX-APP-ID');
	if ($callerAppId === Application::BACKEND_APP_ID) {
		return null;
	}
	$this->logger->warning('Audio & Video Search: content gateway called by a foreign ExApp', ['app' => $callerAppId]);
	return new DataResponse(
		['error' => 'This route is reserved for the Audio & Video Search backend.'],
		Http::STATUS_FORBIDDEN,
	);
}
```

### Recheck je Anfrage
**Source:** `AVS/php/lib/Service/ReaderContext.php` Z. 48 bis 65 + `FileAccess.php` Z. 33 bis 50
**Apply to:** JobController (Start, Status), ReviewController (Seite, Bild, Platzhalter), GatewayController, PublishJob. Eine Funktion `FileAccess::recheck($job, $uid)` (lesbar, keine Sperre, Etag), damit ein Gate prüfen kann, dass jede Route sie ruft.

### Logs ohne Inhalt (PHP)
**Source:** `FIN/php/lib/Controller/QueueController.php` Z. 133 bis 144, `AVS/php/lib/Controller/PageController.php` Z. 196 bis 203
**Apply to:** alle PHP-Dateien
```php
} catch (\Throwable $e) {
	$this->logger->error('Findling: could not hand out a batch', ['exception' => $e]);
	return new DataResponse(['error' => 'Queue is not available.'], Http::STATUS_INTERNAL_SERVER_ERROR);
}
```
Statischer englischer Satz mit App-Präfix "PII Redaction: ", Kontext nur `jobId, fileId, status, reason, app, exception` (bzw. `class` bei Warnungen). Nie `getName()`, `getPath()`, `$path` (Gate-Regel 6), nie `$e->getMessage()`.

### Logs ohne Inhalt (Python)
**Source:** `AVS/.../nc.py` Z. 139 bis 141, `companion.py` Z. 112 bis 114
**Apply to:** alle Backend-Module
```python
LOGGER.warning("gateway read failed", extra={"file_id": file_id, "reason": reason, "status": status})
```
Literal ohne Platzhalter, Werte nur über `extra=`, kein `LOGGER.exception`, kein f-String.

### Geschlossene Listen statt Freitext
**Source:** `FIN/php/lib/Controller/QueueController.php` Z. 466 bis 490; `AVS/.../store/repo.py` Z. 41 bis 48; `FIN/php/lib/Migration/...` Z. 110 bis 117
**Apply to:** Status, Grund, Stufe, Aufgabe, Betreff der Benachrichtigung, Sprachkürzel; in PHP, Python, DB-Spaltenlänge.

### Container-Antwort ist außerhalb der Vertrauensgrenze
**Source:** `AVS/php/lib/Service/ExAppService.php` Z. 28 bis 33 und 646 bis 697
**Apply to:** Queue-Meldungen, Seitenbild (Magic, Größe), Ausgabe (sha256, Größe), `/status`.

### Admin-Statusbereich und Bannerfarben
**Source:** `AVS/php/templates/admin.php` Z. 50 bis 58, 110 bis 135; `AVS/php/css/play.css` Z. 65 bis 167; `AVS/php/css/admin.css` Z. 122 bis 128
**Apply to:** `php/templates/admin.php`, `php/css/admin.css`; Präfix `pii-`, `[hidden]` nur unter `#pii-admin` bzw. `#pii-review` (Gate-Regel 11).

### Gate mit Selbsttest
**Source:** `AVS/backend/tests/test_php_gates.py` Z. 349 bis 445, `test_lockstep_versions.py` Z. 128 bis 183
**Apply to:** jede neue statische Regel (Recheck-Regel, Migrationsspalten, Logkontext, Log-AST, Routen-leer); ohne mutiertes Beispiel, das die Regel auslöst, gilt sie als nicht vorhanden.

### PHP-Dateikopf
**Source:** alle AVS-PHP-Dateien; Gate-Regel 7
```php
<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\...;
```
Kein `#[\Override]` (PHP 8.2), Klassen `final`, außer `ExAppService` (Mock-Begründung AVS Z. 54 bis 57).

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `php/lib/Service/PublishService.php` / Kern von `PublishJob` | service | file-I/O | Keine App schreibt bisher per `newFile()` mit Strom aus `exAppRequest(stream)`; RESEARCH Code-Beispiel "Ausgabe holen und ablegen" verwenden |
| Lease-Regel "ein Auftrag zur Zeit" in `JobMapper` | model | Lease | Findling claimt Bänder ohne globale Einzelregel; RESEARCH Pattern 2 plus MariaDB-Bein |
| `php/src/ReviewPlaceholder.vue` (Polling, Fokus, Live-Region) | component | polling | Kein Vue-Code in eigenen Repos; nur Mount/`loadState` aus SRV encryption |
| `php/package.json`, `vite.config.ts`, `tsconfig.json` | config | n. a. | Kein eigenständiger App-Build mit `@nextcloud/vite-config` vorhanden; SRV-Build ist der Server-Sammelbuild |
| `backend/src/pii_redaction_backend/workers/render.py` | utility | file-I/O | PyMuPDF-Rendering neu |
| `backend/src/pii_redaction_backend/workers/soffice.py` | utility | file-I/O | LibreOffice-Aufruf neu (RESEARCH Pattern 4 und STACK "LibreOffice im Container") |
| `backend/src/pii_redaction_backend/workers/placeholder.py` | utility | file-I/O | Einseitige PDF nach UI-SPEC Fläche 4 |
| `backend/src/pii_redaction_backend/runner/runner.py` | service | batch | Semaphore 1 plus Wächter plus Rückoff; nur Bausteine in AVS main.py und FIN queue.py |
| `ci/make_fixtures.py` | utility | file-I/O | Kanarien-PDF/DOCX/ODT per stdlib neu |
| `ci/measure.sh`, Mess-Schritte in `docker.yml`/`deploy-harp.yml` | utility | batch | RESEARCH Entscheid 12 |
| Kanarien-Schritt in `deploy-harp.yml` | config | batch | AVS prüft nur Testdateinamen (Z. 516); Erweiterung um DB-Dump, `state.db`, Positivkontrolle neu |

## Hinweise für den Planer (Abweichungen zwischen Vorbild und Vorgabe)

1. **Gate-Regel 3** ("`exAppRequest(` genau einmal in `ExAppService.php`"): PII braucht `stream => true` für die Ausgabe. Lösung: `proxyRequest` um `array $options` erweitern, keinen zweiten Aufruf schreiben.
2. **`test_boundary.py`** erlaubt HTTP-Bibliotheken nur in `nc.py`; die RESEARCH-Struktur `tasks/client.py`, `tasks/fetch.py` muss das beachten.
3. **"Apps öffnen"**: AVS wählt die Route über leeren Rückgabewert von `linkToRoute`, UI-SPEC nennt Serverversion. Eine Form festlegen.
4. **Notifier-Vorbild** `files_reminders` setzt Dateinamen in den Betreff und loggt `getMessage()`; beides nicht übernehmen.
5. **`LOGGER.exception`** steht in AVS `main.py` Z. 78, 112 und `companion.py` Z. 132; RESEARCH verbietet es per AST-Gate.
6. **Download-Sperre**: AVS erlaubt im Fehlerfall und respektiert `shareapi_allow_view_without_download`; PII sperrt fail-safe und kennt keine Ausnahme.
7. **Lease-Spalte**: Findling `locked_at DATETIME` mit Epoche als Frei-Marke; RESEARCH sieht `lease_until BIGINT`. Bei BIGINT bleibt `ITimeFactory::getTime()` die einzige Uhr.
8. **Routen leer**: heutiges `appinfo/info.xml` hat `^/status$` ADMIN; die Skeleton-CI prüft "admin route answers through HaRP". Beides wird umgedreht.

## Metadata

**Analog search scope:** `C:/Users/Student/nextcloud-audio-video-search` (`php/`, `backend/`, `ci/`, `.github/workflows/`, `scripts/release/`), `C:/Users/Student/nextcloud-search` (`php/lib/{Db,Controller,Migration,Listener,BackgroundJobs,AppInfo}`, `backend/src/findling/{memory_guard,hardware}.py`, `nc/queue.py`, `extract/sandbox.py`), `C:/Users/Student/.cache/findling-phpunit/server` (stable34: `apps/files_reminders`, `apps/encryption`, `apps/comments`, `apps/files/src/utils/permissions.ts`, `build/frontend/vite.config.ts`), heutiges Skeleton in `C:/Users/Student/nextcloud-pii-redaction`
**Files scanned:** ca. 45 gelesen oder gezielt durchsucht
**Pattern extraction date:** 2026-11-07
