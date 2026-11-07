/**
 * SPDX-FileCopyrightText: 2026 Khaled Cherif
 * SPDX-License-Identifier: AGPL-3.0-or-later
 *
 * "Check again" in the admin section (UI-SPEC Fläche 5, after Audio & Video
 * Search admin.js). The server renders the page complete: one banner per
 * state under #pii-backend-state, all but the current one hidden, the
 * version line and the time of the last check. This script asks
 * GET admin/state, shows the banner of the new state, replaces versions and
 * time as text and moves the focus to the state area. It flips hidden
 * attributes and replaces text; it never builds markup.
 *
 * DOM contract with php/templates/admin.php (plan 11):
 *   #pii-admin                      root
 *   #pii-backend-state              state area, tabindex -1, holds the banners
 *   [data-state="<state>"]          one banner per state of ExAppService::STATES
 *   #pii-recheck-failed             warning banner "could not check again"
 *   .pii-version-own, .pii-version-backend   text of the version line
 *   #pii-checked-at                 <time> of the last check
 *   #pii-recheck, #pii-recheck-label         the button and its text
 */
import axios from '@nextcloud/axios'
import { t } from '@nextcloud/l10n'
import { generateUrl } from '@nextcloud/router'

const STATES = ['ok', 'version_patch_differs', 'version_drift', 'backend_missing', 'backend_disabled', 'backend_unreachable', 'no_app_api']

type Answer = {
	state?: unknown
	ownVersion?: unknown
	backendVersion?: unknown
	checkedAt?: unknown
	checkedAtText?: unknown
}

function setText(nodes: Iterable<Element>, value: string): void {
	for (const node of nodes) {
		node.textContent = value
	}
}

function version(value: unknown): string {
	return typeof value === 'string' && value !== '' ? value : t('pii_redaction', 'unknown')
}

function clock(seconds: number): string {
	const date = new Date(seconds * 1000)
	try {
		return date.toLocaleTimeString(document.documentElement.lang || undefined)
	} catch {
		return date.toLocaleTimeString()
	}
}

const root = document.getElementById('pii-admin')
const stateArea = document.getElementById('pii-backend-state')
const button = document.getElementById('pii-recheck') as HTMLButtonElement | null

if (root !== null && stateArea !== null && button !== null) {
	const label = document.getElementById('pii-recheck-label') ?? button
	const failed = document.getElementById('pii-recheck-failed')
	const checkedAt = document.getElementById('pii-checked-at')
	const banners = stateArea.querySelectorAll<HTMLElement>('[data-state]')
	const idleText = label.textContent ?? ''

	const busy = (on: boolean): void => {
		button.disabled = on
		button.classList.toggle('icon-loading-small', on)
		label.textContent = on ? t('pii_redaction', 'Checking…') : idleText
		if (on) {
			stateArea.setAttribute('aria-busy', 'true')
		} else {
			stateArea.removeAttribute('aria-busy')
		}
	}

	const show = (answer: Answer): void => {
		for (const banner of banners) {
			banner.hidden = banner.dataset.state !== answer.state
		}
		setText(root.querySelectorAll('.pii-version-own'), version(answer.ownVersion))
		setText(root.querySelectorAll('.pii-version-backend'), version(answer.backendVersion))
		if (checkedAt !== null && typeof answer.checkedAt === 'number' && Number.isInteger(answer.checkedAt)) {
			checkedAt.textContent = typeof answer.checkedAtText === 'string' && answer.checkedAtText !== ''
				? answer.checkedAtText
				: clock(answer.checkedAt)
			checkedAt.setAttribute('datetime', new Date(answer.checkedAt * 1000).toISOString())
		}
	}

	button.addEventListener('click', async () => {
		busy(true)
		try {
			const response = await axios.get(generateUrl('/apps/pii_redaction/admin/state'))
			const answer = (response.data ?? {}) as Answer
			if (typeof answer.state !== 'string' || !STATES.includes(answer.state)) {
				throw new Error('pii_redaction: unknown state')
			}
			show(answer)
			if (failed !== null) {
				failed.hidden = true
			}
		} catch {
			// The last banner stays; the warning says it is not fresh.
			if (failed !== null) {
				failed.hidden = false
			}
		} finally {
			busy(false)
			stateArea.focus()
		}
	})
}
