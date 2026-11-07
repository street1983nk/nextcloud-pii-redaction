<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Settings;

use OCA\PiiRedaction\AppInfo\Application;
use OCA\PiiRedaction\Service\ExAppService;
use OCP\AppFramework\Http\TemplateResponse;
use OCP\AppFramework\Utility\ITimeFactory;
use OCP\IDateTimeFormatter;
use OCP\IURLGenerator;
use OCP\Settings\ISettings;
use Psr\Log\LoggerInterface;

/**
 * The form of the section: the state of the other half, the versions, the
 * time of the check and "Check again" (UI-SPEC Fläche 5, AVS without the
 * debug block).
 *
 * The page is rendered complete on the server, so it reads without
 * JavaScript; the admin script only refreshes it in place. The template gets
 * codes, versions and a time, and translates every sentence itself. No file
 * name, no path and no job number reaches this page.
 */
final class Admin implements ISettings {
	public function __construct(
		private ExAppService $exAppService,
		private IDateTimeFormatter $dateTimeFormatter,
		private IURLGenerator $urlGenerator,
		private ITimeFactory $timeFactory,
		private LoggerInterface $logger,
	) {
	}

	public function getForm(): TemplateResponse {
		$state = $this->state();

		// RENDER_AS_BLANK: the settings page supplies the frame around the form.
		return new TemplateResponse(Application::APP_ID, 'admin', [
			'state' => $state['state'],
			'ownVersion' => $state['ownVersion'],
			'backendVersion' => $state['backendVersion'],
			'checkedAtText' => $this->dateTimeFormatter->formatTime($state['checkedAt'], 'medium'),
			'checkedAtIso' => gmdate('Y-m-d\TH:i:s\Z', $state['checkedAt']),
			'urlGenerator' => $this->urlGenerator,
		], TemplateResponse::RENDER_AS_BLANK);
	}

	public function getSection(): ?string {
		return Application::APP_ID;
	}

	public function getPriority(): int {
		// The only form of the section so far.
		return 50;
	}

	/**
	 * The state of the other half. backendState answers every failure with a
	 * code of its own; should it throw all the same, the page still renders
	 * and names the backend as unreachable.
	 *
	 * @return array{state:string,ownVersion:string,backendVersion:?string,checkedAt:int}
	 */
	private function state(): array {
		try {
			$state = $this->exAppService->backendState();
			return [
				'state' => $state['state'],
				'ownVersion' => $state['ownVersion'],
				'backendVersion' => $state['backendVersion'],
				'checkedAt' => $state['checkedAt'],
			];
		} catch (\Throwable $e) {
			$this->logger->error('PII Redaction: backend state not readable for the admin page', ['class' => $e::class]);
			return [
				'state' => ExAppService::STATE_BACKEND_UNREACHABLE,
				'ownVersion' => $this->exAppService->ownVersion(),
				'backendVersion' => null,
				'checkedAt' => $this->timeFactory->getTime(),
			];
		}
	}
}
