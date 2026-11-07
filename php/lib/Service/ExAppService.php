<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Service;

use OCA\PiiRedaction\AppInfo\Application;
use OCP\App\IAppManager;
use OCP\AppFramework\Utility\ITimeFactory;
use OCP\Http\Client\IResponse;
use OCP\IAppConfig;
use OCP\IGroupManager;
use OCP\IUserManager;
use Psr\Container\ContainerExceptionInterface;
use Psr\Container\NotFoundExceptionInterface;
use Psr\Log\LoggerInterface;

/**
 * The one and only place in this app that talks to the container (taken over
 * from Audio & Video Search, reduced to what PII Redaction needs).
 *
 * backend/tests/test_php_gates.py (rule 3) holds the AppAPI call to exactly
 * one line of this file. Every route of the container goes through
 * proxyRequest: the JSON calls through call(), the page image buffered and
 * capped, the output as a stream (orchestrator decision 1).
 *
 * The container is outside the trust boundary. A JSON answer has to be a
 * bounded object, a page image has to be a PNG of at most 16 MiB with status
 * 200, an output stream needs status 200. Everything else ends in null, and
 * nothing the container says reaches a log: only status codes and class names.
 *
 * The contract, as the container implements it (01-SKELETON.md):
 *   GET /status                 -> {version, ready, companion, busy, lastChild}
 *   GET /jobs/{id}/pages/{n}.png -> PNG or 404
 *   GET /jobs/{id}/output        -> PDF stream or 404
 *
 * The state of the other half is read in two steps: the registration in
 * AppAPI first, without a network call, then GET /status. Seven codes come out
 * of it; a job may only start in ok and version_patch_differs, and only while
 * the container does not report the PHP half as missing.
 *
 * @final Not meant to be extended. The keyword is missing only because PHPUnit
 *        cannot double a final class, and the AppAPI class is absent from the
 *        autoload space of the unit suite, so proxyRequest is doubled there.
 */
class ExAppService {
	/** GET /status: the admin page and the start of a job wait for it. */
	public const STATUS_TIMEOUT_SECONDS = 1.5;
	/** One rendered page through the review page. */
	public const PAGE_TIMEOUT_SECONDS = 10.0;
	/** The finished copy, streamed into the user's folder. */
	public const OUTPUT_TIMEOUT_SECONDS = 120.0;

	/** Ceiling of one page image (provisional, phase 2 hardens it). */
	public const MAX_PAGE_BYTES = 16777216;
	/** Ceiling of a JSON answer before it is parsed. */
	private const MAX_BODY_BYTES = 1048576;
	private const PNG_MAGIC = "\x89PNG\r\n\x1a\n";

	/** The version of the other half, as it was last reported. */
	public const KEY_BACKEND_VERSION = 'backend_app_version';
	/** The last verdict, as JSON of codes, versions and numbers only. */
	public const KEY_BACKEND_STATE = 'backend_state';
	/** How long a verdict is trusted before it is determined again. */
	public const STATE_MAX_AGE_SECONDS = 60;

	/** The seven states of the other half, in the order they are checked. */
	public const STATE_NO_APP_API = 'no_app_api';
	public const STATE_BACKEND_MISSING = 'backend_missing';
	public const STATE_BACKEND_DISABLED = 'backend_disabled';
	public const STATE_VERSION_DRIFT = 'version_drift';
	public const STATE_BACKEND_UNREACHABLE = 'backend_unreachable';
	public const STATE_VERSION_PATCH_DIFFERS = 'version_patch_differs';
	public const STATE_OK = 'ok';

	public const STATES = [
		self::STATE_NO_APP_API,
		self::STATE_BACKEND_MISSING,
		self::STATE_BACKEND_DISABLED,
		self::STATE_VERSION_DRIFT,
		self::STATE_BACKEND_UNREACHABLE,
		self::STATE_VERSION_PATCH_DIFFERS,
		self::STATE_OK,
	];

	/** The two states in which a job may start. */
	private const STARTABLE_STATES = [self::STATE_OK, self::STATE_VERSION_PATCH_DIFFERS];

	/** What GET /status may say about the PHP half, seen from the container. */
	public const COMPANION_VALUES = ['ok', 'missing', 'unknown'];
	/** The kinds of child process the container reports in lastChild. */
	private const CHILD_KINDS = ['render', 'soffice', 'placeholder'];

	/**
	 * What a version has to look like before it is compared or stored: major
	 * and minor mandatory, patch optional, a prerelease tail allowed.
	 */
	private const VERSION_PATTERN = '/^\d{1,5}\.\d{1,5}(?:\.[0-9A-Za-z][0-9A-Za-z.-]{0,19})?$/D';

	public function __construct(
		private IAppManager $appManager,
		private IUserManager $userManager,
		private IAppConfig $appConfig,
		private LoggerInterface $logger,
		private IGroupManager $groupManager,
		private ITimeFactory $timeFactory,
	) {
	}

	// -- the calls of the contract ----------------------------------------------

	/**
	 * GET /status, field by field, or null when the container gives no
	 * usable answer.
	 *
	 * @return array{version:?string,ready:bool,companion:?string,busy:bool,lastChild:?array{kind:string,rssKb:int,ms:int}}|null
	 */
	public function status(?string $uid = null): ?array {
		$uid ??= $this->firstAdmin();
		if ($uid === null) {
			return null;
		}
		$raw = $this->call('/status', $uid, self::STATUS_TIMEOUT_SECONDS);
		if ($raw === null) {
			return null;
		}

		$version = is_string($raw['version'] ?? null) ? $this->versionOrNothing($raw['version']) : '';
		$companion = $raw['companion'] ?? null;

		return [
			'version' => $version !== '' ? $version : null,
			'ready' => ($raw['ready'] ?? null) === true,
			'companion' => is_string($companion) && in_array($companion, self::COMPANION_VALUES, true) ? $companion : null,
			'busy' => ($raw['busy'] ?? null) === true,
			'lastChild' => self::lastChild($raw['lastChild'] ?? null),
		];
	}

	/**
	 * Page $n of a job as PNG bytes, or null. The body is read up to one byte
	 * past the ceiling, so a container that sends more is refused without
	 * holding all of it.
	 */
	public function page(int $jobId, int $n, string $uid): ?string {
		if ($jobId <= 0 || $n <= 0) {
			return null;
		}
		$response = $this->proxyRequest("/jobs/{$jobId}/pages/{$n}.png", $uid, 'GET', [], self::PAGE_TIMEOUT_SECONDS);
		if (!$response instanceof IResponse) {
			$this->logger->warning('PII Redaction: page image not delivered', ['jobId' => $jobId]);
			return null;
		}
		if ($response->getStatusCode() !== 200) {
			$this->logger->info('PII Redaction: page image refused by the backend', ['jobId' => $jobId, 'status' => $response->getStatusCode()]);
			return null;
		}

		$bytes = self::boundedBody($response->getBody(), self::MAX_PAGE_BYTES);
		if ($bytes === null || !str_starts_with($bytes, self::PNG_MAGIC)) {
			$this->logger->warning('PII Redaction: page image is not a bounded PNG', ['jobId' => $jobId]);
			return null;
		}

		return $bytes;
	}

	/**
	 * The finished copy of a job as a stream response, or null. The caller
	 * (PublishService) checks size and sha256 against what the container
	 * reported in its ack.
	 */
	public function output(int $jobId, string $uid): ?IResponse {
		if ($jobId <= 0) {
			return null;
		}
		$response = $this->proxyRequest(
			"/jobs/{$jobId}/output",
			$uid,
			'GET',
			[],
			self::OUTPUT_TIMEOUT_SECONDS,
			['stream' => true],
		);
		if (!$response instanceof IResponse) {
			$this->logger->warning('PII Redaction: output not delivered', ['jobId' => $jobId]);
			return null;
		}
		if ($response->getStatusCode() !== 200) {
			$this->logger->info('PII Redaction: output refused by the backend', ['jobId' => $jobId, 'status' => $response->getStatusCode()]);
			return null;
		}

		return $response;
	}

	// -- the state of the other half --------------------------------------------

	/**
	 * Whether a new job may start: the state is ok or only the patch differs,
	 * and the container does not report this half as missing.
	 */
	public function startAllowed(): bool {
		$state = $this->backendState();

		return in_array($state['state'], self::STARTABLE_STATES, true) && $state['companion'] !== 'missing';
	}

	/**
	 * The state of the other half. A verdict at most sixty seconds old is
	 * reused unless $fresh; otherwise it is determined under the first enabled
	 * admin (the answer is the same for every user) and remembered.
	 *
	 * @return array{state:string,ownVersion:string,backendVersion:?string,checkedAt:int,companion:?string}
	 */
	public function backendState(bool $fresh = false): array {
		if (!$fresh) {
			$remembered = $this->rememberedState();
			if ($remembered !== null) {
				return $remembered;
			}
		}

		$result = $this->determineState($this->firstAdmin());
		$encoded = json_encode($result);
		if (is_string($encoded)) {
			$this->appConfig->setValueString(Application::APP_ID, self::KEY_BACKEND_STATE, $encoded);
		}

		return $result;
	}

	/**
	 * What AppAPI knows about the backend: an array with appid, version, name
	 * and enabled, null when it is not registered, false when the public
	 * functions of AppAPI cannot be resolved. Protected for the unit suite.
	 *
	 * @return array<mixed>|false|null
	 */
	protected function exAppInfo(string $uid): array|false|null {
		$appApi = $this->publicFunctions($uid);
		if ($appApi === null) {
			return false;
		}

		$info = $appApi->getExApp(Application::BACKEND_APP_ID);

		return is_array($info) ? $info : null;
	}

	/** @return array{state:string,ownVersion:string,backendVersion:?string,checkedAt:int,companion:?string} */
	private function determineState(?string $uid): array {
		$own = $this->ownVersion();
		$result = [
			'state' => self::STATE_NO_APP_API,
			'ownVersion' => $own,
			'backendVersion' => null,
			'checkedAt' => $this->timeFactory->getTime(),
			'companion' => null,
		];

		if ($uid === null || !$this->appApiEnabledFor($uid)) {
			return $result;
		}

		try {
			$info = $this->exAppInfo($uid);
		} catch (\Throwable $e) {
			$this->logger->warning('PII Redaction: the registration of the backend could not be read', ['class' => $e::class]);
			$result['state'] = self::STATE_BACKEND_UNREACHABLE;
			return $result;
		}

		if ($info === false) {
			return $result;
		}
		if ($info === null) {
			$result['state'] = self::STATE_BACKEND_MISSING;
			return $result;
		}

		$registered = is_string($info['version'] ?? null) ? $this->versionOrNothing($info['version']) : '';
		if ($registered !== '') {
			$result['backendVersion'] = $registered;
			$this->rememberBackendVersion($registered);
		}

		if (!self::isEnabledFlag($info['enabled'] ?? null)) {
			$result['state'] = self::STATE_BACKEND_DISABLED;
			return $result;
		}

		// A container of the wrong version is never asked anything.
		if ($this->drifts($own, $registered)) {
			$result['state'] = self::STATE_VERSION_DRIFT;
			return $result;
		}

		$status = $this->status($uid);
		if ($status === null) {
			$result['state'] = self::STATE_BACKEND_UNREACHABLE;
			return $result;
		}

		// The version the running container reports wins over the registration.
		if ($status['version'] !== null) {
			$result['backendVersion'] = $status['version'];
			$this->rememberBackendVersion($status['version']);
		}
		$result['companion'] = $status['companion'];

		$backend = $result['backendVersion'] ?? '';
		if ($this->drifts($own, $backend)) {
			$result['state'] = self::STATE_VERSION_DRIFT;
			return $result;
		}

		// An unknown version on either side is a hint and never ok.
		$result['state'] = $own !== '' && $own === $backend ? self::STATE_OK : self::STATE_VERSION_PATCH_DIFFERS;

		return $result;
	}

	/** @return array{state:string,ownVersion:string,backendVersion:?string,checkedAt:int,companion:?string}|null */
	private function rememberedState(): ?array {
		$raw = $this->appConfig->getValueString(Application::APP_ID, self::KEY_BACKEND_STATE, '');
		$decoded = $raw === '' ? null : json_decode($raw, true);
		if (!is_array($decoded)) {
			return null;
		}

		$state = $decoded['state'] ?? null;
		$checkedAt = $decoded['checkedAt'] ?? null;
		if (!is_string($state) || !in_array($state, self::STATES, true) || !is_int($checkedAt)) {
			return null;
		}
		$age = $this->timeFactory->getTime() - $checkedAt;
		if ($age < 0 || $age > self::STATE_MAX_AGE_SECONDS) {
			return null;
		}

		$backend = is_string($decoded['backendVersion'] ?? null) ? $this->versionOrNothing($decoded['backendVersion']) : '';
		$companion = $decoded['companion'] ?? null;

		return [
			'state' => $state,
			'ownVersion' => $this->ownVersion(),
			'backendVersion' => $backend !== '' ? $backend : null,
			'checkedAt' => $checkedAt,
			'companion' => is_string($companion) && in_array($companion, self::COMPANION_VALUES, true) ? $companion : null,
		];
	}

	/** True when both versions are known and differ in major or minor. */
	private function drifts(string $own, string $other): bool {
		return $own !== '' && $other !== '' && $this->majorMinor($own) !== $this->majorMinor($other);
	}

	/** The enabled flag of AppAPI: a boolean, or 0 and 1 out of the database. */
	private static function isEnabledFlag(mixed $flag): bool {
		return $flag === true || $flag === 1 || $flag === '1';
	}

	/** A real user with app_api enabled, without resolving AppAPI itself. */
	private function appApiEnabledFor(string $uid): bool {
		$user = $this->userManager->get($uid);

		return $user !== null && $this->appManager->isEnabledForUser('app_api', $user);
	}

	/** The uid of the first enabled member of the admin group, or null. */
	public function firstAdmin(): ?string {
		$group = $this->groupManager->get('admin');
		if ($group === null) {
			return null;
		}

		foreach ($group->getUsers() as $user) {
			if ($user->isEnabled()) {
				return $user->getUID();
			}
		}

		return null;
	}

	/** The version of this half, or an empty string when it has no shape. */
	public function ownVersion(): string {
		return $this->versionOrNothing($this->appManager->getAppVersion(Application::APP_ID));
	}

	/** Major and minor of a version as one string, or null for a non version. */
	public function majorMinor(string $version): ?string {
		$candidate = $this->versionOrNothing($version);
		if ($candidate === '') {
			return null;
		}

		$parts = explode('.', $candidate);

		return $parts[0] . '.' . $parts[1];
	}

	private function versionOrNothing(string $version): string {
		$candidate = trim($version);

		return preg_match(self::VERSION_PATTERN, $candidate) === 1 ? $candidate : '';
	}

	/** Remember the version of the other half, and only when it changed. */
	private function rememberBackendVersion(string $version): void {
		if ($version === $this->appConfig->getValueString(Application::APP_ID, self::KEY_BACKEND_VERSION, '')) {
			return;
		}

		$this->appConfig->setValueString(Application::APP_ID, self::KEY_BACKEND_VERSION, $version);
	}

	/** @return array{kind:string,rssKb:int,ms:int}|null */
	private static function lastChild(mixed $raw): ?array {
		if (!is_array($raw)) {
			return null;
		}
		$kind = $raw['kind'] ?? null;
		$rssKb = $raw['rssKb'] ?? null;
		$ms = $raw['ms'] ?? null;
		if (!is_string($kind) || !in_array($kind, self::CHILD_KINDS, true) || !is_int($rssKb) || !is_int($ms) || $rssKb < 0 || $ms < 0) {
			return null;
		}

		return ['kind' => $kind, 'rssKb' => $rssKb, 'ms' => $ms];
	}

	// -- transport ----------------------------------------------------------------

	/**
	 * The single outbound call of this app, through AppAPI. Protected rather
	 * than private as the one concession to the unit suite.
	 *
	 * @param array<string,mixed> $params
	 * @param array<string,mixed> $options extra Guzzle options, e.g. stream
	 * @return array<mixed>|IResponse|null null when the pre-flight refused, an
	 *                                     array when AppAPI turned a transport
	 *                                     failure into one, a response otherwise
	 */
	protected function proxyRequest(string $route, string $userId, string $method, array $params, float $timeout, array $options = []): array|IResponse|null {
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
			['timeout' => $timeout] + $options,
		);
	}

	/**
	 * The pre-flight: a real user, app_api enabled for them, and the public
	 * functions of AppAPI resolvable.
	 */
	private function publicFunctions(string $userId): ?\OCA\AppAPI\PublicFunctions {
		$user = $this->userManager->get($userId);
		if ($user === null || !$this->appManager->isEnabledForUser('app_api', $user)) {
			$this->logger->info('PII Redaction: no AppAPI for this request, no call to the backend');
			return null;
		}

		try {
			return \OCP\Server::get(\OCA\AppAPI\PublicFunctions::class);
		} catch (ContainerExceptionInterface|NotFoundExceptionInterface) {
			$this->logger->info('PII Redaction: AppAPI public functions unavailable');
			return null;
		}
	}

	/**
	 * A JSON call: an array from AppAPI (transport failure), a status of 400
	 * and above, a body that is not bounded, a body that is not a JSON object
	 * all end in null, none of them throws.
	 *
	 * @return array<mixed>|null
	 */
	private function call(string $route, string $userId, float $timeout): ?array {
		$response = $this->proxyRequest($route, $userId, 'GET', [], $timeout);
		if (!$response instanceof IResponse) {
			if ($response !== null) {
				$this->logger->warning('PII Redaction: backend unreachable');
			}
			return null;
		}
		if ($response->getStatusCode() >= 400) {
			$this->logger->warning('PII Redaction: backend returned an error', ['status' => $response->getStatusCode()]);
			return null;
		}

		$body = self::boundedBody($response->getBody(), self::MAX_BODY_BYTES);
		$decoded = $body === null ? null : json_decode($body, true);
		if (!is_array($decoded) || ($decoded !== [] && array_is_list($decoded))) {
			$this->logger->warning('PII Redaction: malformed backend response');
			return null;
		}

		return $decoded;
	}

	/**
	 * A response body as a string of at most $max bytes, or null. A stream is
	 * read up to one byte past the ceiling and no further.
	 *
	 * @param string|resource|mixed $body
	 */
	private static function boundedBody(mixed $body, int $max): ?string {
		if (is_resource($body)) {
			$body = stream_get_contents($body, $max + 1);
		}
		if (!is_string($body) || strlen($body) > $max) {
			return null;
		}

		return $body;
	}
}
