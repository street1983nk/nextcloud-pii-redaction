#!/usr/bin/env bash
# Rights in the real run (01-17-PLAN.md, JOB-03, decision 5 and 6):
#
#   (a) bob starts on a file of alice: 404 not_readable
#   (b) bob reads a job of alice (status, review page, page image): 404 each,
#       no file name in the body
#   (c) carol starts on a file behind the group folder ACL -read: 404, and
#       carol reads alice's group folder job: 404
#   (d) bob starts on a share with the download switched off: 403 download_blocked
#   (e) bob reaches review on a plain share, alice revokes it: status, review
#       page and page image 404 for bob
#   (f) bob reaches review on a share with download, alice switches the download
#       off: page image 403, status 200 with recheck download_blocked
#
# Positive controls in the same script: alice reads her own job with 200 and
# the page image, bob reads his jobs before the share is revoked or blocked.
# Writes ci/out/rights-*.json (status codes and job ids only).
set -euo pipefail

# shellcheck source=ci/lib.sh
. "$(dirname "$0")/lib.sh"

load_fileids
STEM='Bescheid 2026-114'
PDF="${STEM}.pdf"
SHARES_API='/ocs/v2.php/apps/files_sharing/api/v1/shares'

# expect_code <what> <expected> <actual>
expect_code() {
	[ "$3" = "$2" ] || fail "$1 answered $3, expected $2"
	echo "ok: $1 -> $3"
}

# A body of a refusal carries neither the file name nor the canary.
no_name_in() {
	if grep -aqF "${STEM}" "$1" || grep -aqF "$(urlpath "${STEM}")" "$1" || grep -aqF "${CANARY}" "$1"; then
		fail "the answer in $(basename "$1") carries the file name or the canary"
	fi
}

# refused_start <user> <file id> <code> <reason>
refused_start() {
	local body="${CI_OUT}/rights-start-$1-$2.json" code
	code=$(req "$1" POST "${APP_PATH}/api/v1/jobs" "${body}" "${body}.headers" \
		-H 'Content-Type: application/json' --data "{\"fileId\": $2}")
	expect_code "start as $1 on file $2" "$3" "${code}"
	[ "$(json_field "${body}" reason)" = "$4" ] || fail "start as $1 on file $2 gave reason '$(json_field "${body}" reason)', expected $4"
	no_name_in "${body}"
}

# three_routes <user> <job> <status code> <page code> <image code>
three_routes() {
	local user="$1" job="$2" out="${CI_OUT}/rights-$1-$2" code
	code=$(job_status "${user}" "${job}" "${out}-status.json")
	expect_code "status of job ${job} as ${user}" "$3" "${code}"
	code=$(req "${user}" GET "${APP_PATH}/review/${job}" "${out}-page.html" "${out}-page.headers")
	expect_code "review page of job ${job} as ${user}" "$4" "${code}"
	code=$(req "${user}" GET "${APP_PATH}/review/${job}/page/1" "${out}-image.bin" "${out}-image.headers")
	expect_code "page image of job ${job} as ${user}" "$5" "${code}"
	if [ "$3" = "404" ]; then
		no_name_in "${out}-status.json"
		no_name_in "${out}-page.html"
		no_name_in "${out}-image.bin"
	fi
}

# A fresh copy of the PDF for alice over WebDAV COPY; prints nothing.
copy_for_alice() {
	curl -sfS -u "alice:${CI_PASS}" -X COPY -H "Destination: $(dav_url alice "$1")" -H 'Overwrite: F' \
		"$(dav_url alice "${PDF}")" > /dev/null || fail "the copy for alice could not be made"
}

# share_with_bob <path> <attributes or empty>: prints the share id.
share_with_bob() {
	local body="${CI_OUT}/rights-share.json" code
	local args=(--data-urlencode "path=/$1" --data-urlencode 'shareWith=bob'
		--data-urlencode 'shareType=0' --data-urlencode 'permissions=1')
	[ -z "$2" ] || args+=(--data-urlencode "attributes=$2")
	code=$(req alice POST "${SHARES_API}?format=json" "${body}" "${body}.headers" "${args[@]}")
	[ "${code}" = "200" ] || fail "the share to bob answered ${code}"
	python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["ocs"]["data"]["id"])' "${body}"
}

# bob_file <path>: the file id bob sees for a share (the mount lands in the
# mount cache with the PROPFIND and the scan).
bob_file() {
	occ files:scan bob > /dev/null
	local id
	id=$(fileid_of bob "$1")
	[[ "${id}" =~ ^[0-9]+$ ]] || fail "bob does not see the share"
	printf '%s' "${id}"
}

# -- positive control: alice reads her own job ---------------------------------

job_alice=$(start_job alice "${FILE_PDF_ALICE}" 201)
wait_status alice "${job_alice}" review
three_routes alice "${job_alice}" 200 200 200
[ "$(json_field "${CI_OUT}/rights-alice-${job_alice}-status.json" recheck)" = "ok" ] || fail "alice's own job does not recheck ok"

# -- (a) a foreign file ----------------------------------------------------------

refused_start bob "${FILE_PDF_ALICE}" 404 not_readable

# -- (b) a foreign job -------------------------------------------------------------

three_routes bob "${job_alice}" 404 404 404

# -- (c) the group folder ACL ------------------------------------------------------

refused_start carol "${FILE_GF_CAROL}" 404 not_readable
job_group=$(start_job alice "${FILE_GF_ALICE}" 201)
wait_status alice "${job_group}" review
three_routes alice "${job_group}" 200 200 200
# carol reads the file itself (seed.sh proved it) but not alice's job on it.
three_routes carol "${job_group}" 404 404 404

# -- (d) the share with the download switched off -----------------------------

refused_start bob "${FILE_SHARED_BLOCKED_BOB}" 403 download_blocked

# -- (e) a share revoked after review -------------------------------------------

revoked="${STEM} Freigabe.pdf"
copy_for_alice "${revoked}"
share_revoked=$(share_with_bob "${revoked}" '')
file_revoked=$(bob_file "${revoked}")
job_revoked=$(start_job bob "${file_revoked}" 201)
wait_status bob "${job_revoked}" review
three_routes bob "${job_revoked}" 200 200 200
code=$(req alice DELETE "${SHARES_API}/${share_revoked}?format=json" "${CI_OUT}/rights-unshare.json" "${CI_OUT}/rights-unshare.headers")
expect_code "unshare of share ${share_revoked}" 200 "${code}"
three_routes bob "${job_revoked}" 404 404 404

# -- (f) the download switched off after review ---------------------------------

blocked_later="${STEM} Sperre.pdf"
copy_for_alice "${blocked_later}"
share_later=$(share_with_bob "${blocked_later}" '[{"scope":"permissions","key":"download","value":true}]')
file_later=$(bob_file "${blocked_later}")
job_later=$(start_job bob "${file_later}" 201)
wait_status bob "${job_later}" review
three_routes bob "${job_later}" 200 200 200
code=$(req alice PUT "${SHARES_API}/${share_later}?format=json" "${CI_OUT}/rights-block.json" "${CI_OUT}/rights-block.headers" \
	--data-urlencode 'permissions=1' \
	--data-urlencode 'attributes=[{"scope":"permissions","key":"download","value":false}]')
expect_code "download switched off on share ${share_later}" 200 "${code}"
code=$(req bob GET "${APP_PATH}/review/${job_later}/page/1" "${CI_OUT}/rights-block-image.bin" "${CI_OUT}/rights-block-image.headers")
expect_code "page image of job ${job_later} as bob under the download block" 403 "${code}"
code=$(job_status bob "${job_later}" "${CI_OUT}/rights-block-status.json")
expect_code "status of job ${job_later} as bob under the download block" 200 "${code}"
recheck=$(json_field "${CI_OUT}/rights-block-status.json" recheck)
[ "${recheck}" = "download_blocked" ] || fail "the status of job ${job_later} rechecks '${recheck}', expected download_blocked"
no_name_in "${CI_OUT}/rights-block-image.bin"

echo "rights done: jobs ${job_alice} ${job_group} ${job_revoked} ${job_later}"
