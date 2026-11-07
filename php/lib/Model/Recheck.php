<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Model;

/**
 * The answer of FileAccess::recheck, asked on every request that touches a
 * job: the file is readable for the user, not download blocked, and still the
 * version the job was started on. Missing covers "gone" and "not allowed"
 * alike, so the two cannot be told apart from outside.
 */
enum Recheck: string {
	case Ok = 'ok';
	case Missing = 'missing';
	case DownloadBlocked = 'download_blocked';
	case Changed = 'changed';
}
