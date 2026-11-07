/**
 * SPDX-FileCopyrightText: 2026 Khaled Cherif
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */
import { createAppConfig } from '@nextcloud/vite-config'
import { join, resolve } from 'node:path'

// Three entries, built to js/pii_redaction-<entry>.mjs: the file action in
// Files, the review page and the admin state section. Vue styles stay out of
// the components; css/review.css carries the page layout.
export default createAppConfig({
	init: resolve(join('src', 'init.ts')),
	review: resolve(join('src', 'review.ts')),
	admin: resolve(join('src', 'admin.ts')),
}, {
	appName: 'pii_redaction',
	extractLicenseInformation: false,
	// Styles of the bundled libraries travel inside the scripts, so php/css/
	// holds only the hand written sheets that the gates judge.
	inlineCSS: { relativeCSSInjection: true },
})
