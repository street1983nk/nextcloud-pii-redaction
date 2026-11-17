"""The jail start program: argument rules, the order of the layers, fail closed, and on Linux the real limits."""

import ast
import json
import socket
import sys
from pathlib import Path

import pytest

from pii_redaction_backend.sandbox import jail
from pii_redaction_backend.sandbox.profiles import PROFILES
from tests.conftest import BACKEND_ROOT

LINUX_ONLY = [pytest.mark.linux, pytest.mark.skipif(not sys.platform.startswith("linux"), reason="needs Linux")]
JAIL_SOURCE = BACKEND_ROOT / "src" / "pii_redaction_backend" / "sandbox" / "jail.py"


class Recorder:
    """Every system call of the jail, in order; failures on request."""

    def __init__(
        self,
        *,
        landlock_abi: int = 6,
        seccomp_ok: bool = True,
        fail: str = "",
    ) -> None:
        self.calls: list[tuple[str, object]] = []
        self.abi = landlock_abi
        self.seccomp_ok = seccomp_ok
        self.fail = fail

    def _maybe_fail(self, name: str) -> None:
        if self.fail == name:
            raise OSError(1, name)

    def setrlimit(self, name: str, value: tuple[int, int]) -> None:
        self.calls.append(("setrlimit", (name, value)))
        self._maybe_fail(f"setrlimit:{name}")

    def prctl(self, option: int, value: int) -> None:
        self.calls.append(("prctl", (option, value)))
        self._maybe_fail("prctl")

    def landlock_abi(self) -> int:
        return self.abi

    def landlock_restrict(self, read: tuple[str, ...], write: tuple[str, ...]) -> object:
        self.calls.append(("landlock", (read, write)))
        self._maybe_fail("landlock")
        return self.abi

    def seccomp_available(self) -> bool:
        return self.seccomp_ok

    def seccomp_install(self) -> None:
        self.calls.append(("seccomp", None))
        self._maybe_fail("seccomp")

    def execv(self, path: str, args: list[str]) -> object:
        self.calls.append(("execv", (path, list(args))))
        self._maybe_fail("execv")
        return None

    def ops(self) -> jail.Ops:
        return jail.Ops(
            setrlimit=self.setrlimit,
            prctl=self.prctl,
            landlock_abi=self.landlock_abi,
            landlock_restrict=self.landlock_restrict,
            seccomp_available=self.seccomp_available,
            seccomp_install=self.seccomp_install,
            execv=self.execv,
        )

    def kinds(self) -> list[str]:
        return [kind for kind, _ in self.calls]

    def rlimits(self) -> dict[str, tuple[int, int]]:
        found: dict[str, tuple[int, int]] = {}
        for kind, value in self.calls:
            if kind == "setrlimit":
                name, limit = value  # type: ignore[misc]
                found[name] = limit
        return found


# -- arguments ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["unknown", "--", "/bin/true"],
        ["render", "/bin/true"],
        ["render", "--"],
        ["render", "--", "true"],
        ["render", "--read", "relative", "--", "/bin/true"],
        ["render", "--read", "--", "/bin/true"],
        ["render", "--other", "/x", "--", "/bin/true"],
        [],
    ],
)
def test_malformed_calls_end_with_2_and_start_nothing(argv: list[str]) -> None:
    recorder = Recorder()
    assert jail.main(argv, recorder.ops()) == jail.EXIT_USAGE
    assert recorder.calls == []


@pytest.mark.parametrize(
    "path",
    [
        "/nc_app_pii_redaction_backend_data",
        "/nc_app_pii_redaction_backend_data/state.db",
        "/nc_app_pii_redaction_backend_data/work",
        "/nc_app_pii_redaction_backend_data/work/../state.db",
        "/nc_app_pii_redaction_backend_data/models",
    ],
)
def test_a_write_path_on_the_volume_outside_work_is_refused(path: str) -> None:
    recorder = Recorder()
    assert jail.main(["render", "--write", path, "--", "/bin/true"], recorder.ops()) == jail.EXIT_USAGE
    assert recorder.calls == []


def test_a_write_path_below_work_is_accepted() -> None:
    recorder = Recorder()
    work = "/nc_app_pii_redaction_backend_data/work/7"
    assert jail.main(["render", "--write", work, "--", "/bin/true"], recorder.ops()) == jail.EXIT_LAYER_FAILED
    assert recorder.kinds()[-1] == "execv"


def test_jail_argv_names_the_profile_and_the_paths() -> None:
    argv = jail.jail_argv("soffice", ["/usr/bin/soffice", "x"], read=("/in",), write=("/out", "/work/lo-1"))
    assert argv[:4] == [sys.executable, "-I", "-m", "pii_redaction_backend.sandbox.jail"]
    assert argv[4:] == [
        "soffice",
        "--read",
        "/in",
        "--write",
        "/out",
        "--write",
        "/work/lo-1",
        "--",
        "/usr/bin/soffice",
        "x",
    ]
    with pytest.raises(ValueError, match="unknown sandbox profile"):
        jail.jail_argv("none", ["/bin/true"])


def test_jail_argv_round_trips_through_the_parser() -> None:
    argv = jail.jail_argv("render", ["/usr/bin/python3", "-I", "a"], read=("/src",), write=("/work",))
    call = jail.parse(argv[4:])
    assert call is not None
    assert call.profile is PROFILES["render"]
    assert call.read == ("/src",)
    assert call.write == ("/work",)
    assert call.command == ["/usr/bin/python3", "-I", "a"]


# -- order and fail closed ------------------------------------------------------------


def test_the_layers_come_in_the_fixed_order() -> None:
    recorder = Recorder()
    jail.main(["render", "--", "/usr/bin/python3", "-I", "x"], recorder.ops())
    kinds = recorder.kinds()
    first_other = kinds.index("prctl")
    assert set(kinds[:first_other]) == {"setrlimit"}
    assert kinds[first_other:] == ["prctl", "landlock", "seccomp", "execv"]
    assert recorder.calls[first_other] == ("prctl", (38, 1))
    assert recorder.calls[-1] == ("execv", ("/usr/bin/python3", ["/usr/bin/python3", "-I", "x"]))


def test_the_limits_follow_the_profile_and_the_core_is_zero() -> None:
    recorder = Recorder()
    jail.main(["render", "--", "/bin/true"], recorder.ops())
    profile = PROFILES["render"]
    limits = recorder.rlimits()
    assert limits == {
        "RLIMIT_CPU": (profile.cpu_s, profile.cpu_s),
        "RLIMIT_FSIZE": (profile.file_size, profile.file_size),
        "RLIMIT_NOFILE": (profile.open_files, profile.open_files),
        "RLIMIT_AS": (profile.address_space, profile.address_space),
        "RLIMIT_CORE": (0, 0),
    }


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_no_profile_ever_sets_the_process_count(name: str) -> None:
    recorder = Recorder()
    jail.main([name, "--", "/bin/true"], recorder.ops())
    limits = recorder.rlimits()
    assert "RLIMIT_NPROC" not in limits
    assert limits["RLIMIT_CORE"] == (0, 0)
    assert ("RLIMIT_AS" in limits) is (PROFILES[name].address_space is not None)


def test_the_job_paths_are_added_to_the_profile_paths() -> None:
    recorder = Recorder()
    work = "/nc_app_pii_redaction_backend_data/work/3"
    jail.main(["soffice", "--read", "/in/src.docx", "--write", work, "--", "/usr/bin/soffice"], recorder.ops())
    (read, write) = next(value for kind, value in recorder.calls if kind == "landlock")  # type: ignore[misc]
    assert read == (*PROFILES["soffice"].read_paths, "/in/src.docx")
    assert write == (*PROFILES["soffice"].write_paths, work)


def test_without_seccomp_the_child_still_starts() -> None:
    recorder = Recorder(seccomp_ok=False)
    jail.main(["render", "--", "/bin/true"], recorder.ops())
    assert "seccomp" not in recorder.kinds()
    assert recorder.kinds()[-1] == "execv"


def test_without_landlock_the_child_still_starts() -> None:
    recorder = Recorder(landlock_abi=0)
    jail.main(["render", "--", "/bin/true"], recorder.ops())
    assert "landlock" not in recorder.kinds()
    assert recorder.kinds()[-2:] == ["seccomp", "execv"]


@pytest.mark.parametrize("failing", ["seccomp", "landlock", "prctl", "setrlimit:RLIMIT_CORE", "setrlimit:RLIMIT_CPU"])
def test_a_layer_that_fails_to_load_stops_the_start(failing: str) -> None:
    recorder = Recorder(fail=failing)
    assert jail.main(["render", "--", "/bin/true"], recorder.ops()) == jail.EXIT_LAYER_FAILED
    assert "execv" not in recorder.kinds()


def test_positive_control_the_same_call_without_a_failure_reaches_execv() -> None:
    recorder = Recorder()
    jail.main(["render", "--", "/bin/true"], recorder.ops())
    assert recorder.kinds()[-1] == "execv"


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="the refusal is for systems without rlimits")
def test_off_linux_the_jail_refuses_to_start_anything() -> None:
    assert jail.main(["render", "--", "/bin/true"]) == jail.EXIT_LAYER_FAILED


def test_the_jail_names_preexec_fn_only_in_prose() -> None:
    tree = ast.parse(JAIL_SOURCE.read_text(encoding="utf-8"))
    names = [node.id for node in ast.walk(tree) if isinstance(node, ast.Name)]
    names += [node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)]
    names += [kw.arg for node in ast.walk(tree) if isinstance(node, ast.Call) for kw in node.keywords if kw.arg]
    assert "preexec_fn" not in names
    assert "preexec_fn" in (ast.get_docstring(tree) or "")


# -- the real jail on Linux ----------------------------------------------------------


def _jailed(profile: str, script: Path, tmp_path: Path) -> list[str]:
    read = (sys.base_prefix, sys.prefix, str(tmp_path))
    return jail.jail_argv(profile, [sys.executable, "-I", str(script)], read=read, write=(str(tmp_path),))


def _run_jail(argv: list[str]) -> int:
    import subprocess

    return subprocess.run(argv, env={"PATH": "/usr/bin:/bin"}, check=False, timeout=60).returncode  # noqa: S603


@pytest.mark.linux
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="needs Linux")
def test_the_real_jail_sets_the_profile_limits(tmp_path: Path) -> None:
    # The child asks the kernel itself; /proc is outside its Landlock paths.
    out = tmp_path / "limits.json"
    script = tmp_path / "limits.py"
    script.write_text(
        "import json, resource\n"
        "names = ('RLIMIT_CPU', 'RLIMIT_FSIZE', 'RLIMIT_AS', 'RLIMIT_CORE', 'RLIMIT_NOFILE')\n"
        "seen = {n: list(resource.getrlimit(getattr(resource, n))) for n in names}\n"
        f"open({str(out)!r}, 'w').write(json.dumps(seen))\n",
        encoding="utf-8",
    )

    assert _run_jail(_jailed("precheck", script, tmp_path)) == 0

    seen = json.loads(out.read_text(encoding="utf-8"))
    profile = PROFILES["precheck"]
    assert seen["RLIMIT_CPU"] == [profile.cpu_s] * 2
    assert seen["RLIMIT_FSIZE"] == [profile.file_size] * 2
    assert seen["RLIMIT_AS"] == [profile.address_space] * 2
    assert seen["RLIMIT_CORE"] == [0, 0]
    assert seen["RLIMIT_NOFILE"] == [profile.open_files] * 2


@pytest.mark.linux
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="needs Linux")
def test_the_real_jail_blocks_an_inet_socket_when_seccomp_is_there(tmp_path: Path) -> None:
    from pii_redaction_backend.sandbox import seccomp

    out = tmp_path / "socket.txt"
    script = tmp_path / "socket_probe.py"
    script.write_text(
        "import socket\n"
        "try:\n"
        "    socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()\n"
        "    result = 'open'\n"
        "except PermissionError:\n"
        "    result = 'blocked'\n"
        f"open({str(out)!r}, 'w').write(result)\n",
        encoding="utf-8",
    )
    # Positive control: outside the jail the same script opens the socket.
    socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()

    assert _run_jail(_jailed("precheck", script, tmp_path)) == 0

    expected = "blocked" if seccomp.available() else "open"
    assert out.read_text(encoding="utf-8") == expected
