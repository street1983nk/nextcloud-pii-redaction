<!--
  - SPDX-FileCopyrightText: 2026 Khaled Cherif
  - SPDX-License-Identifier: AGPL-3.0-or-later
-->
<template>
	<div class="pii-review__column">
		<h2 class="pii-review__name">
			{{ heading }}
		</h2>
		<p v-if="showMeta" class="pii-review__meta">
			{{ startedParts[0] }}<time :datetime="createdIso">{{ createdText }}</time>{{ startedParts[1] }}
		</p>

		<div id="pii-review-state"
			ref="stateRegion"
			class="pii-review__state"
			role="status"
			aria-live="polite"
			tabindex="-1">
			<div v-if="line" class="pii-review__line">
				<NcLoadingIcon :size="20" aria-hidden="true" />
				<div>
					<p class="pii-line__title">
						{{ line.title }}
					</p>
					<p class="pii-line__text">
						{{ line.text }}
					</p>
				</div>
			</div>
			<NcNoteCard v-else-if="card" :type="card.type">
				<p class="pii-note__title">
					{{ card.title }}
				</p>
				<p v-if="card.text" class="pii-note__text">
					{{ card.text }}
				</p>
				<p v-if="card.link" class="pii-note__text">
					<a class="pii-review__link" :href="card.link.href">{{ card.link.label }}</a>
				</p>
			</NcNoteCard>
		</div>

		<div v-if="line && progress !== null" class="pii-review__progress">
			<NcProgressBar size="medium" :value="progress" :aria-label="line.title" />
			<p class="pii-review__counter">
				{{ counterText }}
			</p>
		</div>

		<NcNoteCard v-if="pollFailed && !sessionExpired" type="warning">
			<p class="pii-note__text">
				{{ t('pii_redaction', 'Status not updated. Retrying.') }}
			</p>
		</NcNoteCard>

		<NcNoteCard v-if="sessionExpired" type="warning">
			<p class="pii-note__text">
				{{ t('pii_redaction', 'Your session has expired. Reload the page.') }}
			</p>
			<NcButton variant="secondary" @click="reloadPage">
				{{ t('pii_redaction', 'Reload page') }}
			</NcButton>
		</NcNoteCard>

		<NcNoteCard v-if="backendWarning" type="warning">
			<p class="pii-note__title">
				{{ t('pii_redaction', 'PII Redaction is not ready') }}
			</p>
			<p class="pii-note__text">
				{{ t('pii_redaction', 'The job waits and continues afterwards.') }}
			</p>
		</NcNoteCard>

		<template v-if="isReady">
			<NcNoteCard type="info">
				<p class="pii-note__title">
					{{ t('pii_redaction', 'Preview without detection') }}
				</p>
				<p class="pii-note__text">
					{{ t('pii_redaction', 'No search for personal data yet. The copy contains nothing from the original.') }}
				</p>
			</NcNoteCard>

			<div class="pii-review__actions">
				<NcButton id="pii-placeholder"
					variant="primary"
					:disabled="posting || !job.backendReady"
					@click="requestCopy">
					<template v-if="posting" #icon>
						<NcLoadingIcon :size="20" />
					</template>
					{{ posting ? t('pii_redaction', 'Creating…') : t('pii_redaction', 'Create placeholder copy') }}
				</NcButton>
				<NcButton variant="tertiary" :href="fileLink">
					{{ t('pii_redaction', 'Show in Files') }}
				</NcButton>
			</div>

			<NcNoteCard v-if="postFailed" type="error" show-alert>
				<p class="pii-note__text">
					{{ t('pii_redaction', 'The copy could not be requested. Try again.') }}
				</p>
			</NcNoteCard>

			<NcNoteCard v-if="imageFailed" type="warning">
				<p class="pii-note__title">
					{{ t('pii_redaction', 'Page 1 cannot be loaded') }}
				</p>
				<p class="pii-note__text">
					{{ t('pii_redaction', 'Load it again. If it persists, tell your administrators.') }}
				</p>
				<NcButton variant="secondary" @click="retryImage">
					{{ t('pii_redaction', 'Load again') }}
				</NcButton>
			</NcNoteCard>

			<figure v-else-if="job.backendReady"
				class="pii-review__page"
				:aria-busy="imageLoading ? 'true' : 'false'">
				<div class="pii-review__frame">
					<div v-if="imageLoading" class="pii-review__loading" :style="frameStyle">
						<NcLoadingIcon :size="32" />
					</div>
					<img :key="imageSrc"
						class="pii-review__image"
						:class="{ 'pii-review__image--loading': imageLoading }"
						:src="imageSrc"
						:width="imageWidth"
						:height="imageHeight"
						:alt="pageLabel"
						decoding="async"
						@load="imageLoading = false"
						@error="onImageError">
				</div>
				<figcaption class="pii-review__caption">
					{{ pageLabel }}
				</figcaption>
			</figure>
		</template>
	</div>
</template>

<script setup lang="ts">
import axios from '@nextcloud/axios'
import { getCanonicalLocale, n, t } from '@nextcloud/l10n'
import { generateUrl } from '@nextcloud/router'
import NcButton from '@nextcloud/vue/components/NcButton'
import NcLoadingIcon from '@nextcloud/vue/components/NcLoadingIcon'
import NcNoteCard from '@nextcloud/vue/components/NcNoteCard'
import NcProgressBar from '@nextcloud/vue/components/NcProgressBar'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

type Job = {
	status: string
	stage: string | null
	reason: string | null
	ahead: number | null
	pagesDone: number | null
	pagesTotal: number | null
	backendReady: boolean
	outputFileId: number | null
	outputName: string | null
}

type Card = {
	type: 'success' | 'info' | 'warning' | 'error'
	title: string
	text: string
	link: { href: string, label: string } | null
}

const props = defineProps({
	initial: { type: Object, required: true },
})

// UI-SPEC Fläche 2, Abfrage: every 3 s while open, back off on failures.
const POLL_MS = 3000
const BACKOFF_MS = [3000, 6000, 12000, 30000]
const OPEN = ['queued', 'analyzing', 'approved', 'applying', 'verified']
const COPYING = ['approved', 'applying', 'verified']

const start = props.initial as Record<string, unknown>

function int(value: unknown): number | null {
	return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null
}

function text(value: unknown): string | null {
	return typeof value === 'string' && value !== '' ? value : null
}

const jobId = int(start.jobId) ?? 0
const fileId = int(start.fileId) ?? 0
const createdAt = int(start.createdAt)
const image = (start.image ?? null) as { width?: unknown, height?: unknown } | null
const imageWidth = int(image?.width) ?? undefined
const imageHeight = int(image?.height) ?? undefined
const startName = text(start.fileName)

const job = reactive<Job>({
	status: text(start.status) ?? '',
	stage: text(start.stage),
	reason: text(start.reason),
	ahead: int(start.ahead),
	pagesDone: int(start.pagesDone),
	pagesTotal: int(start.pagesTotal),
	backendReady: start.backendReady === true,
	outputFileId: int(start.outputFileId),
	outputName: text(start.outputName),
})

const unavailable = ref(start.state === 'unavailable' || jobId === 0)
const blocked = ref(start.state === 'blocked' || start.recheck === 'download_blocked')
const pollFailed = ref(false)
const sessionExpired = ref(false)
const posting = ref(false)
const postFailed = ref(false)
const imageFailed = ref(false)
const imageLoading = ref(true)
const imageRetry = ref(0)
const stateRegion = ref<HTMLElement | null>(null)

let timer: ReturnType<typeof setTimeout> | null = null
let failures = 0
let stopped = false

const isOpen = computed(() => !unavailable.value && !blocked.value && OPEN.includes(job.status))
const isReady = computed(() => !unavailable.value && !blocked.value && job.status === 'review')
const nameVisible = computed(() => !unavailable.value && job.status !== 'cancelled' && startName !== null)
const heading = computed(() => nameVisible.value ? startName as string : t('pii_redaction', 'Review'))
const showMeta = computed(() => !unavailable.value && createdAt !== null)
const backendWarning = computed(() => !job.backendReady && (isOpen.value || isReady.value))

const startedParts = computed(() => {
	const parts = t('pii_redaction', 'Started on %s').split('%s')
	return [parts[0] ?? '', parts.slice(1).join('')]
})
const createdIso = computed(() => createdAt === null ? '' : new Date(createdAt * 1000).toISOString())
const createdText = computed(() => createdAt === null
	? ''
	: new Intl.DateTimeFormat(getCanonicalLocale(), { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(createdAt * 1000)))

const fileLink = computed(() => generateUrl('/f/{fileId}', { fileId }))
const filesLink = computed(() => generateUrl('/apps/files/'))

/** The status line of a waiting or running job, or null. */
const line = computed<{ title: string, text: string } | null>(() => {
	if (!isOpen.value) {
		return null
	}
	if (job.status === 'queued') {
		const ahead = job.ahead ?? 0
		return {
			title: t('pii_redaction', 'In the queue'),
			text: ahead === 0
				? t('pii_redaction', 'It is next.')
				: n('pii_redaction', '%n job is ahead.', '%n jobs are ahead.', ahead),
		}
	}
	if (COPYING.includes(job.status)) {
		return { title: t('pii_redaction', 'Creating the copy'), text: t('pii_redaction', 'The original stays unchanged.') }
	}
	switch (job.stage) {
	case 'fetching':
		return { title: t('pii_redaction', 'Loading the file'), text: t('pii_redaction', 'The file stays on this server.') }
	case 'converting':
		return { title: t('pii_redaction', 'Converting to PDF'), text: t('pii_redaction', 'Large documents take a little longer.') }
	case 'rendering':
		return { title: t('pii_redaction', 'Creating the page image'), text: t('pii_redaction', 'Page 1 appears shortly.') }
	default:
		return { title: t('pii_redaction', 'Analysis is starting'), text: t('pii_redaction', 'The job is being prepared.') }
	}
})

function failure(reason: string | null): [string, string] {
	switch (reason) {
	case 'render_failed':
		return [t('pii_redaction', 'The file could not be displayed'), t('pii_redaction', 'It may be damaged. Save it as PDF and analyse that.')]
	case 'out_of_memory':
		return [t('pii_redaction', 'Not enough memory'), t('pii_redaction', 'The analysis was stopped. Start it again later.')]
	case 'repeatedly_stuck':
		return [t('pii_redaction', 'The analysis got stuck'), t('pii_redaction', 'Stopped after three attempts. Tell your administrators.')]
	case 'backend_state_lost':
		return [t('pii_redaction', 'Intermediate data missing'), t('pii_redaction', 'The backend was reset. Analyse the file again.')]
	case 'target_not_writable':
		return [t('pii_redaction', 'Copy not created'), t('pii_redaction', 'The folder of the original is not writable. Analyse again afterwards.')]
	case 'unsupported_format':
		return [t('pii_redaction', 'Format not supported'), t('pii_redaction', 'Only PDF, DOCX and ODT can be analysed.')]
	default:
		return [t('pii_redaction', 'The analysis failed'), t('pii_redaction', 'Analyse the file again. If it persists, tell your administrators.')]
	}
}

/** The status card of every state without a status line, or null. */
const card = computed<Card | null>(() => {
	const showFile = { href: fileLink.value, label: t('pii_redaction', 'Show in Files') }
	const goFiles = { href: filesLink.value, label: t('pii_redaction', 'Go to Files') }
	if (unavailable.value) {
		return { type: 'error', title: t('pii_redaction', 'This review is not available'), text: t('pii_redaction', 'It has ended or permission is missing. Analyse the file again.'), link: goFiles }
	}
	if (blocked.value) {
		return { type: 'info', title: t('pii_redaction', 'Review blocked for this share'), text: t('pii_redaction', 'The share no longer allows downloads. The person who shared it can allow them.'), link: null }
	}
	switch (job.status) {
	case 'published':
		return {
			type: 'success',
			title: t('pii_redaction', 'Copy created'),
			text: job.outputName === null ? '' : t('pii_redaction', '"%s" is next to the original.').replace('%s', job.outputName),
			link: job.outputFileId === null ? null : { href: generateUrl('/f/{fileId}', { fileId: job.outputFileId }), label: t('pii_redaction', 'Show copy in Files') },
		}
	case 'stale':
		return { type: 'warning', title: t('pii_redaction', 'The file has changed'), text: t('pii_redaction', 'The analysis was for the old version. Analyse the file again.'), link: showFile }
	case 'cancelled':
		return { type: 'info', title: t('pii_redaction', 'The file was deleted'), text: t('pii_redaction', 'The analysis was stopped.'), link: goFiles }
	case 'expired':
		return { type: 'info', title: t('pii_redaction', 'This review has expired'), text: t('pii_redaction', 'Reviews are deleted after 14 days. Analyse the file again.'), link: null }
	case 'failed': {
		const [title, sentence] = failure(job.reason)
		return { type: 'error', title, text: sentence, link: showFile }
	}
	default:
		return null
	}
})

const progress = computed(() => {
	const total = job.pagesTotal
	if (total === null || total <= 0) {
		return null
	}
	return Math.round(100 * Math.min(job.pagesDone ?? 0, total) / total)
})
const counterText = computed(() => t('pii_redaction', '%1$s of %2$s pages')
	.replace('%1$s', String(job.pagesDone ?? 0))
	.replace('%2$s', String(job.pagesTotal ?? 0)))
const pageLabel = computed(() => job.pagesTotal !== null && job.pagesTotal > 0
	? t('pii_redaction', 'Page 1 of %s').replace('%s', String(job.pagesTotal))
	: t('pii_redaction', 'Page 1'))

const imageSrc = computed(() => {
	const base = generateUrl('/apps/pii_redaction/review/{jobId}/page/1', { jobId })
	return imageRetry.value > 0 ? `${base}?r=${imageRetry.value}` : base
})
const frameStyle = computed(() => imageWidth !== undefined && imageHeight !== undefined && imageHeight > 0
	? { aspectRatio: `${imageWidth} / ${imageHeight}` }
	: {})

// -- polling ----------------------------------------------------------------

function apply(data: Record<string, unknown>): void {
	job.status = text(data.status) ?? job.status
	job.stage = text(data.stage)
	job.reason = text(data.reason)
	job.ahead = int(data.ahead)
	job.pagesDone = int(data.pagesDone)
	job.pagesTotal = int(data.pagesTotal)
	job.backendReady = data.backendReady === true
	job.outputFileId = int(data.outputFileId)
	job.outputName = text(data.outputName)
}

function schedule(delay: number): void {
	if (timer !== null) {
		clearTimeout(timer)
	}
	timer = null
	if (stopped || !isOpen.value || document.visibilityState === 'hidden') {
		return
	}
	timer = setTimeout(() => {
		void poll()
	}, delay)
}

async function poll(): Promise<void> {
	if (stopped || jobId === 0) {
		return
	}
	try {
		const response = await axios.get(generateUrl('/apps/pii_redaction/api/v1/jobs/{jobId}', { jobId }))
		apply((response.data ?? {}) as Record<string, unknown>)
		pollFailed.value = false
		failures = 0
		schedule(POLL_MS)
	} catch (error) {
		const status = (error as { response?: { status?: number } }).response?.status
		if (status === 404) {
			unavailable.value = true
			stopped = true
			return
		}
		if (status === 401) {
			sessionExpired.value = true
			stopped = true
			return
		}
		pollFailed.value = true
		schedule(BACKOFF_MS[Math.min(failures, BACKOFF_MS.length - 1)])
		failures += 1
	}
}

function onVisibility(): void {
	if (document.visibilityState === 'hidden') {
		if (timer !== null) {
			clearTimeout(timer)
			timer = null
		}
		return
	}
	if (isOpen.value && !stopped) {
		void poll()
	}
}

// -- actions ----------------------------------------------------------------

async function requestCopy(): Promise<void> {
	if (posting.value) {
		return
	}
	posting.value = true
	postFailed.value = false
	try {
		const response = await axios.post(generateUrl('/apps/pii_redaction/review/{jobId}/placeholder', { jobId }))
		const status = text((response.data as Record<string, unknown> | null)?.status)
		job.status = status ?? 'approved'
		job.stage = 'waiting'
		await nextTick()
		stateRegion.value?.focus()
		schedule(POLL_MS)
	} catch {
		postFailed.value = true
	} finally {
		posting.value = false
	}
}

async function onImageError(): Promise<void> {
	imageLoading.value = false
	// A failed image can mean the file changed or the share closed: the
	// status decides, otherwise the warning card offers a new attempt.
	stopped = false
	await poll()
	if (job.status === 'review' && !unavailable.value) {
		imageFailed.value = true
	}
}

function retryImage(): void {
	imageFailed.value = false
	imageLoading.value = true
	imageRetry.value += 1
}

function reloadPage(): void {
	window.location.reload()
}

// -- title ------------------------------------------------------------------

const titleSuffix = (() => {
	const at = document.title.indexOf(' - ')
	return at >= 0 ? document.title.slice(at) : ''
})()

watch(heading, () => {
	const title = nameVisible.value
		? t('pii_redaction', 'Review: %s').replace('%s', startName as string)
		: t('pii_redaction', 'Review')
	document.title = title + titleSuffix
}, { immediate: true })

// Once open becomes closed (review, end states) the timer simply ends.
watch(isOpen, (open) => {
	if (open) {
		schedule(POLL_MS)
	}
})

onMounted(() => {
	document.addEventListener('visibilitychange', onVisibility)
	schedule(POLL_MS)
})

onBeforeUnmount(() => {
	stopped = true
	document.removeEventListener('visibilitychange', onVisibility)
	if (timer !== null) {
		clearTimeout(timer)
	}
})
</script>
