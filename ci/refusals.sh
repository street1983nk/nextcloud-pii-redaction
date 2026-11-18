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
#       stranger (404) and the session of the initiator without or with a
#       made-up request token (412 CSRF check failed) cannot confirm; the POST
#       of the same session with its request token can, and the job reaches
#       review with signature_confirmed after signature_notice
#   (g) D-02-02: none of the refusals (a) to (e) made a notification. Judged
#       last, so one run shows every other proof before it.
#
# Every proof runs on its own (proof below): one that fails is named, the
# others still run, and the script ends red when any of them failed or could
# not run. A CI run shows every finding at once that way, not only the first.
#
# Which notification a job has is asked of two witnesses. The OCS API of the
# notifications app says what the user sees: it carries the rendered title in
# the language of the user ("A review is ready"), never the subject word. The
# word (review_ready) stands in oc_notifications.subject only, so it is read
# there (as ci/stale.sh does). Nothing here depends on the language of alice.
#
# A6: the script reads the columns of oc_filecache from the database itself
# and stops when there is no column "encrypted" (the flag FileAccess asks at
# the folders above a file).
#
# The files come from ci/make_corpus.py --e2e into ci/out/corpus, where the
# Playwright suite reads them afterwards. Output: words of the closed lists,
# ids, numbers and the fixed titles of the notifications only, never the
# content of a file, a password or a request token.
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
# What one proof hands to a later one: each proof is a process of its own.
STATE="${CI_OUT}/refusals-state"
NOTIFICATIONS_API='/ocs/v2.php/apps/notifications/api/v2/notifications?format=json'
# The API hands out one page of notifications; a count close to it could hide
# a new one. alice has six after ci/flow.sh.
NOTIFICATION_PAGE=20
# The ceiling of one job: the pre-check answers within seconds, the two runs
# through the renderer and LibreOffice within a minute.
REFUSAL_SECONDS=180
REVIEW_SECONDS=300
# The four refusals of the pre-check, (a) to (d).
REFUSALS_EXPECTED=4
PROOFS=0
FAILED=()
SKIPPED=()
STUCK=0

db_init
rm -rf "${STATE}"
mkdir -p "${STATE}"

# -- helpers -----------------------------------------------------------------------

# proof <function> [arguments...]: runs one proof in a process of its own and
# goes on when it fails. The call stands alone on its line: behind "if" or
# before "||" bash would switch errexit off inside the proof. A proof that
# failed after a wait ran out leaves the queue in an unknown state; the proofs
# after it are not run and count as failed (no half an hour of further waits).
proof() {
	local name="$*" code=0 began="${SECONDS}"
	PROOFS=$((PROOFS + 1))
	if [ "${STUCK}" = "1" ]; then
		SKIPPED+=("${name}")
		echo "NOT RUN: ${name} (an earlier proof ran out of time)" >&2
		return 0
	fi
	set +e
	(
		set -e
		"$@"
	)
	code=$?
	set -e
	if [ "${code}" != "0" ]; then
		FAILED+=("${name}")
		echo "PROOF FAILED: ${name}" >&2
		if [ "$((SECONDS - began))" -ge "${REFUSAL_SECONDS}" ]; then
			STUCK=1
		fi
	fi
	return 0
}

# keep <key> <value> and kept <key>: a value for the proofs that follow.
keep() {
	printf '%s' "$2" > "${STATE}/$1"
}

kept() {
	[ -s "${STATE}/$1" ] || fail "$1 is not known: the proof that sets it did not get that far"
	cat "${STATE}/$1"
}

# shown <file>: the start of an answer for a failure message, on one line, at
# most 300 characters, request tokens blanked.
shown() {
	python3 - "$1" <<'PY'
import re, sys
try:
    text = open(sys.argv[1], "rb").read(4096).decode("utf-8", "replace")
except OSError:
    text = ""
text = re.sub(r'(requesttoken"?\s*[=:]\s*")[^"]*', r"\1...", text, flags=re.IGNORECASE)
print(" ".join(text.split())[:300] or "(empty)")
PY
}

# field_of <file> <key>: one field of a JSON object, or nothing when the
# answer is no JSON object (json_field of ci/lib.sh stops with a traceback).
field_of() {
	python3 - "$1" "$2" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except (OSError, ValueError):
    data = None
value = data.get(sys.argv[2]) if isinstance(data, dict) else None
print("" if value is None else value)
PY
}

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
	id=$(fileid_of "$1" "$2") || fail "the file id of $2 could not be asked"
	[[ "${id}" =~ ^[0-9]+$ ]] || fail "no file id for $2"
	printf '%s' "${id}"
}

# started <user> <file id>: a new job (201); prints its id.
started() {
	local job
	job=$(start_job "$1" "$2" 201)
	[[ "${job}" =~ ^[0-9]+$ ]] || fail "the start as $1 on file $2 gave no job id"
	printf '%s' "${job}"
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

# encrypted_of <file id>: the E2E flag of one row of oc_filecache.
encrypted_of() {
	db_query "SELECT encrypted FROM oc_filecache WHERE fileid = $1"
}

events_of() {
	db_query "SELECT action FROM oc_pii_job_events WHERE job_id = $1 ORDER BY id"
}

# events_line <job>: the events of a job on one line, for a message.
events_line() {
	local events
	events=$(events_of "$1") || fail "the events of job $1 could not be read"
	printf '%s' "${events//$'\n'/,}"
}

# has_event <job> <action>. The rows are read first: a grep -q that leaves
# early would break the pipe of the query under pipefail. A query that fails
# stops the proof: "no such event" is an answer only when the rows were read.
has_event() {
	local events
	events=$(events_of "$1") || fail "the events of job $1 could not be read"
	grep -qx "$2" <<<"${events}"
}

# awaited_event <job> <action>: has_event, asked for up to 10 s. JobService
# stores the state confirm first and the event signature_notice right after
# it, in the same request; the status can be read a moment before the event.
awaited_event() {
	for _ in $(seq 1 10); do
		if has_event "$1" "$2"; then
			return 0
		fi
		sleep 1
	done
	return 1
}

# end_of <job> <seconds> <status...>: waits for one of the states and prints
# the one the job reached.
end_of() {
	local job="$1" seconds="$2"
	shift 2
	WAIT_SECONDS="${seconds}" wait_status alice "${job}" "$@"
	json_field "${CI_OUT}/status-${job}.json" status
}

# notifications <user> [job]: prints "<of the app> <of the job> <of the job
# with the link to its review page> <titles of the job>", read over the OCS
# API the notification bell uses. The titles are the rendered sentences of the
# catalog in the language of the user; they are printed, never compared.
notifications() {
	local user="$1" job="${2:-0}" body="${CI_OUT}/refusals-notifications.json" code
	code=$(req "${user}" GET "${NOTIFICATIONS_API}" "${body}" "${body}.headers")
	[ "${code}" = "200" ] || fail "the notifications answered ${code} (is the notifications app enabled?): $(shown "${body}")"
	python3 - "${body}" "${job}" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))["ocs"]["data"]
ours = [n for n in data if n.get("app") == "pii_redaction"]
of_job = [n for n in ours if n.get("object_type") == "job" and str(n.get("object_id")) == sys.argv[2]]
linked = [n for n in of_job if str(n.get("link", "")).endswith("/apps/pii_redaction/review/" + sys.argv[2])]
titles = [str(n.get("subject") or "(no title)") for n in of_job]
# ASCII only: the title of a French or German user must not depend on the
# locale of the runner.
shown = (" | ".join(sorted(titles)) or "-").encode("ascii", "backslashreplace").decode("ascii")
print(len(ours), len(of_job), len(linked), shown)
PY
}

# app_notifications <user>: how many notifications of the app the API shows.
app_notifications() {
	local seen
	seen=$(notifications "$1") || return 1
	printf '%s' "${seen%% *}"
}

# The subject words of the notifications of one job, from the table of the
# notifications app: the second witness next to the API, and the only place
# that holds the word of the closed list.
subjects_of() {
	db_query "SELECT subject FROM oc_notifications WHERE app = 'pii_redaction' AND object_type = 'job' AND object_id = '$1'"
}

notification_rows() {
	db_query "SELECT COUNT(*) FROM oc_notifications WHERE app = 'pii_redaction' AND object_type = 'job' AND object_id = '$1'"
}

# seen_notification <user> <job> <subject>: waits up to 20 s until both
# witnesses agree. The API shows the user exactly one notification of the job,
# with a title and the link to its review page; the database holds exactly one
# row of the job, with that subject word. The state of a job changes a moment
# before its notification is sent, within the same request of the container.
seen_notification() {
	local seen shown_job="" linked="" titles="" keys=""
	for _ in $(seq 1 20); do
		seen=$(notifications "$1" "$2") || return 1
		read -r _ shown_job linked titles <<<"${seen}"
		keys=$(subjects_of "$2") || return 1
		if [ "${shown_job}" = "1" ] && [ "${linked}" = "1" ] && [ "${titles}" != "(no title)" ] && [ "${keys}" = "$3" ]; then
			return 0
		fi
		sleep 1
	done
	echo "job $2: the API shows $1 ${shown_job} notifications (${titles}), ${linked} with the link to the review page; oc_notifications holds the subjects '${keys//$'\n'/,}'; expected exactly one $3" >&2
	return 1
}

# head_value <html file> <attribute>: the value of one attribute of the page.
head_value() {
	grep -o "$2=\"[^\"]*\"" "$1" | head -n 1 | cut -d'"' -f2 || true
}

# cookie_names: the names of the cookies in the jar on one line, never a value.
cookie_names() {
	local names=""
	if [ -s "${JAR}" ]; then
		names=$(awk -F'\t' 'NF >= 7 { print $6 }' "${JAR}" | sort -u | tr '\n' ' ')
	fi
	names="${names% }"
	printf '%s' "${names:-none}"
}

# login_reason: why the server refused the login. LoginController stores one
# word of its closed list in the session and hands it to the next login page
# as the start state core-loginErrors. Only a word of that list is printed.
login_reason() {
	local page="${CI_OUT}/refusals-login-refused.html"
	curl -s -o "${page}" -c "${JAR}" -b "${JAR}" "${NC_URL}/index.php/login" || true
	python3 - "${page}" <<'PY'
import base64, json, re, sys
KNOWN = {"invalidOrigin", "csrfCheckFailed", "invalidpassword", "userdisabled"}
try:
    html = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    found = re.search(r'id="initial-state-core-loginErrors"[^>]*value="([^"]*)"', html)
    errors = json.loads(base64.b64decode(found.group(1))) if found else None
except (OSError, ValueError):
    errors = None
if not isinstance(errors, list):
    print("not told")
else:
    print(",".join(e if e in KNOWN else "another message" for e in map(str, errors)) or "none named")
PY
}

# session_login <user>: a browser session in the cookie jar, built the way the
# login form builds it (no basic auth, no OCS-APIRequest): the login page for
# the session cookie, the two same-site cookies and the request token, then
# the form with the Origin header a browser adds to a POST. The server refuses
# a form without a trusted Origin before it looks at anything else
# (core/Controller/LoginController.php, tryLogin: invalidOrigin). A failure
# names the code of each step, the names of the cookies and the address the
# form led to, never a password, a token or the value of a cookie.
session_login() {
	local user="$1" page="${CI_OUT}/refusals-login.html" answer="${CI_OUT}/refusals-login.headers"
	local origin page_code token code target before
	rm -f "${JAR}" "${STATE}/session"
	origin=$(printf '%s' "${NC_URL}" | sed -E 's|^([a-z]+://[^/]+).*$|\1|')
	page_code=$(curl -s -o "${page}" -w '%{http_code}' -c "${JAR}" -b "${JAR}" "${NC_URL}/index.php/login") || true
	[ "${page_code}" = "200" ] || fail "the login page answered '${page_code}' (cookies set: $(cookie_names))"
	token=$(head_value "${page}" data-requesttoken)
	[ -n "${token}" ] || fail "the login page (HTTP 200) carries no request token (cookies set: $(cookie_names))"
	before=$(cookie_names)
	code=$(curl -s -o /dev/null -D "${answer}" -w '%{http_code}' -c "${JAR}" -b "${JAR}" \
		-H "Origin: ${origin}" \
		--data-urlencode "user=${user}" --data-urlencode "password=$(password_of "${user}")" \
		--data-urlencode "requesttoken=${token}" "${NC_URL}/index.php/login") || true
	target=$(header_of "${answer}" Location || true)
	# The address without its query: after a refused login the query names the user.
	target="${target%%\?*}"
	case "${code}" in
		30[23]) ;;
		*) fail "the login form answered '${code}' for ${user} (login page 200, request token found, Origin ${origin}, cookies before the form: ${before}, after it: $(cookie_names), Location '${target}')" ;;
	esac
	case "${target}" in
		*/login | */login/*)
			fail "the login of ${user} was refused: the form answered ${code} and led back to ${target} (login page 200, request token found, Origin ${origin}, cookies before the form: ${before}, after it: $(cookie_names), reason of the server: $(login_reason))"
			;;
	esac
}

# session_token <user> <path>: opens a page in the session and prints its
# request token. The page has to be the page of that user, so a login that
# did not happen stops here.
session_token() {
	local user="$1" page="${CI_OUT}/refusals-page.html" code token target
	code=$(curl -s -o "${page}" -D "${page}.headers" -w '%{http_code}' -c "${JAR}" -b "${JAR}" "${NC_URL}$2") || true
	target=$(header_of "${page}.headers" Location || true)
	[ "${code}" = "200" ] \
		|| fail "the page $2 answered '${code}' in the session of ${user} (Location '${target%%\?*}', cookies: $(cookie_names))"
	[ "$(head_value "${page}" data-user)" = "${user}" ] \
		|| fail "the session is not the session of ${user}: the page names the user '$(head_value "${page}" data-user)' (cookies: $(cookie_names))"
	token=$(head_value "${page}" data-requesttoken)
	[ -n "${token}" ] || fail "the page $2 (HTTP 200, user ${user}) carries no request token"
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

# csrf_refused <job> <answer file> <what> [curl args...]: the confirmation in
# the session of alice that the server has to refuse as a forged request, and
# for that reason only: 412 with "CSRF check failed" is what SecurityMiddleware
# answers a logged-in session whose request token is missing or wrong. A
# session that is not logged in gets 401 and a stranger 404; neither counts.
csrf_refused() {
	local job="$1" answer="$2" what="$3" code got
	shift 3
	code=$(session_post "${APP_PATH}/review/${job}/confirm" "${answer}" "$@")
	got=$(field_of "${answer}" message)
	[ "${code}" = "412" ] \
		|| fail "confirm of job ${job} ${what} answered ${code}, expected the CSRF refusal 412: $(shown "${answer}")"
	[ "${got}" = "CSRF check failed" ] \
		|| fail "confirm of job ${job} ${what} answered 412 with the message '${got}', expected 'CSRF check failed': $(shown "${answer}")"
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

# The count of (g) may report "none" only after it saw one: a job that reaches
# review, its review_ready with both witnesses, and the count one higher.
control_review() {
	local before after job status
	before=$(app_notifications alice)
	[ "${before}" -lt "${NOTIFICATION_PAGE}" ] \
		|| fail "alice has ${before} notifications of the app, a new one could fall off the page of the API"
	job=$(started alice "$(id_of alice "${FOLDER}/${CONTROL}")")
	keep job_control "${job}"
	status=$(end_of "${job}" "${REVIEW_SECONDS}" review)
	[ "${status}" = "review" ] || fail "the control ${CONTROL} is ${status}, expected review"
	seen_notification alice "${job}" review_ready \
		|| fail "positive control failed: job ${job} has no review_ready that the API shows and the database holds"
	after=$(app_notifications alice)
	[ "${after}" = "$((before + 1))" ] \
		|| fail "positive control failed: the count went from ${before} to ${after}, expected one more"
	[ "$(notification_rows "${job}")" = "1" ] \
		|| fail "positive control failed: oc_notifications has not exactly one row for job ${job}"
	keep control_passed yes
	echo "positive control: ${CONTROL} reached review (job ${job}), the count saw its review_ready (${before} -> ${after})"
}
proof control_review

# The second control waits for its notification as well: the count before the
# refusals is taken after it, and a review_ready that arrived a moment later
# would look like a notification of a refusal.
control_sanitized() {
	local job status
	job=$(started alice "$(id_of alice "${FOLDER}/${SANITIZED}")")
	keep job_sanitized "${job}"
	status=$(end_of "${job}" "${REVIEW_SECONDS}" review)
	[ "${status}" = "review" ] || fail "${SANITIZED} is ${status}, expected review"
	has_event "${job}" external_links_removed \
		|| fail "job ${job} on ${SANITIZED} has no event external_links_removed, its events: $(events_line "${job}")"
	seen_notification alice "${job}" review_ready \
		|| fail "job ${job} on ${SANITIZED} is in review without its review_ready"
	echo "ok: ${SANITIZED} -> review with external_links_removed (job ${job})"
}
proof control_sanitized

# -- (a) to (d) the refusals of the pre-check --------------------------------------

# refused <file name> <reason>: a start that the pre-check ends as failed.
refused() {
	local name="$1" reason="$2" job status got
	job=$(started alice "$(id_of alice "${FOLDER}/${name}")")
	status=$(end_of "${job}" "${REFUSAL_SECONDS}" failed review confirm)
	got=$(json_field "${CI_OUT}/status-${job}.json" reason)
	[ "${status}" = "failed" ] \
		|| fail "job ${job} on ${name} is ${status}, expected failed ${reason}; its events: $(events_line "${job}")"
	[ "${got}" = "${reason}" ] \
		|| fail "job ${job} on ${name} failed with '${got}', expected ${reason}; its events: $(events_line "${job}")"
	echo "${job}" >> "${STATE}/refused"
	echo "ok: ${name} -> failed ${reason} (job ${job})"
}

before_refusals=$(app_notifications alice) || before_refusals='unknown'
proof refused wrong_pdf_as_docx.docx wrong_type
proof refused pdf_301_pages.pdf too_many_pages
proof refused pdf_user_password.pdf encrypted_pdf
proof refused cfb_encrypted.docx encrypted_document

# -- (e) the folder with the E2E flag ----------------------------------------------

e2e_refusal() {
	local e2e_folder e2e_file e2e_body code got jobs
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
	keep e2e_folder "${e2e_folder}"
	keep e2e_file "${e2e_file}"
	got=$(encrypted_of "${e2e_folder}")
	[ "${got}" = "0" ] || fail "the new folder ${e2e_folder} starts with encrypted = '${got}', expected 0"
	db_exec "UPDATE oc_filecache SET encrypted = 1 WHERE fileid = ${e2e_folder}"
	got=$(encrypted_of "${e2e_folder}")
	[ "${got}" = "1" ] || fail "the E2E flag of folder ${e2e_folder} was not stored (encrypted = '${got}')"

	e2e_body="${CI_OUT}/refusals-start-e2e.json"
	code=$(req alice POST "${APP_PATH}/api/v1/jobs" "${e2e_body}" "${e2e_body}.headers" \
		-H 'Content-Type: application/json' --data "{\"fileId\": ${e2e_file}}")
	case "${code}" in
		4??) ;;
		*) fail "the start below the E2E folder answered ${code}, expected a refusal: $(shown "${e2e_body}")" ;;
	esac
	got=$(field_of "${e2e_body}" reason)
	[ "${got}" = "e2e_encrypted" ] \
		|| fail "the start below the E2E folder gave reason '${got}' (HTTP ${code}), expected e2e_encrypted: $(shown "${e2e_body}")"
	jobs=$(db_query "SELECT COUNT(*) FROM oc_pii_jobs WHERE file_id = ${e2e_file}")
	[ "${jobs}" = "0" ] || fail "${jobs} jobs exist for the file below the E2E folder, expected none"
	echo "ok: start below the E2E folder -> HTTP ${code} e2e_encrypted, no job (file ${e2e_file})"
}
proof e2e_refusal

after_refusals=$(app_notifications alice) || after_refusals='unknown'

# The same file starts once the flag is gone: the flag refused it. The flag
# is taken back also when the proof before this one failed half way.
e2e_control() {
	local e2e_folder e2e_file job status got
	e2e_folder=$(kept e2e_folder)
	e2e_file=$(kept e2e_file)
	db_exec "UPDATE oc_filecache SET encrypted = 0 WHERE fileid = ${e2e_folder}"
	got=$(encrypted_of "${e2e_folder}")
	[ "${got}" = "0" ] || fail "the E2E flag of folder ${e2e_folder} was not taken back (encrypted = '${got}')"
	job=$(started alice "${e2e_file}")
	keep job_unflagged "${job}"
	status=$(end_of "${job}" "${REVIEW_SECONDS}" review)
	[ "${status}" = "review" ] || fail "the file ${e2e_file} is ${status} without the E2E flag, expected review"
	echo "control: without the flag the same file reached review (job ${job})"
}
proof e2e_control

# -- (f) the signed PDF ------------------------------------------------------------

signed_waits() {
	local job_signed status seen of_signed titles_signed rows
	job_signed=$(started alice "$(id_of alice "${FOLDER}/${SIGNED}")")
	status=$(end_of "${job_signed}" "${REFUSAL_SECONDS}" confirm review failed)
	[ "${status}" = "confirm" ] \
		|| fail "job ${job_signed} on ${SIGNED} is ${status}, expected confirm before any analysis; its events: $(events_line "${job_signed}")"
	keep job_signed "${job_signed}"
	awaited_event "${job_signed}" signature_notice || fail "job ${job_signed} has no event signature_notice, its events: $(events_line "${job_signed}")"
	if has_event "${job_signed}" signature_confirmed; then
		fail "job ${job_signed} carries signature_confirmed before anybody confirmed"
	fi
	seen=$(notifications alice "${job_signed}")
	read -r _ of_signed _ titles_signed <<<"${seen}"
	rows=$(notification_rows "${job_signed}")
	if [ "${of_signed}" != "0" ] || [ "${rows}" != "0" ]; then
		fail "job ${job_signed} in confirm made a notification (API ${of_signed}: ${titles_signed}; ${rows} rows in oc_notifications), D-02-02 allows none"
	fi
	echo "ok: ${SIGNED} -> confirm with signature_notice, no notification (job ${job_signed})"
}
proof signed_waits

signed_refuses() {
	local job_signed foreign code status made_up='AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='
	job_signed=$(kept job_signed)

	# A stranger cannot confirm (ci/rights.sh holds the other routes).
	foreign="${CI_OUT}/refusals-confirm-bob.json"
	code=$(req bob POST "${APP_PATH}/review/${job_signed}/confirm" "${foreign}" "${foreign}.headers")
	[ "${code}" = "404" ] || fail "confirm of job ${job_signed} as bob answered ${code}, expected 404: $(shown "${foreign}")"

	# The session of alice cannot either, without the request token and with a
	# made-up one (CSRF). The page is opened before and after: the session is a
	# session of alice that sees the job, and the refusals did not end it. The
	# proof after this one confirms in this very session, with its token.
	session_login alice
	session_token alice "${APP_PATH}/review/${job_signed}" > /dev/null
	csrf_refused "${job_signed}" "${CI_OUT}/refusals-confirm-no-token.json" 'without the request token'
	csrf_refused "${job_signed}" "${CI_OUT}/refusals-confirm-made-up-token.json" 'with a made-up request token' \
		-H "requesttoken: ${made_up}"
	session_token alice "${APP_PATH}/review/${job_signed}" > /dev/null
	keep session alice
	status=$(end_of "${job_signed}" "${REFUSAL_SECONDS}" confirm review failed)
	[ "${status}" = "confirm" ] || fail "job ${job_signed} left confirm without a valid confirmation, it is ${status}"
	if has_event "${job_signed}" signature_confirmed; then
		fail "job ${job_signed} carries signature_confirmed after three refused attempts"
	fi
	echo "ok: confirm refused for a stranger (404) and in the session of alice without and with a made-up request token (412 CSRF check failed)"
}
proof signed_refuses

# The initiator confirms with the request token of the session: the session
# the server refused twice just before, when the proof before this one got that
# far (the only difference to the refused attempts is the token), a new one
# otherwise.
signed_confirms() {
	local job_signed token confirmed code got cache_control status events_signed notice_at confirmed_at session='a new session'
	job_signed=$(kept job_signed)
	if [ -s "${STATE}/session" ]; then
		session='the session the server refused without the token'
	else
		session_login alice
	fi
	token=$(session_token alice "${APP_PATH}/review/${job_signed}")
	confirmed="${CI_OUT}/refusals-confirm.json"
	code=$(session_post "${APP_PATH}/review/${job_signed}/confirm" "${confirmed}" -H "requesttoken: ${token}")
	[ "${code}" = "202" ] || fail "confirm of job ${job_signed} with the request token answered ${code}: $(shown "${confirmed}")"
	got=$(field_of "${confirmed}" status)
	[ "${got}" = "queued" ] || fail "confirm of job ${job_signed} answered status '${got}', expected queued: $(shown "${confirmed}")"
	cache_control=$(header_of "${confirmed}.headers" Cache-Control || true)
	[[ "${cache_control}" == *no-store* ]] || fail "the confirm answer is not no-store (Cache-Control '${cache_control}')"
	status=$(end_of "${job_signed}" "${REVIEW_SECONDS}" review)
	[ "${status}" = "review" ] || fail "job ${job_signed} is ${status} after the confirmation, expected review"
	got=$(json_field "${CI_OUT}/status-${job_signed}.json" signatureConfirmed)
	[ "${got}" = "True" ] || fail "the status of job ${job_signed} reports signatureConfirmed '${got}', expected True"
	events_signed=$(events_of "${job_signed}")
	notice_at=$(grep -nx signature_notice <<<"${events_signed}" | head -n 1 | cut -d: -f1 || true)
	confirmed_at=$(grep -nx signature_confirmed <<<"${events_signed}" | head -n 1 | cut -d: -f1 || true)
	if [ -z "${notice_at}" ] || [ -z "${confirmed_at}" ] || [ "${notice_at}" -ge "${confirmed_at}" ]; then
		fail "the events of job ${job_signed} do not carry signature_notice before signature_confirmed: ${events_signed//$'\n'/,}"
	fi
	[ "$(grep -cx signature_confirmed <<<"${events_signed}" || true)" = "1" ] \
		|| fail "job ${job_signed} carries signature_confirmed more than once: ${events_signed//$'\n'/,}"
	keep signed_confirmed yes
	echo "ok: ${SIGNED} confirmed with the request token in ${session} -> review, events signature_notice then signature_confirmed"
}
proof signed_confirms

# -- (g) no notification for a refusal (D-02-02) -----------------------------------

no_notification_for_a_refusal() {
	local findings=0 refused_jobs=() job seen of_job titles_job rows
	# Without the positive control a count of zero proves nothing.
	[ -s "${STATE}/control_passed" ] \
		|| fail "the positive control did not pass, so the count cannot judge the refusals; D-02-02 allows none and stays unproven"
	if [ -s "${STATE}/refused" ]; then
		mapfile -t refused_jobs < "${STATE}/refused"
	fi
	if [ "${#refused_jobs[@]}" != "${REFUSALS_EXPECTED}" ]; then
		echo "FINDING: ${#refused_jobs[@]} of ${REFUSALS_EXPECTED} refusals happened, the others cannot be judged" >&2
		findings=$((findings + 1))
	fi
	for job in "${refused_jobs[@]}"; do
		seen=$(notifications alice "${job}")
		read -r _ of_job _ titles_job <<<"${seen}"
		rows=$(notification_rows "${job}")
		if [ "${of_job}" != "0" ] || [ "${rows}" != "0" ]; then
			echo "FINDING: refused job ${job} has ${of_job} notifications (${titles_job}), ${rows} rows in oc_notifications" >&2
			findings=$((findings + 1))
		fi
	done
	if [ "${before_refusals}" = "unknown" ] || [ "${after_refusals}" = "unknown" ]; then
		echo "FINDING: the notifications of the app could not be counted (${before_refusals} before, ${after_refusals} after)" >&2
		findings=$((findings + 1))
	elif [ "${after_refusals}" != "${before_refusals}" ]; then
		echo "FINDING: the notifications of the app went from ${before_refusals} to ${after_refusals} over the refusals" >&2
		findings=$((findings + 1))
	fi
	[ "${findings}" = "0" ] || fail "a refusal made a notification or could not be judged, D-02-02 allows none (${findings} findings)"
	echo "ok: ${#refused_jobs[@]} refused jobs and the refused start made no notification (${before_refusals} before, ${after_refusals} after)"
}
proof no_notification_for_a_refusal

# -- the verdict -------------------------------------------------------------------

for name in "${FAILED[@]}"; do
	echo "failed: ${name}" >&2
done
for name in "${SKIPPED[@]}"; do
	echo "not run: ${name}" >&2
done
[ "$((${#FAILED[@]} + ${#SKIPPED[@]}))" = "0" ] \
	|| fail "${#FAILED[@]} of ${PROOFS} proofs failed, ${#SKIPPED[@]} were not run"

echo "refusals done: ${PROOFS} proofs, jobs $(tr '\n' ' ' < "${STATE}/refused")refused, $(kept job_signed) confirmed, controls $(kept job_control) $(kept job_sanitized) $(kept job_unflagged)"
