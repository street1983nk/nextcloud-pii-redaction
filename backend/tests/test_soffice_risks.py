"""The helpers of the risk checks R1 and R2 of the profile template (plan 02-16, owner 17.11.).

The container runs (tests/test_container_soffice.py) need LibreOffice and run
only in sandbox.yml; what they count, print and run is decided by these
helpers, which run everywhere. Test only.
"""

import os
import sys
import time
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest

from pii_redaction_backend.sandbox import jail, profiles
from pii_redaction_backend.workers import soffice
from tests import jail_layers, profile_work
from tests import test_container_soffice as diag

# -- R1: the start counter ------------------------------------------------------------------


def stat_line(pid: int, name: str, start: int, ppid: int = 1) -> str:
    # Fields from 3 on: state, ppid (field 4), 17 more, then field 22, the start time.
    rest = " ".join(["S", str(ppid), *[str(n) for n in range(17)], str(start), "0"])
    return f"{pid} ({name}) {rest}\n"


def fake_process(proc: Path, pid: int, name: str, start: int, ppid: int = 1) -> None:
    folder = proc / str(pid)
    folder.mkdir(parents=True)
    (folder / "stat").write_text(stat_line(pid, name, start, ppid), encoding="ascii")


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
    call = jail.parse(["render", "--read", "/x", "--", "/usr/bin/true"])
    assert call is not None
    changed = jail_layers.with_deny_connect(call)
    assert changed.profile.deny_connect is True
    assert replace(changed.profile, deny_connect=False) == call.profile
    assert (changed.read, changed.write, changed.command) == (call.read, call.write, call.command)
    # The product profiles stay as they are: render keeps connect(), soffice does not.
    assert profiles.profile_for("render").deny_connect is False
    assert profiles.profile_for("soffice").deny_connect is True


@pytest.mark.parametrize("profile", ["render", "precheck", "sanitize", "ocr", "detect"])
def test_the_deny_connect_jail_installs_seccomp_with_deny_connect(profile: str) -> None:
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
    # Negative control: the product jail of the same profile hands on False.
    calls.clear()
    call = jail.parse([profile, "--", "/usr/bin/true"])
    assert call is not None
    jail.run(call, ops)
    assert "seccomp False" in calls


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


def test_with_models_and_tesseract_detect_and_ocr_are_work(tmp_path: Path) -> None:
    (tmp_path / "gliner2").mkdir()
    works = diag.profile_works(
        tmp_path / "a.pdf", tmp_path / "a.docx", tmp_path / "a.png", tmp_path, "/usr/bin/tesseract"
    )
    ocr = next(work for work in works if isinstance(work, diag.Work) and work.profile == "ocr")
    assert ocr.argv(tmp_path / "out") == ["/usr/bin/tesseract", str(tmp_path / "a.png"), f"{tmp_path / 'out'}/text"]
    detect = next(work for work in works if isinstance(work, diag.Work) and work.profile == "detect")
    assert detect.argv(tmp_path)[-2:] == ["detect", str(tmp_path)]
    assert detect.read == (str(tmp_path),)


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
