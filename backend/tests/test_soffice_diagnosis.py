"""The helpers of the lasting soffice container checks (tests/test_container_soffice.py, plan 02-16).

The container runs need LibreOffice and run only in sandbox.yml; what they
print and which stand-ins they make is decided by these helpers, which run
everywhere. Test only.
"""

import os
import sys
from pathlib import Path

import pytest

from pii_redaction_backend.sandbox import profiles
from pii_redaction_backend.workers import soffice
from tests import jail_layers
from tests import test_container_soffice as diag


def test_the_layer_line_names_exit_pdf_time_and_template() -> None:
    line = diag.layer_line({"exit": 0, "signal": None, "pdf": True, "ms": 900, "template": "ok"})
    assert line == "SOFFICE-LAYER product exit=0 signal=None pdf=ja ms=900 template=ok"
    missing = diag.layer_line({"exit": "-", "signal": None, "pdf": False, "ms": 1, "template": "missing"})
    assert missing == "SOFFICE-LAYER product exit=- signal=None pdf=nein ms=1 template=missing"


@pytest.mark.skipif(sys.platform == "win32", reason="posix modes and owners")
def test_template_facts_count_and_flag_write_bits_and_self_references(tmp_path: Path) -> None:
    assert sys.platform != "win32"
    root = tmp_path / "template"
    (root / "user" / "config").mkdir(parents=True)
    (root / "user" / soffice.TEMPLATE_MARKER).write_bytes(b"<items/>")
    (root / "user" / "config" / "a.xml").write_bytes(f"<x href='file://{root}/user'/>".encode())
    facts = diag.template_facts(root)
    assert facts["dirs"] == 3
    assert facts["files"] == 2
    assert facts["mentions_path"] == "ja"
    # Everything here is writable for its owner: the gate in the container would fire.
    assert facts["writable"] == 5
    assert facts["owner"] == f"{os.getuid()}:{os.getgid()}"
    for path in (root, *root.rglob("*")):
        path.chmod(0o555 if path.is_dir() else 0o444)
    try:
        if os.geteuid() != 0:
            assert diag.template_facts(root)["writable"] == 0
    finally:
        for path in (root, *root.rglob("*")):
            path.chmod(0o700 if path.is_dir() else 0o600)
    line = diag.template_line(facts)
    assert line.startswith("TEMPLATE-FACTS dirs=3 files=2 bytes=")
    assert line.endswith(" other=0 mentions_path=ja")


def test_the_product_still_grants_no_removal_on_tmp() -> None:
    # REMOVE_FILE on /tmp was refused (UNLINK-RISK); the soffice profile keeps socket creation as its one /tmp rule.
    assert profiles.profile_for("soffice").socket_paths == ("/tmp",)  # noqa: S108 - the rule as it stands
    assert profiles.profile_for("soffice").write_paths == ()
    assert jail_layers.landlock.SOCKET_ACCESS & jail_layers.landlock.ACCESS_FS_REMOVE_FILE == 0


def test_the_unlink_check_runs_only_bare_and_in_the_product_jail() -> None:
    assert diag.UNLINK_JAILS == ("none", "product")


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
    # The grant of round 3 is gone: no child gets REMOVE_FILE on /tmp, not even in a test.
    with pytest.raises(ValueError, match="unknown jail"):
        diag.unlink_argv("grant", tmp_path / "x")


def test_unlink_argv_runs_the_probe_bare_and_in_the_product_jail(tmp_path: Path) -> None:
    target = tmp_path / "pii-unlink-probe.file"
    bare = diag.unlink_argv("none", target)
    assert bare[-2:] == ["unlink", str(target)]
    assert diag.unlink_argv("product", target)[-len(bare) :] == bare


def test_describe_says_absent_for_a_missing_path(tmp_path: Path) -> None:
    assert diag.describe(tmp_path / "missing") == "absent"
    assert diag.like_exapp(tmp_path / "missing", tmp_path / "missing") == "-"
