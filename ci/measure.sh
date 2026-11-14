#!/usr/bin/env bash
# The measurements of one leg (01-17-PLAN.md, RESEARCH decision 12): numbers
# only, no threshold is set here.
#
#   imageBytes, imageGzipBytes   docker image inspect of the image built in
#                                this run, docker save | gzip -c | wc -c
#   coldStart*Ms                 from ci/out/coldstart.json (deploy-harp.yml)
#   idle*Bytes                   memory.current, memory.peak and anon of
#                                memory.stat in the cgroup of the container
#                                (memory.peak needs kernel 5.19; missing, it
#                                is null and a note is printed, assumption A7)
#   lastChild*                   GET /apps/pii_redaction/admin/state as dora:
#                                peak RSS and duration of the last child, under
#                                the key of its kind (the others stay null)
#
# Output: ci/out/measurements-<server>-<arch>-<db>.json with fixed keys;
# python3 checks that every value is a number or null.
set -euo pipefail

# shellcheck source=ci/lib.sh
. "$(dirname "$0")/lib.sh"

: "${BACKEND_CONTAINER:?BACKEND_CONTAINER is required}"
IMAGE="${MEASURE_IMAGE:-${LOCAL_REGISTRY:-localhost:5000}/${BACKEND_APP_ID:-pii_redaction_backend}:${LOCAL_IMAGE_TAG:-citest}}"
SERVER="${SERVER_VERSION:-unknown}"
case "$(uname -m)" in
	x86_64 | amd64) ARCH=amd64 ;;
	aarch64 | arm64) ARCH=arm64 ;;
	*) ARCH="$(uname -m)" ;;
esac
DB="${DB_KIND:-sqlite}"
[[ "${SERVER}${ARCH}${DB}" =~ ^[A-Za-z0-9_]+$ ]] || fail "server, arch or database is no plain word"
OUT="${CI_OUT}/measurements-${SERVER}-${ARCH}-${DB}.json"

image_bytes=$(docker image inspect --format '{{.Size}}' "${IMAGE}")
image_gzip_bytes=$(docker save "${IMAGE}" | gzip -c | wc -c | tr -d ' ')

cgroup() {
	docker exec "${BACKEND_CONTAINER}" cat "/sys/fs/cgroup/$1" 2> /dev/null || true
}
memory_current=$(cgroup memory.current)
memory_peak=$(cgroup memory.peak)
if [ -z "${memory_peak}" ]; then
	echo "note: memory.peak is not there (kernel older than 5.19?), idlePeakBytes is null (assumption A7)"
	memory_peak=null
fi
memory_anon=$(cgroup memory.stat | awk '$1 == "anon" { print $2 }')
[ -n "${memory_current}" ] || fail "memory.current of the container could not be read"
[ -n "${memory_anon}" ] || fail "anon of memory.stat could not be read"

state="${CI_OUT}/measure-admin-state.json"
code=$(req dora GET "${APP_PATH}/admin/state" "${state}" "${state}.headers")
[ "${code}" = "200" ] || fail "admin state as dora answered ${code}"

python3 - "${CI_OUT}/coldstart.json" "${state}" "${OUT}" "${image_bytes}" "${image_gzip_bytes}" \
	"${memory_current}" "${memory_peak}" "${memory_anon}" <<'PY'
import json, sys

coldstart_path, state_path, out_path = sys.argv[1:4]
image, image_gzip, current, peak, anon = sys.argv[4:9]


def number(text):
    if text in ("", "null", "max"):
        return None
    return int(text)


with open(coldstart_path, encoding="utf-8") as handle:
    cold = json.load(handle)
with open(state_path, encoding="utf-8") as handle:
    child = json.load(handle).get("lastChild") or {}

start = cold.get("registerStartMs")
registered = cold.get("registeredMs")
ready = cold.get("readyMs")
kind = child.get("kind")

measurements = {
    "imageBytes": number(image),
    "imageGzipBytes": number(image_gzip),
    "coldStartRegisterMs": registered - start if start is not None and registered is not None else None,
    "coldStartReadyMs": ready - start if start is not None and ready is not None else None,
    "idleMemoryCurrentBytes": number(current),
    "idlePeakBytes": number(peak),
    "idleAnonBytes": number(anon),
}
for name in ("render", "soffice", "placeholder"):
    measurements[f"lastChild_{name}_rssKb"] = child.get("rssKb") if kind == name else None
    measurements[f"lastChild_{name}_ms"] = child.get("ms") if kind == name else None
if kind is not None and kind not in ("render", "soffice", "placeholder"):
    sys.exit("the last child has a kind outside the fixed list")

with open(out_path, "w", encoding="utf-8") as handle:
    json.dump(measurements, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY

# The check: fixed keys, every value a number or null, never a word.
python3 -c '
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
bad = [key for key, value in data.items() if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)))]
if bad or not data:
    sys.exit("measurements that are no numbers: " + ", ".join(bad))
print(json.dumps(data, sort_keys=True))
' "${OUT}"
echo "measurements written to $(basename "${OUT}")"
