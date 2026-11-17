"""The helpers of the soffice diagnosis round 2 (tests/test_container_soffice.py, plan 02-16).

The container runs need LibreOffice and run only in sandbox.yml; what they
print and clean is decided by these helpers, which run everywhere. Test only.
"""

import os
import sys
from pathlib import Path

import pytest

from pii_redaction_backend.workers import child
from tests import jail_layers
from tests import test_container_soffice as diag


def test_every_landlock_variant_of_round_2_parses() -> None:
    for spec in diag.LANDLOCK_VARIANTS:
        assert jail_layers.parse_specs(spec) is not None, spec
    assert len(set(diag.LANDLOCK_VARIANTS)) == len(diag.LANDLOCK_VARIANTS)


def test_write_tmp_is_split_into_single_rights_and_leave_one_out() -> None:
    grants = [spec.removeprefix(diag.GRANT) for spec in diag.LANDLOCK_VARIANTS if spec.startswith(diag.GRANT)]
    for right in ("MAKE_DIR", "MAKE_REG", "WRITE_FILE", "TRUNCATE", "REMOVE_FILE", "REMOVE_DIR", "MAKE_SOCK"):
        assert right in grants
    assert "MAKE_DIR+MAKE_REG+WRITE_FILE" in grants
    # Leave-one-out: write=/tmp without exactly one right, for every right of write=/tmp.
    full = set(diag.WRITE_RIGHTS)
    left_out = {
        next(iter(full - set(grant.split("+")))) for grant in grants if len(set(grant.split("+"))) == len(full) - 1
    }
    assert left_out == full
    # The split together is write=/tmp.
    total = 0
    for name in diag.WRITE_RIGHTS:
        total |= jail_layers.GRANT_RIGHTS[name]
    assert total == jail_layers.landlock.WRITE_ACCESS
    # The controls: the driver without Landlock first, write=/tmp last.
    assert diag.LANDLOCK_VARIANTS[0] == "no-landlock"
    assert diag.LANDLOCK_VARIANTS[-1] == "write=/tmp"


def test_the_env_variants_change_only_home_xdg_and_dconf() -> None:
    allowed = {"HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR", "GSETTINGS_BACKEND", "DCONF_PROFILE"}
    names = [name for name, _changes in diag.ENV_VARIANTS]
    assert names[0] == "product"
    assert diag.ENV_VARIANTS[0][1] == {}
    for _name, changes in diag.ENV_VARIANTS:
        assert set(changes) <= allowed
        # A folder value always lies inside the job profile ("@name").
        for key in ("HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR"):
            if key in changes:
                assert changes[key].startswith("@"), (key, changes)
    assert len(set(names)) == len(names)


def test_negative_the_product_allowlist_still_refuses_the_env_variants() -> None:
    # The variants bypass child_env in the test; the product keeps refusing them.
    for key in ("HOME", "XDG_CACHE_HOME", "GSETTINGS_BACKEND", "DCONF_PROFILE"):
        with pytest.raises(ValueError, match="not allowed"):
            child.child_env({key: "/srv/lo-1/home"}, profile="soffice")


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
