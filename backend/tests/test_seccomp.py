"""The seccomp network block: probe, rule list, fail closed, and on Linux the real effect."""

import errno
import subprocess
import sys
from pathlib import Path

import pytest

from pii_redaction_backend.sandbox import seccomp
from pii_redaction_backend.sandbox.seccomp import (
    AF_INET,
    AF_INET6,
    AF_NETLINK,
    AF_PACKET,
    DENIED_SYSCALLS,
    SCMP_ACT_ALLOW,
    SCMP_CMP_EQ,
    available,
    errno_action,
    install_network_denylist,
)

LINUX_ONLY = [pytest.mark.linux, pytest.mark.skipif(not sys.platform.startswith("linux"), reason="needs Linux")]
CONTEXT = 0xC0FFEE
NUMBERS = {name: index + 100 for index, name in enumerate(("socket", "connect", *DENIED_SYSCALLS))}


class FakeSeccomp:
    """libseccomp stand-in that records every call."""

    def __init__(self, *, init: int = CONTEXT, fail_rule: int | None = None, load: int = 0, unknown: str = "") -> None:
        self.init_result = init
        self.fail_rule = fail_rule
        self.load_result = load
        self.unknown = unknown
        self.rules: list[tuple[int, int, int, list[tuple[int, int, int]]]] = []
        self.calls: list[str] = []

    def seccomp_init(self, action: int) -> int:
        self.calls.append(f"init:{action:#x}")
        return self.init_result

    def seccomp_release(self, context: int) -> None:
        self.calls.append(f"release:{context:#x}")

    def seccomp_syscall_resolve_name(self, name: bytes) -> int:
        return -1 if name.decode() == self.unknown else NUMBERS[name.decode()]

    def seccomp_rule_add_exact_array(self, context: int, action: int, number: int, count: int, conditions) -> int:
        assert context == CONTEXT
        compared = [(conditions[i].arg, conditions[i].op, conditions[i].datum_a) for i in range(count)]
        self.rules.append((action, number, count, compared))
        if self.fail_rule is not None and len(self.rules) == self.fail_rule:
            return -errno.EFAULT
        return 0

    def seccomp_load(self, context: int) -> int:
        self.calls.append(f"load:{context:#x}")
        return self.load_result


def test_there_is_no_filter_off_linux_and_no_exception() -> None:
    if sys.platform.startswith("linux"):
        pytest.skip("this is the probe off Linux")
    assert available() is False


def test_a_context_that_cannot_be_created_means_unavailable() -> None:
    assert available(FakeSeccomp(init=0)) is False


def test_a_working_library_means_available_and_the_probe_releases() -> None:
    fake = FakeSeccomp()
    assert available(fake) is True
    assert fake.calls == [f"init:{SCMP_ACT_ALLOW:#x}", f"release:{CONTEXT:#x}"]


def test_the_denylist_refuses_four_socket_domains_and_ten_calls() -> None:
    fake = FakeSeccomp()
    install_network_denylist(fake)
    refuse = errno_action(errno.EACCES)
    socket_rules = [rule for rule in fake.rules if rule[1] == NUMBERS["socket"]]
    assert socket_rules == [
        (refuse, NUMBERS["socket"], 1, [(0, SCMP_CMP_EQ, domain)])
        for domain in (AF_INET, AF_INET6, AF_PACKET, AF_NETLINK)
    ]
    plain = [rule for rule in fake.rules if rule[1] != NUMBERS["socket"]]
    assert plain == [(refuse, NUMBERS[name], 0, []) for name in DENIED_SYSCALLS]
    assert fake.calls[-2:] == [f"load:{CONTEXT:#x}", f"release:{CONTEXT:#x}"]


def test_without_deny_connect_connect_is_not_touched() -> None:
    fake = FakeSeccomp()
    install_network_denylist(fake)
    assert all(rule[1] != NUMBERS["connect"] for rule in fake.rules)


def test_deny_connect_refuses_connect_for_every_family() -> None:
    fake = FakeSeccomp()
    install_network_denylist(fake, deny_connect=True)
    refuse = errno_action(errno.EACCES)
    connect_rules = [rule for rule in fake.rules if rule[1] == NUMBERS["connect"]]
    # No argument condition: every address family, AF_UNIX included.
    assert connect_rules == [(refuse, NUMBERS["connect"], 0, [])]
    # The rest of the denylist stays as it is, and the filter is loaded once.
    others = [rule for rule in fake.rules if rule[1] != NUMBERS["connect"]]
    plain = FakeSeccomp()
    install_network_denylist(plain)
    assert others == plain.rules
    assert fake.calls[-2:] == [f"load:{CONTEXT:#x}", f"release:{CONTEXT:#x}"]


def test_a_failing_connect_rule_raises_and_loads_nothing() -> None:
    fake = FakeSeccomp(fail_rule=4 + len(DENIED_SYSCALLS) + 1)
    with pytest.raises(OSError, match="Bad address"):
        install_network_denylist(fake, deny_connect=True)
    assert fake.rules[-1][1] == NUMBERS["connect"]
    assert not any(call.startswith("load") for call in fake.calls)


def test_unix_sockets_stay_open() -> None:
    fake = FakeSeccomp()
    install_network_denylist(fake)
    domains = {condition[2] for rule in fake.rules for condition in rule[3]}
    assert 1 not in domains  # AF_UNIX
    assert domains == {2, 10, 16, 17}


def test_the_action_is_errno_eacces() -> None:
    assert errno_action(errno.EACCES) == 0x0005000D


@pytest.mark.parametrize("fail_rule", [1, 4, 5, 14])
def test_a_rule_that_fails_after_a_good_probe_raises_and_releases(fail_rule: int) -> None:
    fake = FakeSeccomp(fail_rule=fail_rule)
    with pytest.raises(OSError, match="Bad address") as caught:
        install_network_denylist(fake)
    assert caught.value.errno == errno.EFAULT
    assert fake.calls[-1] == f"release:{CONTEXT:#x}"
    assert not any(call.startswith("load") for call in fake.calls)


def test_a_load_that_fails_raises() -> None:
    fake = FakeSeccomp(load=-errno.EACCES)
    with pytest.raises(OSError, match="Permission denied") as caught:
        install_network_denylist(fake)
    assert caught.value.errno == errno.EACCES
    assert fake.calls[-1] == f"release:{CONTEXT:#x}"


def test_an_unknown_system_call_raises() -> None:
    with pytest.raises(OSError, match="unknown to libseccomp"):
        install_network_denylist(FakeSeccomp(unknown="bpf"))


def test_a_failed_init_raises_when_the_filter_is_required() -> None:
    with pytest.raises(OSError, match="seccomp_init failed"):
        install_network_denylist(FakeSeccomp(init=0))


def test_a_missing_library_raises_when_the_filter_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seccomp, "_load", lambda: None)
    with pytest.raises(OSError, match="libseccomp not available"):
        install_network_denylist()


CHILD = """
import errno, socket, sys
from pii_redaction_backend.sandbox import seccomp

before = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
before.close()
print("inet-before-ok")
seccomp.install_network_denylist()
for family in (socket.AF_INET, socket.AF_INET6):
    try:
        socket.socket(family, socket.SOCK_STREAM)
    except PermissionError as error:
        assert error.errno == errno.EACCES
        print(f"denied-{int(family)}")
unix = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
unix.close()
print("unix-ok")
"""


@pytest.mark.linux
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="needs Linux")
def test_the_real_filter_blocks_inet_and_keeps_unix(tmp_path: Path) -> None:
    if not available():
        pytest.skip("libseccomp not available on this host")
    script = tmp_path / "child.py"
    script.write_text(CHILD, encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - fixed interpreter, script written by this test
        [sys.executable, "-I", str(script)], capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["inet-before-ok", "denied-2", "denied-10", "unix-ok"]


CONNECT_CHILD = """
import errno, socket, sys
from pii_redaction_backend.sandbox import seccomp

path = sys.argv[1]
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(path)
server.listen(1)
before = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
before.connect(path)
before.close()
print("unix-connect-before-ok")
seccomp.install_network_denylist(deny_connect=True)
probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
try:
    probe.connect(path)
except PermissionError as error:
    assert error.errno == errno.EACCES
    print("unix-connect-denied")
own = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
own.bind(path + "-own")
own.listen(1)
print("unix-bind-ok")
"""


@pytest.mark.linux
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="needs Linux")
def test_the_real_filter_with_deny_connect_refuses_unix_connect_and_keeps_bind(tmp_path: Path) -> None:
    if not available():
        pytest.skip("libseccomp not available on this host")
    script = tmp_path / "child.py"
    script.write_text(CONNECT_CHILD, encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - fixed interpreter, script written by this test
        [sys.executable, "-I", str(script), str(tmp_path / "s")],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["unix-connect-before-ok", "unix-connect-denied", "unix-bind-ok"]
