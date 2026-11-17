"""The test-only partial and variant jail of the soffice diagnosis (tests/jail_layers.py, plan 02-16).

It must switch off exactly the layers above the one named, or change exactly
the one rule a variant names, and keep the code of the product for the rest,
or the diagnosis would measure something else.
"""

import errno
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from pii_redaction_backend.sandbox import jail, landlock, seccomp
from tests import jail_layers
from tests.test_landlock import FakeKernel

ON_LINUX = sys.platform.startswith("linux")


def test_limits_switches_off_landlock_and_seccomp_only() -> None:
    ops = jail_layers.layered_ops("limits")
    product = jail.system_ops()
    assert ops.landlock_abi() == 0
    assert ops.seccomp_available() is False
    assert (ops.setrlimit, ops.prctl, ops.execv) == (product.setrlimit, product.prctl, product.execv)


def test_landlock_switches_off_seccomp_only() -> None:
    ops = jail_layers.layered_ops("landlock")
    product = jail.system_ops()
    assert ops.landlock_abi is product.landlock_abi
    assert ops.landlock_restrict is product.landlock_restrict
    assert ops.seccomp_available() is False


def test_an_unknown_layer_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown layer"):
        jail_layers.layered_ops("seccomp")
    assert jail_layers.main(["layers", "seccomp", "soffice", "--", "/usr/bin/soffice"]) == jail.EXIT_USAGE
    assert jail_layers.main(["layers", "limits", "nonsense"]) == jail.EXIT_USAGE
    assert jail_layers.main([]) == jail.EXIT_USAGE


def test_the_partial_jail_applies_its_layers_in_product_order() -> None:
    calls: list[str] = []
    base = jail_layers.layered_ops("landlock")
    ops = replace(
        base,
        setrlimit=lambda name, _value: calls.append(name),
        prctl=lambda _option, _value: calls.append("prctl"),
        landlock_abi=lambda: 6,
        landlock_restrict=lambda *_paths: calls.append("landlock"),
        execv=lambda path, _args: calls.append(f"exec {path}"),
    )
    call = jail.parse(["soffice", "--", "/usr/bin/soffice"])
    assert call is not None
    assert jail.run(call, ops) == jail.EXIT_LAYER_FAILED  # a fake execv returns
    assert calls[-3:] == ["prctl", "landlock", "exec /usr/bin/soffice"]
    assert "seccomp" not in calls


# -- variants: one change against the product rules, test only (plan 02-16) -----------------


class RecordingKernel(FakeKernel):
    """FakeKernel that also keeps the flags of landlock_restrict_self."""

    def __init__(self, ruleset_fd_path: Path, *, abi: int) -> None:
        super().__init__(ruleset_fd_path, abi=abi)
        self.restrict_flags: list[int] = []

    def __call__(self, number: int, *args: object) -> int:
        if number == landlock.SYS_RESTRICT_SELF:
            self.restrict_flags.append(int(args[1]))  # type: ignore[arg-type]
        return super().__call__(number, *args)


@pytest.fixture
def fd_file(tmp_path: Path) -> Path:
    path = tmp_path / "ruleset"
    path.write_bytes(b"")
    return path


@pytest.mark.parametrize(
    "text",
    [
        "refer",
        "read=/proc",
        "write=/dev/null,refer",
        "fs-all,net-off,scope-off",
        "no-landlock,seccomp,deny-connect",
        "grant=/tmp:MAKE_DIR",
        "grant=/tmp:READ+MAKE_DIR+MAKE_REG+WRITE_FILE",
    ],
)
def test_known_specs_parse(text: str) -> None:
    assert jail_layers.parse_specs(text) == tuple(text.split(","))


@pytest.mark.parametrize(
    "text",
    [
        "",
        ",",
        "bogus",
        "read=proc",
        "exec=/usr",
        "read",
        "refer,unknown",
        "nosock=/tmp",
        "grant=/tmp",
        "grant=/tmp:",
        "grant=tmp:MAKE_DIR",
        "grant=/tmp:MAKE_DIR+",
        "grant=/tmp:make_dir",
        "grant=/tmp:IOCTL_DEV",
    ],
)
def test_negative_unknown_or_malformed_specs_are_refused(text: str) -> None:
    assert jail_layers.parse_specs(text) is None
    assert jail_layers.main(["variant", text, "soffice", "--", "/usr/bin/soffice"]) == jail.EXIT_USAGE


def test_without_a_change_the_variant_ruleset_is_the_product_ruleset(fd_file: Path) -> None:
    product, variant = FakeKernel(fd_file, abi=6), FakeKernel(fd_file, abi=6)
    landlock.restrict((), (), product)
    jail_layers.restrict_variant(("seccomp",), (), (), (), variant)
    assert variant.created == product.created
    assert variant.rules == product.rules


@pytest.mark.parametrize(
    ("spec", "net", "scoped"),
    [
        ("net-off", 0, landlock.SCOPE_ABSTRACT_UNIX_SOCKET | landlock.SCOPE_SIGNAL),
        ("scope-off", landlock.ACCESS_NET_BIND_TCP | landlock.ACCESS_NET_CONNECT_TCP, 0),
    ],
)
def test_net_off_and_scope_off_drop_exactly_their_class(fd_file: Path, spec: str, net: int, scoped: int) -> None:
    kernel = FakeKernel(fd_file, abi=6)
    jail_layers.restrict_variant((spec,), (), (), (), kernel)
    fs, handled_net, handled_scoped, _size = kernel.created[0]
    assert (fs, handled_net, handled_scoped) == (landlock.handled_access(6).fs, net, scoped)


def test_audit_needs_abi_7_and_then_logs_after_the_exec(fd_file: Path) -> None:
    old = RecordingKernel(fd_file, abi=6)
    with pytest.raises(OSError, match="needs ABI 7"):
        jail_layers.restrict_variant(("audit",), (), (), (), old)
    assert old.created == []
    new = RecordingKernel(fd_file, abi=7)
    jail_layers.restrict_variant(("audit",), (), (), (), new)
    assert new.restrict_flags == [jail_layers.RESTRICT_SELF_LOG_NEW_EXEC_ON]
    plain = RecordingKernel(fd_file, abi=7)
    jail_layers.restrict_variant(("net-off",), (), (), (), plain)
    assert plain.restrict_flags == [0]


@pytest.mark.skipif(not ON_LINUX, reason="O_PATH needs Linux")
def test_each_rule_change_touches_only_its_rule(tmp_path: Path, fd_file: Path) -> None:
    read, write, sockets, extra = (tmp_path / name for name in ("read", "write", "sock", "extra"))
    for folder in (read, write, sockets, extra):
        folder.mkdir()
    paths = ((str(read),), (str(write),), (str(sockets),))
    handled = landlock.handled_access(6).fs
    read_rights = landlock.READ_ACCESS & handled
    write_rights = landlock.WRITE_ACCESS & handled

    def rights(*specs: str) -> list[int]:
        kernel = FakeKernel(fd_file, abi=6)
        jail_layers.restrict_variant(specs, *paths, kernel)
        return [allowed for allowed, _fd in kernel.rules]

    assert rights() == [read_rights, write_rights, landlock.SOCKET_ACCESS]
    assert rights("refer") == [read_rights, write_rights | landlock.ACCESS_FS_REFER, landlock.SOCKET_ACCESS]
    assert rights("ioctl") == [read_rights | landlock.ACCESS_FS_IOCTL_DEV, write_rights, landlock.SOCKET_ACCESS]
    assert rights("nosock") == [read_rights, write_rights]
    assert rights(f"read={extra}") == [read_rights, read_rights, write_rights, landlock.SOCKET_ACCESS]
    assert rights(f"write={extra}") == [read_rights, write_rights, write_rights, landlock.SOCKET_ACCESS]
    assert rights("fs-all") == [read_rights, write_rights, landlock.SOCKET_ACCESS, handled]
    make = landlock.ACCESS_FS_MAKE_DIR
    assert rights(f"grant={extra}:MAKE_DIR") == [read_rights, write_rights, landlock.SOCKET_ACCESS, make]
    trio = make | landlock.ACCESS_FS_MAKE_REG | landlock.ACCESS_FS_WRITE_FILE
    assert rights(f"grant={extra}:MAKE_DIR+MAKE_REG+WRITE_FILE")[-1] == trio
    assert rights(f"grant={extra}:READ+TRUNCATE")[-1] == landlock.READ_ACCESS | landlock.ACCESS_FS_TRUNCATE
    # A missing path is skipped, like in the product.
    assert rights(f"read={tmp_path / 'missing'}") == rights()


class FakeSeccompLib:
    """libseccomp stand-in for the deny-connect filter."""

    def __init__(self) -> None:
        self.rules: list[tuple[int, int, int]] = []
        self.loaded = 0

    def seccomp_init(self, _action: int) -> int:
        return 0xC0FFEE

    def seccomp_release(self, _context: int) -> None:
        return None

    def seccomp_syscall_resolve_name(self, name: bytes) -> int:
        return {b"connect": 42}.get(name, -1)

    def seccomp_rule_add_exact_array(self, _context: int, action: int, number: int, count: int, _cond: object) -> int:
        self.rules.append((action, number, count))
        return 0

    def seccomp_load(self, _context: int) -> int:
        self.loaded += 1
        return 0


def test_deny_connect_refuses_connect_with_eacces_for_every_family(monkeypatch: pytest.MonkeyPatch) -> None:
    lib = FakeSeccompLib()
    product: list[str] = []
    monkeypatch.setattr(seccomp, "_load", lambda: lib)
    monkeypatch.setattr(
        seccomp, "install_network_denylist", lambda *, deny_connect: product.append(f"product {deny_connect}")
    )

    jail_layers.install_variant_filters(("deny-connect",))
    assert lib.rules == [(seccomp.errno_action(errno.EACCES), 42, 0)]
    assert lib.loaded == 1
    assert product == []

    jail_layers.install_variant_filters(("seccomp", "deny-connect"))
    assert product == ["product False"]
    # "seccomp" is the product filter as the profile has it: soffice hands deny_connect on.
    jail_layers.install_variant_filters(("seccomp",), True)
    assert product == ["product False", "product True"]


def test_variant_ops_switch_the_layers_the_specs_name() -> None:
    plain = jail_layers.variant_ops(("refer",))
    assert plain.landlock_abi is jail.system_ops().landlock_abi
    assert plain.seccomp_available() is False
    assert jail_layers.variant_ops(("no-landlock",)).landlock_abi() == 0
    assert jail_layers.variant_ops(("deny-connect",)).seccomp_available() is True
    assert jail_layers.variant_ops(("seccomp",)).seccomp_available() is True


def test_a_variant_runs_in_product_order() -> None:
    calls: list[str] = []
    ops = replace(
        jail_layers.variant_ops(("refer", "deny-connect")),
        setrlimit=lambda name, _value: calls.append(name),
        prctl=lambda _option, _value: calls.append("prctl"),
        landlock_abi=lambda: 6,
        landlock_restrict=lambda *_paths: calls.append("landlock"),
        seccomp_install=lambda deny: calls.append(f"seccomp {deny}"),
        execv=lambda path, _args: calls.append(f"exec {path}"),
    )
    call = jail.parse(["soffice", "--", "/usr/bin/soffice"])
    assert call is not None
    assert jail.run(call, ops) == jail.EXIT_LAYER_FAILED  # a fake execv returns
    assert calls[-4:] == ["prctl", "landlock", "seccomp True", "exec /usr/bin/soffice"]


def test_each_grant_right_is_one_landlock_right_and_read_is_the_product_read_set() -> None:
    singles = {name: bits for name, bits in jail_layers.GRANT_RIGHTS.items() if name != "READ"}
    assert all(bits and not bits & (bits - 1) for bits in singles.values())
    assert len(set(singles.values())) == len(singles)
    assert jail_layers.GRANT_RIGHTS["READ"] == landlock.READ_ACCESS
    # write=P is exactly the sum of its single rights, so the split covers it.
    write_names = ("READ", "WRITE_FILE", "TRUNCATE", "MAKE_DIR", "MAKE_REG", "MAKE_SOCK", "MAKE_FIFO", "MAKE_SYM")
    removal = ("REMOVE_FILE", "REMOVE_DIR")
    total = 0
    for name in (*write_names, *removal):
        total |= jail_layers.GRANT_RIGHTS[name]
    assert total == landlock.WRITE_ACCESS


def test_parse_grant_names_path_and_rights() -> None:
    assert jail_layers.parse_grant("/srv/data:MAKE_DIR+MAKE_REG") == (
        "/srv/data",
        landlock.ACCESS_FS_MAKE_DIR | landlock.ACCESS_FS_MAKE_REG,
    )
    assert jail_layers.parse_grant("/srv/data") is None
    assert jail_layers.parse_grant("/srv/data:NOPE") is None


def test_unlink_removes_and_answers_ok_absent_or_the_errno(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "pii-unlink-probe.file"
    target.write_bytes(b"x")
    assert jail_layers.main(["unlink", str(target)]) == 0
    assert not target.exists()
    assert jail_layers.main(["unlink", str(target)]) == 3
    assert capsys.readouterr().out.split() == ["ok", "absent"]

    def refuse(_path: str) -> None:
        raise PermissionError(errno.EACCES, "Landlock")

    monkeypatch.setattr(jail_layers.os, "unlink", refuse)
    assert jail_layers.main(["unlink", str(target)]) == 1
    assert capsys.readouterr().out.strip() == "EACCES"


@pytest.mark.skipif(not ON_LINUX, reason="libc access(2)")
def test_access_asks_libc_and_names_the_errno(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert jail_layers.main(["access", str(tmp_path)]) == 0
    assert jail_layers.main(["access", str(tmp_path / "missing")]) == 1
    assert capsys.readouterr().out.split() == ["ok", "ENOENT"]


def test_negative_unlink_and_access_take_exactly_one_path() -> None:
    assert jail_layers.main(["unlink"]) == jail.EXIT_USAGE
    assert jail_layers.main(["access", "/a", "/b"]) == jail.EXIT_USAGE
