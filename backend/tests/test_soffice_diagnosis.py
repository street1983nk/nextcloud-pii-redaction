"""The helpers of the soffice diagnosis round 3 (tests/test_container_soffice.py, plan 02-16).

The container runs need LibreOffice and run only in sandbox.yml; what they
start, print and clean is decided by these helpers, which run everywhere.
Test only.
"""

import os
import sys
from pathlib import Path

import pytest

from pii_redaction_backend.sandbox import profiles
from pii_redaction_backend.workers import child, soffice
from tests import jail_layers
from tests import test_container_soffice as diag

SOURCE = Path("/work/probe.docx")
OUTDIR = Path("/work/out")
PROFILE = Path("/tmp/lo-7")  # noqa: S108 - a name only, nothing is made there


def test_every_variant_of_round_3_parses_and_labels_are_unique() -> None:
    labels = [label for label, _steps in diag.CANDIDATES]
    assert len(set(labels)) == len(labels)
    assert diag.TEMPLATE_LABEL not in labels
    assert diag.CONTROL_LABEL not in labels
    for _label, steps in diag.CANDIDATES:
        assert steps
        for step in steps:
            if step.layer.startswith("variant:"):
                assert jail_layers.parse_specs(step.layer.removeprefix("variant:")) is not None, step


def test_round_3_controls_are_the_product_and_the_grant_of_round_2() -> None:
    assert diag.CANDIDATES[0] == ("variant=seccomp", (diag.Step("variant:seccomp"),))
    assert diag.CANDIDATES[1][1] == (diag.Step("variant:seccomp,grant=/tmp:REMOVE_FILE"),)


def test_negative_no_candidate_after_the_controls_grants_an_extra_right_on_tmp() -> None:
    # Part 2 asks for a way without any right on /tmp: past the two controls
    # only the product jail, or /tmp read only with /var/tmp writable.
    for _label, steps in diag.CANDIDATES[2:]:
        for step in steps:
            spec = step.layer.removeprefix("variant:")
            assert "grant=" not in spec, step
            assert "write=/tmp" not in spec.split(","), step
            assert "fs-all" not in spec, step
            assert "no-landlock" not in spec, step
            assert step.layer == diag.PRODUCT or "seccomp" in spec.split(","), step


def test_the_profile_option_index_matches_the_product_command() -> None:
    command = soffice.command(SOURCE, OUTDIR, "7")
    assert command[diag.PROFILE_ARG_END - 1].startswith("-env:UserInstallation=")
    assert command[diag.PROFILE_ARG_END] == "--convert-to"


def test_step_command_puts_options_before_the_document_and_init_drops_it(tmp_path: Path) -> None:
    profile = tmp_path / "lo-7"
    profile.mkdir()
    product = soffice.command(SOURCE, OUTDIR, "7")
    assert diag.step_command(diag.Step(diag.PRODUCT), SOURCE, OUTDIR, "7", profile) == product
    with_env = diag.step_command(
        diag.Step(diag.PRODUCT, args=("-env:OSL_SOCKET_PATH=@ipc",)), SOURCE, OUTDIR, "7", profile
    )
    assert with_env == [*product[:7], f"-env:OSL_SOCKET_PATH={profile / 'ipc'}", *product[7:]]
    assert (profile / "ipc").is_dir()
    init = diag.step_command(diag.Step(diag.PRODUCT, init_only=True), SOURCE, OUTDIR, "7", profile)
    assert init == [*product[:7], diag.INIT_ONLY]
    assert str(SOURCE) not in init


def test_fill_keeps_plain_values_and_makes_private_folders(tmp_path: Path) -> None:
    assert diag.fill(tmp_path, "1") == "1"
    assert diag.fill(tmp_path, "-env:A=b") == "-env:A=b"
    assert diag.fill(tmp_path, "@home") == str(tmp_path / "home")
    if sys.platform != "win32":
        assert (tmp_path / "home").stat().st_mode & 0o777 == 0o700


def test_step_labels_number_only_sequences() -> None:
    assert diag.step_labels("variant=x", 1) == ["variant=x"]
    assert diag.step_labels("variant=x", 2) == ["variant=x/1", "variant=x/2"]


@pytest.mark.skipif(sys.platform == "win32", reason="posix paths: a drive colon reads as a grant separator")
def test_path_state_names_existing_and_missing_paths(tmp_path: Path) -> None:
    assert diag.path_state("env=libo-flatpak") == "-"
    assert diag.path_state("variant=warm-jailed-twice") == "-"
    assert diag.path_state(f"variant=seccomp,read={tmp_path.as_posix()}") == "ja"
    assert diag.path_state(f"variant=seccomp,write={tmp_path.as_posix()}/missing") == "nein"


def test_negative_the_product_allowlist_still_refuses_the_env_changes() -> None:
    # The candidates bypass child_env in the test; the product keeps refusing them.
    for key in ("LIBO_FLATPAK", "HOME", "XDG_CACHE_HOME"):
        with pytest.raises(ValueError, match="not allowed"):
            child.child_env({key: "1"}, profile="soffice")


def test_the_product_still_grants_no_removal_on_tmp() -> None:
    # Round 3 measures only; the soffice profile keeps socket creation as its one /tmp rule.
    assert profiles.profile_for("soffice").socket_paths == ("/tmp",)  # noqa: S108 - the rule as it stands
    assert profiles.profile_for("soffice").write_paths == ()
    assert jail_layers.landlock.SOCKET_ACCESS & jail_layers.landlock.ACCESS_FS_REMOVE_FILE == 0


@pytest.mark.skipif(sys.platform == "win32", reason="Unix sockets and uids")
@pytest.mark.parametrize("kind", diag.UNLINK_TARGETS)
def test_unlink_targets_are_own_stand_ins_and_never_the_harp_socket(tmp_path: Path, kind: str) -> None:
    like = tmp_path / "exapp.sock"
    like.write_bytes(b"")
    like.chmod(0o640)
    path, listener = diag.unlink_target(kind, tmp_path, like)
    try:
        assert path.exists()
        assert path.name != "exapp.sock"
        assert diag.UNLINK_PREFIX in path.as_posix()
        if kind == "socket-copy":
            assert listener is not None
            assert diag.describe(path).endswith(":0640:sock")
            assert diag.like_exapp(path, like) == "ja"
        else:
            assert listener is None
            assert diag.describe(path).endswith(":0600:file")
    finally:
        if listener is not None:
            listener.close()


def test_negative_an_unknown_unlink_target_or_jail_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown unlink target"):
        diag.unlink_target("exapp", tmp_path, tmp_path / "exapp.sock")
    with pytest.raises(ValueError, match="unknown jail"):
        diag.unlink_argv("bogus", tmp_path / "x")


def test_unlink_argv_runs_the_probe_bare_in_the_product_jail_and_with_the_grant(tmp_path: Path) -> None:
    target = tmp_path / "pii-unlink-probe.file"
    bare = diag.unlink_argv("none", target)
    assert bare[-2:] == ["unlink", str(target)]
    assert diag.unlink_argv("product", target)[-len(bare) :] == bare
    grant = diag.unlink_argv("grant", target)
    assert grant[3:7] == ["variant", diag.GRANT_REMOVE, "soffice", "--"]
    assert grant[-len(bare) :] == bare


def test_describe_says_absent_for_a_missing_path(tmp_path: Path) -> None:
    assert diag.describe(tmp_path / "missing") == "absent"
    assert diag.like_exapp(tmp_path / "missing", tmp_path / "missing") == "-"


def test_env_for_makes_private_folders_inside_the_profile(tmp_path: Path) -> None:
    profile = tmp_path / "lo-7"
    profile.mkdir()
    values = diag.env_for(profile, {"HOME": "@home", "GSETTINGS_BACKEND": "memory"})
    assert values == {"HOME": str(profile / "home"), "GSETTINGS_BACKEND": "memory"}
    assert (profile / "home").is_dir()
    if sys.platform != "win32":
        assert (profile / "home").stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize(
    ("name", "known"),
    [
        (".cache", True),
        (".config", True),
        ("dconf", True),
        ("OSL_PIPE_10001_SingleOfficeIPC_abc", True),
        ("lo-990101", True),
        ("lu12345.tmp", True),
        ("exapp.sock", False),
        ("pytest-of-exapp", False),
    ],
)
def test_without_baseline_only_known_names_are_cleaned(name: str, known: bool) -> None:
    assert diag.cleanable(name, None) is known


def test_with_baseline_new_hidden_entries_go_and_the_rest_stays() -> None:
    baseline = frozenset({"exapp.sock", "pytest-of-exapp", "keep", ".keep"})
    assert diag.cleanable(".new-thing", baseline) is True
    assert diag.cleanable(".keep", baseline) is False
    assert diag.cleanable("keep", baseline) is False
    # Negative: a new plain entry may belong to the server process of the same uid.
    assert diag.cleanable("new-thing", baseline) is False
    assert diag.cleanable("exapp.sock", baseline) is False
    # pytest folders never go, not even when new.
    assert diag.cleanable("pytest-of-other", baseline) is False
    # Known names go even when they were there at the start.
    assert diag.cleanable(".cache", frozenset({".cache"})) is True


def test_tmp_new_lists_new_paths_and_cuts_the_job_profile() -> None:
    root = Path("/scratch")
    before = frozenset({"/scratch/exapp.sock", "/scratch/lo-1"})
    after = before | {
        "/scratch/.cache",
        "/scratch/.cache/dconf",
        "/scratch/.cache/dconf/user",
        "/scratch/lo-1/user",
        "/scratch/lo-1/user/config",
        "/scratch/lo-1/user/config/soffice.cfg",
        "/scratch/lo-1/user/config/soffice.cfg/deep",
    }
    assert diag.tmp_new(before, after, root) == [
        "/scratch/.cache",
        "/scratch/.cache/dconf",
        "/scratch/.cache/dconf/user",
        "/scratch/lo-1/user",
        "/scratch/lo-1/user/config",
    ]
    assert diag.tmp_new(before, before, root) == []


def test_the_tmpnew_line_names_count_and_caps_the_list() -> None:
    assert diag.tmpnew_line("env=product", []) == "SOFFICE-TMPNEW env=product n=0"
    assert diag.tmpnew_line("x", ["/x/a", "/x/b"]) == "SOFFICE-TMPNEW x n=2 /x/a /x/b"
    many = [f"/x/f{i}" for i in range(diag.TMPNEW_MAX + 3)]
    line = diag.tmpnew_line("x", many)
    assert line.startswith(f"SOFFICE-TMPNEW x n={diag.TMPNEW_MAX + 3} /x/f0 ")
    assert line.endswith(" +3 more")


@pytest.mark.skipif(sys.platform == "win32", reason="uid and posix paths")
def test_clean_and_snapshot_on_a_real_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diag, "TMP", tmp_path)
    (tmp_path / "exapp.sock").write_text("", encoding="utf-8")
    (tmp_path / ".cache" / "dconf").mkdir(parents=True)
    baseline = diag._baseline()
    assert ".cache" not in baseline
    assert "exapp.sock" in baseline
    before = diag.tmp_snapshot(tmp_path)
    (tmp_path / ".fresh").mkdir()
    (tmp_path / ".fresh" / "file").write_text("x", encoding="utf-8")
    (tmp_path / "server-file").write_text("x", encoding="utf-8")
    assert diag.tmp_new(before, diag.tmp_snapshot(tmp_path), tmp_path) == [
        f"{tmp_path.as_posix()}/.fresh",
        f"{tmp_path.as_posix()}/.fresh/file",
        f"{tmp_path.as_posix()}/server-file",
    ]
    assert diag.clean_tmp(baseline) == [".fresh"]
    assert sorted(os.listdir(tmp_path)) == ["exapp.sock", "server-file"]
