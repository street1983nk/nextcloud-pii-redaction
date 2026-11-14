#!/usr/bin/env bash
# Register the backend again at a version of choice, on the volume it had
# (01-18-PLAN.md, drift steps; AVS ci/redeploy.sh with the ids of this app).
#
# The drift steps of .github/workflows/deploy-harp.yml need a container that
# reports a version other than the one of the PHP app. The image stays the
# image of this commit: AppAPI hands <version> of the info.xml to the
# container as APP_VERSION, and that value is all the lockstep check compares
# (config.app_version). The same image is pushed once more with the version
# as its tag, so the registration names an image tag that fits what it claims.
#
# The registration that is there goes first, through app_api:app:unregister
# without the data flag. AppAPI then asks HaRP to remove the container and to
# keep the volume nc_app_<id>_data (HaRP deletes the volume only on
# remove_data and reuses an existing one at create), so state.db and the work
# folders come back with the new container. Without a registration (after the
# step that unregistered the backend on purpose) the script only registers.
#
# Unlike AVS there is no GET /status through HaRP to read the version back:
# the routes element of info.xml is empty on purpose (decision 9), so every
# unsigned call into the container ends at HaRP. The script checks APP_VERSION
# in the environment of the new container and waits until Docker reports it
# healthy; what the PHP app makes of it is read by ci/admin-state.sh.
#
# usage: INFO_XML=<info.xml pointed at the local registry> [OCC=<path to occ>]
#        ci/redeploy.sh <major.minor.patch>
# Needs the variables of ci/lib.sh. Writes ci/out/info-<version>.xml.
set -euo pipefail

# shellcheck source=ci/lib.sh
. "$(dirname "$0")/lib.sh"

version="${1:-}"
: "${INFO_XML:?INFO_XML is required (the info.xml pointed at the local registry)}"
OCC="${OCC:-${NC_ROOT}/occ}"
BACKEND_APP_ID="${BACKEND_APP_ID:-pii_redaction_backend}"
LOCAL_REGISTRY="${LOCAL_REGISTRY:-localhost:5000}"
LOCAL_IMAGE_TAG="${LOCAL_IMAGE_TAG:-citest}"
DAEMON="${DAEMON:-harp_proxy_host}"

[[ "${version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "usage: ci/redeploy.sh <major.minor.patch>, got '${version}'"
[ -s "${INFO_XML}" ] || fail "INFO_XML ${INFO_XML} is missing or empty"

image="${LOCAL_REGISTRY}/${BACKEND_APP_ID}"
docker tag "${image}:${LOCAL_IMAGE_TAG}" "${image}:${version}"
docker push "${image}:${version}" > /dev/null

info="${CI_OUT}/info-${version}.xml"
sed -e "s|<version>[^<]*</version>|<version>${version}</version>|" \
	-e "s|<image-tag>[^<]*</image-tag>|<image-tag>${version}</image-tag>|" \
	"${INFO_XML}" > "${info}"
# Exactly one version element and one image tag, both rewritten, and the empty
# routes element still there; anything else means the sed hit a line it was
# not aimed at.
if [ "$(grep -c '<version>[^<]*</version>' "${info}")" != "1" ] \
	|| [ "$(grep -c "<version>${version}</version>" "${info}")" != "1" ] \
	|| [ "$(grep -c "<image-tag>${version}</image-tag>" "${info}")" != "1" ] \
	|| [ "$(grep -c '<routes/>' "${info}")" != "1" ]; then
	fail "${info} does not carry exactly one version, one image tag ${version} and the empty routes element"
fi

# The list goes into a variable first: grep -q on a pipe ends the pipe early,
# and with pipefail that reads as a failure of occ.
registered=$(timeout 30 "${OCC}" app_api:app:list)
if grep -q "${BACKEND_APP_ID}" <<<"${registered}"; then
	timeout 300 "${OCC}" app_api:app:unregister "${BACKEND_APP_ID}"
else
	echo "${BACKEND_APP_ID} is not registered, registering only"
fi
timeout 600 "${OCC}" app_api:app:register "${BACKEND_APP_ID}" "${DAEMON}" \
	--info-xml "${info}" --wait-finish

container=$(docker ps --filter "name=nc_app_${BACKEND_APP_ID}" --format '{{.Names}}' | head -n 1)
if [ -z "${container}" ]; then
	docker ps -a
	fail "the registration at ${version} left no running container"
fi
running=$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "${container}" \
	| sed -n 's/^APP_VERSION=//p' | head -n 1)
[ "${running}" = "${version}" ] || fail "the container runs APP_VERSION '${running}' while the registration asked for '${version}'"

health=none
for _ in $(seq 1 60); do
	health=$(docker inspect --format '{{.State.Health.Status}}' "${container}")
	[ "${health}" = "healthy" ] && break
	sleep 2
done
[ "${health}" = "healthy" ] || fail "${container} at ${version} is ${health} after 120 s"
echo "${container} redeployed at ${version}, APP_VERSION matches, healthy"
