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
import sys
from dataclasses import replace
from pathlib import Path

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
