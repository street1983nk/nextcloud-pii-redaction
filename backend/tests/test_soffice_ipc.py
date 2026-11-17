"""The server removes only the LibreOffice pipe sockets of its own uid (plan 02-16, risk R4).

soffice binds /tmp/OSL_PIPE_<uid>_SingleOfficeIPC_<hash> and may not remove
it (no REMOVE_FILE on /tmp), so the server does, before and after each run.
/tmp also holds the HaRP socket exapp.sock of the same uid: the cleanup must
never touch it, nor anything else that is not exactly a pipe socket of this
uid. The name rule runs everywhere; the real removal on Linux.
"""

import contextlib
import os
import shutil
import socket
import stat
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from pii_redaction_backend.workers import soffice

UID = 10001
HASH = "d41d8cd98f0b24e9800998ecf8427e"  # 30 hex digits: two bytes below 0x10 lost their zero


def info(mode: int, uid: int = UID) -> os.stat_result:
    return os.stat_result((mode, 0, 0, 1, uid, uid, 0, 0, 0, 0))


SOCK = stat.S_IFSOCK | 0o755
FILE = stat.S_IFREG | 0o600


def test_the_pipe_socket_of_this_uid_is_removed() -> None:
    assert soffice.is_own_ipc_socket(f"OSL_PIPE_{UID}_SingleOfficeIPC_{HASH}", info(SOCK), UID)
    # 16 and 32 hex digits are the two ends a 16 byte MD5 can give.
    assert soffice.is_own_ipc_socket(f"OSL_PIPE_{UID}_SingleOfficeIPC_{'a' * 16}", info(SOCK), UID)
    assert soffice.is_own_ipc_socket(f"OSL_PIPE_{UID}_SingleOfficeIPC_{'f' * 32}", info(SOCK), UID)


@pytest.mark.parametrize(
    ("name", "mode", "owner"),
    [
        # The HaRP socket: same uid, a socket, but not the pipe name.
        ("exapp.sock", SOCK, UID),
        # The name of another uid, even when the socket belongs to this one.
        (f"OSL_PIPE_10002_SingleOfficeIPC_{HASH}", SOCK, UID),
        # A socket with the right name that another uid owns.
        (f"OSL_PIPE_{UID}_SingleOfficeIPC_{HASH}", SOCK, 0),
        # A file that borrows the name.
        (f"OSL_PIPE_{UID}_SingleOfficeIPC_{HASH}", FILE, UID),
        # Near misses of the name.
        (f"OSL_PIPE_{UID}_SingleOfficeIPC_{HASH}.bak", SOCK, UID),
        (f"xOSL_PIPE_{UID}_SingleOfficeIPC_{HASH}", SOCK, UID),
        (f"OSL_PIPE_{UID}_SingleOfficeIPC_{HASH.upper()}", SOCK, UID),
        (f"OSL_PIPE_{UID}_SingleOfficeIPC_{'a' * 15}", SOCK, UID),
        (f"OSL_PIPE_{UID}_SingleOfficeIPC_{'a' * 33}", SOCK, UID),
        (f"OSL_PIPE_{UID}_OtherIPC_{HASH}", SOCK, UID),
        (f"OSL_PIPE_SingleOfficeIPC_{HASH}", SOCK, UID),
    ],
)
def test_negative_anything_else_stays(name: str, mode: int, owner: int) -> None:
    assert not soffice.is_own_ipc_socket(name, info(mode, owner), UID)


@pytest.fixture
def short_root() -> Iterator[Path]:
    """A folder with a short path: a Unix socket path must fit into 108 bytes."""
    root = Path(tempfile.mkdtemp(prefix="ipc-", dir="/tmp"))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _listen(path: Path) -> socket.socket:
    family = getattr(socket, "AF_UNIX", None)
    if family is None:
        pytest.skip("AF_UNIX needed")
    listener = socket.socket(family, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen(1)
    return listener


@pytest.mark.skipif(sys.platform == "win32", reason="Unix sockets and uids")
def test_negative_cleanup_leaves_exapp_sock_and_foreign_files(short_root: Path) -> None:
    assert sys.platform != "win32"
    uid = os.getuid()
    pipe = short_root / f"OSL_PIPE_{uid}_SingleOfficeIPC_{HASH}"
    other_uid = short_root / f"OSL_PIPE_{uid + 1}_SingleOfficeIPC_{HASH}"
    harp = short_root / "exapp.sock"
    borrowed = short_root / f"OSL_PIPE_{uid}_SingleOfficeIPC_{'b' * 32}"
    foreign = short_root / "notes.txt"
    listeners = [_listen(pipe), _listen(other_uid), _listen(harp)]
    try:
        harp.chmod(0o666)
        borrowed.write_bytes(b"not a socket\n")
        foreign.write_bytes(b"someone else's file\n")
        soffice._remove_ipc_sockets(short_root)
        # Positive control: the pipe socket of this uid is gone.
        assert not pipe.exists()
        # Everything else stands, the HaRP socket first of all.
        assert stat.S_ISSOCK(harp.lstat().st_mode)
        assert stat.S_ISSOCK(other_uid.lstat().st_mode)
        assert borrowed.read_bytes() == b"not a socket\n"
        assert foreign.read_bytes() == b"someone else's file\n"
    finally:
        for listener in listeners:
            with contextlib.suppress(OSError):
                listener.close()
