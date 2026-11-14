"""The PHP server log and data/nextcloud.log as ci/canary.sh searches them for the test file names.

Usage: names_filter.py php|nextcloud <source> <target>; writes the log to
<target> without what is named below and prints two numbers: the request
lines taken out (or url fields replaced) and the NotFound lines dropped.

What is taken out is the request of the test client itself, never a line the
app or the backend wrote:

- php: the access line of a WebDAV request (its path is the one the test
  client chose), and the core exception line ``Sabre\\DAV\\Exception\\NotFound``
  "File with name P could not be located" only when the next access line of
  the same worker process is a 404 of a WebDAV request on exactly that path P.
- nextcloud: the "url" field of an entry made during a WebDAV request is
  replaced, and an entry is dropped only when it is the uncaught Sabre
  NotFound of that very request (the path in the message equals the decoded
  path of its url).

Such a NotFound comes from a test that asks for a missing path on purpose:
ci/seed.sh proves that carol cannot read the file behind the ACL (run
43615560742). An exception of any other kind, a NotFound on another path and
every line of the app that names a file stay in and are counted.
"""

import itertools
import json
import re
import sys
from urllib.parse import unquote

NOT_FOUND = "Sabre\\DAV\\Exception\\NotFound"
# The class name as it stands in the JSON text of a log line (backslashes escaped).
NOT_FOUND_RAW = json.dumps(NOT_FOUND)
MESSAGE = re.compile(r"^File with name (/.*) could not be located$")
# [pid] [Sat Nov 14 16:34:47 2026] rest: the PHP built-in server with workers.
PREFIX = re.compile(r"^\[(\d+)\] \[[^\]]*\] (.*)$")
ACCESS = re.compile(r"^\S+:\d+ \[(\d{3})\]: ([A-Z]+) (\S+)")
DAV_FILES = re.compile(r"^/remote\.php/dav/files/[^/]+(/.*)$")
DAV_LINE = re.compile(r"\]: [A-Z]+ /remote\.php/dav/")


def dav_path(url: str) -> str | None:
    """The path below the user root of a WebDAV files url, decoded, or None."""
    match = DAV_FILES.match(url.split("?", 1)[0])
    return None if match is None else unquote(match.group(1)).rstrip("/")


def not_found_path(exception: object) -> str | None:
    """P of a Sabre NotFound "File with name P could not be located", or None."""
    if not isinstance(exception, dict) or exception.get("Exception") != NOT_FOUND:
        return None
    match = MESSAGE.match(str(exception.get("Message", "")))
    return None if match is None else match.group(1).rstrip("/")


def _answered_with_404(parsed: list[re.Match[str] | None], index: int, pid: str, path: str) -> bool:
    """True when the next access line of the same process is a WebDAV 404 on path."""
    for other in itertools.islice(parsed, index + 1, None):
        if other is None or other.group(1) != pid:
            continue
        access = ACCESS.match(other.group(2))
        if access is not None:
            return access.group(1) == "404" and dav_path(access.group(3)) == path
    return False


def filter_php(lines: list[str]) -> tuple[list[str], int, int]:
    """The PHP server log without WebDAV access lines and the NotFound of such a 404."""
    parsed = [PREFIX.match(line.rstrip("\n")) for line in lines]
    kept: list[str] = []
    requests = dropped = 0
    for index, line in enumerate(lines):
        if DAV_LINE.search(line):
            requests += 1
            continue
        match = parsed[index]
        if match is not None and NOT_FOUND_RAW in line:
            try:
                path = not_found_path(json.loads(match.group(2)))
            except ValueError:
                path = None
            if path is not None and _answered_with_404(parsed, index, match.group(1), path):
                dropped += 1
                continue
        kept.append(line)
    return kept, requests, dropped


def filter_nextcloud(lines: list[str]) -> tuple[list[str], int, int]:
    """data/nextcloud.log without the url of WebDAV requests and their own NotFound."""
    kept: list[str] = []
    requests = dropped = 0
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            kept.append(line)
            continue
        if not isinstance(entry, dict) or not str(entry.get("url", "")).startswith("/remote.php/dav/"):
            kept.append(line)
            continue
        path = not_found_path(entry.get("exception"))
        if path is not None and entry.get("message") == "Uncaught exception" and dav_path(str(entry["url"])) == path:
            dropped += 1
            continue
        requests += 1
        entry["url"] = "(WebDAV request of the test client)"
        kept.append(json.dumps(entry, ensure_ascii=False) + "\n")
    return kept, requests, dropped


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] not in ("php", "nextcloud"):
        sys.stderr.write("usage: names_filter.py php|nextcloud <source> <target>\n")
        return 2
    with open(argv[2], encoding="utf-8", errors="replace") as source:
        lines = source.readlines()
    kept, requests, dropped = filter_php(lines) if argv[1] == "php" else filter_nextcloud(lines)
    with open(argv[3], "w", encoding="utf-8") as target:
        target.writelines(kept)
    print(requests, dropped)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
