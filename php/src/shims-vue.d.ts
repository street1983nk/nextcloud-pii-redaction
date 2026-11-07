/**
 * SPDX-FileCopyrightText: 2026 Khaled Cherif
 * SPDX-License-Identifier: AGPL-3.0-or-later
 *
 * tsc reads .ts only; a .vue import is a component to it. The script blocks of
 * the components are checked by the Vite build (esbuild), not by tsc.
 */
declare module '*.vue' {
	import type { DefineComponent } from 'vue'
	const component: DefineComponent<object, object, unknown>
	export default component
}
