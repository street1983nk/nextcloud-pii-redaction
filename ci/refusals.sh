#!/usr/bin/env bash
# The refusals of the pre-check on the real instance (02-23-PLAN.md, JOB-05,
# D-02-02, D-02-04, pitfall 5 / assumption A6), as alice:
#
#   (0) controls: harmless.pdf reaches review and its notification is counted
#       (so the count below can see one), ext_image.docx reaches review with
#       the event external_links_removed
#   (a) wrong_pdf_as_docx.docx  -> failed wrong_type
#   (b) pdf_301_pages.pdf       -> failed too_many_pages
#   (c) pdf_user_password.pdf   -> failed encrypted_pdf
#   (d) cfb_encrypted.docx      -> failed encrypted_document
#   (e) a file below a folder with the E2E flag: the start is refused with
#       e2e_encrypted and no job exists; without the flag the same file
#       starts (the refusal came from the flag and from nothing else)
#   (f) pdf_signed.pdf waits in confirm with the event signature_notice; a
#       stranger and a session without the request token cannot confirm; the
#       POST of the initiator with the request token of the session can, and
#       the job reaches review with signature_confirmed after signature_notice
#   (g) D-02-02: none of the refusals (a) to (e) made a notification. Judged
#       last, so one run shows every other proof before it.
#
# A6: the script reads the columns of oc_filecache from the database itself
# and stops when there is no column "encrypted" (the flag FileAccess asks at
# the folders above a file).
#
# The files come from ci/make_corpus.py --e2e into ci/out/corpus, where the
# Playwright suite reads them afterwards. Output: words of the closed lists,
# ids and numbers only, never the content of a file.
#
# Uses the contract of ci/lib.sh plus DB_KIND (and DB_CONTAINER, DB_USER,
# DB_PASS, DB_NAME on the MariaDB leg).
set -euo pipefail

# shellcheck source=ci/lib.sh
. "$(dirname "$0")/lib.sh"

CORPUS="${CI_OUT}/corpus"
FOLDER='refusals'
E2E_FOLDER='refusals-e2e'
CONTROL='harmless.pdf'
SANITIZED='ext_image.docx'
SIGNED='pdf_signed.pdf'
JAR="${CI_OUT}/refusals-session.cookies"
NOTIFICATIONS_API='/ocs/v2.php/apps/notifications/api/v2/notifications?format=json'
# The API hands out one page of notifications; a count close to it could hide
# a new one. alice has six after ci/flow.sh.
NOTIFICATION_PAGE=20
# The ceiling of one job: the pre-check answers within seconds, the two runs
# through the renderer and LibreOffice within a minute.
REFUSAL_SECONDS=180
REVIEW_SECONDS=300
REFUSED_JOBS=()

db_init

# -- helpers -----------------------------------------------------------------------

mkcol() {
	curl -sfS -u "$1:$(password_of "$1")" -X MKCOL "$(dav_url "$1" "$2")" > /dev/null \
		|| fail "folder $2 for $1 could not be created"
}

upload() {
	curl -sfS -u "$1:$(password_of "$1")" -T "$2" "$(dav_url "$1" "$3")" > /dev/null \
		|| fail "upload of $(basename "$2") for $1 failed"
}

# id_of <user> <path>: the file id, or a stop when there is none.
id_of() {
	local id
	id=$(fileid_of "$1" "$2")
	[[ "${id}" =~ ^[0-9]+$ ]] || fail "no file id for $2"
	printf '%s' "${id}"
}

# db_exec <sql>: one changing statement, committed. db_query of ci/lib.sh only
# reads (its SQLite connection never commits).
db_exec() {
	if [ "${DB_KIND:-sqlite}" = "mariadb" ]; then
		: "${DB_CONTAINER:?DB_CONTAINER is required on the mariadb leg}"
		docker exec "${DB_CONTAINER}" mariadb -u"${DB_USER}" -p"${DB_PASS}" "${DB_NAME}" -e "$1"
	else
		python3 - "${DB_FILE}" "$1" <<'PY'
import sqlite3, sys
connection = sqlite3.connect(sys.argv[1], timeout=30)
with connection:
    changed = connection.execute(sys.argv[2]).rowcount
if changed != 1:
    sys.exit(f"the statement changed {changed} rows, expected 1")
PY
	fi
}

# column_of <table> <column>: the name of the column when the table has it.
column_of() {
	if [ "${DB_KIND:-sqlite}" = "mariadb" ]; then
		db_query "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '$1' AND COLUMN_NAME = '$2'"
	else
		db_query "SELECT name FROM pragma_table_info('$1') WHERE name = '$2'"
	fi
}

events_of() {
	db_query "SELECT action FROM oc_pii_job_events WHERE job_id = $1 ORDER BY id"
}

# has_event <job> <action>. The rows are read first: a grep -q that leaves
# early would break the pipe of the query under pipefail.
has_event() {
	local events
	events=$(events_of "$1")
	grep -qx "$2" <<<"${events}"
}

# end_of <job> <seconds> <status...>: waits for one of the states and prints
# the one the job reached.
end_of() {
	local job="$1" seconds="$2"
	shift 2
	WAIT_SECONDS="${seconds}" wait_status alice "${job}" "$@"
	json_field "${CI_OUT}/status-${job}.json" status
}

# notifications <user> [job]: prints "<of the app> <of the job> <subjects of
# the job>", read over the OCS API the notification bell uses.
notifications() {
	local user="$1" job="${2:-0}" body="${CI_OUT}/refusals-notifications.json" code
	code=$(req "${user}" GET "${NOTIFICATIONS_API}" "${body}" "${body}.headers")
	[ "${code}" = "200" ] || fail "the notifications answered ${code} (is the notifications app enabled?)"
	python3 - "${body}" "${job}" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))["ocs"]["data"]
ours = [n for n in data if n.get("app") == "pii_redaction"]
of_job = [n for n in ours if n.get("object_type") == "job" and str(n.get("object_id")) == sys.argv[2]]
print(len(ours), len(of_job), ",".join(sorted(str(n.get("subject")) for n in of_job)) or "-")
PY
}

app_notifications() {
	notifications "$1" | cut -d' ' -f1
}

# seen_notification <user> <job> <subject>: waits up to 20 s for exactly that
# one notification of the job. The state of a job changes a moment before its
# notification is sent, within the same request of the container.
seen_notification() {
	local of_job="" subjects=""
	for _ in $(seq 1 20); do
		read -r _ of_job subjects < <(notifications "$1" "$2")
		if [ "${of_job}" = "1" ] && [ "${subjects}" = "$3" ]; then
			return 0
		fi
		sleep 1
	done
	echo "job $2 has ${of_job} notifications (${subjects}), expected one $3" >&2
	return 1
}

# The rows of the notifications app for one job, read in the database: the
# second witness next to the API.
notification_rows() {
	db_query "SELECT COUNT(*) FROM oc_notifications WHERE app = 'pii_redaction' AND object_type = 'job' AND object_id = '$1'"
}

# refused <file name> <reason>: a start that the pre-check ends as failed.
refused() {
	local name="$1" reason="$2" file job status got
	file=$(id_of alice "${FOLDER}/${name}")
	job=$(start_job alice "${file}" 201)
	[[ "${job}" =~ ^[0-9]+$ ]] || fail "the start on ${name} gave no job id"
	status=$(end_of "${job}" "${REFUSAL_SECONDS}" failed review confirm)
	got=$(json_field "${CI_OUT}/status-${job}.json" reason)
	[ "${status}" = "failed" ] || fail "job ${job} on ${name} is ${status}, expected failed ${reason}"
	[ "${got}" = "${reason}" ] || fail "job ${job} on ${name} failed with '${got}', expected ${reason}"
	REFUSED_JOBS+=("${job}")
	echo "ok: ${name} -> failed ${reason} (job ${job})"
}

# head_value <html file> <attribute>: the value of one attribute of the page.
head_value() {
	grep -o "$2=\"[^\"]*\"" "$1" | head -n 1 | cut -d'"' -f2 || true
}

# session_login <user>: a browser session in the cookie jar, built the way the
# login form builds it (no basic auth, no OCS-APIRequest).
session_login() {
	local user="$1" page="${CI_OUT}/refusals-login.html" token code
	rm -f "${JAR}"
	code=$(curl -s -o "${page}" -w '%{http_code}' -c "${JAR}" -b "${JAR}" "${NC_URL}/index.php/login")
	[ "${code}" = "200" ] || fail "the login page answered ${code}"
	token=$(head_value "${page}" data-requesttoken)
	[ -n "${token}" ] || fail "the login page carries no request token"
	code=$(curl -s -o /dev/null -w '%{http_code}' -c "${JAR}" -b "${JAR}" \
		--data-urlencode "user=${user}" --data-urlencode "password=$(password_of "${user}")" \
		--data-urlencode "requesttoken=${token}" "${NC_URL}/index.php/login")
	case "${code}" in
		30[23]) ;;
		*) fail "the login form answered ${code} for ${user}" ;;
	esac
}

# session_token <user> <path>: opens a page in the session and prints its
# request token. The page has to be the page of that user, so a login that
# did not happen stops here.
session_token() {
	local user="$1" page="${CI_OUT}/refusals-page.html" code token
	code=$(curl -s -o "${page}" -w '%{http_code}' -c "${JAR}" -b "${JAR}" "${NC_URL}$2")
	[ "${code}" = "200" ] || fail "the page $2 answered ${code} in the session of ${user}"
	[ "$(head_value "${page}" data-user)" = "${user}" ] || fail "the session is not the session of ${user}"
	token=$(head_value "${page}" data-requesttoken)
	[ -n "${token}" ] || fail "the page $2 carries no request token"
	printf '%s' "${token}"
}

# session_post <path> <body file> [curl args...]: a POST with the cookies of
# the session only; prints the HTTP status.
session_post() {
	local route="$1" answer="$2"
	shift 2
	curl -s -o "${answer}" -D "${answer}.headers" -w '%{http_code}' -X POST -c "${JAR}" -b "${JAR}" \
		-H 'Accept: application/json' "$@" "${NC_URL}${route}"
}

# -- the files ---------------------------------------------------------------------

python3 "${CI_DIR}/make_corpus.py" "${CORPUS}" --e2e
[ -s "${CORPUS}/manifest.json" ] || fail "ci/make_corpus.py wrote no manifest"
mkcol alice "${FOLDER}"
for name in "${CONTROL}" "${SANITIZED}" "${SIGNED}" wrong_pdf_as_docx.docx pdf_301_pages.pdf pdf_user_password.pdf cfb_encrypted.docx; do
	[ -s "${CORPUS}/${name}" ] || fail "ci/make_corpus.py --e2e wrote no ${name}"
	upload alice "${CORPUS}/${name}" "${FOLDER}/${name}"
done

# -- (0) the controls --------------------------------------------------------------

before_control=$(app_notifications alice)
[ "${before_control}" -lt "${NOTIFICATION_PAGE}" ] \
	|| fail "alice has ${before_control} notifications of the app, a new one could fall off the page of the API"
job_control=$(start_job alice "$(id_of alice "${FOLDER}/${CONTROL}")" 201)
status=$(end_of "${job_control}" "${REVIEW_SECONDS}" review)
[ "${status}" = "review" ] || fail "the control ${CONTROL} is ${status}, expected review"
seen_notification alice "${job_control}" review_ready \
	|| fail "positive control failed: the API shows no review_ready for job ${job_control}"
after_control=$(app_notifications alice)
[ "${after_control}" = "$((before_control + 1))" ] \
	|| fail "positive control failed: the count went from ${before_control} to ${after_control}, expected one more"
[ "$(notification_rows "${job_control}")" = "1" ] \
	|| fail "positive control failed: oc_notifications has no row for job ${job_control}"
echo "positive control: ${CONTROL} reached review (job ${job_control}), the count saw its review_ready (${before_control} -> ${after_control})"

job_sanitized=$(start_job alice "$(id_of alice "${FOLDER}/${SANITIZED}")" 201)
status=$(end_of "${job_sanitized}" "${REVIEW_SECONDS}" review)
[ "${status}" = "review" ] || fail "${SANITIZED} is ${status}, expected review"
has_event "${job_sanitized}" external_links_removed \
	|| fail "job ${job_sanitized} on ${SANITIZED} has no event external_links_removed"
echo "ok: ${SANITIZED} -> review with external_links_removed (job ${job_sanitized})"

# -- (a) to (d) the refusals of the pre-check --------------------------------------

before_refusals=$(app_notifications alice)
refused wrong_pdf_as_docx.docx wrong_type
refused pdf_301_pages.pdf too_many_pages
refused pdf_user_password.pdf encrypted_pdf
refused cfb_encrypted.docx encrypted_document

# -- (e) the folder with the E2E flag ----------------------------------------------

# A6, on this database: the query finds a column that is there, and the one
# the app relies on.
[ "$(column_of oc_filecache fileid)" = "fileid" ] \
	|| fail "positive control failed: the column query does not see oc_filecache.fileid"
[ "$(column_of oc_filecache encrypted)" = "encrypted" ] \
	|| fail "A6 does not hold: oc_filecache has no column 'encrypted' on ${SERVER_VERSION:-this server} (${DB_KIND:-sqlite})"
echo "ok: oc_filecache carries the column encrypted (A6)"

mkcol alice "${E2E_FOLDER}"
upload alice "${CORPUS}/${CONTROL}" "${E2E_FOLDER}/${CONTROL}"
e2e_folder=$(id_of alice "${E2E_FOLDER}")
e2e_file=$(id_of alice "${E2E_FOLDER}/${CONTROL}")
[ "$(db_query "SELECT encrypted FROM oc_filecache WHERE fileid = ${e2e_folder}")" = "0" ] \
	|| fail "the new folder ${e2e_folder} does not start with encrypted = 0"
db_exec "UPDATE oc_filecache SET encrypted = 1 WHERE fileid = ${e2e_folder}"
[ "$(db_query "SELECT encrypted FROM oc_filecache WHERE fileid = ${e2e_folder}")" = "1" ] \
	|| fail "the E2E flag of folder ${e2e_folder} was not stored"

e2e_body="${CI_OUT}/refusals-start-e2e.json"
code=$(req alice POST "${APP_PATH}/api/v1/jobs" "${e2e_body}" "${e2e_body}.headers" \
	-H 'Content-Type: application/json' --data "{\"fileId\": ${e2e_file}}")
case "${code}" in
	4??) ;;
	*) fail "the start below the E2E folder answered ${code}, expected a refusal: $(cat "${e2e_body}")" ;;
esac
got=$(json_field "${e2e_body}" reason)
[ "${got}" = "e2e_encrypted" ] || fail "the start below the E2E folder gave reason '${got}', expected e2e_encrypted"
[ "$(db_query "SELECT COUNT(*) FROM oc_pii_jobs WHERE file_id = ${e2e_file}")" = "0" ] \
	|| fail "a job exists for the file below the E2E folder"
echo "ok: start below the E2E folder -> HTTP ${code} e2e_encrypted, no job (file ${e2e_file})"

after_refusals=$(app_notifications alice)

# The same file starts once the flag is gone: the flag refused it.
db_exec "UPDATE oc_filecache SET encrypted = 0 WHERE fileid = ${e2e_folder}"
[ "$(db_query "SELECT encrypted FROM oc_filecache WHERE fileid = ${e2e_folder}")" = "0" ] \
	|| fail "the E2E flag of folder ${e2e_folder} was not taken back"
job_unflagged=$(start_job alice "${e2e_file}" 201)
status=$(end_of "${job_unflagged}" "${REVIEW_SECONDS}" review)
[ "${status}" = "review" ] || fail "the file ${e2e_file} is ${status} without the E2E flag, expected review"
echo "control: without the flag the same file reached review (job ${job_unflagged})"

# -- (f) the signed PDF ------------------------------------------------------------

job_signed=$(start_job alice "$(id_of alice "${FOLDER}/${SIGNED}")" 201)
status=$(end_of "${job_signed}" "${REFUSAL_SECONDS}" confirm review failed)
[ "${status}" = "confirm" ] || fail "job ${job_signed} on ${SIGNED} is ${status}, expected confirm before any analysis"
has_event "${job_signed}" signature_notice || fail "job ${job_signed} has no event signature_notice"
if has_event "${job_signed}" signature_confirmed; then
	fail "job ${job_signed} carries signature_confirmed before anybody confirmed"
fi
read -r _ of_signed subjects_signed < <(notifications alice "${job_signed}")
[ "${of_signed}" = "0" ] || fail "job ${job_signed} in confirm made a notification (${subjects_signed}), D-02-02 allows none"
echo "ok: ${SIGNED} -> confirm with signature_notice, no notification (job ${job_signed})"

# A stranger cannot confirm (ci/rights.sh holds the other routes).
foreign="${CI_OUT}/refusals-confirm-bob.json"
code=$(req bob POST "${APP_PATH}/review/${job_signed}/confirm" "${foreign}" "${foreign}.headers")
[ "${code}" = "404" ] || fail "confirm of job ${job_signed} as bob answered ${code}, expected 404"

# The session of alice without the request token cannot either (CSRF).
session_login alice
token=$(session_token alice "${APP_PATH}/review/${job_signed}")
forged="${CI_OUT}/refusals-confirm-no-token.json"
code=$(session_post "${APP_PATH}/review/${job_signed}/confirm" "${forged}")
case "${code}" in
	2??) fail "confirm of job ${job_signed} without the request token answered ${code}" ;;
esac
[ "$(end_of "${job_signed}" "${REFUSAL_SECONDS}" confirm review failed)" = "confirm" ] \
	|| fail "job ${job_signed} left confirm without a valid confirmation"
if has_event "${job_signed}" signature_confirmed; then
	fail "job ${job_signed} carries signature_confirmed after two refused attempts"
fi
echo "ok: confirm refused for a stranger (404) and without the request token (HTTP ${code})"

# The initiator confirms with the request token of the session.
confirmed="${CI_OUT}/refusals-confirm.json"
code=$(session_post "${APP_PATH}/review/${job_signed}/confirm" "${confirmed}" -H "requesttoken: ${token}")
[ "${code}" = "202" ] || fail "confirm of job ${job_signed} with the request token answered ${code}: $(cat "${confirmed}")"
[ "$(json_field "${confirmed}" status)" = "queued" ] || fail "confirm of job ${job_signed} did not answer queued"
cache_control=$(header_of "${confirmed}.headers" Cache-Control || true)
[[ "${cache_control}" == *no-store* ]] || fail "the confirm answer is not no-store"
status=$(end_of "${job_signed}" "${REVIEW_SECONDS}" review)
[ "${status}" = "review" ] || fail "job ${job_signed} is ${status} after the confirmation, expected review"
[ "$(json_field "${CI_OUT}/status-${job_signed}.json" signatureConfirmed)" = "True" ] \
	|| fail "the status of job ${job_signed} does not report signatureConfirmed"
events_signed=$(events_of "${job_signed}")
notice_at=$(grep -nx signature_notice <<<"${events_signed}" | head -n 1 | cut -d: -f1 || true)
confirmed_at=$(grep -nx signature_confirmed <<<"${events_signed}" | head -n 1 | cut -d: -f1 || true)
if [ -z "${notice_at}" ] || [ -z "${confirmed_at}" ] || [ "${notice_at}" -ge "${confirmed_at}" ]; then
	fail "the events of job ${job_signed} do not carry signature_notice before signature_confirmed"
fi
[ "$(grep -cx signature_confirmed <<<"${events_signed}" || true)" = "1" ] \
	|| fail "job ${job_signed} carries signature_confirmed more than once"
echo "ok: ${SIGNED} confirmed with the request token -> review, events signature_notice then signature_confirmed"

# -- (g) no notification for a refusal (D-02-02) -----------------------------------

findings=0
for job in "${REFUSED_JOBS[@]}"; do
	read -r _ of_job subjects_job < <(notifications alice "${job}")
	rows=$(notification_rows "${job}")
	if [ "${of_job}" != "0" ] || [ "${rows}" != "0" ]; then
		echo "FINDING: refused job ${job} has ${of_job} notifications (${subjects_job}), ${rows} rows in oc_notifications" >&2
		findings=$((findings + 1))
	fi
done
if [ "${after_refusals}" != "${before_refusals}" ]; then
	echo "FINDING: the notifications of the app went from ${before_refusals} to ${after_refusals} over the refusals" >&2
	findings=$((findings + 1))
fi
[ "${findings}" = "0" ] || fail "a refusal made a notification, D-02-02 allows none (${findings} findings)"
echo "ok: ${#REFUSED_JOBS[@]} refused jobs and the refused start made no notification (${before_refusals} before, ${after_refusals} after)"

echo "refusals done: jobs ${REFUSED_JOBS[*]} refused, ${job_signed} confirmed, controls ${job_control} ${job_sanitized} ${job_unflagged}"
