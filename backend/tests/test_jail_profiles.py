"""The fixed sandbox profiles (D-02-05, D-02-07): limits, paths, no process count limit."""

from pathlib import Path

import pytest

from pii_redaction_backend.config import MAX_SOURCE_BYTES
from pii_redaction_backend.sandbox import profiles
from pii_redaction_backend.sandbox.profiles import GIB, MIB, PROFILES, profile_for

SOCKET_ROOT = "/tmp"  # noqa: S108 - the path under test, nothing is written there
FORBIDDEN_PREFIXES = ("/nc_app_pii_redaction_backend_data", "/certs", "/frpc.toml", "/proc")


def forbidden_paths(paths: tuple[str, ...]) -> list[str]:
    """Paths that would let a child read a secret; /proc/self alone is harmless."""
    found = []
    for path in paths:
        if path == "/proc/self" or path.startswith("/proc/self/"):
            continue
        if any(path == prefix or path.startswith(prefix + "/") for prefix in FORBIDDEN_PREFIXES):
            found.append(path)
    return found


def test_there_are_exactly_six_profiles() -> None:
    assert set(PROFILES) == {"render", "precheck", "sanitize", "soffice", "ocr", "detect"}


def test_the_profiles_cannot_be_changed_at_run_time() -> None:
    with pytest.raises(TypeError):
        PROFILES["render"] = PROFILES["detect"]  # type: ignore[index]


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_cpu_is_the_wall_clock_plus_five_and_core_is_zero(name: str) -> None:
    profile = PROFILES[name]
    assert profile.name == name
    assert profile.cpu_s == profile.wall_s + 5
    assert profile.core == 0
    assert profile.open_files == (1024 if name == "soffice" else 256)


def test_the_wall_clocks_match_the_research_table() -> None:
    walls = {name: profile.wall_s for name, profile in PROFILES.items()}
    assert walls == {"precheck": 60, "sanitize": 60, "soffice": 120, "render": 60, "ocr": 120, "detect": 1800}


def test_only_torch_and_libreoffice_run_without_an_address_space_limit() -> None:
    assert PROFILES["detect"].address_space is None
    assert PROFILES["soffice"].address_space is None
    for name in ("precheck", "sanitize", "render", "ocr"):
        assert PROFILES[name].address_space == GIB


def test_the_file_size_limits() -> None:
    assert PROFILES["precheck"].file_size == MIB
    assert PROFILES["sanitize"].file_size == 288 * MIB
    assert PROFILES["sanitize"].file_size >= MAX_SOURCE_BYTES * 11 // 10
    for name in ("soffice", "render", "ocr"):
        assert PROFILES[name].file_size == 512 * MIB
    assert PROFILES["detect"].file_size == 64 * MIB


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_no_profile_reaches_a_secret(name: str) -> None:
    profile = PROFILES[name]
    assert forbidden_paths(profile.read_paths) == []
    assert forbidden_paths(profile.write_paths) == []
    assert forbidden_paths(profile.socket_paths) == []


def test_the_secret_rule_fires_on_a_tampered_probe() -> None:
    probe = ("/usr", "/certs/frp/client.key", "/frpc.toml", "/proc/1/environ", "/nc_app_pii_redaction_backend_data/x")
    assert forbidden_paths(probe) == list(probe[1:])
    assert forbidden_paths(("/proc/self/status", "/proc/self")) == []
    assert forbidden_paths(("/proc",)) == ["/proc"]


def test_libreoffice_reads_its_installation_and_the_fonts() -> None:
    soffice = PROFILES["soffice"].read_paths
    assert "/usr/lib/libreoffice" in soffice
    assert "/usr/share/fonts" in soffice
    assert "/usr/lib/libreoffice" not in PROFILES["render"].read_paths


def test_the_python_children_are_marked() -> None:
    assert {name for name, profile in PROFILES.items() if profile.python_child} == {
        "render",
        "precheck",
        "sanitize",
        "detect",
    }


def test_an_unknown_profile_is_a_programming_error() -> None:
    assert profile_for("render") is PROFILES["render"]
    with pytest.raises(ValueError, match="unknown sandbox profile"):
        profile_for("unknown")


def test_the_process_count_limit_is_never_set() -> None:
    source = Path(profiles.__file__).read_text(encoding="utf-8")
    code = [line for line in source.splitlines() if not line.lstrip().startswith("#")]
    assert not any("RLIMIT_NPROC" in line for line in code)
    assert "never set" in source


def test_only_libreoffice_may_create_a_socket_and_only_in_tmp() -> None:
    sockets = {name: profile.socket_paths for name, profile in PROFILES.items() if profile.socket_paths}
    assert sockets == {"soffice": (SOCKET_ROOT,)}
    # No profile writes /tmp itself: the socket rule is the only right there.
    assert all(SOCKET_ROOT not in profile.write_paths for profile in PROFILES.values())
