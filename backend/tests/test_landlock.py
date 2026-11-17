"""The Landlock layer: ABI probe, handled rights per ABI, fail closed, and on Linux the real effect."""

import ctypes
import errno
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pii_redaction_backend.sandbox import landlock
from pii_redaction_backend.sandbox.landlock import (
    ACCESS_FS_IOCTL_DEV,
    ACCESS_FS_READ_DIR,
    ACCESS_FS_REFER,
    ACCESS_FS_TRUNCATE,
    ACCESS_NET_BIND_TCP,
    ACCESS_NET_CONNECT_TCP,
    FILE_ACCESS,
    READ_ACCESS,
    SCOPE_ABSTRACT_UNIX_SOCKET,
    SCOPE_SIGNAL,
    SYS_ADD_RULE,
    SYS_CREATE_RULESET,
    SYS_RESTRICT_SELF,
    RulesetAttr,
    abi_version,
    handled_access,
    restrict,
)

ON_LINUX = sys.platform.startswith("linux")
FS_ABI_1 = (1 << 13) - 1


class FakeKernel:
    """The three Landlock calls; the ruleset fd is a real file so close() is safe."""

    def __init__(self, ruleset_fd_path: Path, *, abi: int = 4, add_rule: int = 0, restrict_self: int = 0) -> None:
        self.abi = abi
        self.add_rule_result = add_rule
        self.restrict_result = restrict_self
        self.ruleset_fd_path = ruleset_fd_path
        self.ruleset_fd = -1
        self.created: list[tuple[int, int, int, int]] = []
        self.rules: list[tuple[int, int]] = []
        self.calls: list[int] = []

    def __call__(self, number: int, *args: object) -> int:
        self.calls.append(number)
        if number == SYS_CREATE_RULESET and args[0] is None:
            return self.abi if self.abi > 0 else -errno.ENOSYS
        if number == SYS_CREATE_RULESET:
            attr = args[0].contents  # type: ignore[attr-defined]
            self.created.append((attr.handled_access_fs, attr.handled_access_net, attr.scoped, int(args[1])))  # type: ignore[arg-type]
            self.ruleset_fd = os.open(self.ruleset_fd_path, os.O_RDONLY)
            return self.ruleset_fd
        if number == SYS_ADD_RULE:
            rule = args[2].contents  # type: ignore[attr-defined]
            self.rules.append((rule.allowed_access, rule.parent_fd))
            return self.add_rule_result
        if number == SYS_RESTRICT_SELF:
            return self.restrict_result
        return -errno.ENOSYS


@pytest.fixture
def fd_file(tmp_path: Path) -> Path:
    path = tmp_path / "ruleset"
    path.write_bytes(b"")
    return path


def fd_is_closed(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return True
    return False


@pytest.mark.parametrize("missing", [errno.ENOSYS, errno.EOPNOTSUPP, errno.EINVAL])
def test_a_kernel_without_landlock_answers_zero(missing: int) -> None:
    assert abi_version(lambda *_: -missing) == 0


def test_another_probe_error_raises() -> None:
    with pytest.raises(OSError, match="not permitted") as caught:
        abi_version(lambda *_: -errno.EPERM)
    assert caught.value.errno == errno.EPERM


def test_the_probe_asks_for_the_version() -> None:
    seen: list[tuple[object, ...]] = []

    def kernel(*args: object) -> int:
        seen.append(args)
        return 6

    assert abi_version(kernel) == 6
    assert seen == [(SYS_CREATE_RULESET, None, 0, 1)]


def test_off_linux_there_is_no_landlock() -> None:
    if ON_LINUX:
        pytest.skip("this is the probe off Linux")
    assert abi_version() == 0
    with pytest.raises(OSError, match="needs Linux"):
        restrict((), ())


def test_the_handled_rights_grow_with_the_abi() -> None:
    assert handled_access(1).fs == FS_ABI_1
    assert handled_access(2).fs == FS_ABI_1 | ACCESS_FS_REFER
    assert handled_access(3).fs == FS_ABI_1 | ACCESS_FS_REFER | ACCESS_FS_TRUNCATE
    assert handled_access(4).fs == handled_access(3).fs
    assert handled_access(5).fs == handled_access(3).fs | ACCESS_FS_IOCTL_DEV
    assert handled_access(6).fs == handled_access(5).fs
    for abi in (1, 2, 3):
        assert handled_access(abi).net == 0
        assert handled_access(abi).scoped == 0
    for abi in (4, 5, 6, 7):
        assert handled_access(abi).net == ACCESS_NET_BIND_TCP | ACCESS_NET_CONNECT_TCP
    assert handled_access(5).scoped == 0
    assert handled_access(6).scoped == SCOPE_ABSTRACT_UNIX_SOCKET | SCOPE_SIGNAL


def test_the_ruleset_struct_holds_three_words() -> None:
    assert ctypes.sizeof(RulesetAttr) == 24
    assert ctypes.sizeof(landlock.PathBeneathAttr) == 12


@pytest.mark.parametrize(("abi", "size"), [(1, 8), (3, 8), (4, 16), (5, 16), (6, 24)])
def test_restrict_hands_the_kernel_the_ruleset_of_its_abi(fd_file: Path, abi: int, size: int) -> None:
    kernel = FakeKernel(fd_file, abi=abi)
    assert restrict(("/does/not/exist",), (), kernel) == abi
    handled = handled_access(abi)
    assert kernel.created == [(handled.fs, handled.net, handled.scoped, size)]
    assert kernel.calls[-1] == SYS_RESTRICT_SELF
    assert kernel.rules == []  # a missing path is skipped
    assert fd_is_closed(kernel.ruleset_fd)


def test_restrict_without_landlock_raises(fd_file: Path) -> None:
    with pytest.raises(OSError, match="not available"):
        restrict((), (), FakeKernel(fd_file, abi=0))


def test_a_failing_restrict_self_raises_and_closes(fd_file: Path) -> None:
    kernel = FakeKernel(fd_file, restrict_self=-errno.EPERM)
    with pytest.raises(OSError, match="landlock_restrict_self") as caught:
        restrict((), (), kernel)
    assert caught.value.errno == errno.EPERM
    assert fd_is_closed(kernel.ruleset_fd)


def test_a_failing_create_ruleset_raises(fd_file: Path) -> None:
    def kernel(number: int, *args: object) -> int:
        return 4 if args[0] is None else -errno.E2BIG

    with pytest.raises(OSError, match="landlock_create_ruleset"):
        restrict((), (), kernel)


@pytest.mark.linux
@pytest.mark.skipif(not ON_LINUX, reason="O_PATH needs Linux")
def test_rules_carry_directory_rights_only_for_directories(tmp_path: Path, fd_file: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()
    single = tmp_path / "single"
    single.write_bytes(b"x")
    kernel = FakeKernel(fd_file, abi=5)
    restrict((str(folder), str(single)), (), kernel)
    assert [rights for rights, _ in kernel.rules] == [READ_ACCESS, READ_ACCESS & FILE_ACCESS]
    assert not kernel.rules[1][0] & ACCESS_FS_READ_DIR


@pytest.mark.linux
@pytest.mark.skipif(not ON_LINUX, reason="O_PATH needs Linux")
def test_a_failing_rule_raises(tmp_path: Path, fd_file: Path) -> None:
    kernel = FakeKernel(fd_file, add_rule=-errno.EBADF)
    with pytest.raises(OSError, match="landlock_add_rule"):
        restrict((str(tmp_path),), (), kernel)
    assert SYS_RESTRICT_SELF not in kernel.calls


CHILD = """
import ctypes, os, sys
from pii_redaction_backend.sandbox import landlock

inside, outside = sys.argv[1], sys.argv[2]
open(os.path.join(outside, "secret.txt")).read()
with open(os.path.join(outside, "before.txt"), "w") as handle:
    handle.write("positive control")
print("outside-before-ok")
libc = ctypes.CDLL(None, use_errno=True)
assert libc.prctl(38, 1, 0, 0, 0) == 0  # PR_SET_NO_NEW_PRIVS, the jail does this in plan 02-08
landlock.restrict(
    (sys.prefix, sys.base_prefix, "/usr", "/lib", "/etc", inside),
    (inside,),
)
open("/etc/os-release").read()
print("etc-ok")
with open(os.path.join(inside, "written.txt"), "w") as handle:
    handle.write("ok")
print("inside-write-ok")
try:
    open(os.path.join(outside, "secret.txt")).read()
except PermissionError:
    print("outside-denied")
try:
    open(os.path.join(outside, "after.txt"), "w").close()
except PermissionError:
    print("outside-write-denied")
"""


@pytest.mark.linux
@pytest.mark.skipif(not ON_LINUX, reason="needs Linux")
def test_the_real_ruleset_confines_reads_and_writes(tmp_path: Path) -> None:
    if abi_version() == 0:
        pytest.skip("no Landlock in this kernel")
    inside = tmp_path / "inside"
    outside = tmp_path / "outside"
    inside.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("not for the child", encoding="utf-8")
    script = tmp_path / "child.py"
    script.write_text(CHILD, encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - fixed interpreter, script written by this test
        [sys.executable, "-I", str(script), str(inside), str(outside)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == [
        "outside-before-ok",
        "etc-ok",
        "inside-write-ok",
        "outside-denied",
        "outside-write-denied",
    ]


# -- socket paths (plan 02-08, LibreOffice's single-instance pipe in /tmp) -----------------


@pytest.mark.linux
@pytest.mark.skipif(not ON_LINUX, reason="O_PATH needs Linux")
def test_a_socket_path_carries_only_the_socket_right(tmp_path: Path, fd_file: Path) -> None:
    kernel = FakeKernel(fd_file, abi=6)
    restrict((), (), kernel, socket_paths=(str(tmp_path),))
    assert [rights for rights, _ in kernel.rules] == [landlock.ACCESS_FS_MAKE_SOCK]


SOCKET_CHILD = """
import ctypes, os, socket, sys
from pii_redaction_backend.sandbox import landlock

sockets, work = sys.argv[1], sys.argv[2]


def attempt(name, action):
    try:
        action()
        print(name + "-ok")
    except PermissionError:
        print(name + "-denied")


def bind(path):
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.close()


# Positive control: before the ruleset every action works.
attempt("before-socket", lambda: bind(os.path.join(sockets, "before.sock")))
attempt("before-file", lambda: open(os.path.join(sockets, "before.txt"), "w").close())
libc = ctypes.CDLL(None, use_errno=True)
assert libc.prctl(38, 1, 0, 0, 0) == 0
landlock.restrict((sys.prefix, sys.base_prefix, "/usr", "/lib", "/etc"), (work,), socket_paths=(sockets,))
attempt("socket", lambda: bind(os.path.join(sockets, "after.sock")))
attempt("file", lambda: open(os.path.join(sockets, "after.txt"), "w").close())
attempt("folder", lambda: os.mkdir(os.path.join(sockets, "folder")))
attempt("remove", lambda: os.unlink(os.path.join(sockets, "before.txt")))
attempt("read", lambda: open(os.path.join(sockets, "secret.txt")).read())
attempt("work", lambda: open(os.path.join(work, "out.txt"), "w").close())
"""


@pytest.mark.linux
@pytest.mark.skipif(not ON_LINUX, reason="needs Linux")
def test_the_real_socket_rule_allows_a_socket_and_nothing_else(tmp_path: Path) -> None:
    if abi_version() == 0:
        pytest.skip("no Landlock in this kernel")
    sockets = tmp_path / "s"
    work = tmp_path / "w"
    sockets.mkdir()
    work.mkdir()
    (sockets / "secret.txt").write_text("not for the child", encoding="utf-8")
    script = tmp_path / "socket_child.py"
    script.write_text(SOCKET_CHILD, encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - fixed interpreter, script written by this test
        [sys.executable, "-I", str(script), str(sockets), str(work)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == [
        "before-socket-ok",
        "before-file-ok",
        "socket-ok",
        "file-denied",
        "folder-denied",
        "remove-denied",
        "read-denied",
        "work-ok",
    ]
    assert (sockets / "before.txt").exists()
    assert not (sockets / "after.txt").exists()
