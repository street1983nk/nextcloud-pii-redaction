"""The helpers of the risk checks R1 and R2 of the profile template (plan 02-16, owner 17.11.).

The container runs (tests/test_container_soffice.py) need LibreOffice and run
only in sandbox.yml; what they count, print and run is decided by these
helpers, which run everywhere. Test only.
"""

import errno
import faulthandler
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import replace
from functools import partial
from pathlib import Path

import pymupdf
import pytest

from pii_redaction_backend.sandbox import jail, profiles
from pii_redaction_backend.workers import soffice
from tests import jail_layers, profile_work
from tests import test_container_soffice as diag

# -- R1: the start counter ------------------------------------------------------------------


def stat_line(pid: int, name: str, start: int, ppid: int = 1, state: str = "S") -> str:
    # Fields from 3 on: state, ppid (field 4), 17 more, then field 22, the start time.
    rest = " ".join([state, str(ppid), *[str(n) for n in range(17)], str(start), "0"])
    return f"{pid} ({name}) {rest}\n"


# A fake /proc cannot hold the exe symlink everywhere (Windows needs a right
# for symlinks), so the fake keeps the target name in a plain file and the
# counter tests read it through FAKE_EXE instead of readlink.
FAKE_EXE = "exe-name"
REAL_EXE_BASENAME = diag.exe_basename
LO_CMDLINE = b"/usr/lib/libreoffice/program/soffice.bin\0-env:UserInstallation=file:///tmp/lo-1\0--headless\0"


def _fake_exe_basename(proc: Path, pid: int) -> str:
    try:
        return (proc / str(pid) / FAKE_EXE).read_text(encoding="ascii")
    except OSError:
        return "-"


@pytest.fixture(autouse=True)
def fake_exe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diag, "exe_basename", _fake_exe_basename)


def fake_process(
    proc: Path, pid: int, name: str, start: int, ppid: int = 1, *, identity: bool | None = None, state: str = "S"
) -> None:
    """A fake /proc/<pid>; a soffice.bin gets the cmdline and exe of the real program unless identity is False."""
    folder = proc / str(pid)
    folder.mkdir(parents=True)
    (folder / "stat").write_text(stat_line(pid, name, start, ppid, state), encoding="ascii")
    if identity if identity is not None else name == diag.SOFFICE_BIN:
        (folder / "cmdline").write_bytes(LO_CMDLINE)
        (folder / FAKE_EXE).write_text(diag.SOFFICE_BIN, encoding="ascii")


def test_the_fake_stat_line_has_ppid_and_start_where_the_kernel_puts_them() -> None:
    # Written out by hand from proc(5): pid (comm) state ppid ... field 22 starttime.
    fields = stat_line(7, "x", 999, ppid=3).split()
    assert fields[0] == "7"
    assert fields[3] == "3"
    assert fields[21] == "999"


def test_the_counter_finds_soffice_bin_by_name_and_start_time(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    fake_process(proc, 101, "soffice.bin", 5000)
    fake_process(proc, 102, "oosplash", 4999)
    # A name with a blank and a parenthesis: the name ends at the last ")".
    fake_process(proc, 103, "soffice.bin) (x", 5001)
    (proc / "self").mkdir()
    (proc / "104").mkdir()  # gone between listing and reading: no stat file
    broken = proc / "105"
    broken.mkdir()
    (broken / "stat").write_text("garbage", encoding="ascii")
    assert diag.soffice_processes(proc) == {(101, 5000)}
    # Another uid is not counted.
    assert diag.soffice_processes(proc, uid=(proc / "101").stat().st_uid + 1) == set()


def test_negative_a_soffice_bin_forked_by_soffice_bin_is_no_start(tmp_path: Path) -> None:
    """The df2d2e5 finding: helpers forked by soffice.bin carry its name until their exec."""
    proc = tmp_path / "proc"
    fake_process(proc, 10, "soffice", 900)  # the shell script, exec'd into oosplash
    fake_process(proc, 11, "oosplash", 901, ppid=10)
    fake_process(proc, 12, "soffice.bin", 902, ppid=11)  # the start
    fake_process(proc, 13, "soffice.bin", 903, ppid=12)  # fork of the start, before its exec
    fake_process(proc, 14, "soffice.bin", 904, ppid=12)  # another one
    fake_process(proc, 15, "soffice.bin", 905, ppid=13)  # a fork of a fork
    fake_process(proc, 16, "sh", 906, ppid=12)  # a helper after its exec: not soffice.bin at all
    assert diag.soffice_processes(proc) == {(12, 902)}
    # A restart: oosplash starts soffice.bin again, that counts.
    fake_process(proc, 20, "soffice.bin", 950, ppid=11)
    assert diag.soffice_processes(proc) == {(12, 902), (20, 950)}
    # A parent /proc does not show (gone, or another pid namespace) is no soffice.bin: counted.
    fake_process(proc, 30, "soffice.bin", 960, ppid=4242)
    assert (30, 960) in diag.soffice_processes(proc)


def test_negative_the_counter_does_not_count_forks_while_it_runs(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    fake_process(proc, 11, "oosplash", 901)
    with diag.StartCounter(proc=proc, poll_s=0.001) as counter:
        fake_process(proc, 12, "soffice.bin", 902, ppid=11)
        time.sleep(0.05)
        for pid in range(13, 19):
            fake_process(proc, pid, "soffice.bin", 900 + pid, ppid=12)
        time.sleep(0.05)
    assert counter.seen == {(12, 902)}


def test_negative_a_restart_is_a_second_process_and_earlier_ones_do_not_count(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    fake_process(proc, 90, "soffice.bin", 100)  # running before the block: not this job
    with diag.StartCounter(proc=proc, poll_s=0.001) as counter:
        fake_process(proc, 201, "soffice.bin", 7000)
        time.sleep(0.05)
        fake_process(proc, 202, "soffice.bin", 7100)
    assert counter.n == 2
    assert counter.seen == {(201, 7000), (202, 7100)}


def test_the_same_pid_with_a_new_start_time_is_a_new_start(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    proc.mkdir()
    with diag.StartCounter(proc=proc, poll_s=0.001) as counter:
        fake_process(proc, 301, "soffice.bin", 1)
        time.sleep(0.05)
        (proc / "301" / "stat").write_text(
            "301 (soffice.bin) " + " ".join(["S", *[str(n) for n in range(18)], "2", "0"]) + "\n", encoding="ascii"
        )
    assert counter.n == 2


def _move(proc: Path, pid: int, name: str, start: int, ppid: int, state: str = "S") -> None:
    (proc / str(pid) / "stat").write_text(stat_line(pid, name, start, ppid, state), encoding="ascii")


def _gone(proc: Path, pid: int) -> None:
    for path in (proc / str(pid)).iterdir():
        path.unlink()
    (proc / str(pid)).rmdir()


def test_a_fork_handed_to_another_parent_is_counted_and_its_detail_says_so(tmp_path: Path) -> None:
    """A live fork with the program identity whose soffice.bin parent is gone still counts (a known limit)."""
    proc = tmp_path / "proc"
    fake_process(proc, 11, "oosplash", 901)
    with diag.StartCounter(proc=proc, poll_s=0.001) as counter:
        fake_process(proc, 12, "soffice.bin", 902, ppid=11)
        time.sleep(0.05)
        fake_process(proc, 13, "soffice.bin", 903, ppid=12)  # a fork of the start, before its exec
        time.sleep(0.05)
        # The start ends; the kernel hands its fork to the subreaper (pid 1 here).
        _move(proc, 13, "soffice.bin", 903, ppid=1)
        _gone(proc, 12)
        time.sleep(0.05)
    assert counter.seen == {(12, 902), (13, 903)}
    lines = counter.detail_lines("product")
    assert len(lines) == 2
    start, fork = lines
    assert start.startswith(
        "SOFFICE-START-DETAIL kind=product counted=ja pid=12 ppid=11 parent_comm=oosplash comm=soffice.bin "
        "exe_basename=soffice.bin cmdline_head=/usr/lib/libreoffice/program/soffice.bin,"
    )
    assert "earlier_fork=nein" in start
    assert "ppids=11 " in start
    assert fork.startswith(
        "SOFFICE-START-DETAIL kind=product counted=ja pid=13 ppid=1 parent_comm=gone comm=soffice.bin"
    )
    assert "first_ppid=12 first_parent_comm=soffice.bin earlier_fork=ja ppids=12>1 " in fork


def test_negative_the_zombies_of_335a80f_are_no_start(tmp_path: Path) -> None:
    """Sandbox run of 335a80f: three orphaned soffice.bin without exe and cmdline, state Z or R>Z, counted n=4."""
    proc = tmp_path / "proc"
    fake_process(proc, 56, "oosplash", 900)
    with diag.StartCounter(proc=proc, poll_s=0.001) as counter:
        fake_process(proc, 71, "soffice.bin", 901, ppid=56)  # the real start
        time.sleep(0.05)
        fake_process(proc, 76, "soffice.bin", 902, identity=False, state="Z")
        fake_process(proc, 78, "soffice.bin", 903, identity=False, state="R")  # in its exit, not yet Z
        time.sleep(0.05)
        _move(proc, 78, "soffice.bin", 903, ppid=1, state="Z")
        fake_process(proc, 80, "soffice.bin", 904, identity=False, state="Z")
        time.sleep(0.05)
    assert counter.seen == {(71, 901)}
    assert counter.n == 1
    lines = counter.detail_lines("product")
    assert len(lines) == 4
    assert lines[0].startswith("SOFFICE-START-DETAIL kind=product counted=ja pid=71 ppid=56 parent_comm=oosplash")
    refused = {line.split(" pid=")[1].split()[0]: line for line in lines[1:]}
    assert set(refused) == {"76", "78", "80"}
    assert "counted=nein reason=zombie pid=76 ppid=1 " in refused["76"]
    assert "counted=nein reason=no_cmdline>zombie pid=78 " in refused["78"]
    assert "states=R>Z" in refused["78"]
    assert "exe_basename=- cmdline_head=-" in refused["80"]
    # The fake stat line carries 0 in the group field.
    assert counter.pgrps() == {0}


def test_a_real_second_start_with_its_cmdline_still_counts(tmp_path: Path) -> None:
    """The positive control of the fix: a restart is a live soffice.bin with cmdline and exe, so n stays 2."""
    proc = tmp_path / "proc"
    fake_process(proc, 82, "oosplash", 900)
    with diag.StartCounter(proc=proc, poll_s=0.001) as counter:
        fake_process(proc, 97, "soffice.bin", 901, ppid=82)
        time.sleep(0.05)
        _gone(proc, 97)
        fake_process(proc, 101, "soffice.bin", 902, ppid=82)  # the restart
        time.sleep(0.05)
        fake_process(proc, 102, "soffice.bin", 903, ppid=1, identity=False, state="Z")
        time.sleep(0.05)
    assert counter.seen == {(97, 901), (101, 902)}
    assert counter.n == 2
    assert [line.split()[2] for line in counter.detail_lines("control-fresh-unjailed")] == [
        "counted=ja",
        "counted=ja",
        "counted=nein",
    ]


@pytest.mark.parametrize(
    ("cmdline", "exe", "state", "reason"),
    [
        (LO_CMDLINE, "soffice.bin", "S", None),
        (LO_CMDLINE, "soffice.bin", "R", None),
        (LO_CMDLINE, "soffice.bin", "Z", "zombie"),
        (LO_CMDLINE, "soffice.bin", "X", "zombie"),
        (None, "soffice.bin", "S", "no_cmdline"),
        (b"", "soffice.bin", "S", "no_cmdline"),
        (b"/usr/bin/python3\0-c\0", "soffice.bin", "S", "other_cmdline"),
        (b"soffice.bin\0", "soffice.bin", "S", "other_cmdline"),
        (LO_CMDLINE, None, "S", "no_exe"),
        (LO_CMDLINE, "python3.13", "S", "other_exe"),
    ],
)
def test_identity_reason(
    tmp_path: Path, cmdline: bytes | None, exe: str | None, state: str, reason: str | None
) -> None:
    fake_process(tmp_path, 5, "soffice.bin", 1, identity=False, state=state)
    if cmdline is not None:
        (tmp_path / "5" / "cmdline").write_bytes(cmdline)
    if exe is not None:
        (tmp_path / "5" / FAKE_EXE).write_text(exe, encoding="ascii")
    entry = diag.read_proc(tmp_path)[5]
    assert diag.identity_reason(tmp_path, 5, entry) == reason


def test_cmdline_program_reads_the_first_argument(tmp_path: Path) -> None:
    fake_process(tmp_path, 6, "soffice.bin", 1)
    assert diag.cmdline_program(tmp_path, 6) == diag.SOFFICE_BIN_PATH
    assert diag.cmdline_program(tmp_path, 7) is None


def test_the_detail_line_follows_an_exec_and_a_zombie(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    proc.mkdir()
    with diag.StartCounter(proc=proc, poll_s=0.001) as counter:
        fake_process(proc, 21, "soffice.bin", 500, ppid=1)
        time.sleep(0.05)
        (proc / "21" / "stat").write_text(
            "21 (soffice.bin) " + " ".join(["Z", "1", *[str(n) for n in range(17)], "500", "0"]) + "\n",
            encoding="ascii",
        )
        time.sleep(0.05)
    (line,) = counter.detail_lines("control-fresh-unjailed")
    assert "counted=ja" in line
    assert "states=S>Z" in line
    # An exec renames the process: the names chain shows what it became.
    proc2 = tmp_path / "proc2"
    proc2.mkdir()
    with diag.StartCounter(proc=proc2, poll_s=0.001) as counter:
        fake_process(proc2, 31, "soffice.bin", 600, ppid=1)
        time.sleep(0.05)
        _move(proc2, 31, "sh", 600, ppid=1)
        time.sleep(0.05)
    (line,) = counter.detail_lines("product")
    assert "names=soffice.bin>sh" in line


def test_cmdline_head_and_exe_from_a_fake_proc(tmp_path: Path) -> None:
    fake_process(tmp_path, 41, "soffice.bin", 1)
    (tmp_path / "41" / "cmdline").write_bytes(b"/usr/lib/libreoffice/program/soffice.bin\0--headless\0--a b\0x\0")
    assert diag.cmdline_head(tmp_path, 41) == "/usr/lib/libreoffice/program/soffice.bin,--headless,--a_b"
    assert diag.cmdline_head(tmp_path, 42) == "-"
    assert REAL_EXE_BASENAME(tmp_path, 41) == "-"


def test_zombie_counts_and_line() -> None:
    def entry(state: str, pgrp: int, owner: int = 10001) -> diag.ProcEntry:
        return diag.ProcEntry("soffice.bin", 1, 1, owner, state, pgrp)

    table = {1: entry("Z", 56), 2: entry("S", 56), 3: entry("Z", 99), 4: entry("Z", 56, owner=0), 5: entry("Z", 57)}
    assert diag.zombie_counts(table, {56, 57}, 10001) == (2, 1)
    assert diag.zombie_counts(table, {56}, None) == (2, 2)
    assert diag.zombie_counts({}, set(), 10001) == (0, 0)
    assert diag.zombies_line(0, 3, {82, 56}, True) == "ZOMBIES after_job=0 pgrp=56,82 other_uid_zombies=3 subreaper=ja"
    assert diag.zombies_line(1, 0, set(), False) == "ZOMBIES after_job=1 pgrp=- other_uid_zombies=0 subreaper=nein"


def test_the_starts_line() -> None:
    assert diag.starts_line("product", 1) == "SOFFICE-STARTS product n=1"
    assert diag.starts_line("control-fresh-unjailed", 2, "exit=0 pdf=ja") == (
        "SOFFICE-STARTS control-fresh-unjailed n=2 exit=0 pdf=ja"
    )


# -- R1: what stays in /tmp, and the pipe name ----------------------------------------------


def test_the_rest_line_names_only_new_entries() -> None:
    before = {"exapp.sock": "sock"}
    now = {"exapp.sock": "sock", "OSL_PIPE_10001_SingleOfficeIPC_ab": "sock", "lo-1": "dir"}
    rest = diag.new_entries(before, now)
    assert rest == ["OSL_PIPE_10001_SingleOfficeIPC_ab:sock", "lo-1:dir"]
    assert diag.rest_line(rest, []) == (
        "TMP-REST product before_cleanup=OSL_PIPE_10001_SingleOfficeIPC_ab:sock,lo-1:dir after_cleanup=-"
    )


def test_lo_hex_drops_the_leading_zero_of_each_byte() -> None:
    # Independent of hashlib: fixed bytes, the expected text written out by hand.
    assert diag.lo_hex(bytes([0x00, 0x01, 0x0F, 0x10, 0xFF])) == "01f10ff"


def test_the_predicted_pipe_name_fits_the_cleanup_rule(tmp_path: Path) -> None:
    argv = soffice.command(tmp_path / "a.docx", tmp_path, "990001")
    name = diag.predicted_pipe_name(argv, 10001)
    match = soffice.IPC_SOCKET_NAME.fullmatch(name)
    assert match is not None
    assert match["uid"] == "10001"
    # A different job gives a different name: the hash covers the profile URL.
    assert diag.predicted_pipe_name(soffice.command(tmp_path / "a.docx", tmp_path, "990002"), 10001) != name


# -- R1: what LibreOffice compares at start -------------------------------------------------


def make_install(root: Path, buildid: str | None) -> Path:
    program = root / "program"
    program.mkdir(parents=True)
    lines = ["[Version]", "ProductMajor=2520"] + ([f"buildid={buildid}"] if buildid is not None else [])
    (program / "versionrc").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


def make_template(root: Path, buildid: str | None, completed: bool = True, mention: bool = False) -> Path:
    user = root / "user"
    (user / "extensions").mkdir(parents=True)
    if buildid is not None:
        (user / "extensions" / "buildid").write_bytes(buildid.encode())
    value = "true" if completed else "false"
    items = (
        '<item oor:path="/org.openoffice.Setup/Office"><prop oor:name="ooSetupInstCompleted" oor:op="fuse">'
        f"<value>{value}</value></prop></item>"
    )
    if mention:
        items += f"<item><value>file://{root}/user/basic</value></item>"
    (user / soffice.TEMPLATE_MARKER).write_text(f"<oor:items>{items}</oor:items>", encoding="utf-8")
    return root


def test_restart_facts_match_when_buildid_and_setup_agree(tmp_path: Path) -> None:
    lo_root = make_install(tmp_path / "lo", "abc123")
    (lo_root / "share" / "extensions").mkdir(parents=True)
    facts = diag.restart_facts(make_template(tmp_path / "template", "abc123"), lo_root)
    assert facts == {"buildid": "match", "setup_completed": "ja", "bundled": "0", "shared": "absent", "mentions": "-"}
    assert diag.restart_line(facts) == (
        "TEMPLATE-RESTART buildid=match setup_completed=ja bundled=0 shared=absent mentions=-"
    )


@pytest.mark.parametrize(
    ("stored", "installed", "word"),
    [("abc123", "zzz999", "differs"), (None, "abc123", "missing"), ("abc123", None, "unknown")],
)
def test_negative_restart_facts_name_each_mismatch(
    tmp_path: Path, stored: str | None, installed: str | None, word: str
) -> None:
    facts = diag.restart_facts(make_template(tmp_path / "t", stored), make_install(tmp_path / "lo", installed))
    assert facts["buildid"] == word


def test_negative_restart_facts_see_setup_and_self_references(tmp_path: Path) -> None:
    template = make_template(tmp_path / "t", "x", completed=False, mention=True)
    facts = diag.restart_facts(template, make_install(tmp_path / "lo", "x"))
    assert facts["setup_completed"] == "nein"
    assert facts["mentions"] == f"user/{soffice.TEMPLATE_MARKER}"


# -- R2: the deny-connect variant -----------------------------------------------------------


def test_deny_connect_changes_only_the_flag_and_leaves_the_profiles_alone() -> None:
    call = jail.parse(["detect", "--read", "/x", "--", "/usr/bin/true"])
    assert call is not None
    changed = jail_layers.with_deny_connect(call)
    assert changed.profile.deny_connect is True
    assert replace(changed.profile, deny_connect=False) == call.profile
    assert (changed.read, changed.write, changed.command) == (call.read, call.write, call.command)
    # The product profiles stay as they are: detect keeps connect(), soffice and render do not.
    assert profiles.profile_for("detect").deny_connect is False
    assert profiles.profile_for("soffice").deny_connect is True
    assert profiles.profile_for("render").deny_connect is True


@pytest.mark.parametrize("profile", ["render", "precheck", "sanitize", "ocr", "detect"])
def test_the_deny_connect_jail_installs_seccomp_with_deny_connect(profile: str) -> None:
    # Since 17.11. the product refuses connect() for render, precheck and
    # sanitize too; for them the variant equals the product. detect and ocr
    # still differ (negative control below).
    product_flag = profile in ("render", "precheck", "sanitize")
    calls: list[str] = []
    ops = jail.Ops(
        setrlimit=lambda name, _value: calls.append(name),
        prctl=lambda _option, _value: calls.append("prctl"),
        landlock_abi=lambda: 6,
        landlock_restrict=lambda *_paths: calls.append("landlock"),
        seccomp_available=lambda: True,
        seccomp_install=lambda deny: calls.append(f"seccomp {deny}"),
        execv=lambda path, _args: calls.append(f"exec {path}"),
    )
    assert jail_layers.deny_connect_main([profile, "--", "/usr/bin/true"], ops) == jail.EXIT_LAYER_FAILED
    assert calls[-4:] == ["prctl", "landlock", "seccomp True", "exec /usr/bin/true"]
    # The product jail of the same profile hands on what the profile says.
    calls.clear()
    call = jail.parse([profile, "--", "/usr/bin/true"])
    assert call is not None
    jail.run(call, ops)
    assert f"seccomp {product_flag}" in calls


def test_negative_a_malformed_deny_connect_call_is_a_usage_error() -> None:
    assert jail_layers.main(["deny-connect"]) == jail.EXIT_USAGE
    assert jail_layers.deny_connect_main(["nosuchprofile", "--", "/bin/true"]) == jail.EXIT_USAGE
    assert jail_layers.deny_connect_main(["render", "--", "relative"]) == jail.EXIT_USAGE


def test_deny_connect_argv_is_the_product_jail_through_the_driver(tmp_path: Path) -> None:
    args = ["/usr/bin/true", "x"]
    product = diag.jail_argv("detect", args, read=(str(tmp_path),), write=("/w",))
    variant = diag.deny_connect_argv("detect", args, read=(str(tmp_path),), write=("/w",))
    assert variant[:4] == [sys.executable, "-I", str(diag.DRIVER), "deny-connect"]
    assert variant[4:] == product[4:]
    assert product[2:4] == ["-m", jail.MODULE]


# -- R2: the work and its line ---------------------------------------------------------------


def test_the_work_list_names_every_profile_but_soffice(tmp_path: Path) -> None:
    works = diag.profile_works(tmp_path / "a.pdf", tmp_path / "a.docx", tmp_path / "a.png", tmp_path, None)
    named = {(work.profile, work.name) for work in works if isinstance(work, diag.Work)}
    assert named == {
        ("render", "render"),
        ("render", "placeholder"),
        ("precheck", "precheck"),
        ("sanitize", "sanitize"),
    }
    absent = [work for work in works if isinstance(work, str)]
    assert any("profile=detect" in line and "result=no-models" in line for line in absent)
    assert any("profile=ocr" in line and "result=absent" in line for line in absent)
    covered = {line.split("profile=")[1].split()[0] for line in absent} | {profile for profile, _ in named}
    assert covered == set(profiles.PROFILES) - {"soffice"}


def test_only_detect_and_ocr_are_still_measured_with_deny_connect() -> None:
    # render, precheck and sanitize refuse connect() in the product: one run, a gate.
    for name in ("render", "precheck", "sanitize"):
        assert diag.jails_for(name) == ("product",)
    # detect and ocr keep connect(): the product and the variant, a measurement.
    for name in ("detect", "ocr"):
        assert diag.jails_for(name) == ("product", "deny")
    assert set(diag.CONNECT_REFUSED) == {name for name, p in profiles.PROFILES.items() if p.deny_connect}


def test_the_product_work_line() -> None:
    work = diag.Work("sanitize", "sanitize", (), ())
    product = {"ok": True, "result": "result=ok events=-", "tail": "", "exit": 0}
    assert diag.product_work_line(work, product) == (
        "PROFILE-WORK profile=sanitize work=sanitize product_ok=ja result=ok events=- tail=-"
    )
    failed = {"ok": False, "result": "result=fail:exit2 events=socket.connect", "tail": "boom", "exit": 1}
    assert diag.product_work_line(work, failed) == (
        "PROFILE-WORK profile=sanitize work=sanitize product_ok=nein result=fail:exit2 events=socket.connect tail=boom"
    )


def test_with_models_and_tesseract_detect_and_ocr_are_work(tmp_path: Path) -> None:
    (tmp_path / "gliner2").mkdir()
    works = diag.profile_works(
        tmp_path / "a.pdf", tmp_path / "a.docx", tmp_path / "a.png", tmp_path, "/usr/bin/tesseract"
    )
    ocr = next(work for work in works if isinstance(work, diag.Work) and work.profile == "ocr")
    assert ocr.argv(tmp_path / "out") == ["/usr/bin/tesseract", str(tmp_path / "a.png"), f"{tmp_path / 'out'}/text"]
    detect = next(work for work in works if isinstance(work, diag.Work) and work.profile == "detect")
    assert detect.argv(tmp_path / "out")[-4:] == [
        "detect",
        str(tmp_path),
        str(tmp_path / "out"),
        str(diag.DETECT_DUMP_EVERY_S),
    ]
    assert detect.read == (str(tmp_path),)
    assert detect.timeout_s == diag.DETECT_TIMEOUT_S
    assert detect.trace(tmp_path / "out") == tmp_path / "out" / profile_work.TRACE_FILE
    # Dumps come several times before the limit, so a hang shows whether it moves.
    assert diag.DETECT_TIMEOUT_S >= 4 * diag.DETECT_DUMP_EVERY_S
    assert ocr.trace(tmp_path / "out") is None


# -- why a run hangs: the trace of profile_work.py and what the test reads of it ----------------

FAULTHANDLER_SAMPLE = """MARK t=0.0s step=start torch=nein rss=-
MARK t=4.2s step=offline_configured torch=nein rss=-
Timeout (0:01:00)!
Thread 0x0000ffff8a1bf120 (most recent call first):
  File "/usr/lib/python3.13/threading.py", line 359 in wait
  File "/usr/local/lib/python3.13/site-packages/torch/_utils.py", line 12 in worker

Current thread 0x0000ffff9b2c0040 (most recent call first):
  File "/usr/local/lib/python3.13/site-packages/torch/__init__.py", line 405 in _load_global_deps
  File "<frozen importlib._bootstrap>", line 488 in _call_with_frames_removed
  File "/app/tests/profile_work.py", line 160 in _detect
HARNESS dump on timeout
Current thread 0x0000ffff9b2c0040 (most recent call first):
  File "/usr/local/lib/python3.13/site-packages/torch/__init__.py", line 405 in _load_global_deps
"""


def test_condense_trace_keeps_the_marks_and_the_last_dump() -> None:
    text = diag.condense_trace(FAULTHANDLER_SAMPLE)
    assert text.startswith(
        "marks=t=0.0s step=start torch=nein rss=- ; t=4.2s step=offline_configured torch=nein rss=- dumps=2 "
    )
    # Only the dump after the harness mark, with the module path after site-packages.
    assert text.endswith("last_dump=current 0x0000ffff9b2c0040 < torch/__init__.py:405 _load_global_deps")
    # Without the harness mark the timeout dump is the last one: both threads, short paths.
    first = diag.condense_trace(FAULTHANDLER_SAMPLE.split("HARNESS")[0])
    assert "dumps=1" in first
    assert "Thread 0x0000ffff8a1bf120 < python3.13/threading.py:359 wait < torch/_utils.py:12 worker" in first
    assert "tests/profile_work.py:160 _detect" in first
    assert diag.condense_trace("") == "marks=- dumps=0 last_dump=-"
    assert diag.read_trace(None) == "-"


def test_proc_snapshot_reads_state_cpu_and_threads(tmp_path: Path) -> None:
    base = tmp_path / "77"
    (base / "task" / "77").mkdir(parents=True)
    (base / "task" / "78").mkdir()
    (base / "status").write_text(
        "Name:\tpython\nState:\tS (sleeping)\nThreads:\t2\nVmRSS:\t  1234 kB\n", encoding="ascii"
    )
    # utime 250 and stime 50 ticks: 3.0 s.
    stat = "77 (python) S 1 " + " ".join(["0"] * 9) + " 250 50 0 0\n"
    (base / "stat").write_text(stat, encoding="ascii")
    (base / "wchan").write_text("futex_wait_queue", encoding="ascii")
    (base / "task" / "77" / "stat").write_text(stat, encoding="ascii")
    (base / "task" / "78" / "stat").write_text(
        "78 (torch worker) R 1 " + " ".join(["0"] * 9) + " 900 0\n", encoding="ascii"
    )
    snapshot = diag.proc_snapshot(77, tmp_path)
    assert snapshot.startswith("state=S_(sleeping) threads=2 vmrss=1234_kB cpu_s=3.0 wchan=futex_wait_queue ")
    assert snapshot.endswith("top_threads=torch_worker:R:9.0s:-,python:S:3.0s:-")
    assert diag.proc_snapshot(99, tmp_path) == "proc=gone"


def test_the_trace_marks_steps_and_dumps_stacks(tmp_path: Path) -> None:
    was_enabled = faulthandler.is_enabled()
    trace = profile_work.Trace(tmp_path, 0.05)
    try:
        trace.mark("start")
        time.sleep(0.3)
        trace.mark("done")
    finally:
        trace.close()
        if was_enabled and sys.__stderr__ is not None:
            faulthandler.enable(file=sys.__stderr__)
    text = (tmp_path / profile_work.TRACE_FILE).read_text(encoding="ascii")
    condensed = diag.condense_trace(text)
    assert "step=start torch=" in condensed
    assert "step=done" in condensed
    # faulthandler really wrote stacks on its timer: the test's own frame is in them.
    assert "Timeout (" in text
    assert "test_the_trace_marks_steps_and_dumps_stacks" in text


def test_negative_detect_refuses_a_bad_dump_interval() -> None:
    assert profile_work.main(["detect", "/models", "/work", "zero"]) == 1
    assert profile_work.main(["detect", "/models", "/work", "-1"]) == 1


@pytest.mark.linux
async def test_a_timed_out_run_shows_proc_and_trace_in_its_tail(tmp_path: Path) -> None:
    sleep = shutil.which("sleep")
    assert sleep is not None
    trace = tmp_path / profile_work.TRACE_FILE
    trace.write_text("MARK t=0.0s step=start torch=nein rss=-\n", encoding="ascii")
    run = await diag._run_work([sleep, "30"], "detect", 0.5, trace)
    assert run["result"] == "result=fail:timeout events=-"
    assert run["ok"] is False
    tail = str(run["tail"])
    assert tail.startswith("state=")
    assert "cpu_s=" in tail
    assert "top_threads=sleep:" in tail
    assert "trace=marks=t=0.0s step=start" in tail
    # The harness marked the file before it asked for a dump (sleep has no handler and dies of SIGUSR1).
    assert diag.HARNESS_MARK in trace.read_text(encoding="ascii")


def test_the_work_line_and_what_counts_as_run() -> None:
    work = diag.Work("render", "render", (), ())
    product = {"ok": True, "result": "result=ok events=-", "tail": "", "exit": 0}
    denied = {"ok": False, "result": "result=fail:exit2 events=socket.connect", "tail": "boom", "exit": 1}
    assert diag.work_line(work, product, denied) == (
        "PROFILE-DENY-CONNECT profile=render work=render ok=nein product_ok=ja result=fail:exit2 "
        "events=socket.connect tail=boom"
    )
    assert diag.really_ran(denied)
    assert not diag.really_ran({**denied, "exit": jail.EXIT_LAYER_FAILED})
    assert not diag.really_ran({**denied, "result": "no-answer exit=1"})


# -- R2: the work driver ------------------------------------------------------------------------


def test_the_driver_line_names_result_and_events(capsys: pytest.CaptureFixture[str]) -> None:
    assert profile_work.result_line("ok", set()) == "result=ok events=-"
    assert profile_work.result_line("fail:x", {"socket.connect", "socket.__new__"}) == (
        "result=fail:x events=socket.__new__,socket.connect"
    )
    assert profile_work.main(["bogus"]) == 1
    assert capsys.readouterr().out.strip() == "result=fail:usage events=-"


def test_negative_the_driver_runs_only_the_known_children() -> None:
    with pytest.raises(profile_work.WorkFailed, match="unknown_child"):
        profile_work.run_module("soffice", [])


def test_the_driver_does_the_precheck_and_sanitize_work(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    with pymupdf.open() as document:
        document.new_page().insert_text((72, 72), "x")
        document.save(pdf)
    docx = diag._docx(tmp_path / "a.docx")
    profile_work.precheck(pdf, docx)
    profile_work.sanitize(docx, tmp_path / "clean.docx")
    assert (tmp_path / "clean.docx").stat().st_size > 0
    # Negative: a PDF named as the DOCX is no DOCX.
    with pytest.raises(Exception):  # noqa: B017, PT011 - Rejected or WorkFailed, either ends the work
        profile_work.precheck(pdf, pdf)


@pytest.mark.filterwarnings("ignore:.*found in sys.modules after import of package:RuntimeWarning")
def test_the_driver_runs_a_product_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    out = tmp_path / "ph.pdf"
    profile_work.run_module("placeholder", [str(out), "990002"])
    assert out.stat().st_size > 0
    with pytest.raises(profile_work.WorkFailed, match="exit2"):
        profile_work.run_module("placeholder", [str(out), "not-a-number"])


def test_detect_puts_temp_and_the_torch_cache_into_its_work_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The df2d2e5 finding: without a writable temp folder torch's import ends in FileNotFoundError.
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.delenv("TORCHINDUCTOR_CACHE_DIR", raising=False)
    monkeypatch.setattr(tempfile, "tempdir", None)
    monkeypatch.setattr(tempfile, "_get_default_tempdir", _no_tempdir)
    # Negative control: as in the jail, no temp folder is to be found.
    with pytest.raises(FileNotFoundError):
        tempfile.gettempdir()
    profile_work.use_work_folder_as_temp(tmp_path)
    assert tempfile.gettempdir() == str(tmp_path)
    assert os.environ["TMPDIR"] == str(tmp_path)
    assert Path(os.environ["TORCHINDUCTOR_CACHE_DIR"]).parent == tmp_path


def _no_tempdir() -> str:
    raise FileNotFoundError(errno.ENOENT, "no usable temporary directory")


def test_negative_detect_needs_its_work_folder() -> None:
    assert profile_work.main(["detect", "/models"]) == 1


def test_the_detect_folder_must_be_unique(tmp_path: Path) -> None:
    (tmp_path / "gliner2" / "a").mkdir(parents=True)
    assert profile_work._gliner_folder(tmp_path) == tmp_path / "gliner2" / "a"
    (tmp_path / "gliner2" / "b").mkdir()
    with pytest.raises(profile_work.WorkFailed, match="gliner_folder"):
        profile_work._gliner_folder(tmp_path)


def test_uid_is_a_number() -> None:
    assert isinstance(diag._uid(), int)
    if sys.platform != "win32":
        assert diag._uid() == os.getuid()


# -- detect on every architecture: the gate and the negative control ------------------------------


def test_the_detect_gate_variants_and_their_commands(tmp_path: Path) -> None:
    models, out = tmp_path / "models", tmp_path / "out"
    by_name = {variant.name: variant for variant in diag.DETECT_VARIANTS}
    assert list(by_name) == ["unjailed", "jailed-product", "control-omp-limit-1"]
    # Two gates, one control; the control costs at most CONTROL_TIMEOUT_S, at most 120 s.
    assert [variant.gated for variant in diag.DETECT_VARIANTS] == [True, True, False]
    assert by_name["jailed-product"].timeout_s == diag.VARIANT_TIMEOUT_S == 60.0
    assert by_name["control-omp-limit-1"].timeout_s == diag.CONTROL_TIMEOUT_S <= 120.0
    # Stacks at 15, 30 and 45 s, before the 60 s kill.
    assert diag.VARIANT_TIMEOUT_S / diag.VARIANT_DUMP_EVERY_S >= 3
    work = diag.work_argv("detect", str(models), str(out), str(diag.VARIANT_DUMP_EVERY_S))
    # (a) the work itself, no jail.
    assert diag.variant_argv(by_name["unjailed"], models, out) == work
    # (b) exactly the product jail of detect; (c) the same command, only the environment differs.
    product = jail.jail_argv("detect", work, read=(str(models),), write=(str(out),))
    assert diag.variant_argv(by_name["jailed-product"], models, out) == product
    assert diag.variant_argv(by_name["control-omp-limit-1"], models, out) == product
    with pytest.raises(ValueError, match="unknown jail"):
        diag.variant_argv(diag.DetectVariant("x", "bogus"), models, out)


def test_the_detect_gate_fails_on_a_timeout_a_miss_or_a_slow_extraction() -> None:
    gate, control = diag.DETECT_VARIANTS[1], diag.DETECT_VARIANTS[2]
    ok = {"ok": True, "result": "result=ok events=-", "tail": "", "exit": 0}
    hung = {"ok": False, "result": "result=fail:timeout events=-", "tail": "", "exit": None}
    missed = {"ok": False, "result": "result=fail:gliner_missed events=-", "tail": "", "exit": 1}
    assert diag.gate_failure(gate, ok, {"ms_extract": "231"}) is None
    assert diag.gate_failure(gate, ok, {"ms_extract": str(diag.EXTRACT_BUDGET_MS)}) is None
    assert diag.gate_failure(gate, hung, {}) == "jailed-product: result=fail:timeout"
    assert diag.gate_failure(gate, missed, {}) == "jailed-product: result=fail:gliner_missed"
    assert diag.gate_failure(gate, ok, {"ms_extract": "-"}) == "jailed-product: no EXTRACT line"
    slow = diag.gate_failure(gate, ok, {"ms_extract": str(diag.EXTRACT_BUDGET_MS + 1)})
    assert slow == f"jailed-product: extract {diag.EXTRACT_BUDGET_MS + 1} ms > {diag.EXTRACT_BUDGET_MS} ms"
    # The negative control never fails the gate, hung or not.
    assert diag.gate_failure(control, hung, {}) is None


def test_detect_is_gated_with_connect_denied_and_runs_in_the_gate_budget() -> None:
    assert diag.DENY_GATED == ("detect",)
    assert set(diag.DENY_GATED) <= {name for name, p in profiles.PROFILES.items() if not p.deny_connect}
    assert diag.DETECT_TIMEOUT_S == diag.VARIANT_TIMEOUT_S


TRACE_WITH_FACTS = (
    "MARK t=0.0s step=start torch=nein rss=-\n"
    "FACTS torch_threads=8 interop=8 cpu_cap=NO_AVX cpu_count=8 affinity=8:0-7 present=EACCES possible=EACCES "
    "online=EACCES cpuinfo=EACCES omp_num_threads=- omp_thread_limit=1\n"
    "MARK t=9.0s step=gliner_loaded torch=ja rss=-\n"
    "EXTRACT ms=412\n"
)


def test_trace_facts_and_the_variant_line() -> None:
    facts = diag.trace_facts(TRACE_WITH_FACTS)
    assert facts["torch_threads"] == "8"
    assert facts["present"] == "EACCES"
    assert facts["ms_extract"] == "412"
    assert diag.trace_facts("") == {"ms_extract": "-"}
    variant = diag.DETECT_VARIANTS[0]
    ok = {"ok": True, "result": "result=ok events=-", "tail": "", "exit": 0}
    assert diag.variant_line(variant, ok, TRACE_WITH_FACTS) == (
        "DETECT-VARIANT name=unjailed ok=ja ms_extract=412 threads=8 cpu_cap=NO_AVX interop=8 cpu_count=8 "
        "affinity=8:0-7 present=EACCES possible=EACCES online=EACCES cpuinfo=EACCES omp_num_threads=- "
        "omp_thread_limit=1 result=ok tail=-"
    )
    hung = {"ok": False, "result": "result=fail:timeout events=-", "tail": "state=R x" * 400, "exit": None}
    line = diag.variant_line(variant, hung, "")
    assert line.startswith("DETECT-VARIANT name=unjailed ok=nein ms_extract=- threads=- cpu_cap=- interop=- ")
    assert " result=fail:timeout tail=state=R" in line
    assert len(line.partition(" tail=")[2]) == diag.VARIANT_TAIL_CHARS


def test_the_gates_run_the_product_env_and_the_control_adds_only_the_omp_limit() -> None:
    product = diag.child.child_env(profile="detect")
    assert "OMP_THREAD_LIMIT" not in product
    assert product["OMP_NUM_THREADS"].isdigit()
    for variant in diag.DETECT_VARIANTS:
        env = diag.variant_env(variant)
        if variant.omp_limit:
            assert env == {**product, "OMP_THREAD_LIMIT": "1"}
        else:
            assert env == product
    # The product environment itself is untouched by a variant.
    assert "OMP_THREAD_LIMIT" not in diag.child.child_env(profile="detect")


STACK_SAMPLE = """MARK t=0.0s step=start torch=nein rss=-
MARK t=21.0s step=gliner_loaded torch=ja rss=-
Timeout (0:00:30)!
Thread 0x0000ffff8a1bf120 (most recent call first):
  File "/usr/lib/python3.13/threading.py", line 359 in wait

Current thread 0x0000ffff9b2c0040 (most recent call first):
  File "/app/.venv/lib/python3.13/site-packages/gliner2/layers.py", line 487 in score_queries
  File "/app/.venv/lib/python3.13/site-packages/gliner2/models/span/model.py", line 621 in _compute_span_scores_core
Timeout (0:01:00)!
Current thread 0x0000ffff9b2c0040 (most recent call first):
  File "/app/.venv/lib/python3.13/site-packages/gliner2/layers.py", line 487 in score_queries
HARNESS dump on timeout
Current thread 0x0000ffff9b2c0040 (most recent call first):
  File "/app/.venv/lib/python3.13/site-packages/gliner2/layers.py", line 491 in score_queries
"""


def test_stack_lines_one_per_dump() -> None:
    lines = diag.stack_lines("unjailed", STACK_SAMPLE)
    assert len(lines) == 3
    assert lines[0] == (
        "DETECT-STACK name=unjailed dump=1/3 at=0:00:30 threads=2 "
        "stacks=Thread 0x0000ffff8a1bf120 < python3.13/threading.py:359 wait || "
        "current 0x0000ffff9b2c0040 < gliner2/layers.py:487 score_queries < "
        "gliner2/models/span/model.py:621 _compute_span_scores_core"
    )
    # Each dump ends at the next header: the second holds one thread only.
    assert lines[1] == (
        "DETECT-STACK name=unjailed dump=2/3 at=0:01:00 threads=1 "
        "stacks=current 0x0000ffff9b2c0040 < gliner2/layers.py:487 score_queries"
    )
    assert lines[2].startswith("DETECT-STACK name=unjailed dump=3/3 at=harness threads=1 ")
    assert lines[2].endswith("gliner2/layers.py:491 score_queries")
    assert diag.stack_lines("x", "MARK t=0.0s step=start torch=nein rss=-\n") == []
    long = STACK_SAMPLE.replace("score_queries", "score_queries" * 400)
    assert all(len(line) <= diag.STACK_CHARS for line in diag.stack_lines("x", long))
    # condense_trace still sees the last dump only.
    assert diag.condense_trace(STACK_SAMPLE).endswith(
        "last_dump=current 0x0000ffff9b2c0040 < gliner2/layers.py:491 score_queries"
    )


PARALLEL_INFO_SAMPLE = """ATen/Parallel:
\tat::get_num_threads() : 1
\tat::get_num_interop_threads() : 4
OpenMP 201511 (a.k.a. OpenMP 4.5)
\tomp_get_max_threads() : 1
Intel(R) MKL-DNN v3.7.1 (Git Hash 8d263e693366ef8db40acc569cc7d8edf644556d)
std::thread::hardware_concurrency() : 4
Environment variables:
\tOMP_NUM_THREADS : [not set]
\tMKL_NUM_THREADS : [not set]
ATen parallel backend: OpenMP
"""


def test_parallel_summary_names_threads_backend_and_versions() -> None:
    assert profile_work.parallel_summary(PARALLEL_INFO_SAMPLE) == (
        "aten_threads=1 aten_interop=4 omp_max_threads=1 mkl_max_threads=- hw_concurrency=4 backend=OpenMP "
        "openmp=201511 mkldnn_version=v3.7.1"
    )
    assert profile_work.parallel_summary("") == (
        "aten_threads=- aten_interop=- omp_max_threads=- mkl_max_threads=- hw_concurrency=- backend=- "
        "openmp=- mkldnn_version=-"
    )


BENCH_SAMPLE = (
    "BENCH step=start\n"
    "BENCH step=facts torch=2.15.0+cpu aten_threads=1 aten_interop=4 omp_max_threads=1 mkl_max_threads=- "
    "hw_concurrency=4 backend=OpenMP openmp=201511 mkldnn_version=v3.7.1 num_threads=1 interop=4 mkldnn=ja "
    "acl=ja config_acl=ja mkl=nein omp_avail=ja cpu_cap=SVE128 omp_thread_limit=1 omp_num_threads=-\n"
    "BENCH step=matmul ms=41.5\n"
    "BENCH step=score_queries ms=timeout\n"
    "BENCH step=score_queries_ftz ms=3.2 first_ms=0.4 ftz=ja\n"
)


def test_bench_values_and_the_torch_facts_line() -> None:
    values = diag.bench_values(BENCH_SAMPLE)
    assert values["torch"] == "2.15.0+cpu"
    assert values["acl"] == "ja"
    assert values["matmul"] == "41.5"
    assert values["score_queries"] == "timeout"
    assert values["score_queries_ftz_first_ms"] == "0.4"
    assert values["ftz"] == "ja"
    assert "start" not in values
    ok = {"ok": True, "result": "result=ok events=-", "tail": "", "exit": 0}
    line = diag.torch_facts_line("unjailed", "aarch64", ok, BENCH_SAMPLE)
    assert line.startswith("TORCH-FACTS env=unjailed arch=aarch64 ok=ja result=ok torch=2.15.0+cpu aten_threads=1 ")
    assert " cpu_cap=SVE128 omp_thread_limit=1 omp_num_threads=- matmul512_x20_ms=41.5 " in line
    assert " score_queries_x20_ms=timeout score_queries_first_ms=- " in line
    assert line.endswith(" score_queries_ftz_x20_ms=3.2 score_queries_ftz_first_ms=0.4 ftz=ja tail=-")
    keys = [part.partition("=")[0] for part in line.split()[1:]]
    assert len(keys) == len(set(keys))
    # A run killed by the harness before the bench wrote anything: every value -, the tail kept.
    hung = {"ok": False, "result": "result=fail:timeout events=-", "tail": "state=R", "exit": None}
    empty = diag.torch_facts_line("jailed-product", "aarch64", hung, "")
    assert " result=fail:timeout torch=- " in empty
    assert empty.endswith("ftz=- tail=state=R")


def test_the_bench_commands(tmp_path: Path) -> None:
    out = tmp_path / "out"
    work = diag.work_argv("torchbench", str(out))
    assert diag.bench_argv("unjailed", out) == work
    assert diag.bench_argv("jailed-product", out) == jail.jail_argv("detect", work, write=(str(out),))
    with pytest.raises(ValueError, match="unknown bench env"):
        diag.bench_argv("bogus", out)
    assert len(profile_work.BENCH_STEPS) * profile_work.BENCH_STEP_S < diag.BENCH_TIMEOUT_S
    assert profile_work.main(["torchbench"]) == 1


def test_a_hung_bench_step_still_yields_its_line(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("torch")
    monkeypatch.setitem(profile_work.BENCH_CALLS, "matmul", partial(_slow_step, 2.0))
    assert profile_work.bench_step("matmul", 0.1) == ("BENCH step=matmul ms=timeout", True)
    monkeypatch.setitem(profile_work.BENCH_CALLS, "matmul", lambda: 1 / 0)
    assert profile_work.bench_step("matmul", 5.0) == ("BENCH step=matmul ms=fail:ZeroDivisionError", False)


def _fake_step(step: str) -> str:
    return f"ms=1.0 seen={step}"


def _slow_step(seconds: float) -> str:
    time.sleep(seconds)
    return "ms=never"


def test_a_hung_step_lets_the_others_run_and_ends_in_bench_hung(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("torch")
    monkeypatch.setattr(profile_work, "use_work_folder_as_temp", lambda _work: None)
    calls: dict[str, Callable[[], str]] = {step: partial(_fake_step, step) for step in profile_work.BENCH_STEPS}
    calls["score_queries"] = partial(_slow_step, 2.0)
    monkeypatch.setattr(profile_work, "BENCH_CALLS", calls)
    with pytest.raises(profile_work.BenchHung):
        profile_work.torchbench(tmp_path, 0.1)
    lines = (tmp_path / profile_work.BENCH_FILE).read_text(encoding="ascii").splitlines()
    assert lines == [
        "BENCH step=start",
        "BENCH step=facts ms=1.0 seen=facts",
        "BENCH step=matmul ms=1.0 seen=matmul",
        "BENCH step=score_queries ms=timeout",
        "BENCH step=score_queries_ftz ms=1.0 seen=score_queries_ftz",
    ]


def test_the_real_torch_bench_writes_every_step(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("torch")
    monkeypatch.setattr(profile_work, "use_work_folder_as_temp", lambda _work: None)
    profile_work.torchbench(tmp_path, 120.0)
    text = (tmp_path / profile_work.BENCH_FILE).read_text(encoding="ascii")
    values = diag.bench_values(text)
    for step in ("matmul", "score_queries", "score_queries_ftz"):
        assert float(values[step]) > 0, text
    assert values["torch"].startswith("2.")
    assert values["mkldnn"] in {"ja", "nein"}
    assert values["ftz"] in {"ja", "nein"}
    assert values["aten_threads"] != "-", text
    # The torch_facts keys of the line are exactly what the facts step writes.
    facts = next(line for line in text.splitlines() if line.startswith("BENCH step=facts "))
    keys = [part.partition("=")[0] for part in facts.split()[2:]]
    assert keys == list(diag.TORCH_FACT_KEYS)


def test_detect_takes_no_thread_argument_any_more() -> None:
    # The count comes from the environment of the parent; a fifth word is a usage error before anything loads.
    assert profile_work.main(["detect", "/models", "/work", "60", "cpu"]) == 1
    assert not hasattr(profile_work, "thread_count")


def test_the_work_hands_the_env_count_to_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    torch = pytest.importorskip("torch")
    before = torch.get_num_threads()
    monkeypatch.setenv("OMP_NUM_THREADS", "1")
    try:
        profile_work.apply_threads()
        assert torch.get_num_threads() == 1
    finally:
        torch.set_num_threads(before)


def test_cpu_facts_is_one_line_with_every_key() -> None:
    line = profile_work.cpu_facts()
    assert line.startswith("FACTS torch_threads=")
    keys = [part.partition("=")[0] for part in line.split()[1:]]
    assert keys == [
        "torch_threads",
        "interop",
        "cpu_cap",
        "cpu_count",
        "affinity",
        "present",
        "possible",
        "online",
        "cpuinfo",
        "omp_num_threads",
        "omp_thread_limit",
    ]
    assert "\n" not in line


def test_readable_names_the_errno_of_a_missing_file(tmp_path: Path) -> None:
    assert profile_work._readable(str(tmp_path / "absent")) == "ENOENT"
    (tmp_path / "present").write_text("0-3\n", encoding="ascii")
    assert profile_work._readable(str(tmp_path / "present")) == "0-3"


def test_the_trace_takes_extra_lines(tmp_path: Path) -> None:
    was_enabled = faulthandler.is_enabled()
    trace = profile_work.Trace(tmp_path, 60.0)
    try:
        trace.line("EXTRACT ms=5")
    finally:
        trace.close()
        if was_enabled and sys.__stderr__ is not None:
            faulthandler.enable(file=sys.__stderr__)
    assert "EXTRACT ms=5\n" in (tmp_path / profile_work.TRACE_FILE).read_text(encoding="ascii")
