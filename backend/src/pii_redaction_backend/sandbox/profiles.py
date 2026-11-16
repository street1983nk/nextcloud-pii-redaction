"""Fixed limits for every kind of child that touches a foreign file (D-02-05, D-02-07).

A profile is the whole budget of one child: wall clock, CPU seconds, address
space, the largest file it may write, open files, and the paths Landlock lets
it read or write. The values are constants on purpose (D-02-07): no admin
setting can loosen them, and a change is a reviewed commit.

The paths here are the system part only. The job paths (source file, work
folder, LibreOffice profile) are added per run by the jail (plan 02-08). No
profile names the persistent volume, /frpc.toml, /certs or /proc of another
process: those hold APP_SECRET, HP_SHARED_KEY and the frp client key, and a
parser that was taken over must not reach them (RESEARCH Pitfall 1).

The core size is always 0, so a crashing parser leaves no memory image with
document content behind. The process count limit is never set: the kernel counts
it for the whole uid 10001, which Findling and AV share on the same host, so a
limit for one child would make children of the other apps fail at random.
"""

import types
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from pii_redaction_backend.config import MAX_SOURCE_BYTES

MIB: Final = 1024 * 1024
GIB: Final = 1024 * MIB

# CPU seconds are the wall clock plus this margin, so the wall clock in the
# server (killpg) fires first and the CPU limit is only the backstop.
CPU_MARGIN_S: Final = 5

# A file the sanitizer writes is the cleaned copy of the source; it can grow a
# little when the archive is written anew. 10 % on top of the largest source,
# rounded up to a whole 16 MiB step: 288 MiB for the 256 MiB source limit.
_SANITIZE_STEP: Final = 16 * MIB
SANITIZE_FILE_SIZE: Final = -(-(MAX_SOURCE_BYTES * 11 // 10) // _SANITIZE_STEP) * _SANITIZE_STEP

# What every child may read: the interpreter, the libraries, the app code and
# the two harmless devices. /lib64 exists on amd64 only; missing paths are
# skipped by the Landlock layer.
SYSTEM_READ: Final[tuple[str, ...]] = (
    "/usr",
    "/lib",
    "/lib64",
    "/etc",
    "/app/.venv",
    "/app",
    "/dev/null",
    "/dev/urandom",
)

# LibreOffice reads its own installation and the fonts on top.
SOFFICE_READ: Final[tuple[str, ...]] = (*SYSTEM_READ, "/usr/share/fonts", "/usr/lib/libreoffice")


@dataclass(frozen=True, slots=True)
class Profile:
    """The fixed budget of one kind of child."""

    name: str
    wall_s: float
    cpu_s: int
    # None means no address space limit (torch reserves far more than it uses).
    address_space: int | None
    file_size: int
    open_files: int
    read_paths: tuple[str, ...]
    write_paths: tuple[str, ...]
    # A Python child gets one malloc arena before it parses (Findling pattern).
    python_child: bool
    # Always 0: no core file with document content.
    core: int = 0


def _profile(
    name: str,
    *,
    wall_s: int,
    address_space: int | None,
    file_size: int,
    open_files: int = 256,
    read_paths: tuple[str, ...] = SYSTEM_READ,
    python_child: bool = True,
) -> Profile:
    return Profile(
        name=name,
        wall_s=float(wall_s),
        cpu_s=wall_s + CPU_MARGIN_S,
        address_space=address_space,
        file_size=file_size,
        open_files=open_files,
        read_paths=read_paths,
        write_paths=(),
        python_child=python_child,
    )


PROFILES: Final[Mapping[str, Profile]] = types.MappingProxyType(
    {
        # MuPDF renders one page to PNG: 60 s like the phase 1 deadline, 1 GiB
        # address space, the PNG of a large page stays far below 512 MiB.
        "render": _profile("render", wall_s=60, address_space=GIB, file_size=512 * MIB),
        # The pre-check only answers with a verdict file of a few hundred bytes.
        "precheck": _profile("precheck", wall_s=60, address_space=GIB, file_size=MIB),
        # The sanitizer writes the cleaned copy of the source.
        "sanitize": _profile("sanitize", wall_s=60, address_space=GIB, file_size=SANITIZE_FILE_SIZE),
        # LibreOffice: 120 s like phase 1; no address space limit until plan
        # 02-24 has measured it (D-02-13); it opens many files at start.
        "soffice": _profile(
            "soffice",
            wall_s=120,
            address_space=None,
            file_size=512 * MIB,
            open_files=1024,
            read_paths=SOFFICE_READ,
            python_child=False,
        ),
        # Tesseract on one page image.
        "ocr": _profile("ocr", wall_s=120, address_space=GIB, file_size=512 * MIB, python_child=False),
        # The detector loads torch: no address space limit (CLAUDE.md), half an
        # hour for a long document, it writes only findings.
        "detect": _profile("detect", wall_s=1800, address_space=None, file_size=64 * MIB),
    }
)


def profile_for(name: str) -> Profile:
    """The profile with this name; an unknown name is a programming error."""
    try:
        return PROFILES[name]
    except KeyError:
        msg = f"unknown sandbox profile {name!r}"
        raise ValueError(msg) from None
