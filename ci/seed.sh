#!/usr/bin/env bash
# The seed of the integration proof, on a throwaway Nextcloud in CI only.
#
# Users, a group folder with ACL, a share with the download switched off and
# the fixtures of ci/make_fixtures.py, all over the real paths (occ, WebDAV,
# the sharing API). The file ids land in ci/out/fileids.env, the only place
# that pairs an id with a test file.
#
#   alice  en, initiator; owns all four fixtures, member of "team"
#   bob    en, foreign; receives one PDF of alice with download switched off
#   carol  en, member of "team", ACL -read on the folder Akten/Gesperrt
#   dora   en, admin, high contrast theme, one PDF of her own
#   elke   de_DE, one PDF;  greta  de (the "du" catalogue), one PDF
#   fleur  fr, one PDF
#
# usage: NC_URL=... NC_ROOT=... ADMIN_USER=... ADMIN_PASS=... CI_PASS=...
#        SERVER_VERSION=stable3x ci/seed.sh
# The fixtures are read from ci/out/fixtures (python3 ci/make_fixtures.py ci/out/fixtures).
set -euo pipefail

# shellcheck source=ci/lib.sh
. "$(dirname "$0")/lib.sh"

FIXTURES="${CI_OUT}/fixtures"
PDF='Bescheid 2026-114.pdf'
DOCX='Antrag.docx'
ODT='Vermerk.odt'
TXT='notes.txt'
BLOCKED='Bescheid 2026-114 Kopie.pdf'
GROUP_FOLDER='Akten'
LOCKED_DIR='Gesperrt'
SERVER_VERSION="${SERVER_VERSION:-}"

for name in "${PDF}" "${DOCX}" "${ODT}" "${TXT}"; do
	[ -s "${FIXTURES}/${name}" ] || fail "fixture ${name} is missing in ci/out/fixtures"
done

# -- users and the group ------------------------------------------------------

for user in alice bob carol dora elke greta fleur; do
	OC_PASS="${CI_PASS}" occ user:add --password-from-env "${user}"
done
occ group:adduser admin dora
occ group:add team
occ group:adduser team alice
occ group:adduser team carol
occ user:setting dora theming enabled-themes '["light-highcontrast"]'
# Before the first login: Nextcloud stores the browser language as the user
# language on the first request of a user who has none.
occ user:setting elke core lang de_DE
occ user:setting elke core locale de_DE
occ user:setting greta core lang de
occ user:setting greta core locale de_DE
occ user:setting fleur core lang fr
occ user:setting fleur core locale fr_FR
for user in alice bob carol dora; do
	occ user:setting "${user}" core lang en
done

# -- the fixtures -------------------------------------------------------------

upload() {
	local user="$1" source="$2" target="$3"
	curl -sfS -u "${user}:$(password_of "${user}")" -T "${source}" "$(dav_url "${user}" "${target}")" \
		|| fail "upload of a fixture for ${user} failed"
}

mkcol() {
	curl -sfS -u "$1:$(password_of "$1")" -X MKCOL "$(dav_url "$1" "$2")" > /dev/null \
		|| fail "folder for $1 could not be created"
}

for name in "${PDF}" "${DOCX}" "${ODT}" "${TXT}"; do
	upload alice "${FIXTURES}/${name}" "${name}"
done
upload alice "${FIXTURES}/${PDF}" "${BLOCKED}"
for user in dora elke greta fleur; do
	upload "${user}" "${FIXTURES}/${PDF}" "${PDF}"
done

# -- the group folder with ACL ------------------------------------------------

# The app store first; the tarball of the matching major line if the store
# does not deliver inside the job (mapping as in AVS and Findling).
if occ app:install groupfolders --force; then
	echo "groupfolders came from the app store"
else
	case "${SERVER_VERSION}" in
		stable33) tag='v21.0.15' ;;
		stable34) tag='v22.0.6' ;;
		*) tag='' ;;
	esac
	[ -n "${tag}" ] || fail "groupfolders is neither in the store nor mapped for ${SERVER_VERSION}"
	curl -sfSL -o "${RUNNER_TEMP:-/tmp}/groupfolders.tar.gz" \
		"https://github.com/nextcloud-releases/groupfolders/releases/download/${tag}/groupfolders-${tag}.tar.gz"
	tar -xzf "${RUNNER_TEMP:-/tmp}/groupfolders.tar.gz" -C "${NC_ROOT}/apps"
	echo "groupfolders came from the tarball ${tag}"
fi
occ app:enable -f groupfolders

folder_id=$(occ groupfolders:create "${GROUP_FOLDER}" | tr -dc '0-9')
[ -n "${folder_id}" ] || fail "the group folder could not be created"
occ groupfolders:group "${folder_id}" team read write share delete
occ groupfolders:permissions "${folder_id}" --enable

mkcol alice "${GROUP_FOLDER}/${LOCKED_DIR}"
upload alice "${FIXTURES}/${PDF}" "${GROUP_FOLDER}/${PDF}"
upload alice "${FIXTURES}/${PDF}" "${GROUP_FOLDER}/${LOCKED_DIR}/${PDF}"
# carol keeps the folder but loses read on the subfolder and what is in it.
occ groupfolders:permissions "${folder_id}" --user carol "${LOCKED_DIR}" -- -read

# -- the share with the download switched off ---------------------------------

code=$(req alice POST /ocs/v2.php/apps/files_sharing/api/v1/shares "${CI_OUT}/share-blocked.json" "${CI_OUT}/share-blocked.headers" \
	--data-urlencode "path=/${BLOCKED}" --data-urlencode 'shareWith=bob' \
	--data-urlencode 'shareType=0' --data-urlencode 'permissions=1' \
	--data-urlencode 'attributes=[{"scope":"permissions","key":"download","value":false}]')
[ "${code}" = "200" ] || fail "the share with download switched off answered ${code}"

# The mount of a recipient lands in the mount cache with a scan.
occ files:scan --all > /dev/null

# -- the file ids -------------------------------------------------------------

# record_id <name> <id>: one line of fileids.env; only a number passes, so an
# empty answer of fileid_of ends the seed here.
record_id() {
	[[ "$2" =~ ^[0-9]+$ ]] || fail "the file id $1 could not be read"
	echo "$1=$2"
}

FILE_GF_ALICE=$(fileid_of alice "${GROUP_FOLDER}/${PDF}")

{
	record_id FILE_PDF_ALICE "$(fileid_of alice "${PDF}")"
	record_id FILE_DOCX_ALICE "$(fileid_of alice "${DOCX}")"
	record_id FILE_ODT_ALICE "$(fileid_of alice "${ODT}")"
	record_id FILE_TXT_ALICE "$(fileid_of alice "${TXT}")"
	record_id FILE_PDF_DORA "$(fileid_of dora "${PDF}")"
	record_id FILE_PDF_ELKE "$(fileid_of elke "${PDF}")"
	record_id FILE_PDF_GRETA "$(fileid_of greta "${PDF}")"
	record_id FILE_PDF_FLEUR "$(fileid_of fleur "${PDF}")"
	record_id FILE_SHARED_BLOCKED_BOB "$(fileid_of bob "${BLOCKED}")"
	record_id FILE_GF_ALICE "${FILE_GF_ALICE}"
	record_id FILE_GF_CAROL "$(fileid_of alice "${GROUP_FOLDER}/${LOCKED_DIR}/${PDF}")"
	echo "GROUP_FOLDER_ID=${folder_id}"
} > "${CI_OUT}/fileids.env"

# carol reads the open file of the group folder (positive control of the ACL)
# and not the one in the locked subfolder.
[ "$(fileid_of carol "${GROUP_FOLDER}/${PDF}")" = "${FILE_GF_ALICE}" ] || fail "carol cannot read the open file of the group folder"
code=$(curl -s -o /dev/null -w '%{http_code}' -u "carol:${CI_PASS}" "$(dav_url carol "${GROUP_FOLDER}/${LOCKED_DIR}/${PDF}")")
[ "${code}" = "404" ] || [ "${code}" = "403" ] || fail "carol reads the file behind the ACL (${code})"
echo "seed done: $(wc -l < "${CI_OUT}/fileids.env") ids"
