<?php

declare(strict_types=1);

namespace OCA\PiiRedaction\Model;

/**
 * The closed list of reasons for failed, stale and cancelled jobs, stored in
 * pii_jobs.reason (32 characters). No path, name or message ever fits in
 * here, which is the point: the reason is a word from this list or null.
 */
enum Reason: string {
	case EncryptedPdf = 'encrypted_pdf';
	case UnsupportedFormat = 'unsupported_format';
	case TooManyPages = 'too_many_pages';
	case OutOfMemory = 'out_of_memory';
	case RepeatedlyStuck = 'repeatedly_stuck';
	case LeakDetected = 'leak_detected';
	case CheckError = 'check_error';
	case OriginalChanged = 'original_changed';
	case OriginalDeleted = 'original_deleted';
	case TargetNotWritable = 'target_not_writable';
	case BackendStateLost = 'backend_state_lost';
	case DownloadBlocked = 'download_blocked';
	case NotReadable = 'not_readable';
	case RenderFailed = 'render_failed';
	case BackendUnavailable = 'backend_unavailable';
	// Phase 2 (JOB-05): refusals of the pre-check and of the user.
	case E2eEncrypted = 'e2e_encrypted';
	case EncryptedDocument = 'encrypted_document';
	case WrongType = 'wrong_type';
	case Damaged = 'damaged';
	case TooLarge = 'too_large';
	case UnsafeContent = 'unsafe_content';
	case SignatureDeclined = 'signature_declined';
}
