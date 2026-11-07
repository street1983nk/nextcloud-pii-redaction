<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Model;

/**
 * The closed list of progress stages inside a running task, stored in
 * pii_jobs.stage (16 characters) and reported by the container.
 */
enum Stage: string {
	case Waiting = 'waiting';
	case Fetching = 'fetching';
	case Converting = 'converting';
	case Rendering = 'rendering';
	case Done = 'done';
}
