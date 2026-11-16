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
	// The pre-check of the source in a jailed child (phase 2, SAFE-02).
	case Checking = 'checking';
	case Converting = 'converting';
	case Rendering = 'rendering';
	case Done = 'done';
}
