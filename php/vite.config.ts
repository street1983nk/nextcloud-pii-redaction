/**
 * SPDX-FileCopyrightText: 2026 Khaled Cherif
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */
import { createAppConfig } from '@nextcloud/vite-config'

// Three entries, paths relative to php/ (the Vite root), built to
// js/pii_redaction-<entry>.mjs: the file action in Files, the review page and
// the admin state section. No node:path import, so tsc checks this file
// without Node type definitions. Vue styles stay out of the components;
// css/review.css carries the page layout.
//
// npm run build loads this file with --configLoader runner: the default
// esbuild bundling of the config reads every tsconfig.json above php/ and
// warned in CI about the one of the nextcloud/server tree (plan 01-15). The
// output is byte for byte the same.
export default createAppConfig({
	init: 'src/init.ts',
	review: 'src/review.ts',
	admin: 'src/admin.ts',
}, {
	appName: 'pii_redaction',
	extractLicenseInformation: false,
	// Styles of the bundled libraries travel inside the scripts, so php/css/
	// holds only the hand written sheets that the gates judge.
	inlineCSS: { relativeCSSInjection: true },
})
