#!/usr/bin/env bash
# One job at a time, sampled in the database (01-17-PLAN.md, JOB-06):
#
#   three jobs (PDF, DOCX, ODT on fresh WebDAV copies) started right after one
#   another; the position "ahead" of each start answer is logged and must not
#   fall, the third is at least 1;
#   until all three are in review, every 0.5 s one sample
#     SELECT COUNT(*) FROM oc_pii_jobs
#     WHERE status IN ('analyzing','applying') AND lease_until > <now>
#   on SQLite (python3 sqlite3 on the data directory) or on MariaDB (the
#   mariadb client inside the service container), into ci/out/queue-samples.log.
#
# Every sample is at most 1; at least one sample is exactly 1 (positive
# control: the query does see a running job).
set -euo pipefail

# shellcheck source=ci/lib.sh
. "$(dirname "$0")/lib.sh"

db_init
SAMPLES="${CI_OUT}/queue-samples.log"
: > "${SAMPLES}"

copy_for_alice() {
	curl -sfS -u "alice:${CI_PASS}" -X COPY -H "Destination: $(dav_url alice "$2")" -H 'Overwrite: F' \
		"$(dav_url alice "$1")" > /dev/null || fail "the copy for alice could not be made"
	local id
	id=$(fileid_of alice "$2")
	[[ "${id}" =~ ^[0-9]+$ ]] || fail "the copy has no file id"
	printf '%s' "${id}"
}

file_pdf=$(copy_for_alice 'Bescheid 2026-114.pdf' 'Bescheid 2026-114 Queue.pdf')
file_docx=$(copy_for_alice 'Antrag.docx' 'Antrag Queue.docx')
file_odt=$(copy_for_alice 'Vermerk.odt' 'Vermerk Queue.odt')
files=("${file_pdf}" "${file_docx}" "${file_odt}")

# Nothing of the earlier scripts may still hold a lease, or the first
# position would count it.
idle_deadline=$((SECONDS + 120))
until [ "$(db_query "SELECT COUNT(*) FROM oc_pii_jobs WHERE status IN ('analyzing','applying') AND lease_until > $(date +%s)")" = "0" ]; do
	[ "${SECONDS}" -lt "${idle_deadline}" ] || fail "a job of an earlier script still holds a lease"
	sleep 1
done

job_ids=()
aheads=()
for file in "${files[@]}"; do
	body="${CI_OUT}/queue-start-${file}.json"
	code=$(req alice POST "${APP_PATH}/api/v1/jobs" "${body}" "${body}.headers" \
		-H 'Content-Type: application/json' --data "{\"fileId\": ${file}}")
	[ "${code}" = "201" ] || fail "start on file ${file} answered ${code}"
	job_ids+=("$(json_field "${body}" jobId)")
	aheads+=("$(json_field "${body}" ahead)")
done
echo "jobs ${job_ids[*]}, ahead ${aheads[*]}" | tee -a "${SAMPLES}"

previous=-1
for ahead in "${aheads[@]}"; do
	[[ "${ahead}" =~ ^[0-9]+$ ]] || fail "a start answer has no position (ahead '${ahead}')"
	[ "${ahead}" -ge "${previous}" ] || fail "the positions fall: ${aheads[*]}"
	previous="${ahead}"
done
[ "${aheads[2]}" -ge 1 ] || fail "the third job has nothing ahead of it: ${aheads[*]}"

# -- the samples ---------------------------------------------------------------

deadline=$((SECONDS + ${WAIT_SECONDS:-600}))
round=0
while :; do
	count=$(db_query "SELECT COUNT(*) FROM oc_pii_jobs WHERE status IN ('analyzing','applying') AND lease_until > $(date +%s)")
	[[ "${count}" =~ ^[0-9]+$ ]] || fail "a sample gave no number: '${count}'"
	echo "sample ${round} active ${count}" >> "${SAMPLES}"
	[ "${count}" -le 1 ] || fail "${count} jobs hold an active lease at once (sample ${round})"

	# Every fourth round (2 s) the status of the three jobs.
	if [ $((round % 4)) -eq 0 ]; then
		in_review=0
		for job in "${job_ids[@]}"; do
			code=$(job_status alice "${job}" "${CI_OUT}/queue-status-${job}.json")
			[ "${code}" = "200" ] || fail "status of job ${job} answered ${code}"
			status=$(json_field "${CI_OUT}/queue-status-${job}.json" status)
			case "${status}" in
				review) in_review=$((in_review + 1)) ;;
				failed | stale | cancelled | expired) fail "job ${job} ended as ${status}" ;;
			esac
		done
		echo "round ${round} in review ${in_review}" >> "${SAMPLES}"
		[ "${in_review}" -lt "${#job_ids[@]}" ] || break
	fi
	[ "${SECONDS}" -lt "${deadline}" ] || fail "the three jobs did not all reach review in ${WAIT_SECONDS:-600} s"
	round=$((round + 1))
	sleep 0.5
done

samples=$(grep -c '^sample ' "${SAMPLES}")
exactly_one=$(grep -c '^sample [0-9]* active 1$' "${SAMPLES}" || true)
over_one=$(grep -cE '^sample [0-9]+ active ([2-9]|[1-9][0-9]+)$' "${SAMPLES}" || true)
[ "${over_one}" = "0" ] || fail "${over_one} samples saw more than one active lease"
[ "${exactly_one}" -ge 1 ] || fail "no sample saw a running job (positive control of the query)"
echo "queue done: ${samples} samples, ${exactly_one} with exactly 1 active lease, none above 1, ahead ${aheads[*]}" | tee -a "${SAMPLES}"
