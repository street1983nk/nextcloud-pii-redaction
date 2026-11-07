<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Controller;

use OCA\PiiRedaction\AppInfo\Application;
use OCA\PiiRedaction\Service\ExAppService;
use OCP\AppFramework\Controller;
use OCP\AppFramework\Http;
use OCP\AppFramework\Http\DataResponse;
use OCP\IDateTimeFormatter;
use OCP\IRequest;
use OCP\IURLGenerator;
use Psr\Log\LoggerInterface;

/**
 * The one address the admin section asks for "Check again" (UI-SPEC
 * Fläche 5, AVS without the test switch).
 *
 * Its protection is what is missing from it: no attribute lifts the admin
 * requirement, the request token or the session, and none lets a registered
 * container in. So the security middleware of the server demands a signed in
 * administrator with the request token of the session (T-01-11-01);
 * SettingsControllerTest reads the attributes and holds that.
 *
 * The answer carries codes, versions, numbers and the address of the app
 * management, never a file name, a path or a job number.
 */
final class SettingsController extends Controller {
	/** The states in which the container answers and its last child is worth asking for. */
	private const ANSWERING_STATES = [ExAppService::STATE_OK, ExAppService::STATE_VERSION_PATCH_DIFFERS];

	public function __construct(
		IRequest $request,
		private ExAppService $exAppService,
		private IURLGenerator $urlGenerator,
		private IDateTimeFormatter $dateTimeFormatter,
		private LoggerInterface $logger,
	) {
		parent::__construct(Application::APP_ID, $request);
	}

	/**
	 * The state of the other half, determined anew: the same shape the admin
	 * section rendered, plus the last child of the container (kind, peak
	 * memory, duration; plan 17 reads it for the measurement), the address of
	 * the app management and the formatted time of the check.
	 */
	#[\OCP\AppFramework\Http\Attribute\FrontpageRoute(verb: 'GET', url: '/admin/state')]
	public function state(): DataResponse {
		try {
			$state = $this->exAppService->backendState(true);
			$lastChild = null;
			if (in_array($state['state'], self::ANSWERING_STATES, true)) {
				$lastChild = $this->exAppService->status()['lastChild'] ?? null;
			}

			return new DataResponse([
				'state' => $state['state'],
				'ownVersion' => $state['ownVersion'],
				'backendVersion' => $state['backendVersion'],
				'checkedAt' => $state['checkedAt'],
				'checkedAtText' => $this->dateTimeFormatter->formatTime($state['checkedAt'], 'medium'),
				'companion' => $state['companion'],
				'lastChild' => $lastChild,
				'appsUrl' => $this->appsUrl(),
			]);
		} catch (\Throwable $e) {
			$this->logger->error('PII Redaction: backend state could not be checked again', ['class' => $e::class]);

			return new DataResponse(['state' => 'recheck_failed'], Http::STATUS_SERVICE_UNAVAILABLE);
		}
	}

	/**
	 * The app management of the server, the same rule as the template:
	 * appstore.page.viewApps, and the settings route only where the first one
	 * is unknown (orchestrator decision 3).
	 */
	private function appsUrl(): string {
		$url = $this->urlGenerator->linkToRoute('appstore.page.viewApps');
		if ($url === '') {
			$url = $this->urlGenerator->linkToRoute('settings.AppSettings.viewApps');
		}
		return $url;
	}
}
