#!/usr/bin/env bash
# The canary and the test file names in no database, log or copy
# (01-17-PLAN.md, success criterion 5, decision 10, pitfall I). Runs last.
#
# 1. Positive control first: the canary PIIKANARIE7Q4XZ9 stands in the
#    uploaded originals of alice (grep -aF on the PDF, unzip -p of
#    word/document.xml and content.xml). Without it every search below would
#    be worthless, so a miss stops with "positive control failed".
# 2. Dumps into ci/out/ (named *-dump.* or *.sql, never uploaded, T-01-17-06):
#    the whole Nextcloud database (SQLite iterdump through python3, MariaDB a
#    complete mariadb-dump: the canary may stand in no table), the rows of the
#    oc_pii_* tables, the container log, the HaRP log, state.db of the
#    container, the text of every copy (ci/pdf_text.py).
# 3. grep -F of the canary (and of its hex form, the way SQLite dumps a BLOB)
#    in all of them, in data/nextcloud.log, in the PHP server log and in the
#    status answers and logs of ci/out that are uploaded: no hit anywhere.
# 4. The test file names (Bescheid 2026-114, Antrag, Vermerk) in no line of
#    the container log, the HaRP log, the PHP server log, data/nextcloud.log,
#    the oc_pii_* rows and state.db. Positive control: the full database dump
#    carries all three (oc_filecache), so the search does find them.
#
# Not scanned, by name: the page images (PNG, pixels and no text) and
# work/<job>/src in the volume of the container (the downloaded original
# itself, purged with the job). Two request lines are taken out of the name
# search, never out of the canary search: in the PHP server log the access
# line of a WebDAV request (its path is the one the test client chose), and
# in data/nextcloud.log the "url" field of an entry made during such a
# request. The number of lines taken out is printed.
#
# Uses the contract of ci/lib.sh plus DB_KIND, BACKEND_CONTAINER,
# HARP_CONTAINER and PHP_SERVER_LOG (default ${RUNNER_TEMP}/php-server.log).
set -euo pipefail

# shellcheck source=ci/lib.sh
. "$(dirname "$0")/lib.sh"

: "${BACKEND_CONTAINER:?BACKEND_CONTAINER is required}"
: "${HARP_CONTAINER:?HARP_CONTAINER is required}"
PHP_SERVER_LOG="${PHP_SERVER_LOG:-${RUNNER_TEMP:-/tmp}/php-server.log}"
EXPECTED_COPIES="${EXPECTED_COPIES:-12}"
[ "${CANARY}" = 'PIIKANARIE7Q4XZ9' ] || fail "ci/lib.sh carries another canary"
CANARY_HEX=$(printf '%s' "${CANARY}" | od -An -tx1 | tr -d ' \n')
NAMES=('Bescheid 2026-114' 'Bescheid%202026-114' 'Antrag' 'Vermerk')

db_init
DATA_DIR=$(occ config:system:get datadirectory)
[ -d "${DATA_DIR}/alice/files" ] || fail "the data directory of alice is missing"

# -- 1. positive control -----------------------------------------------------------

grep -aqF "${CANARY}" "${DATA_DIR}/alice/files/Bescheid 2026-114.pdf" \
	|| fail "positive control failed: the canary is not in the PDF of alice"
unzip -p "${DATA_DIR}/alice/files/Antrag.docx" word/document.xml | grep -aF "${CANARY}" > /dev/null \
	|| fail "positive control failed: the canary is not in word/document.xml of the DOCX"
unzip -p "${DATA_DIR}/alice/files/Vermerk.odt" content.xml | grep -aF "${CANARY}" > /dev/null \
	|| fail "positive control failed: the canary is not in content.xml of the ODT"
echo "positive control: the canary stands in the PDF, the DOCX and the ODT of alice"

# -- 2. the dumps --------------------------------------------------------------------

DB_DUMP="${CI_OUT}/nextcloud-db-dump.sql"
PII_DUMP="${CI_OUT}/pii-tables-dump.sql"
STATE_DUMP="${CI_OUT}/state-db-dump.sql"
BACKEND_LOG="${CI_OUT}/backend-log-dump.txt"
HARP_LOG="${CI_OUT}/harp-log-dump.txt"
COPIES_TEXT="${CI_OUT}/copies-text-dump.txt"
PHP_FOR_NAMES="${CI_OUT}/php-server-names-dump.txt"
NC_LOG_FOR_NAMES="${CI_OUT}/nextcloud-log-names-dump.txt"

if [ "${DB_KIND:-sqlite}" = "mariadb" ]; then
	: "${DB_CONTAINER:?DB_CONTAINER is required on the mariadb leg}"
	docker exec "${DB_CONTAINER}" mariadb-dump -u"${DB_USER}" -p"${DB_PASS}" \
		--single-transaction --skip-extended-insert "${DB_NAME}" > "${DB_DUMP}"
	mapfile -t pii_tables < <(db_query "SHOW TABLES LIKE 'oc\\_pii\\_%'")
	[ "${#pii_tables[@]}" -ge 1 ] || fail "no oc_pii_* table found"
	docker exec "${DB_CONTAINER}" mariadb-dump -u"${DB_USER}" -p"${DB_PASS}" \
		--single-transaction --skip-extended-insert "${DB_NAME}" "${pii_tables[@]}" > "${PII_DUMP}"
else
	python3 - "${DB_FILE}" "${DB_DUMP}" "${PII_DUMP}" <<'PY'
import sqlite3, sys
connection = sqlite3.connect(sys.argv[1], timeout=15)
with open(sys.argv[2], "w", encoding="utf-8") as whole:
    for line in connection.iterdump():
        whole.write(line + "\n")
tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'oc!_pii!_%' ESCAPE '!'")]
if not tables:
    sys.exit("no oc_pii_* table found")
with open(sys.argv[3], "w", encoding="utf-8") as pii:
    for table in tables:
        for row in connection.execute(f'SELECT * FROM "{table}"'):
            pii.write(table + " " + repr(row) + "\n")
PY
fi
docker logs "${BACKEND_CONTAINER}" > "${BACKEND_LOG}" 2>&1
docker logs "${HARP_CONTAINER}" > "${HARP_LOG}" 2>&1
docker exec "${BACKEND_CONTAINER}" python3 -c '
import os, sqlite3, sys
path = os.path.join(os.environ["APP_PERSISTENT_STORAGE"], "state.db")
if not os.path.isfile(path):
    sys.exit("state.db is missing")
for line in sqlite3.connect(path, timeout=15).iterdump():
    print(line)
' > "${STATE_DUMP}"

: > "${COPIES_TEXT}"
copies=0
for copy in "${CI_OUT}"/copy-*.pdf; do
	[ -s "${copy}" ] || continue
	text="${copy%.pdf}.canary-dump.txt"
	python3 "${CI_DIR}/pdf_text.py" "${copy}" > "${text}"
	# Positive control per copy: the reader does read its text.
	grep -qF 'Placeholder from PII Redaction' "${text}" || fail "positive control failed: no text read from $(basename "${copy}")"
	cat "${text}" >> "${COPIES_TEXT}"
	copies=$((copies + 1))
done
[ "${copies}" -ge "${EXPECTED_COPIES}" ] || fail "${copies} copies found in ci/out, expected ${EXPECTED_COPIES} from ci/flow.sh"

[ -s "${PHP_SERVER_LOG}" ] || fail "the PHP server log ${PHP_SERVER_LOG} is missing or empty"
# A server that logged nothing has no nextcloud.log: an empty stand-in in ci/out.
NC_LOG="${DATA_DIR}/nextcloud.log"
if [ ! -f "${NC_LOG}" ]; then
	NC_LOG="${CI_OUT}/nextcloud-log-empty-dump.txt"
	: > "${NC_LOG}"
fi
for dump in "${DB_DUMP}" "${PII_DUMP}" "${STATE_DUMP}" "${BACKEND_LOG}" "${HARP_LOG}"; do
	[ -s "${dump}" ] || fail "$(basename "${dump}") is empty, the scan would prove nothing"
done
echo "dumps: database $(wc -l < "${DB_DUMP}") lines, pii tables $(wc -l < "${PII_DUMP}"), state.db $(wc -l < "${STATE_DUMP}"), container log $(wc -l < "${BACKEND_LOG}"), HaRP log $(wc -l < "${HARP_LOG}"), nextcloud.log $(wc -l < "${NC_LOG}"), PHP server log $(wc -l < "${PHP_SERVER_LOG}"), copies ${copies}"

# -- 3. the canary nowhere -------------------------------------------------------------

hits=0
# hits_in <needle> <file...>: counts and names the files, never prints a line.
hits_in() {
	local needle="$1" file count
	shift
	for file in "$@"; do
		count=$(grep -aciF -- "${needle}" "${file}" || true)
		if [ "${count}" != "0" ]; then
			echo "HIT: '${needle}' in ${count} lines of $(basename "${file}")" >&2
			hits=$((hits + 1))
		fi
	done
}

shopt -s nullglob
uploaded=("${CI_OUT}"/*.json "${CI_OUT}"/*.log)
shopt -u nullglob
copy_files=("${CI_OUT}"/copy-*.pdf)
canary_targets=("${DB_DUMP}" "${PII_DUMP}" "${STATE_DUMP}" "${BACKEND_LOG}" "${HARP_LOG}" "${NC_LOG}"
	"${PHP_SERVER_LOG}" "${COPIES_TEXT}" "${copy_files[@]}" "${uploaded[@]}")
hits_in "${CANARY}" "${canary_targets[@]}"
hits_in "${CANARY_HEX}" "${DB_DUMP}" "${PII_DUMP}" "${STATE_DUMP}"
[ "${hits}" = "0" ] || fail "the canary stands in ${hits} places"
echo "ok: the canary is in none of ${#canary_targets[@]} files"

# -- 4. the test file names nowhere they do not belong ----------------------------------

for name in 'Bescheid 2026-114' 'Antrag' 'Vermerk'; do
	grep -aqF "${name}" "${DB_DUMP}" || fail "positive control failed: '${name}' is not in the database dump (oc_filecache)"
done
echo "positive control: the database dump carries all three test file names"

excluded_php=$(grep -cE '\]: [A-Z]+ /remote\.php/dav/' "${PHP_SERVER_LOG}" || true)
grep -vE '\]: [A-Z]+ /remote\.php/dav/' "${PHP_SERVER_LOG}" > "${PHP_FOR_NAMES}" || true
excluded_nc=$(python3 - "${NC_LOG}" "${NC_LOG_FOR_NAMES}" <<'PY'
import json, sys
taken = 0
with open(sys.argv[1], encoding="utf-8", errors="replace") as source, open(sys.argv[2], "w", encoding="utf-8") as target:
    for line in source:
        try:
            entry = json.loads(line)
        except ValueError:
            target.write(line)
            continue
        if isinstance(entry, dict) and str(entry.get("url", "")).startswith("/remote.php/dav/"):
            entry["url"] = "(WebDAV request of the test client)"
            taken += 1
            target.write(json.dumps(entry, ensure_ascii=False) + "\n")
        else:
            target.write(line)
print(taken)
PY
)
echo "request lines taken out of the name search: PHP server log ${excluded_php}, nextcloud.log url fields ${excluded_nc}"

hits=0
for name in "${NAMES[@]}"; do
	hits_in "${name}" "${BACKEND_LOG}" "${HARP_LOG}" "${PHP_FOR_NAMES}" "${NC_LOG_FOR_NAMES}" "${PII_DUMP}" "${STATE_DUMP}"
done
[ "${hits}" = "0" ] || fail "a test file name stands in ${hits} places"
echo "ok: no test file name in the container log, the HaRP log, the PHP server log, nextcloud.log, the oc_pii_* rows or state.db"
echo "canary done"
