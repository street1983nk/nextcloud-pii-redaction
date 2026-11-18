"""The LibreOffice profile template and its copy per job (plan 02-16, owner decision 17.11.).

Sandbox run 44054386548 (amd64 and arm64): with an empty profile soffice
restarts once and the second process fails on the pipe socket of the first;
with a profile made beforehand the conversion works in the unchanged product
jail. The image build therefore makes an empty profile (Dockerfile), and the
server copies it into every job profile before the jail starts. These tests
hold the copy (fresh, separate, private, fail-closed) and that the jail did
not grow a right for it.
"""

import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree

import pytest

from pii_redaction_backend.sandbox import landlock, profiles
from pii_redaction_backend.workers import soffice

TMP = "/tmp"  # noqa: S108 - a rule value only, nothing is made there


def make_template(root: Path) -> Path:
    user = root / soffice.PROFILE_USER
    (user / "config" / "soffice.cfg").mkdir(parents=True)
    (user / soffice.TEMPLATE_MARKER).write_bytes(b'<oor:items><item oor:path="/x"/></oor:items>\n')
    (user / "config" / "soffice.cfg" / "modules.xml").write_bytes(b"<m/>")
    (user / "basic").mkdir()
    return root


def digest(root: Path) -> str:
    """One hash over the relative names and contents of every file below root."""
    hasher = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        hasher.update(path.relative_to(root).as_posix().encode())
        if path.is_file():
            hasher.update(path.read_bytes())
    return hasher.hexdigest()


@pytest.fixture
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    template = make_template(tmp_path / "template")
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    monkeypatch.setattr(soffice, "PROFILE_TEMPLATE", str(template))
    monkeypatch.setattr(soffice, "PROFILE_ROOT", str(jobs))
    return template, jobs


def test_each_job_gets_its_own_fresh_copy_and_the_template_stays_untouched(roots: tuple[Path, Path]) -> None:
    template, _jobs = roots
    before = digest(template)
    first, _ = soffice.prepare_profile("1")
    second, _ = soffice.prepare_profile("2")
    soffice.seed_profile(first)
    soffice.seed_profile(second)

    assert digest(first / "user") == digest(template / "user")
    assert digest(second / "user") == digest(template / "user")
    # A change in one copy reaches neither the other copy nor the template.
    (first / "user" / soffice.TEMPLATE_MARKER).write_bytes(b"changed by job 1")
    (first / "user" / "basic" / "new.xml").write_bytes(b"state of job 1")
    assert digest(second / "user") == digest(template / "user")
    assert digest(template) == before
    assert first != second


def test_a_leftover_of_the_same_job_id_is_gone_before_the_copy(roots: tuple[Path, Path]) -> None:
    template, jobs = roots
    stale = jobs / "lo-3" / "user"
    stale.mkdir(parents=True)
    (stale / "old-document-state.xml").write_bytes(b"from an earlier run")
    profile, _ = soffice.prepare_profile("3")
    soffice.seed_profile(profile)
    assert not (profile / "user" / "old-document-state.xml").exists()
    assert digest(profile / "user") == digest(template / "user")


@pytest.mark.skipif(sys.platform == "win32", reason="posix modes")
def test_the_copy_is_private_to_this_process(roots: tuple[Path, Path]) -> None:
    assert sys.platform != "win32"
    template, _jobs = roots
    # Read only like the image template: the copy must still be writable for LibreOffice.
    for path in sorted(template.rglob("*"), reverse=True):
        path.chmod(0o555 if path.is_dir() else 0o444)
    profile, _ = soffice.prepare_profile("4")
    try:
        soffice.seed_profile(profile)
        for path in (profile / "user", *(profile / "user").rglob("*")):
            info = path.lstat()
            assert info.st_uid == os.getuid()
            assert info.st_mode & 0o777 == (0o700 if path.is_dir() else 0o600), path
    finally:
        for path in template.rglob("*"):
            path.chmod(0o700 if path.is_dir() else 0o600)


def test_negative_a_missing_template_fails_closed(tmp_path: Path, roots: tuple[Path, Path]) -> None:
    del roots
    profile, _ = soffice.prepare_profile("5")
    with pytest.raises(soffice.ProfileTemplateMissing) as caught:
        soffice.seed_profile(profile, tmp_path / "nowhere")
    assert caught.value.reason == "missing"
    assert "nowhere" not in str(caught.value)
    assert not (profile / "user").exists()


def test_negative_a_template_without_its_marker_fails_closed(roots: tuple[Path, Path]) -> None:
    template, _jobs = roots
    (template / "user" / soffice.TEMPLATE_MARKER).unlink()
    profile, _ = soffice.prepare_profile("6")
    with pytest.raises(soffice.ProfileTemplateMissing) as caught:
        soffice.seed_profile(profile)
    assert caught.value.reason == "missing"


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need a privilege on Windows")
def test_negative_a_symlink_in_the_template_fails_closed(tmp_path: Path, roots: tuple[Path, Path]) -> None:
    template, _jobs = roots
    secret = tmp_path / "secret"
    secret.write_bytes(b"not for the child")
    (template / "user" / "basic" / "link").symlink_to(secret)
    profile, _ = soffice.prepare_profile("7")
    with pytest.raises(soffice.ProfileTemplateMissing) as caught:
        soffice.seed_profile(profile)
    assert caught.value.reason == "unsafe_entry"


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="posix modes, root reads anything")
def test_negative_an_unreadable_template_fails_closed(roots: tuple[Path, Path]) -> None:
    template, _jobs = roots
    (template / "user").chmod(0o000)
    try:
        profile, _ = soffice.prepare_profile("8")
        with pytest.raises(soffice.ProfileTemplateMissing) as caught:
            soffice.seed_profile(profile)
        assert caught.value.reason == "unreadable"
    finally:
        (template / "user").chmod(0o700)


async def test_convert_stops_before_soffice_when_the_template_is_missing(
    tmp_path: Path, roots: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _template, jobs = roots
    monkeypatch.setattr(soffice, "PROFILE_TEMPLATE", str(tmp_path / "nowhere"))
    started: list[list[str]] = []

    async def fake_run_child(args: list[str], **_kwargs: object) -> None:
        started.append(args)

    monkeypatch.setattr(soffice, "run_child", fake_run_child)
    with pytest.raises(soffice.ProfileTemplateMissing):
        await soffice.convert(tmp_path / "in.docx", tmp_path / "out", "9")
    # No init run as a fallback: soffice never starts, and the job profile is gone.
    assert started == []
    assert not (jobs / "lo-9").exists()


def test_the_template_error_is_a_conversion_failure() -> None:
    # The runner catches ConversionFailed and fails the job as render_failed.
    assert issubclass(soffice.ProfileTemplateMissing, soffice.ConversionFailed)


# -- the jail did not grow a right for the template -----------------------------------------


def jail_findings(profile: profiles.Profile) -> list[str]:
    """What the soffice jail must not have: a rule for the template, a write or removal right on /tmp."""
    findings: list[str] = []
    template = soffice.PROFILE_TEMPLATE
    for path in (*profile.read_paths, *profile.write_paths, *profile.socket_paths):
        if template == path or (template.startswith(f"{path.rstrip('/')}/") and path not in profiles.SYSTEM_READ):
            findings.append(f"template reachable through {path}")
    if TMP in profile.write_paths or any(path.startswith(f"{TMP}/") for path in profile.write_paths):
        findings.append("write rule on /tmp")
    if profile.socket_paths != (TMP,):
        findings.append(f"socket rule changed: {profile.socket_paths}")
    if landlock.SOCKET_ACCESS & landlock.ACCESS_FS_REMOVE_FILE:
        findings.append("REMOVE_FILE in the socket rule")
    if not profile.deny_connect:
        findings.append("connect() open")
    return findings


def test_the_soffice_jail_is_unchanged_by_the_template() -> None:
    soffice_profile = profiles.profile_for("soffice")
    assert jail_findings(soffice_profile) == []
    assert soffice_profile.write_paths == ()
    assert soffice_profile.read_paths == profiles.SOFFICE_READ
    assert "/opt" not in profiles.SYSTEM_READ


def test_negative_the_jail_rule_fires_on_each_forbidden_right() -> None:
    base = profiles.profile_for("soffice")
    with_template = replace(base, read_paths=(*base.read_paths, soffice.PROFILE_TEMPLATE))
    assert jail_findings(with_template) == [f"template reachable through {soffice.PROFILE_TEMPLATE}"]
    with_opt = replace(base, read_paths=(*base.read_paths, "/opt"))
    assert jail_findings(with_opt) == ["template reachable through /opt"]
    assert jail_findings(replace(base, write_paths=(TMP,))) == ["write rule on /tmp"]
    assert jail_findings(replace(base, socket_paths=())) == ["socket rule changed: ()"]
    assert jail_findings(replace(base, deny_connect=False)) == ["connect() open"]


def test_the_child_environment_still_holds_only_tmpdir(roots: tuple[Path, Path]) -> None:
    del roots
    _profile, env = soffice.prepare_profile("10")
    assert set(env) == {"TMPDIR"}


# -- the hardening of the job profile (plan 02-17, SAFE-03, D-02-06) ------------------------
#
# The table is RESEARCH Pattern 5 (LibreOffice core, branch libreoffice-25-2,
# Common.xcs and Writer.xcs), written down here on its own and never read from
# soffice.py. The file is read with xml.etree, the server merges with lxml.

OOR = "http://openoffice.org/2001/registry"
SCRIPTING = "/org.openoffice.Office.Common/Security/Scripting"
UPDATE = "/org.openoffice.Office.Writer/Content/Update"
UPDATE_CHECK = "/org.openoffice.Office.Jobs/Jobs/org.openoffice.Office.Jobs:Job['UpdateCheck']/Arguments"
HARDENING: dict[tuple[str, str], str] = {
    (SCRIPTING, "DisableMacrosExecution"): "true",
    (SCRIPTING, "MacroSecurityLevel"): "3",
    (SCRIPTING, "BlockUntrustedRefererLinks"): "true",
    (SCRIPTING, "DisableActiveContent"): "true",
    (SCRIPTING, "DisablePythonRuntime"): "true",
    (SCRIPTING, "DisableOLEAutomation"): "true",
    (SCRIPTING, "CheckDocumentEvents"): "true",
    (SCRIPTING, "AllowedDocumentEventURLs"): "",
    ("/org.openoffice.Office.Common/Security", "LoadExoticFileFormats"): "0",
    (UPDATE, "Link"): "2",
    (UPDATE, "Field"): "false",
    (UPDATE_CHECK, "AutoCheckEnabled"): "false",
}
HARDENING_FILE = Path(soffice.__file__).parent / "lo_profile" / "registrymodifications.xcu"
WHEEL_NAME = "pii_redaction_backend/workers/lo_profile/registrymodifications.xcu"
# What LibreOffice 25.2 writes on its first start, shortened: the namespaces and
# the item that marks a finished user installation (TEMPLATE-RESTART setup_completed=ja).
LO_TEMPLATE = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema"'
    b' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
    b'<item oor:path="/org.openoffice.Setup/Office"><prop oor:name="ooSetupInstCompleted" oor:op="fuse">'
    b"<value>true</value></prop></item>\n"
    b"</oor:items>\n"
)
Entry = tuple[str, str, str, str | None]


def entries(data: bytes) -> list[Entry]:
    """(path, property, value, op) of every property of every item, read with xml.etree."""
    root = ElementTree.fromstring(data)  # noqa: S314 - our own package file or a test sample
    assert root.tag == f"{{{OOR}}}items"
    found: list[Entry] = []
    for item in root:
        assert item.tag == "item"
        path = item.get(f"{{{OOR}}}path", "")
        for prop in item:
            assert prop.tag == "prop"
            values = prop.findall("value")
            assert len(values) == 1
            found.append((path, prop.get(f"{{{OOR}}}name", ""), values[0].text or "", prop.get(f"{{{OOR}}}op")))
    return found


def test_the_hardening_file_holds_exactly_the_pattern_5_keys() -> None:
    found = entries(HARDENING_FILE.read_bytes())
    keys = [(path, name) for path, name, _value, _op in found]
    assert sorted(keys) == sorted(HARDENING), "every key exactly once, nothing else"
    assert len(keys) == len(set(keys))
    for path, name, value, op in found:
        assert value == HARDENING[path, name], name
        assert op == "fuse", name


def test_negative_the_key_check_sees_a_changed_value() -> None:
    data = HARDENING_FILE.read_bytes()
    weaker = data.replace(b"<value>3</value>", b"<value>2</value>", 1)
    assert weaker != data
    assert (SCRIPTING, "MacroSecurityLevel", "2", "fuse") in entries(weaker)


def test_the_seven_security_names_stand_in_the_file() -> None:
    text = HARDENING_FILE.read_text(encoding="utf-8")
    names = (
        "DisableMacrosExecution",
        "MacroSecurityLevel",
        "BlockUntrustedRefererLinks",
        "DisableActiveContent",
        "DisablePythonRuntime",
        "DisableOLEAutomation",
        "LoadExoticFileFormats",
    )
    assert len([line for line in text.splitlines() if any(name in line for name in names)]) == len(names)


@pytest.fixture
def lo_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    template = tmp_path / "template"
    (template / soffice.PROFILE_USER / "extensions").mkdir(parents=True)
    (template / soffice.PROFILE_USER / soffice.TEMPLATE_MARKER).write_bytes(LO_TEMPLATE)
    (template / soffice.PROFILE_USER / "extensions" / "buildid").write_bytes(b"[Build]\nbuildid=x\n")
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    monkeypatch.setattr(soffice, "PROFILE_TEMPLATE", str(template))
    monkeypatch.setattr(soffice, "PROFILE_ROOT", str(jobs))
    return template, jobs


def _fake_soffice(seen: list[dict[str, object]]) -> Callable[..., Awaitable[None]]:
    async def fake_run_child(args: list[str], **kwargs: object) -> None:
        write = kwargs["write"]
        assert isinstance(write, tuple)
        outdir, profile = Path(str(write[0])), Path(str(write[1]))
        xcu = profile / soffice.PROFILE_USER / soffice.TEMPLATE_MARKER
        seen.append(
            {
                "args": args,
                "profile": profile,
                "data": xcu.read_bytes() if xcu.is_file() else None,
                "mode": xcu.stat().st_mode & 0o777 if xcu.is_file() else None,
                "buildid": (profile / soffice.PROFILE_USER / "extensions" / "buildid").is_file(),
            }
        )
        (outdir / "in.pdf").write_bytes(b"%PDF-1.7\n")

    return fake_run_child


async def test_convert_hardens_the_job_profile_before_soffice_starts(
    tmp_path: Path, lo_roots: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    template, jobs = lo_roots
    seen: list[dict[str, object]] = []
    monkeypatch.setattr(soffice, "run_child", _fake_soffice(seen))

    await soffice.convert(tmp_path / "in.docx", tmp_path / "out", "11")

    assert len(seen) == 1
    data = seen[0]["data"]
    assert isinstance(data, bytes), "registrymodifications.xcu must be in place before the start"
    found = {(path, name): value for path, name, value, _op in entries(data)}
    for key, value in HARDENING.items():
        assert found.get(key) == value, key
    # The item LibreOffice wrote into the template stays: without it the start
    # counts as a new user installation (userinstall::create, plan 02-16 R1).
    assert found["/org.openoffice.Setup/Office", "ooSetupInstCompleted"] == "true"
    assert len(entries(data)) == len(HARDENING) + 1, "each key exactly once"
    # The items arrive byte for byte as the package file has them.
    for line in HARDENING_FILE.read_bytes().splitlines():
        if line.strip().startswith(b"<item "):
            assert line.strip() in data
    assert seen[0]["buildid"] is True
    if sys.platform != "win32":
        assert seen[0]["mode"] == 0o600
    # The profile is gone after the run, the template is unchanged.
    assert not (jobs / "lo-11").exists()
    assert (template / soffice.PROFILE_USER / soffice.TEMPLATE_MARKER).read_bytes() == LO_TEMPLATE


async def test_the_profile_is_gone_after_a_failed_run_too(
    tmp_path: Path, lo_roots: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _template, jobs = lo_roots
    started: list[bool] = []

    async def failing(_args: list[str], **_kwargs: object) -> None:
        started.append((jobs / "lo-12" / soffice.PROFILE_USER / soffice.TEMPLATE_MARKER).is_file())
        raise RuntimeError

    monkeypatch.setattr(soffice, "run_child", failing)
    with pytest.raises(RuntimeError):
        await soffice.convert(tmp_path / "in.docx", tmp_path / "out", "12")
    assert started == [True]
    assert not (jobs / "lo-12").exists()


async def test_two_jobs_use_two_profiles(
    tmp_path: Path, lo_roots: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _template, jobs = lo_roots
    seen: list[dict[str, object]] = []
    monkeypatch.setattr(soffice, "run_child", _fake_soffice(seen))

    await soffice.convert(tmp_path / "a.docx", tmp_path / "out-a", "21")
    await soffice.convert(tmp_path / "b.docx", tmp_path / "out-b", "22")

    assert [entry["profile"] for entry in seen] == [jobs / "lo-21", jobs / "lo-22"]
    assert seen[0]["data"] == seen[1]["data"]
    assert list(jobs.iterdir()) == []


@pytest.mark.parametrize("job_id", ["", "../1", "1/2", "1 ", "x1", chr(0x0661)])
async def test_an_invalid_job_id_stops_before_any_file_is_touched(
    tmp_path: Path, lo_roots: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, job_id: str
) -> None:
    _template, jobs = lo_roots
    seen: list[dict[str, object]] = []
    monkeypatch.setattr(soffice, "run_child", _fake_soffice(seen))
    with pytest.raises(ValueError, match="digits"):
        await soffice.convert(tmp_path / "in.docx", tmp_path / "out", job_id)
    assert seen == []
    assert not (tmp_path / "out").exists()
    assert list(jobs.iterdir()) == []


async def test_negative_a_template_that_already_sets_a_hardening_key_fails_closed(
    tmp_path: Path, lo_roots: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    template, jobs = lo_roots
    weak = LO_TEMPLATE.replace(
        b"</oor:items>",
        b'<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
        b'<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>0</value></prop></item>\n</oor:items>',
    )
    (template / soffice.PROFILE_USER / soffice.TEMPLATE_MARKER).write_bytes(weak)
    seen: list[dict[str, object]] = []
    monkeypatch.setattr(soffice, "run_child", _fake_soffice(seen))
    with pytest.raises(soffice.ProfileTemplateMissing) as caught:
        await soffice.convert(tmp_path / "in.docx", tmp_path / "out", "13")
    assert caught.value.reason == "conflict"
    assert seen == []
    assert not (jobs / "lo-13").exists()


@pytest.mark.parametrize(
    "broken",
    [
        b"not xml at all",
        b"<oor:items/>",
        b"<items><item/></items>",
        (
            b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e "x">]>'
            b'<oor:items xmlns:oor="http://openoffice.org/2001/registry"></oor:items>'
        ),
    ],
)
async def test_negative_a_template_file_that_is_not_a_registry_fails_closed(
    tmp_path: Path, lo_roots: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, broken: bytes
) -> None:
    template, jobs = lo_roots
    (template / soffice.PROFILE_USER / soffice.TEMPLATE_MARKER).write_bytes(broken)
    seen: list[dict[str, object]] = []
    monkeypatch.setattr(soffice, "run_child", _fake_soffice(seen))
    with pytest.raises(soffice.ProfileTemplateMissing) as caught:
        await soffice.convert(tmp_path / "in.docx", tmp_path / "out", "14")
    assert caught.value.reason == "malformed"
    assert seen == []
    assert not (jobs / "lo-14").exists()


def test_slow_the_wheel_carries_the_hardening_file(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None, "uv builds the wheel in python.yml and locally"
    backend = Path(__file__).resolve().parents[1]
    subprocess.run(  # noqa: S603 - fixed arguments, uv from PATH
        [uv, "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=backend,
        check=True,
        capture_output=True,
        timeout=300,
    )
    wheels = sorted(tmp_path.glob("pii_redaction_backend-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        assert wheel.read(WHEEL_NAME) == HARDENING_FILE.read_bytes()
