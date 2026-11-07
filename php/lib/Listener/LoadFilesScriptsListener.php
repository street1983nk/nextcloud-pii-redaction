<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Listener;

use OCA\Files\Event\LoadAdditionalScriptsEvent;
use OCP\EventDispatcher\Event;
use OCP\EventDispatcher\IEventListener;
use OCP\Util;

/**
 * Loads the file action into the Files app, and only there: the event is
 * dispatched by Files when it renders its page (files_reminders pattern).
 * The init script registers the action through @nextcloud/files.
 *
 * @template-implements IEventListener<LoadAdditionalScriptsEvent>
 */
final class LoadFilesScriptsListener implements IEventListener {
	public function handle(Event $event): void {
		if (!$event instanceof LoadAdditionalScriptsEvent) {
			return;
		}

		Util::addInitScript('pii_redaction', 'pii_redaction-init');
	}
}
