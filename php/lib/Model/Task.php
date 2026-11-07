<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Model;

/**
 * What the container is asked to do with a job, stored in pii_jobs.task
 * (16 characters). Only analyze and apply take the single work slot; purge
 * only deletes container state and runs beside them.
 */
enum Task: string {
	case Analyze = 'analyze';
	case Apply = 'apply';
	case Purge = 'purge';
}
