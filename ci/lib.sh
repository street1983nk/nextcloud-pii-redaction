#!/usr/bin/env bash
# The variables and functions are used by the scripts that source this file.
# shellcheck disable=SC2034,SC2329
# Shared helpers of the CI scripts, sourced by ci/seed.sh, ci/flow.sh and the
# check scripts of plan 17. Not run on its own.
#
# The contract of every script under ci/ (01-15-PLAN.md):
#   NC_URL      address of the throwaway Nextcloud (http://localhost:8080)
#   NC_ROOT     server root in the runner (occ, cron.php, data/)
#   ADMIN_USER  ADMIN_PASS  the instance admin
#   CI_PASS     the password of every test user
#   ci/out/fileids.env  the file ids ci/seed.sh wrote
# Output goes to ci/out/ only. Every failure stops with a clear message.
set -euo pipefail

CI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CI_OUT="${CI_DIR}/out"
mkdir -p "${CI_OUT}"
APP_PATH="/index.php/apps/pii_redaction"
CANARY='PIIKANARIE7Q4XZ9'

: "${NC_URL:?NC_URL is required}"
: "${NC_ROOT:?NC_ROOT is required}"
: "${ADMIN_USER:?ADMIN_USER is required}"
: "${ADMIN_PASS:?ADMIN_PASS is required}"
: "${CI_PASS:?CI_PASS is required}"

fail() {
	echo "FAIL: $*" >&2
	exit 1
}

occ() {
	php "${NC_ROOT}/occ" "$@"
}

load_fileids() {
	[ -s "${CI_OUT}/fileids.env" ] || fail "ci/out/fileids.env is missing, run ci/seed.sh first"
	# shellcheck disable=SC1091 # written by ci/seed.sh at run time
	. "${CI_OUT}/fileids.env"
}

password_of() {
	if [ "$1" = "${ADMIN_USER}" ]; then
		printf '%s' "${ADMIN_PASS}"
	else
		printf '%s' "${CI_PASS}"
	fi
}

# Percent-encode one path (slashes stay), UTF-8 in NFC.
urlpath() {
	python3 -c 'import sys, unicodedata, urllib.parse; print(urllib.parse.quote(unicodedata.normalize("NFC", sys.argv[1]), safe="/"))' "$1"
}

dav_url() {
	printf '%s/remote.php/dav/files/%s/%s' "${NC_URL}" "$1" "$(urlpath "$2")"
}

# req <user> <method> <path> <body file> <header file> [curl args...]
# Prints the HTTP status. Basic auth plus OCS-APIRequest: without a session
# cookie Nextcloud skips the CSRF check of a FrontpageRoute POST.
req() {
	local user="$1" method="$2" path="$3" body="$4" headers="$5"
	shift 5
	curl -s -o "${body}" -D "${headers}" -w '%{http_code}' -X "${method}" \
		-u "${user}:$(password_of "${user}")" \
		-H 'OCS-APIRequest: true' -H 'Accept: application/json' \
		"$@" "${NC_URL}${path}"
}

# The value of one header (case insensitive), without the line end.
header_of() {
	grep -i "^$2:" "$1" | tail -n 1 | cut -d: -f2- | tr -d '\r' | sed 's/^ *//'
}

json_field() {
	python3 -c 'import json, sys; v = json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2]); print("" if v is None else v)' "$1" "$2"
}

# The status answer of one job as one user into the given file; prints the code.
job_status() {
	req "$1" GET "${APP_PATH}/api/v1/jobs/$2" "$3" "$3.headers"
}

# wait_status <user> <job> <target status...>: polls every 2 s, at most
# WAIT_SECONDS (600), logs codes and numbers to PROGRESS_LOG if set, fails on
# a terminal status that is not one of the targets.
wait_status() {
	local user="$1" job="$2"
	shift 2
	local targets=" $* " deadline=$((SECONDS + ${WAIT_SECONDS:-600})) body="${CI_OUT}/status-${job}.json"
	local code status
	while :; do
		code=$(job_status "${user}" "${job}" "${body}")
		[ "${code}" = "200" ] || fail "status of job ${job} as ${user} answered ${code}"
		status=$(json_field "${body}" status)
		if [ -n "${PROGRESS_LOG:-}" ]; then
			python3 -c 'import json, sys; d = json.load(open(sys.argv[1], encoding="utf-8")); print(*(d.get(k) for k in ("status", "stage", "pagesDone", "pagesTotal", "ahead")))' "${body}" >> "${PROGRESS_LOG}"
		fi
		case "${targets}" in *" ${status} "*) return 0 ;; esac
		case "${status}" in
			failed | stale | cancelled | expired)
				fail "job ${job} ended as ${status} ($(json_field "${body}" reason)) while waiting for${targets}"
				;;
		esac
		[ "${SECONDS}" -lt "${deadline}" ] || fail "job ${job} still ${status} after ${WAIT_SECONDS:-600} s, waiting for${targets}"
		sleep 2
	done
}

# The file id of a path of a user over WebDAV.
fileid_of() {
	curl -sfS -u "$1:$(password_of "$1")" -X PROPFIND -H 'Depth: 0' \
		--data '<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns"><d:prop><oc:fileid/></d:prop></d:propfind>' \
		"$(dav_url "$1" "$2")" | sed -n 's|.*<oc:fileid>\([0-9]*\)</oc:fileid>.*|\1|p'
}

etag_of() {
	curl -sfS -u "$1:$(password_of "$1")" -X PROPFIND -H 'Depth: 0' \
		--data '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:getetag/></d:prop></d:propfind>' \
		"$(dav_url "$1" "$2")" | sed -n 's|.*<d:getetag>\([^<]*\)</d:getetag>.*|\1|p'
}

sha256_of() {
	curl -sfS -u "$1:$(password_of "$1")" "$(dav_url "$1" "$2")" | sha256sum | cut -d' ' -f1
}

# -- the database of the instance (plan 17) -------------------------------------
# DB_KIND sqlite reads the SQLite file in the data directory with the sqlite3
# module of python3; DB_KIND mariadb asks the client inside the service
# container (DB_CONTAINER, DB_USER, DB_PASS, DB_NAME from the workflow).

# The SQLite file of the instance; prints its path.
sqlite_file() {
	local datadir dbname
	datadir=$(occ config:system:get datadirectory)
	dbname=$(occ config:system:get dbname)
	[ -n "${datadir}" ] && [ -n "${dbname}" ] || fail "the instance names no data directory or database"
	printf '%s/%s.db' "${datadir}" "${dbname}"
}

# db_query <sql>: one line per row, the columns separated by a tab. On SQLite
# the caller sets DB_FILE once (DB_FILE=$(sqlite_file)), occ is slow.
db_query() {
	if [ "${DB_KIND:-sqlite}" = "mariadb" ]; then
		: "${DB_CONTAINER:?DB_CONTAINER is required on the mariadb leg}"
		docker exec "${DB_CONTAINER}" mariadb -u"${DB_USER}" -p"${DB_PASS}" "${DB_NAME}" -N -B -e "$1"
	else
		: "${DB_FILE:?DB_FILE is not set, call sqlite_file first}"
		python3 - "${DB_FILE}" "$1" <<'PY'
import sqlite3, sys
connection = sqlite3.connect(sys.argv[1], timeout=15)
for row in connection.execute(sys.argv[2]):
    print("\t".join("" if value is None else str(value) for value in row))
PY
	fi
}

db_init() {
	if [ "${DB_KIND:-sqlite}" != "mariadb" ]; then
		DB_FILE=$(sqlite_file)
		[ -s "${DB_FILE}" ] || fail "the SQLite file of the instance is missing"
		export DB_FILE
	fi
	# Positive control: the query reaches the table this app created.
	[ "$(db_query "SELECT COUNT(*) FROM oc_pii_slot WHERE id = 1")" = "1" ] \
		|| fail "the database query does not see the slot row of oc_pii_slot"
}

# The background jobs: one cron.php round (PublishJob is a QueuedJob).
cron_round() {
	php -f "${NC_ROOT}/cron.php" > /dev/null 2>&1 || true
}

# start_job <user> <file id> <expected code>: prints the job id.
start_job() {
	local body="${CI_OUT}/start-$1-$2.json" code
	code=$(req "$1" POST "${APP_PATH}/api/v1/jobs" "${body}" "${body}.headers" \
		-H 'Content-Type: application/json' --data "{\"fileId\": $2}")
	[ "${code}" = "$3" ] || fail "start as $1 on file $2 answered ${code}, expected $3: $(cat "${body}")"
	json_field "${body}" jobId
}
