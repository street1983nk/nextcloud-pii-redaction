/**
 * SPDX-FileCopyrightText: 2026 Khaled Cherif
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */
import type { INode } from '@nextcloud/files'

import { getCurrentUser } from '@nextcloud/auth'
import { FileType, Permission, registerFileAction } from '@nextcloud/files'
import { t } from '@nextcloud/l10n'
import iconSvg from './icon.svg?raw'
import { start } from './startToast'

// The formats of phase 1 (JobService::ALLOWED_MIMES on the server).
const MIMES = [
	'application/pdf',
	'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
	'application/vnd.oasis.opendocument.text',
]

/**
 * The download block as the Files app sees it (server
 * apps/files/src/utils/permissions.ts isDownloadable). Unclear share
 * attributes count as blocked. This is comfort only: the server asks again.
 */
function downloadable(node: INode): boolean {
	const hide = node.attributes['hide-download']
	if (hide === true || hide === 'true') {
		return false
	}
	const raw = node.attributes['share-attributes']
	if (raw) {
		try {
			const attributes = JSON.parse(String(raw)) as Array<{ scope?: string, key?: string, value?: unknown }>
			const download = attributes.find((entry) => entry.scope === 'permissions' && entry.key === 'download')
			if (download !== undefined) {
				return download.value === true
			}
		} catch {
			return false
		}
	}
	return true
}

function encrypted(node: INode): boolean {
	const flag = node.attributes['is-encrypted']
	return flag === true || flag === 1 || flag === '1' || flag === 'true'
}

registerFileAction({
	id: 'pii_redaction-start',
	displayName: () => t('pii_redaction', 'Redact / pseudonymize'),
	iconSvgInline: () => iconSvg,
	order: 60,

	enabled: ({ nodes, view }) => {
		if (getCurrentUser() === null || view?.id === 'trashbin' || nodes.length !== 1) {
			return false
		}
		const node = nodes[0]
		return node.type === FileType.File
			&& MIMES.includes(node.mime ?? '')
			&& (node.permissions & Permission.READ) !== 0
			&& downloadable(node)
			&& !encrypted(node)
			&& typeof node.fileid === 'number'
	},

	async exec({ nodes }) {
		const fileId = nodes[0].fileid
		if (typeof fileId === 'number') {
			await start(fileId)
		}
		return null
	},
})
