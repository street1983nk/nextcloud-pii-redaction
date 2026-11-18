"""Container proof of success criterion 1 (plan 02-21): no secret, the limits, the group kill, no zombie.

Runs only inside the test stage of the image (sandbox.yml, -m container): the
server is PID 1 with the canary APP_SECRET, frpc runs with the canary
HP_SHARED_KEY, /certs/frp/client.key holds the canary key. pytest is a docker
exec as uid 10001 beside them, with PII_CANARY_SECRET, PII_CANARY_HP and
PII_CANARY_KEY.

The test checks exactly the read paths of RESEARCH Pitfall 1, not only
os.environ: /proc/1/environ, /proc/<frpc>/environ, /frpc.toml,
/certs/frp/client.key, state.db and the folder of another job. A probe
(tests/probes/read_secrets.py, standard library only) runs in the jail of
every profile and answers in words only; no canary value ever stands in an
assert text or a printed line.

A1 (frpc installed 0711, so the kernel marks frpc not dumpable) is only
measured: a1_frpc_environ in tests/out/measurements.json, no assert. Should it
not hold, plan 02-24 decides after D-02-14; the protection that is asserted is
the jail read path, which Landlock refuses in every profile. The dumpable
server (main.harden_process, plan 02-14) is a product property and asserted.

Lines in the job log (a gate where an assert follows):

    A1-FRPC-ENVIRON unjailed=<denied|read|...>          (a measurement)
    DUMPABLE-SERVER-ENVIRON unjailed=<denied|...>        (a gate: denied)
    JAIL-READ profile=<p> <label>=<word> ...             (a gate: nothing read, control read)
    JAIL-LIMITS profile=<p> ok=<ja|nein> proc_self_limits=<word>
    JAIL-SOCKET profile=<p> inet=<word> unix=<word>      (a gate: inet refused EACCES, unix ok)
    JAIL-LAYERS seccomp=<word> landlock=<word> abi=<n>   (a gate: both active, else an AR is needed)
    JAIL-GROUP-KILL timeout=<ja|nein> left=<n> grandchild=<gone|alive>
    SOFFICE-MEMORY doc=<name> pages=<n> vmpeak_kb=<n> vmhwm_kb=<n> samples=<n> ms=<n>
    JAIL-ZOMBIES after=<step> n=<zombies of this uid>    (a gate: 0)
"""

import asyncio
import json
import os
import secrets
import shutil
import sys
import threading
import time
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pymupdf
import pytest

from pii_redaction_backend import config
from pii_redaction_backend.sandbox import jail
from pii_redaction_backend.sandbox.profiles import PROFILES
from pii_redaction_backend.sandbox.reaper import become_subreaper
from pii_redaction_backend.workers import child, soffice
from tests.conftest import record_measurement, signed_headers

pytestmark = [pytest.mark.container, pytest.mark.linux]

PROBE = Path(__file__).with_name("probes") / "read_secrets.py"
PROC = Path("/proc")
SERVER_ENVIRON = "/proc/1/environ"
FRPC_TOML = "/frpc.toml"
CLIENT_KEY = "/certs/frp/client.key"
STATE_DB_NAME = "state.db"
CANARY_VARIABLES = ("PII_CANARY_SECRET", "PII_CANARY_HP", "PII_CANARY_KEY")
# What no child may see in its environment (RESEARCH Pitfall 1).
FORBIDDEN_ENV = frozenset(
    {"APP_SECRET", "APP_ID", "NEXTCLOUD_URL", "AA_VERSION", "APP_PERSISTENT_STORAGE", "HP_SHARED_KEY"}
)
HARP_SOCKET = "/tmp/exapp.sock"  # noqa: S108 - the HaRP socket path, only asked over HTTP
# Job ids of this test; far above anything the queue hands out in the container.
FOREIGN_JOB = 990_200
OWN_JOB_BASE = 990_210
SOFFICE_JOBS = {"harmless_docx": "990230", "docx_300_pages": "990231"}
SAMPLE_S = 0.05
SETTLE_S = 5.0
HANG_TIMEOUT_S = 3.0
PAGES = 300
PAGE_BREAK = '<w:br w:type="page"/>'
# The type of pytest's record_property fixture.
RecordProperty = Callable[[str, object], None]
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
PACKAGE_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    "</Relationships>"
)


# -- helpers --------------------------------------------------------------------------------


def _say(capsys: pytest.CaptureFixture[str], *lines: str) -> None:
    """Outside the capture, so the lines stand in the job log of a passing run, too."""
    with capsys.disabled():
        print()
        for line in lines:
            print(line)


def _frpc_pid() -> int:
    """The pid of frpc; without it A1 cannot be measured and the frpc read path not checked."""
    for entry in PROC.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            name = (entry / "comm").read_text(encoding="ascii", errors="replace").strip()
        except OSError:
            continue
        if name == "frpc":
            return int(entry.name)
    pytest.fail("frpc does not run in the container: A1 and the frpc read path cannot be checked")


def _unjailed(path: str) -> str:
    """What this process (uid 10001, no jail) gets when it reads path: read, denied, missing or error."""
    try:
        with open(path, "rb") as handle:
            handle.read(1)
    except PermissionError:
        return "denied"
    except FileNotFoundError:
        return "missing"
    except OSError as exc:
        return f"error {type(exc).__name__}"
    return "read"


def _canaries() -> list[str]:
    missing = [name for name in CANARY_VARIABLES if not os.environ.get(name)]
    if missing:
        pytest.fail(f"canary variables missing: {', '.join(missing)} (sandbox.yml sets them)")
    return [os.environ[name] for name in CANARY_VARIABLES]


def _status_client() -> httpx.Client:
    if os.environ.get("HP_SHARED_KEY"):
        path = os.environ.get("HP_EXAPP_SOCK", HARP_SOCKET)
        return httpx.Client(transport=httpx.HTTPTransport(uds=path), base_url="http://localhost", timeout=10)
    return httpx.Client(base_url=f"http://127.0.0.1:{os.environ['APP_PORT']}", timeout=10)


def _job_folder(job_id: int) -> Path:
    folder = config.work_dir(job_id)
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    return folder


def _stat_fields(pid: int) -> tuple[str, int, int] | None:
    """(state, ppid, pgrp) of a process, or None once it is gone."""
    try:
        raw = (PROC / str(pid) / "stat").read_text(encoding="ascii", errors="replace")
    except OSError:
        return None
    fields = raw.rpartition(")")[2].split()
    return fields[0], int(fields[1]), int(fields[2])


def _uid() -> int:
    if sys.platform == "win32":
        return -1
    return os.getuid()


def _own_pids() -> Iterator[int]:
    uid = _uid()
    for entry in PROC.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != uid:
                continue
        except OSError:
            continue
        yield int(entry.name)


def zombies() -> list[int]:
    """The zombies of this uid that /proc shows now (server and tests both run as 10001)."""
    found = []
    for pid in _own_pids():
        fields = _stat_fields(pid)
        if fields is not None and fields[0] == "Z":
            found.append(pid)
    return found


def settled_zombies() -> list[int]:
    """Zombies that are still there after SETTLE_S: a reaper needs a moment, a leak stays."""
    deadline = time.monotonic() + SETTLE_S
    while (found := zombies()) and time.monotonic() < deadline:
        time.sleep(0.1)
    return found


def group_members(pgid: int) -> list[int]:
    """Every process of this uid in group pgid, zombies included."""
    members = []
    for pid in _own_pids():
        fields = _stat_fields(pid)
        if fields is not None and fields[2] == pgid:
            members.append(pid)
    return members


def settled_group(pgid: int) -> list[int]:
    """The members of group pgid still there after SETTLE_S."""
    deadline = time.monotonic() + SETTLE_S
    while (left := group_members(pgid)) and time.monotonic() < deadline:
        time.sleep(0.1)
    return left


def expected_limits(profile: str) -> dict[str, list[int]]:
    """The rlimits the jail sets for profile; a profile without an address space limit keeps the parent's."""
    plan = {name.removeprefix("RLIMIT_"): list(value) for name, value in jail.limits(PROFILES[profile])}
    if "AS" not in plan:
        plan["AS"] = _own_address_space()
    return plan


def _own_address_space() -> list[int]:
    if sys.platform == "win32":
        return []
    import resource

    return list(resource.getrlimit(resource.RLIMIT_AS))


# -- (a) and (b): frpc runs, the unjailed reads ------------------------------------------------


def test_a1_frpc_environ_is_only_measured(capsys: pytest.CaptureFixture[str], record_property: RecordProperty) -> None:
    """A1: can a process of uid 10001 without a jail read the frpc environment? Measured, never asserted."""
    word = _unjailed(f"/proc/{_frpc_pid()}/environ")
    _say(capsys, f"A1-FRPC-ENVIRON unjailed={word}")
    record_measurement("a1_frpc_environ", word)
    record_property("a1_frpc_environ", word)


def test_the_dumpable_server_environment_is_closed_to_uid_10001(
    capsys: pytest.CaptureFixture[str], record_property: RecordProperty
) -> None:
    word = _unjailed(SERVER_ENVIRON)
    _say(capsys, f"DUMPABLE-SERVER-ENVIRON unjailed={word}")
    record_measurement("dumpable_server_environ", word)
    record_property("dumpable_server_environ", word)
    # main.harden_process (plan 02-14): PR_SET_DUMPABLE 0, so /proc/1/environ is root's to read.
    assert word == "denied"


# -- (c), (d), (e): the probe in the jail of every profile ---------------------------------------


@pytest.mark.parametrize("profile", sorted(PROFILES))
async def test_no_jailed_child_reads_a_secret(profile: str, capsys: pytest.CaptureFixture[str]) -> None:
    canaries = _canaries()
    frpc = _frpc_pid()
    foreign = _job_folder(FOREIGN_JOB)
    own = _job_folder(OWN_JOB_BASE + sorted(PROFILES).index(profile))
    try:
        foreign_token = secrets.token_hex(16)
        (foreign / "src").write_text(foreign_token, encoding="utf-8")
        (own / "canaries.txt").write_text("\n".join([*canaries, foreign_token]) + "\n", encoding="utf-8")
        state_db = str(config.state_db_path())
        targets = {
            "server_environ": SERVER_ENVIRON,
            "frpc_toml": FRPC_TOML,
            "client_key": CLIENT_KEY,
            "state_db": state_db,
            "foreign_file": str(foreign / "src"),
        }
        assert state_db.endswith(STATE_DB_NAME)
        out = own / "answer.json"
        args = [sys.executable, "-I", str(PROBE), str(out), str(own / "canaries.txt"), str(frpc), str(foreign)]
        await child.run_child([*args, *targets.values()], profile=profile, cwd=own, write=(str(own),))
        answer = json.loads(out.read_text(encoding="utf-8"))
        # Positive control of the unjailed view: what exists for uid 10001 outside the jail.
        unjailed = {label: _unjailed(path) for label, path in targets.items()}
    finally:
        shutil.rmtree(foreign, ignore_errors=True)
        shutil.rmtree(own, ignore_errors=True)

    words = {"frpc_environ": answer["paths"][f"/proc/{frpc}/environ"]}
    words |= {label: answer["paths"][path] for label, path in targets.items()}
    words["foreign_listing"] = answer["foreign_listing"]
    allowed_env = set(child.child_env(profile=profile))
    env_ok = set(answer["env_keys"]) <= allowed_env and not set(answer["env_keys"]) & FORBIDDEN_ENV
    limits_ok = answer["limits"] == expected_limits(profile)
    _say(
        capsys,
        f"JAIL-READ profile={profile} control={answer['control']} "
        + " ".join(f"{label}={word}" for label, word in words.items())
        + f" env_ok={'ja' if env_ok else 'nein'} canary_seen={'ja' if answer['canary_seen'] else 'nein'}",
        f"JAIL-LIMITS profile={profile} ok={'ja' if limits_ok else 'nein'} "
        f"proc_self_limits={answer['proc_self_limits']}",
        f"JAIL-SOCKET profile={profile} inet={answer['socket_inet']} unix={answer['socket_unix']}",
    )
    record_measurement(
        f"jail_reads_{profile}",
        {**words, "control": answer["control"], "proc_self_limits": answer["proc_self_limits"]},
    )

    # The probe ran and could read its own work folder: the refusals below mean the jail.
    assert answer["control"] == "read"
    for label, word in words.items():
        assert word != "read", (profile, label)
        assert word in {"denied", "missing"}, (profile, label, word)
    # "missing" only where the file is missing outside the jail, too.
    for label, word in unjailed.items():
        if word != "missing":
            assert words[label] == "denied", (profile, label, words[label])
    # The secrets are readable for uid 10001 outside the jail: so the jail is what keeps them closed.
    assert unjailed["frpc_toml"] == "read"
    assert unjailed["client_key"] == "read"
    assert unjailed["foreign_file"] == "read"
    assert words["foreign_listing"] == "denied"
    assert env_ok, (profile, sorted(set(answer["env_keys"]) - allowed_env))
    assert answer["canary_seen"] is False, profile
    # (d) the rlimits of the profile, core size 0 included.
    assert limits_ok, (profile, answer["limits"], expected_limits(profile))
    assert answer["limits"]["CORE"] == [0, 0]
    # (e) no network socket, a Unix socket still.
    assert answer["socket_inet"] == "refused EACCES", profile
    assert answer["socket_unix"] == "ok", profile


def test_status_shows_seccomp_and_landlock_active(capsys: pytest.CaptureFixture[str]) -> None:
    """A2: both layers active in the real image; otherwise an AR (accepted risk) is needed (plan 02-25)."""
    headers = signed_headers(secret=os.environ["PII_CANARY_SECRET"])
    with _status_client() as client:
        response = client.get("/status", headers=headers)
    assert response.status_code == 200
    sandbox = response.json()["sandbox"]
    _say(
        capsys,
        f"JAIL-LAYERS seccomp={sandbox['seccomp']} landlock={sandbox['landlock']} abi={sandbox['landlockAbi']}",
    )
    record_measurement("a2_landlock", {"landlock": sandbox["landlock"], "abi": sandbox["landlockAbi"]})
    assert sandbox["seccomp"] == "active", "seccomp unavailable: an AR is needed"
    assert sandbox["landlock"] == "active", "Landlock unavailable: an AR is needed"
    assert sandbox["jail"] == "ok"


# -- (f) a hanging child with a grandchild ---------------------------------------------------------


async def test_a_hanging_soffice_child_and_its_grandchild_leave_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # As the server (main.harden_process): orphans come back to this process and reap_group collects them.
    assert become_subreaper()
    ids = tmp_path / "ids.txt"
    script = (
        "import os, subprocess, sys, time\n"
        "p = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(ids)!r}, 'w').write(str(os.getpgrp()) + ' ' + str(p.pid))\n"
        "time.sleep(60)\n"
    )
    timed_out = False
    try:
        await child.run_child(
            [sys.executable, "-I", "-c", script],
            profile="soffice",
            cwd=tmp_path,
            write=(str(tmp_path),),
            timeout_s=HANG_TIMEOUT_S,
        )
    except child.ChildTimeout:
        timed_out = True
    pgid, grandchild = (int(value) for value in ids.read_text(encoding="utf-8").split())
    left = await asyncio.to_thread(settled_group, pgid)
    gone = _stat_fields(grandchild) is None
    found = settled_zombies()
    _say(
        capsys,
        f"JAIL-GROUP-KILL timeout={'ja' if timed_out else 'nein'} left={len(left)} "
        f"grandchild={'gone' if gone else 'alive'}",
        f"JAIL-ZOMBIES after=group-kill n={len(found)}",
    )
    assert timed_out
    assert left == []
    assert gone
    assert found == []


# -- (g) real LibreOffice conversions, memory sampled ---------------------------------------------


def docx_with_pages(path: Path, pages: int) -> Path:
    """A DOCX of pages pages: one paragraph per page, a page break between them."""
    body = "".join(
        f"<w:p><w:r>{'' if page == 0 else PAGE_BREAK}<w:t>Seite {page + 1}</w:t></w:r></w:p>" for page in range(pages)
    )
    document = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W_NS}">'
        f"<w:body>{body}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", PACKAGE_RELS)
        archive.writestr("word/document.xml", document)
    return path


class MemorySampler:
    """VmPeak and VmHWM of every soffice.bin of this uid, read from /proc/<pid>/status every SAMPLE_S."""

    def __init__(self) -> None:
        self.vmpeak_kb = 0
        self.vmhwm_kb = 0
        self.samples = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> "MemorySampler":
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.sample()
            self._stop.wait(SAMPLE_S)

    def sample(self) -> None:
        for pid in _own_pids():
            try:
                if (PROC / str(pid) / "comm").read_text(encoding="ascii").strip() != "soffice.bin":
                    continue
                status = (PROC / str(pid) / "status").read_text(encoding="ascii", errors="replace")
            except OSError:
                continue
            values = vm_values(status)
            if values:
                self.samples += 1
                self.vmpeak_kb = max(self.vmpeak_kb, values.get("VmPeak", 0))
                self.vmhwm_kb = max(self.vmhwm_kb, values.get("VmHWM", 0))


def vm_values(status: str) -> dict[str, int]:
    """VmPeak and VmHWM in KiB out of the text of /proc/<pid>/status."""
    found = {}
    for line in status.splitlines():
        key, _, rest = line.partition(":")
        if key in {"VmPeak", "VmHWM"} and rest.split() and rest.split()[0].isdigit():
            found[key] = int(rest.split()[0])
    return found


async def test_libreoffice_conversions_leave_no_zombie_and_are_measured(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mounted_corpus: tuple[Path, dict[str, dict[str, object]]],
) -> None:
    assert become_subreaper()
    corpus, _ = mounted_corpus
    sources = {
        "harmless_docx": shutil.copyfile(corpus / "harmless.docx", tmp_path / "harmless.docx"),
        "docx_300_pages": docx_with_pages(tmp_path / "pages.docx", PAGES),
    }
    peaks: dict[str, int] = {}
    hwms: dict[str, int] = {}
    lines: list[str] = []
    counts: dict[str, int] = {}
    for name, source in sources.items():
        started = time.monotonic()
        with MemorySampler() as sampler:
            pdf = await soffice.convert(Path(source), tmp_path / f"pdf-{name}", SOFFICE_JOBS[name])
        ms = int((time.monotonic() - started) * 1000)
        with pymupdf.open(pdf) as document:
            counts[name] = document.page_count
        peaks[name], hwms[name] = sampler.vmpeak_kb, sampler.vmhwm_kb
        lines.append(
            f"SOFFICE-MEMORY doc={name} pages={counts[name]} vmpeak_kb={sampler.vmpeak_kb} "
            f"vmhwm_kb={sampler.vmhwm_kb} samples={sampler.samples} ms={ms}"
        )
    found = settled_zombies()
    lines.append(f"JAIL-ZOMBIES after=soffice n={len(found)}")
    _say(capsys, *lines)
    # The basis for RLIMIT_AS of soffice (D-02-13, plan 02-24).
    record_measurement("soffice_vmpeak_kb", peaks)
    record_measurement("soffice_vmhwm_kb", hwms)

    assert counts["harmless_docx"] >= 1
    assert counts["docx_300_pages"] == PAGES
    # Positive control of the sampler: it saw soffice.bin in both runs.
    assert all(value > 0 for value in peaks.values()), peaks
    assert found == []
