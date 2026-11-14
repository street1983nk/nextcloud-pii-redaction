#!/usr/bin/env bash
# The etag binding in the real run (01-17-PLAN.md, JOB-04):
#
#   a job in review, then a WebDAV PUT with changed bytes on the original:
#   status stale(original_changed), page image 409, one notification of the
#   job with the subject job_stale;
#   a second job in review, then a WebDAV DELETE of the original:
#   cancelled(original_deleted) in the database, status 404, the review page
#   shows the deleted card (200), and no notification of the job is left.
#
# Fresh copies over WebDAV COPY: the fixtures of the other scripts stay as
# they are. Positive controls: before the change the image answers 200 and the
# job has its review_ready notification in the database.
set -euo pipefail

# shellcheck source=ci/lib.sh
. "$(dirname "$0")/lib.sh"

load_fileids
db_init
STEM='Bescheid 2026-114'
PDF="${STEM}.pdf"

copy_for_alice() {
	curl -sfS -u "alice:${CI_PASS}" -X COPY -H "Destination: $(dav_url alice "$1")" -H 'Overwrite: F' \
		"$(dav_url alice "${PDF}")" > /dev/null || fail "the copy for alice could not be made"
}

image_code() {
	req alice GET "${APP_PATH}/review/$1/page/1" "${CI_OUT}/stale-image-$1.bin" "${CI_OUT}/stale-image-$1.headers"
}

# The raw subjects of the notifications of one job, from the notifications
# table (the OCS answer carries the rendered text only).
subjects_of() {
	db_query "SELECT subject FROM oc_notifications WHERE app = 'pii_redaction' AND object_type = 'job' AND object_id = '$1'"
}

# review_job <path>: a job of alice on a fresh copy, waited until review;
# prints the job id.
review_job() {
	copy_for_alice "$1"
	local file job
	file=$(fileid_of alice "$1")
	[[ "${file}" =~ ^[0-9]+$ ]] || fail "the copy has no file id"
	job=$(start_job alice "${file}" 201)
	wait_status alice "${job}" review > /dev/null
	[ "$(image_code "${job}")" = "200" ] || fail "page image of job ${job} is not 200 before the change (positive control)"
	subjects_of "${job}" | grep -qx 'review_ready' || fail "job ${job} has no review_ready notification (positive control)"
	printf '%s' "${job}"
}

# -- a changed original ------------------------------------------------------------

changed="${STEM} Stale.pdf"
job_changed=$(review_job "${changed}")
echo "job ${job_changed} in review"

# Changed bytes: the fixture plus one comment line after %%EOF.
{
	curl -sfS -u "alice:${CI_PASS}" "$(dav_url alice "${changed}")"
	printf '%% changed by ci/stale.sh\n'
} > "${CI_OUT}/stale-changed.pdf"
curl -sfS -u "alice:${CI_PASS}" -T "${CI_OUT}/stale-changed.pdf" "$(dav_url alice "${changed}")" > /dev/null \
	|| fail "the PUT on the original failed"
rm -f "${CI_OUT}/stale-changed.pdf"

code=$(job_status alice "${job_changed}" "${CI_OUT}/stale-status-${job_changed}.json")
[ "${code}" = "200" ] || fail "status of the changed job answered ${code}"
status=$(json_field "${CI_OUT}/stale-status-${job_changed}.json" status)
reason=$(json_field "${CI_OUT}/stale-status-${job_changed}.json" reason)
[ "${status}" = "stale" ] && [ "${reason}" = "original_changed" ] \
	|| fail "the changed job is ${status}(${reason}), expected stale(original_changed)"
code=$(image_code "${job_changed}")
[ "${code}" = "409" ] || fail "page image of the changed job answered ${code}, expected 409"
subjects=$(subjects_of "${job_changed}")
[ "${subjects}" = "job_stale" ] || fail "the notifications of the changed job are '${subjects//$'\n'/,}', expected job_stale"
echo "ok: job ${job_changed} stale(original_changed), image 409, notification job_stale"

# -- a deleted original ------------------------------------------------------------

deleted="${STEM} Delete.pdf"
job_deleted=$(review_job "${deleted}")
echo "job ${job_deleted} in review"

curl -sfS -u "alice:${CI_PASS}" -X DELETE "$(dav_url alice "${deleted}")" > /dev/null || fail "the DELETE of the original failed"

row=$(db_query "SELECT status, reason FROM oc_pii_jobs WHERE id = ${job_deleted}")
[ "${row}" = "$(printf 'cancelled\toriginal_deleted')" ] \
	|| fail "the deleted job is '${row//$'\t'/ }' in the database, expected cancelled original_deleted"
# Before the review page is opened, which would dismiss them as well.
subjects=$(subjects_of "${job_deleted}")
[ -z "${subjects}" ] || fail "the deleted job still has notifications: ${subjects//$'\n'/,}"
code=$(job_status alice "${job_deleted}" "${CI_OUT}/stale-status-${job_deleted}.json")
[ "${code}" = "404" ] || fail "status of the deleted job answered ${code}, expected 404 (the file is gone for alice)"
code=$(req alice GET "${APP_PATH}/review/${job_deleted}" "${CI_OUT}/stale-page-${job_deleted}.html" "${CI_OUT}/stale-page-${job_deleted}.headers")
[ "${code}" = "200" ] || fail "the review page of the deleted job answered ${code}, expected the deleted card (200)"
if grep -aqF "${STEM}" "${CI_OUT}/stale-page-${job_deleted}.html"; then
	fail "the deleted card carries the file name"
fi
code=$(image_code "${job_deleted}")
[ "${code}" = "404" ] || fail "page image of the deleted job answered ${code}, expected 404"
echo "ok: job ${job_deleted} cancelled(original_deleted), no notification"
