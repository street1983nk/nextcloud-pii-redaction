#!/usr/bin/env bash
# No browser route reaches the container (01-17-PLAN.md, PLAT-05, decision 9):
#
#   as alice (user) and dora (admin) the AppAPI proxy of the ExApp answers
#   404 for /status, /jobs/1/pages/1.png and /jobs/1/output;
#   an unsigned GET on /exapps/pii_redaction_backend/status, at HaRP itself
#   and through the one address in front of Nextcloud and HaRP, is not 200.
#
# Positive control: GET /apps/pii_redaction/admin/state as dora answers 200
# with state ok, so the signed way into the container works in this run.
#
# HARP_URL (default http://localhost:8780) and FRONT_URL (default
# http://localhost:8090) are the addresses of deploy-harp.yml.
set -euo pipefail

# shellcheck source=ci/lib.sh
. "$(dirname "$0")/lib.sh"

HARP_URL="${HARP_URL:-http://localhost:8780}"
FRONT_URL="${FRONT_URL:-http://localhost:8090}"
PROXY='/index.php/apps/app_api/proxy/pii_redaction_backend'

# -- positive control -----------------------------------------------------------

body="${CI_OUT}/routes-admin-state.json"
code=$(req dora GET "${APP_PATH}/admin/state" "${body}" "${body}.headers")
[ "${code}" = "200" ] || fail "admin state as dora answered ${code} (positive control)"
[ "$(json_field "${body}" state)" = "ok" ] || fail "admin state as dora is '$(json_field "${body}" state)', expected ok (positive control)"
echo "ok: the signed way answers, admin state ok"

# -- the proxy, as user and as admin --------------------------------------------

for user in alice dora; do
	for route in status jobs/1/pages/1.png jobs/1/output; do
		out="${CI_OUT}/routes-${user}-${route//\//-}"
		code=$(req "${user}" GET "${PROXY}/${route}" "${out}.body" "${out}.headers")
		[ "${code}" = "404" ] || fail "app_api/proxy/pii_redaction_backend/${route} as ${user} answered ${code}, expected 404"
		echo "ok: proxy ${route} as ${user} -> 404"
	done
done

# -- unsigned, without Nextcloud ----------------------------------------------------

for base in "${HARP_URL}" "${FRONT_URL}"; do
	code=$(curl -s -o "${CI_OUT}/routes-unsigned.body" -w '%{http_code}' -m 10 "${base}/exapps/pii_redaction_backend/status" || true)
	[ "${code}" != "200" ] || fail "an unsigned GET on ${base}/exapps/pii_redaction_backend/status answered 200"
	echo "ok: unsigned ${base}/exapps/pii_redaction_backend/status -> ${code}"
done
echo "routes done"
