"""Self test of ci/names_filter.py, the filter in front of the name search of ci/canary.sh.

The fixture lines are real lines of run 43615560742 (stable33, sqlite): the
GET of carol on the file behind the ACL (ci/seed.sh) and the PROPFIND of
baseJob() on a file that was not there yet, each with the Sabre NotFound
that Nextcloud logs at loglevel 1. The filter may drop those, and only those;
a line of the app with the same name and a NotFound on another path that no
404 of the test answered must stay, so the scan still counts them.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from tests.conftest import BACKEND_ROOT, REPO_ROOT

FIXTURES = BACKEND_ROOT / "tests" / "fixtures" / "names_filter"
NAME = "Bescheid 2026-114"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ci_names_filter", REPO_ROOT / "ci" / "names_filter.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


names_filter = _load()


def _lines(name: str) -> list[str]:
    return (FIXTURES / name).read_text(encoding="utf-8").splitlines(keepends=True)


def _hits(lines: list[str]) -> int:
    return sum(NAME.lower() in line.lower() for line in lines)


# An info line as the app could write it by mistake: same reqId, same request, with the name.
APP_LINE = json.dumps(
    {
        "reqId": "xcgIqOuvSrVQAfISMDYT",
        "level": 1,
        "app": "pii_redaction",
        "method": "PROPFIND",
        "url": "/remote.php/dav/files/alice/pw-base-alice/Bescheid%202026-114.pdf",
        "message": "PII Redaction: job started for Bescheid 2026-114.pdf",
    }
)


def test_the_fixture_carries_the_name_so_the_test_can_fail() -> None:
    """Positive control: unfiltered, the real lines do carry the name."""
    assert _hits(_lines("php-server.log")) == 2
    assert _hits(_lines("nextcloud.log")) == 2


def test_php_drops_the_notfound_of_a_test_404_and_the_access_lines() -> None:
    kept, requests, dropped = names_filter.filter_php(_lines("php-server.log"))
    assert _hits(kept) == 0
    # GET of carol, PROPFIND and DELETE of baseJob; the NotFound of the file
    # (2) and of the folder pw-base-alice (1, no test name, its own 404).
    assert (requests, dropped) == (3, 3)
    # Every other exception line stays.
    assert sum("AppPathNotFoundException" in line for line in kept) == 9


def test_php_keeps_a_notfound_without_its_404() -> None:
    lines = _lines("php-server.log")
    exception = next(line for line in lines if NAME in line and "Akten" in line)
    # Answered 207 instead of 404: the line is not the trace of a test 404.
    answered = exception.replace("[3422]", "[9999]")
    access = (
        "[9999] [Sat Nov 14 16:28:36 2026] 127.0.0.1:52962 [207]: "
        "GET /remote.php/dav/files/carol/Akten/Gesperrt/Bescheid%202026-114.pdf\n"
    )
    kept, _, dropped = names_filter.filter_php([answered, access])
    assert dropped == 0
    assert _hits(kept) == 1
    # A 404 on another path: stays as well.
    other = access.replace("[207]", "[404]").replace("Bescheid%202026-114.pdf", "x.pdf")
    kept, _, dropped = names_filter.filter_php([answered, other])
    assert dropped == 0
    assert _hits(kept) == 1
    # The 404 of another process does not count either.
    foreign = access.replace("[9999]", "[1111]").replace("[207]", "[404]")
    kept, _, dropped = names_filter.filter_php([answered, foreign])
    assert dropped == 0
    assert _hits(kept) == 1


def test_php_keeps_an_app_line_with_the_name() -> None:
    line = "[3421] [Sat Nov 14 16:34:47 2026] PII Redaction: job started for Bescheid 2026-114.pdf\n"
    kept, _, _ = names_filter.filter_php([line, *_lines("php-server.log")])
    assert _hits(kept) == 1


def test_nextcloud_drops_only_the_notfound_of_its_own_request() -> None:
    kept, requests, dropped = names_filter.filter_nextcloud(_lines("nextcloud.log"))
    assert _hits(kept) == 0
    # The two NotFound with the name go; the other exception of a WebDAV
    # request (viewer, during the DELETE of pw-base-alice) stays with its url replaced.
    assert (requests, dropped) == (1, 2)
    assert len(kept) == 1
    assert "AppPathNotFoundException" in kept[0]
    assert "(WebDAV request of the test client)" in kept[0]


def test_nextcloud_keeps_an_app_line_with_the_name() -> None:
    kept, requests, dropped = names_filter.filter_nextcloud([APP_LINE + "\n", *_lines("nextcloud.log")])
    assert (requests, dropped) == (2, 2)
    assert _hits(kept) == 1
    # Its url field is replaced, its message stays.
    assert "(WebDAV request of the test client)" in kept[0]


def test_nextcloud_keeps_a_notfound_on_another_path() -> None:
    entry = json.loads(_lines("nextcloud.log")[1])
    entry["url"] = "/remote.php/dav/files/alice/pw-base-alice/other.pdf"
    kept, _, dropped = names_filter.filter_nextcloud([json.dumps(entry) + "\n"])
    assert dropped == 0
    assert _hits(kept) == 1


def test_main_writes_the_target_and_prints_both_numbers(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "out.txt"
    assert names_filter.main(["names_filter.py", "php", str(FIXTURES / "php-server.log"), str(target)]) == 0
    assert capsys.readouterr().out.split() == ["3", "3"]
    assert _hits(target.read_text(encoding="utf-8").splitlines()) == 0
    assert names_filter.main(["names_filter.py", "other", "a", "b"]) == 2
