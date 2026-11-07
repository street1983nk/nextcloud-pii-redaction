/**
 * SPDX-FileCopyrightText: 2026 Khaled Cherif
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */
import { loadState } from '@nextcloud/initial-state'
import { createApp } from 'vue'
import ReviewPlaceholder from './ReviewPlaceholder.vue'

// The PHP route renders only <div id="pii-review"> and hands the start state
// over as initial state 'review'. Without it the page shows "not available".
const root = document.getElementById('pii-review')
if (root !== null) {
	const initial = loadState<Record<string, unknown>>('pii_redaction', 'review', { state: 'unavailable' })
	createApp(ReviewPlaceholder, { initial }).mount(root)
}
