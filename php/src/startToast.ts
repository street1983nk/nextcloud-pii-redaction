/**
 * SPDX-FileCopyrightText: 2026 Khaled Cherif
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */
import axios from '@nextcloud/axios'
import { showMessage, ToastType } from '@nextcloud/dialogs/toast'
import { n, t } from '@nextcloud/l10n'
import { generateUrl } from '@nextcloud/router'

// UI-SPEC Fläche 1: success and hints stay 10 s, warnings and errors stay
// until they are closed. The toast never names the file.
const SHORT = 10000
const PERMANENT = -1

type Answer = {
	jobId?: unknown
	ahead?: unknown
	reason?: unknown
}

/**
 * The toast body: a sentence as a text node, optionally followed by the link
 * to the review page. Built from elements, never from markup.
 */
function body(sentence: string, jobId: number | null): HTMLElement {
	const box = document.createElement('div')
	box.append(document.createTextNode(sentence))
	if (jobId !== null) {
		const link = document.createElement('a')
		link.href = generateUrl('/apps/pii_redaction/review/{jobId}', { jobId })
		link.textContent = t('pii_redaction', 'Open review page')
		box.append(document.createTextNode(' '), link)
	}
	return box
}

function positiveId(value: unknown): number | null {
	return typeof value === 'number' && Number.isInteger(value) && value > 0 ? value : null
}

function count(value: unknown): number {
	return typeof value === 'number' && Number.isInteger(value) && value > 0 ? value : 0
}

/**
 * The sentence and toast type for a refusal; the reason from the body
 * decides, the HTTP status is only the fallback.
 */
function refusal(reason: unknown): [string, ToastType] {
	switch (reason) {
	case 'backend_unavailable':
		return [t('pii_redaction', 'PII Redaction is not ready. Tell your administrators.'), ToastType.WARNING]
	case 'download_blocked':
		return [t('pii_redaction', 'This share does not allow downloads. No analysis is possible.'), ToastType.ERROR]
	case 'not_readable':
		return [t('pii_redaction', 'The file can no longer be read. Reload the view.'), ToastType.ERROR]
	case 'unsupported_format':
		return [t('pii_redaction', 'Only PDF, DOCX and ODT can be analysed.'), ToastType.ERROR]
	default:
		return [t('pii_redaction', 'The analysis could not start. Try again later.'), ToastType.ERROR]
	}
}

/**
 * Starts a job on the file and tells the user what happened.
 */
export async function start(fileId: number): Promise<void> {
	let status = 0
	let answer: Answer = {}
	try {
		const response = await axios.post(generateUrl('/apps/pii_redaction/api/v1/jobs'), { fileId })
		status = response.status
		answer = (response.data ?? {}) as Answer
	} catch (error) {
		const response = (error as { response?: { status?: number, data?: Answer } }).response
		status = response?.status ?? 0
		answer = response?.data ?? {}
	}

	const jobId = positiveId(answer.jobId)
	if ((status === 201 || status === 200) && jobId !== null) {
		if (status === 200) {
			showMessage(body(t('pii_redaction', 'An analysis is already running for this file.'), jobId), { type: ToastType.INFO, timeout: SHORT, close: true })
			return
		}
		const ahead = count(answer.ahead)
		const sentence = ahead === 0
			? t('pii_redaction', 'Analysis started. It is next.')
			: n('pii_redaction', 'Analysis started. %n job is ahead.', 'Analysis started. %n jobs are ahead.', ahead)
		showMessage(body(sentence, jobId), { type: ToastType.SUCCESS, timeout: SHORT, close: true })
		return
	}

	const [sentence, type] = refusal(answer.reason)
	showMessage(body(sentence, null), { type, timeout: PERMANENT, close: true })
}
