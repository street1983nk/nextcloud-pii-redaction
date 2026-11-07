<?php

declare(strict_types=1);

/**
 * The admin section: state of the other half, versions, time of the check and
 * "Check again" (UI-SPEC Fläche 5), in this order. Audio & Video Search
 * without its test switch.
 *
 * All seven state banners are rendered here, the current one visible and the
 * others hidden, plus the hidden warning for a failed recheck. The admin
 * script (src/admin.ts) flips hidden attributes and replaces text nodes; it
 * never builds markup. Without JavaScript a reload shows the new state.
 *
 * The versions sit inside the translated sentences as spans: each sentence is
 * translated with private use characters in place of its placeholders and
 * split around them, so the language decides where a version goes and the
 * script can replace the version alone.
 *
 * Every visible string runs through $l->t(), every value is printed with p().
 * No inline script (CSP), no style attribute (theme). No file name, no path
 * and no job number appears on this page.
 *
 * @var array<string,mixed> $_ the parameters of Settings\Admin::getForm()
 * @var \OCP\IL10N $l
 */

// Here and not in getForm(): the layout collects its resource lists after the
// template has been rendered.
\OCP\Util::addScript('pii_redaction', 'pii_redaction-admin');
\OCP\Util::addStyle('pii_redaction', 'admin');

// Material Design Icons by Pictogrammers (Apache-2.0), path data only.
$icons = [
	'error' => 'M11,15H13V17H11V15M11,7H13V13H11V7M12,2C6.47,2 2,6.5 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20Z',
	'warning' => 'M12,2L1,21H23M12,6L19.53,19H4.47M11,10V14H13V10M11,16V18H13V16',
	'info' => 'M11,9H13V7H11M12,20C7.59,20 4,16.41 4,12C4,7.59 7.59,4 12,4C16.41,4 20,7.59 20,12C20,16.41 16.41,20 12,20M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M11,17H13V11H11V17Z',
	'success' => 'M12,2C6.5,2 2,6.5 2,12C2,17.5 6.5,22 12,22C17.5,22 22,17.5 22,12C22,6.5 17.5,2 12,2M12,20C7.59,20 4,16.41 4,12C4,7.59 7.59,4 12,4C16.41,4 20,7.59 20,12C20,16.41 16.41,20 12,20M16.59,7.58L10,14.17L7.41,11.59L6,13L10,17L18,9L16.59,7.58Z',
];

// The parameters, read defensively.
$states = ['ok', 'version_patch_differs', 'version_drift', 'backend_missing', 'backend_disabled', 'backend_unreachable', 'no_app_api'];
$state = in_array($_['state'] ?? null, $states, true) ? $_['state'] : 'backend_unreachable';
$unknown = $l->t('unknown');
$own = is_string($_['ownVersion'] ?? null) && $_['ownVersion'] !== '' ? $_['ownVersion'] : $unknown;
$backend = is_string($_['backendVersion'] ?? null) && $_['backendVersion'] !== '' ? $_['backendVersion'] : $unknown;
$checkedAtText = is_string($_['checkedAtText'] ?? null) ? $_['checkedAtText'] : '';
$checkedAtIso = is_string($_['checkedAtIso'] ?? null) ? $_['checkedAtIso'] : '';

// The app management of the server, the one action of an error banner
// (orchestrator decision 3, AVS form): from Nextcloud 34 on it is the app
// "appstore"; up to 33 it belongs to settings. An unknown route gives an
// empty string, so the second name only counts where the first one is absent.
$urlGenerator = ($_['urlGenerator'] ?? null) instanceof \OCP\IURLGenerator
	? $_['urlGenerator']
	: \OCP\Server::get(\OCP\IURLGenerator::class);
$appsUrl = $urlGenerator->linkToRoute('appstore.page.viewApps');
if ($appsUrl === '') {
	$appsUrl = $urlGenerator->linkToRoute('settings.AppSettings.viewApps');
}

// Placeholders: the own version, the backend version, the time of the check.
$markOwn = "\u{E000}";
$markBackend = "\u{E001}";
$markTime = "\u{E002}";

/**
 * A translated sentence as a list of pieces: [kind, text], kind one of
 * text, own, backend, time.
 *
 * @return list<array{string, string}>
 */
$pieces = static function (string $sentence) use ($markOwn, $markBackend, $markTime): array {
	$parts = preg_split('/(\x{E000}|\x{E001}|\x{E002})/u', $sentence, -1, PREG_SPLIT_DELIM_CAPTURE | PREG_SPLIT_NO_EMPTY);
	$found = [];
	foreach (is_array($parts) ? $parts : [] as $part) {
		$found[] = match ($part) {
			$markOwn => ['own', ''],
			$markBackend => ['backend', ''],
			$markTime => ['time', ''],
			default => ['text', $part],
		};
	}

	return $found;
};

// One banner per state; 'action' names the link to the app management.
$banners = [
	'ok' => ['kind' => 'success', 'action' => false,
		'text' => $l->t('Both apps are connected.')],
	'version_patch_differs' => ['kind' => 'info', 'action' => false,
		'text' => $l->t('Minor version difference. Analyses run; align both apps at the next update.')],
	'version_drift' => ['kind' => 'error', 'action' => true,
		'text' => $l->t('The versions do not match. No analysis starts until both are the same.')],
	'backend_missing' => ['kind' => 'error', 'action' => true,
		'text' => $l->t('The backend is not installed. Without it, no analysis starts.')],
	'backend_disabled' => ['kind' => 'error', 'action' => true,
		'text' => $l->t('The backend is disabled. No analysis starts until it is enabled again.')],
	'backend_unreachable' => ['kind' => 'error', 'action' => true,
		'text' => $l->t('The backend does not respond. Check that it is running and that the deploy daemon can be reached.')],
	'no_app_api' => ['kind' => 'error', 'action' => true,
		'text' => $l->t('AppAPI is not enabled. The backend only runs through AppAPI.')],
];
?>
<div id="pii-admin" class="section pii-admin">
	<h2><?php p($l->t('Connection to the backend')); ?></h2>

	<div id="pii-backend-state" class="pii-admin__state" role="status" aria-live="polite" tabindex="-1">
		<?php foreach ($banners as $name => $banner) { ?>
			<div class="pii-banner pii-banner--<?php p($banner['kind']); ?>" data-state="<?php p($name); ?>"<?php if ($name !== $state) { ?> hidden<?php } ?>>
				<span class="pii-banner__icon"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><path fill="currentColor" d="<?php p($icons[$banner['kind']]); ?>"/></svg></span>
				<div class="pii-banner__body">
					<p class="pii-banner__text"><?php p($banner['text']); ?></p>
					<?php if ($banner['action'] && $appsUrl !== '') { ?>
						<a class="pii-banner__action" href="<?php p($appsUrl); ?>"><?php p($l->t('Open Apps')); ?></a>
					<?php } ?>
				</div>
			</div>
		<?php } ?>

		<div id="pii-recheck-failed" class="pii-banner pii-banner--warning" hidden>
			<span class="pii-banner__icon"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><path fill="currentColor" d="<?php p($icons['warning']); ?>"/></svg></span>
			<div class="pii-banner__body">
				<p class="pii-banner__text"><?php p($l->t('The state could not be checked again. Shown is the state from when the page was loaded.')); ?></p>
			</div>
		</div>
	</div>

	<p class="pii-admin__line"><?php foreach ($pieces($l->t('This app: %1$s · Backend: %2$s', [$markOwn, $markBackend])) as [$kind, $text]) {
		if ($kind === 'own') {
			?><span class="pii-version-own"><?php p($own); ?></span><?php
		} elseif ($kind === 'backend') {
			?><span class="pii-version-backend"><?php p($backend); ?></span><?php
		} else {
			p($text);
		}
	} ?></p>

	<p class="pii-admin__line"><?php foreach ($pieces($l->t('Last checked: %s', [$markTime])) as [$kind, $text]) {
		if ($kind === 'time') {
			?><time id="pii-checked-at" class="pii-admin__time" datetime="<?php p($checkedAtIso); ?>"><?php p($checkedAtText); ?></time><?php
		} else {
			p($text);
		}
	} ?></p>

	<div class="pii-admin__actions">
		<button type="button" id="pii-recheck" class="pii-admin__recheck">
			<span id="pii-recheck-label"><?php p($l->t('Check again')); ?></span>
		</button>
	</div>
</div>
