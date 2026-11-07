<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Model;

/**
 * The subjects of the notifications of this app. The notifier builds its
 * texts from these words only; a file name never becomes part of one
 * (owner decision 07.11.2026).
 */
enum Subject: string {
	case ReviewReady = 'review_ready';
	case JobFailed = 'job_failed';
	case JobStale = 'job_stale';
	case CopyCreated = 'copy_created';
}
