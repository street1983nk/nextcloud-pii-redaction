#!/usr/bin/env bash
# The state of the other half, as the admin section reads it (01-18-PLAN.md;
# AVS ci/admin-state.sh with the ids of this app).
#
# GET /apps/pii_redaction/admin/state is the route behind "Check again": it
# determines the state anew (ExAppService::backendState(true)) under the
# signed in admin and remembers it, so a start in the next minute follows it
# (POST /api/v1/jobs refuses with 503 backend_unavailable outside ok and
# version_patch_differs). The route requires an administrator and passes the
# CSRF check with OCS-APIRequest. Two ways in:
#   1. basic auth of the instance admin with OCS-APIRequest (ci/lib.sh req,
#      the same way ci/routes.sh reads the state as dora),
#   2. an app password of the admin from the OCS route core/getapppassword,
#      as the fallback and as the diagnosis when way one dies (AVS way one).
#
# usage: ci/admin-state.sh <name.json> [expected state]
# The answer lands in ci/out/<name.json>. With an expected state the script
# asks every 3 s until the state is that one, at most ADMIN_STATE_WAIT seconds
# (120): a container that was just started, enabled or registered needs a
# moment before it answers. Needs the variables of ci/lib.sh.
set -euo pipefail

# shellcheck source=ci/lib.sh
. "$(dirname "$0")/lib.sh"

name="${1:?usage: ci/admin-state.sh <name.json> [expected state]}"
expected="${2:-}"
[[ "${name}" =~ ^[a-z0-9-]+\.json$ ]] || fail "the name '${name}' is not a plain file name ending in .json"
out="${CI_OUT}/${name}"

has_state() {
	python3 -c 'import json, sys; sys.exit(0 if isinstance(json.load(open(sys.argv[1], encoding="utf-8")).get("state"), str) else 1)' "${out}" 2> /dev/null
}

report() {
	python3 -c 'import json, sys; d = json.load(open(sys.argv[1], encoding="utf-8")); print("admin state:", json.dumps({k: d.get(k) for k in ("state", "ownVersion", "backendVersion", "companion")}))' "${out}"
}

# read_state: the answer into ${out}; 0 when it carries a state.
read_state() {
	local apppw
	code=$(req "${ADMIN_USER}" GET "${APP_PATH}/admin/state" "${out}" "${out}.headers")
	echo "state via basic auth: HTTP ${code}"
	if [ "${code}" = "200" ] && has_state; then
		return 0
	fi
	apppw=$(curl -s -u "${ADMIN_USER}:${ADMIN_PASS}" -H 'OCS-APIRequest: true' -H 'Accept: application/json' \
		"${NC_URL}/ocs/v2.php/core/getapppassword" \
		| python3 -c 'import json, sys; print(json.load(sys.stdin)["ocs"]["data"]["apppassword"])' 2> /dev/null || true)
	if [ -z "${apppw}" ]; then
		echo "app password: not available"
		return 1
	fi
	# Masked in the log of a GitHub run; harmless elsewhere.
	echo "::add-mask::${apppw}"
	code=$(curl -s -o "${out}" -w '%{http_code}' -u "${ADMIN_USER}:${apppw}" \
		-H 'OCS-APIRequest: true' -H 'Accept: application/json' "${NC_URL}${APP_PATH}/admin/state")
	echo "state via app password: HTTP ${code}"
	[ "${code}" = "200" ] && has_state
}

code=none
deadline=$((SECONDS + ${ADMIN_STATE_WAIT:-120}))
while :; do
	if read_state; then
		report
		state=$(json_field "${out}" state)
		if [ -z "${expected}" ] || [ "${state}" = "${expected}" ]; then
			exit 0
		fi
		echo "state ${state}, waiting for ${expected}"
	fi
	[ "${SECONDS}" -lt "${deadline}" ] || break
	sleep 3
done
echo "the admin state could not be read${expected:+ as ${expected}}; answer head:"
head -c 400 "${out}" || true
echo
fail "admin state not ${expected:-readable} after ${ADMIN_STATE_WAIT:-120} s (last HTTP ${code})"
