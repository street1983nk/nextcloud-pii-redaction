#!/usr/bin/env bash
# The core path of phase 1 for one format and one user, twice, against the
# running instance (01-15-PLAN.md, JOB-01/JOB-02):
#
#   start -> progress until review -> page 1 as PNG through PHP ->
#   notification review_ready without the file name -> placeholder ->
#   background job -> copy next to the original, then the same once more,
#   and the second copy carries " (2)".
#
# usage: ci/flow.sh <pdf|docx|odt> [user, default alice]
# Writes ci/out/progress-<format>-<user>.log (status codes and numbers only).
set -euo pipefail

# shellcheck source=ci/lib.sh
. "$(dirname "$0")/lib.sh"

FORMAT="${1:?usage: ci/flow.sh <pdf|docx|odt> [user]}"
USER_ID="${2:-alice}"
load_fileids
# The canary of ci/make_fixtures.py; lib.sh carries the same value.
[ "${CANARY}" = 'PIIKANARIE7Q4XZ9' ] || fail "ci/lib.sh carries another canary"

case "${FORMAT}" in
	pdf) ORIGINAL='Bescheid 2026-114.pdf' ;;
	docx) ORIGINAL='Antrag.docx' ;;
	odt) ORIGINAL='Vermerk.odt' ;;
	*) fail "unknown format ${FORMAT}" ;;
esac
STEM="${ORIGINAL%.*}"
# The suffix by the language ci/seed.sh gave the user (UI-SPEC area 4).
case "${USER_ID}" in
	elke | greta) COPY="${STEM}_geschwärzt.pdf" ;;
	fleur) COPY="${STEM}_caviardé.pdf" ;;
	*) COPY="${STEM}_redacted.pdf" ;;
esac
COPY_AGAIN="${COPY%.pdf} (2).pdf"

var="FILE_$(printf '%s' "${FORMAT}" | tr '[:lower:]' '[:upper:]')_$(printf '%s' "${USER_ID}" | tr '[:lower:]' '[:upper:]')"
FILE_ID="${!var:-}"
[ -n "${FILE_ID}" ] || fail "no fixture ${var} in ci/out/fileids.env"
PROGRESS_LOG="${CI_OUT}/progress-${FORMAT}-${USER_ID}.log"
export PROGRESS_LOG
: > "${PROGRESS_LOG}"

etag_before=$(etag_of "${USER_ID}" "${ORIGINAL}")
sha_before=$(sha256_of "${USER_ID}" "${ORIGINAL}")
[ -n "${etag_before}" ] || fail "the original has no etag"

nfc() {
	python3 -c 'import sys, unicodedata; print(unicodedata.normalize("NFC", sys.argv[1]))' "$1"
}

one_run() {
	local expected="$1" job body headers code magic notifications
	job=$(start_job "${USER_ID}" "${FILE_ID}" 201)
	[[ "${job}" =~ ^[0-9]+$ ]] || fail "the start gave no job id"
	echo "${FORMAT} ${USER_ID}: job ${job} started"

	wait_status "${USER_ID}" "${job}" review
	body="${CI_OUT}/status-${job}.json"
	header_of "${body}.headers" Cache-Control | grep -q 'no-store' || fail "the status answer is not no-store"

	# Page 1 as PNG through the PHP app, with the recheck of every request.
	headers="${CI_OUT}/page-${job}.headers"
	code=$(req "${USER_ID}" GET "${APP_PATH}/review/${job}/page/1" "${CI_OUT}/page-${job}.png" "${headers}")
	[ "${code}" = "200" ] || fail "page 1 of job ${job} answered ${code}"
	magic=$(head -c 8 "${CI_OUT}/page-${job}.png" | od -An -tx1 | tr -d ' \n')
	[ "${magic}" = "89504e470d0a1a0a" ] || fail "page 1 of job ${job} is no PNG"
	header_of "${headers}" X-Content-Type-Options | grep -qi 'nosniff' || fail "page 1 is not nosniff"
	header_of "${headers}" Cache-Control | grep -q 'no-store' || fail "page 1 is not no-store"

	# The notification of the job, without the file name and without the canary.
	notifications="${CI_OUT}/notifications-${job}.json"
	code=$(req "${USER_ID}" GET '/ocs/v2.php/apps/notifications/api/v2/notifications?format=json' "${notifications}" "${notifications}.headers")
	[ "${code}" = "200" ] || fail "the notifications answered ${code} (is the notifications app enabled?)"
	python3 - "${notifications}" "${job}" <<'PY' || fail "no notification for job ${job}"
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))["ocs"]["data"]
hits = [n for n in data if n.get("app") == "pii_redaction" and n.get("object_type") == "job" and n.get("object_id") == sys.argv[2]]
sys.exit(0 if hits else 1)
PY
	if grep -qF "${STEM}" "${notifications}" || grep -qF "${CANARY}" "${notifications}"; then
		fail "a notification carries the file name or the canary"
	fi

	code=$(req "${USER_ID}" POST "${APP_PATH}/review/${job}/placeholder" "${CI_OUT}/placeholder-${job}.json" "${CI_OUT}/placeholder-${job}.headers")
	[ "${code}" = "202" ] || fail "the placeholder request of job ${job} answered ${code}: $(cat "${CI_OUT}/placeholder-${job}.json")"

	# The container makes the PDF (approved, applying, verified); the copy is
	# stored by PublishJob, a background job, so cron.php runs until published.
	wait_status "${USER_ID}" "${job}" verified published
	local round status=""
	for round in $(seq 1 30); do
		cron_round
		job_status "${USER_ID}" "${job}" "${body}" > /dev/null
		status=$(json_field "${body}" status)
		echo "${status} cron-round ${round}" >> "${PROGRESS_LOG}"
		[ "${status}" = "published" ] && break
		case "${status}" in failed | stale | cancelled | expired) fail "job ${job} ended as ${status} ($(json_field "${body}" reason))" ;; esac
		sleep 2
	done
	[ "${status}" = "published" ] || fail "job ${job} is ${status} after 30 cron rounds"

	local name
	name=$(json_field "${body}" outputName)
	[ "$(nfc "${name}")" = "$(nfc "${expected}")" ] || fail "the copy of job ${job} is called '${name}', expected '${expected}'"
	[ "$(fileid_of "${USER_ID}" "${expected}")" = "$(json_field "${body}" outputFileId)" ] \
		|| fail "the copy of job ${job} is not next to the original"

	curl -sfS -u "${USER_ID}:${CI_PASS}" -o "${CI_OUT}/copy-${job}.pdf" "$(dav_url "${USER_ID}" "${expected}")"
	python3 "${CI_DIR}/pdf_text.py" "${CI_OUT}/copy-${job}.pdf" > "${CI_OUT}/copy-${job}.txt"
	grep -qF 'Placeholder from PII Redaction' "${CI_OUT}/copy-${job}.txt" || fail "the copy of job ${job} is not the placeholder (positive control)"
	if grep -qF "${CANARY}" "${CI_OUT}/copy-${job}.txt" || grep -aqF "${CANARY}" "${CI_OUT}/copy-${job}.pdf"; then
		fail "the copy of job ${job} carries the canary"
	fi
	echo "${FORMAT} ${USER_ID}: job ${job} published as the expected copy"
}

one_run "${COPY}"
one_run "${COPY_AGAIN}"

[ "$(etag_of "${USER_ID}" "${ORIGINAL}")" = "${etag_before}" ] || fail "the etag of the original changed"
[ "$(sha256_of "${USER_ID}" "${ORIGINAL}")" = "${sha_before}" ] || fail "the bytes of the original changed"
echo "${FORMAT} ${USER_ID}: core path twice, original untouched"
