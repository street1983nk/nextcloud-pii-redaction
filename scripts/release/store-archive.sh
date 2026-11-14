#!/bin/sh
# The one place that decides what ships in the two store archives (plan 01-18).
# Taken over from AVS scripts/release/store-archive.sh (plan 01-10), which took
# it from Findling.
#
# One repository, two apps, two archives:
#   pii_redaction          the PHP app out of php/, code signed inside
#   pii_redaction_backend  the External App, metadata only
#
# The signatures are not here. The code signature belongs INSIDE the PHP app
# archive and the release signature belongs OVER each tarball, so the order is
# stage, code sign, pack, release sign, and both signing steps stay in
# .github/workflows/release.yml next to the secrets they read. That is why
# stage and pack are separate subcommands.
#
# Usage, from the root of the repository:
#   store-archive.sh stage-companion <stage-dir>
#   store-archive.sh stage-backend   <stage-dir>
#   store-archive.sh pack            <stage-dir> <app-id> <archive>
#   store-archive.sh assert-contents <archive> <app-id> <wants-signature 0|1>
#
# POSIX sh, no bashisms. backend/tests/test_release_archives.py holds the
# include lists and runs both staging subcommands on a copy of the tree.
set -eu

COMPANION_ID=pii_redaction
BACKEND_ID=pii_redaction_backend
INIT_BUNDLE=js/pii_redaction-init.mjs

usage() {
	echo "usage: store-archive.sh stage-companion <stage-dir>"
	echo "       store-archive.sh stage-backend   <stage-dir>"
	echo "       store-archive.sh pack            <stage-dir> <app-id> <archive>"
	echo "       store-archive.sh assert-contents <archive> <app-id> <wants-signature 0|1>"
}

# An include list and not an exclude list: a new directory in php/ has to be
# named here before it ships, instead of shipping because nobody remembered
# to exclude it. Left out on purpose: src (the sources the bundle is built
# from), node_modules, tests and phpunit.xml (the unit suite), package.json,
# vite.config.ts and tsconfig.json (the build), composer.json (no runtime
# dependency; it would invite a composer install on a production instance),
# .gitkeep (repository plumbing). LICENSE and CHANGELOG.md travel along: the
# store renders the changelog on the release listing.
#
# The bundle js/pii_redaction-init.mjs is built output (npm run build in php/,
# not in git). Without it the file action never shows, and the app would look
# installed and do nothing, so staging stops before it copies anything.
stage_companion() {
	stage="$1"
	app="${stage}/pii_redaction"
	if ! [ -s "php/js/pii_redaction-init.mjs" ]; then
		echo "php/js/pii_redaction-init.mjs is missing or empty; run npm ci && npm run build in php/ first"
		return 1
	fi
	mkdir -p "${app}"
	for d in appinfo lib templates js css img l10n; do
		cp -R "php/${d}" "${app}/${d}"
	done
	cp LICENSE CHANGELOG.md "${app}/"
	find "${app}" -name '.gitkeep' -delete
	echo "staged tree:"
	find "${app}" -maxdepth 1 -mindepth 1 | sed "s|^${app}/|  |" | sort
}

# info.xml is copied byte for byte and never rewritten, and that is a hard
# requirement: the store transform (pre-info.xslt) drops the routes element,
# so the store database never sees it. AppAPI reads it back out of this
# archive at installation and at an update. Here it is empty on purpose
# (decision 9: no browser route into the container), and an empty element is
# what empties the route list of an earlier version on an update (pitfall D);
# without the element the old routes would stay. The image is not in the
# archive: info.xml names it, AppAPI pulls it from ghcr.io.
stage_backend() {
	stage="$1"
	app="${stage}/pii_redaction_backend"
	if [ "$(grep -c '<routes/>' backend/appinfo/info.xml)" != "1" ] || grep -q '<route>' backend/appinfo/info.xml; then
		echo "backend/appinfo/info.xml has to carry exactly one empty <routes/> element and no route"
		return 1
	fi
	mkdir -p "${app}/appinfo"
	cp backend/appinfo/info.xml "${app}/appinfo/info.xml"
	cp LICENSE CHANGELOG.md "${app}/"
	cmp backend/appinfo/info.xml "${app}/appinfo/info.xml"
	echo "info.xml is byte identical to the working tree, with its empty routes element"
}

# No carriage return in anything that ships as text. A checkout with
# core.autocrlf would hand one to every file .gitattributes does not pin, and
# the archive would be a different product from the one release.yml builds on
# its Linux runner under the same version. An allowlist of extensions: a
# binary is never looked at, a new kind of text file has to be named here.
assert_no_crlf() {
	stage="$1"
	app="$2"
	offenders=$(
		find "${stage}/${app}" -type f \
			\( -name '*.php' -o -name '*.xml' -o -name '*.js' -o -name '*.mjs' -o -name '*.json' \
			-o -name '*.css' -o -name '*.md' -o -name '*.svg' -o -name 'LICENSE' \) \
			-exec sh -c '
				for file do
					tr -d "\r" < "${file}" | cmp -s - "${file}" ||
						printf "%s\n" "${file}"
				done
			' sh {} +
	)
	if [ -z "${offenders}" ]; then
		echo "no carriage return in any staged text file"
		return 0
	fi
	echo "these staged text files carry a carriage return, check out with LF and build again:"
	printf '%s\n' "${offenders}" | sed 's/^/  /'
	return 1
}

# Owner and group zero: the uid of a runner has no business in a public
# artefact. A tar.gz is not byte reproducible, so the archive that gets signed
# has to be the archive that gets uploaded; no later step may rebuild it.
pack() {
	stage="$1"
	app="$2"
	archive="$3"
	assert_no_crlf "${stage}" "${app}"
	mkdir -p "$(dirname "${archive}")"
	tar --numeric-owner --owner=0 --group=0 -czf "${archive}" -C "${stage}" "${app}"
	ls -l "${archive}"
}

# The listing is written once into a file and every check reads that file:
# "tar -tzf x | grep -q" lets grep leave early, tar takes SIGPIPE, and the
# answer then depends on the size of the archive (Findling rehearsal 05-18).
assert_contents() {
	archive="$1"
	app="$2"
	wants_signature="$3"
	listing="${archive}.listing"
	fail=0

	tar -tzf "${archive}" > "${listing}"
	echo "${archive}, $(wc -l < "${listing}") entries"
	cat "${listing}"

	tops=$(cut -d/ -f1 "${listing}" | sort -u)
	if [ "${tops}" != "${app}" ]; then
		echo "${archive}: the top level is '${tops}' and the store needs exactly one directory named ${app}"
		fail=1
	fi
	for wanted in appinfo/info.xml LICENSE CHANGELOG.md; do
		grep -qx "${app}/${wanted}" "${listing}" || { echo "${archive}: ${wanted} is missing"; fail=1; }
	done
	if [ "${app}" = "${COMPANION_ID}" ]; then
		for wanted in lib/AppInfo/Application.php "${INIT_BUNDLE}" l10n/de.json l10n/en.json l10n/fr.json; do
			grep -qx "${app}/${wanted}" "${listing}" || { echo "${archive}: ${wanted} is missing"; fail=1; }
		done
	fi
	if [ "${app}" = "${BACKEND_ID}" ] && [ "$(grep -c -v '/$' "${listing}")" != "3" ]; then
		echo "${archive}: the backend archive carries more than info.xml, LICENSE and CHANGELOG.md"
		fail=1
	fi

	if grep -qx "${app}/appinfo/signature.json" "${listing}"; then
		if [ "${wants_signature}" = "0" ]; then
			echo "${archive}: carries a code signature, and this half has no PHP for the integrity check to see"
			fail=1
		else
			echo "${archive}: carries appinfo/signature.json, as the integrity check of the instance requires"
		fi
	elif [ "${wants_signature}" = "1" ]; then
		echo "${archive}: has no appinfo/signature.json, so the integrity check would report the app as modified"
		fail=1
	else
		echo "${archive}: carries no code signature, which is correct for a container half"
	fi

	for forbidden in src node_modules tests vendor phpunit.xml composer.json composer.lock package.json \
		package-lock.json vite.config.ts tsconfig.json scripts docs .github; do
		if grep -q "^${app}/${forbidden}\(/\|$\)" "${listing}"; then
			echo "${archive}: contains ${forbidden}, which is development material and must not be released"
			fail=1
		fi
	done
	if grep -q '\.gitkeep$' "${listing}"; then
		echo "${archive}: contains a .gitkeep"
		fail=1
	fi
	if grep -Eq '\.(key|pem|p12|csr)$' "${listing}"; then
		echo "${archive}: contains a key file"
		fail=1
	fi
	return "${fail}"
}

command="${1:-}"
if [ "$#" -gt 0 ]; then
	shift
fi

case "${command}" in
	stage-companion)
		[ "$#" -eq 1 ] || { usage; exit 1; }
		stage_companion "$1"
		;;
	stage-backend)
		[ "$#" -eq 1 ] || { usage; exit 1; }
		stage_backend "$1"
		;;
	pack)
		[ "$#" -eq 3 ] || { usage; exit 1; }
		pack "$1" "$2" "$3"
		;;
	assert-contents)
		[ "$#" -eq 3 ] || { usage; exit 1; }
		assert_contents "$1" "$2" "$3"
		;;
	*)
		usage
		exit 1
		;;
esac
