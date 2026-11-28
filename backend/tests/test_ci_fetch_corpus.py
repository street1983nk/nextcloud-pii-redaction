"""ci/fetch_corpus.py without the network: the table of the plan, host allowlist, size, checksum, cache.

The table is checked against the table of plan 02-24 ("Nachtrag Task 3"), the
owner's measured values, not against the script itself.
"""

import hashlib
import io
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.conftest import REPO_ROOT, ci_module, repo_text

PLAN = REPO_ROOT / ".planning" / "phases" / "02-sicherer-dateieingang-und-kindprozess-sandbox" / "02-24-PLAN.md"
ROW = re.compile(
    r"^\| (?P<name>[^|]+?) \| (?P<size>\d+) \| (?P<sha>[0-9a-f]{64}) \| (?P<licence>[^|]+?) \| (?P<url>https://\S+) \|$"
)


def fc() -> ModuleType:
    return ci_module("fetch_corpus")


def plan_rows() -> list[dict[str, str]]:
    """The rows of the test set table in the plan, as the owner measured them."""
    return [match.groupdict() for line in repo_text(PLAN).splitlines() if (match := ROW.match(line))]


class Response(io.BytesIO):
    """A download; counts how many bytes the reader took."""

    def __init__(self, data: bytes, url: str) -> None:
        super().__init__(data)
        self.url = url
        self.taken = 0

    def geturl(self) -> str:
        return self.url

    def read(self, size: int | None = -1) -> bytes:
        block = super().read(size)
        self.taken += len(block)
        return block


class FakeOpener:
    """Answers every URL with the bytes in files; remembers the requests."""

    def __init__(self, files: dict[str, bytes], final_url: dict[str, str] | None = None) -> None:
        self.files = files
        self.final_url = final_url or {}
        self.asked: list[urllib.request.Request] = []
        self.responses: list[Response] = []

    def open(self, req: urllib.request.Request, timeout: float) -> Response:
        assert timeout > 0
        self.asked.append(req)
        url = req.get_full_url()
        response = Response(self.files[url], self.final_url.get(url, url))
        self.responses.append(response)
        return response


class BrokenOpener:
    def open(self, _req: object, timeout: float) -> Response:
        assert timeout > 0
        raise OSError("no route")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _doc(name: str, data: bytes, host: str = "dserver.bundestag.de") -> Any:
    return fc().Document(name, f"https://{host}/x/{name}", len(data), _sha(data), "test")


def _table(monkeypatch: pytest.MonkeyPatch, *docs: Any) -> tuple[Any, ...]:
    monkeypatch.setattr(fc(), "DOCUMENTS", docs)
    return docs


# -- the table ---------------------------------------------------------------------------


def test_the_table_is_the_table_of_the_plan() -> None:
    rows = plan_rows()
    assert len(rows) == 10, "the plan table was not found or changed its shape"
    table = {doc.name: doc for doc in fc().DOCUMENTS}
    assert sorted(table) == sorted(row["name"] for row in rows)
    for row in rows:
        doc = table[row["name"]]
        assert doc.url == row["url"], doc.name
        assert doc.size == int(row["size"]), doc.name
        assert doc.sha256 == row["sha"], doc.name
        assert doc.licence == row["licence"], doc.name


def test_seven_docx_and_three_pdf_every_url_allowed_and_every_host_used() -> None:
    formats = sorted(doc.format for doc in fc().DOCUMENTS)
    assert formats == ["docx"] * 7 + ["pdf"] * 3
    for doc in fc().DOCUMENTS:
        assert fc().host_allowed(doc.url), doc.url
        assert re.fullmatch(r"[0-9a-f]{64}", doc.sha256)
        assert doc.size > 0
        assert "/" not in doc.name
        assert not doc.name.startswith(".")
    hosts = {urllib.parse.urlsplit(doc.url).hostname for doc in fc().DOCUMENTS}
    assert hosts == set(fc().ALLOWED_HOSTS)


def test_the_pdfs_are_marked_runtime_only_and_never_distributed() -> None:
    for doc in fc().DOCUMENTS:
        if doc.format == "pdf":
            assert "nur Laufzeit-Download, nicht verteilt" in doc.licence, doc.name
    source = (REPO_ROOT / "ci" / "fetch_corpus.py").read_text(encoding="utf-8")
    assert "never redistributed" in source
    assert "Licence unclear: runtime download only, never distributed" in source


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("https://dserver.bundestag.de/btd/x.pdf", True),
        ("https://transparenz.schleswig-holstein.de/x.docx", True),
        ("https://www.bundesbericht-forschung-innovation.de/files/x.pdf", True),
        ("https://www.bundesbericht-forschung-innovation.de:443/x.pdf", True),
        ("https://cdn.bundestag.de/x.pdf", True),
        ("http://dserver.bundestag.de/x.pdf", False),
        ("https://dserver.bundestag.de:8443/x.pdf", False),
        ("https://dserver.bundestag.de:notaport/x.pdf", False),
        ("https://user@dserver.bundestag.de/x.pdf", False),
        ("https://user:pw@dserver.bundestag.de/x.pdf", False),
        ("https://evilbundestag.de/x.pdf", False),
        ("https://bundestag.de.evil.example/x.pdf", False),
        ("https://dserver.bundestag.de.evil.example/x.pdf", False),
        ("https://xschleswig-holstein.de/x.docx", False),
        ("https://huggingface.co/x", False),
        ("ftp://dserver.bundestag.de/x.pdf", False),
        ("", False),
    ],
)
def test_the_host_allowlist(url: str, allowed: bool) -> None:
    assert fc().host_allowed(url) is allowed


def test_a_redirect_to_a_foreign_host_is_refused() -> None:
    handler = fc().AllowlistRedirects()
    req = urllib.request.Request("https://dserver.bundestag.de/x.pdf")
    with pytest.raises(fc().Refused):
        handler.redirect_request(req, None, 301, "Moved", {}, "https://evil.example/x.pdf")
    with pytest.raises(fc().Refused):
        handler.redirect_request(req, None, 301, "Moved", {}, "http://dserver.bundestag.de/x.pdf")


def test_control_a_redirect_on_the_same_host_is_followed_with_the_user_agent() -> None:
    # The BuFI URL answers 301 to a path on its own host (checked 28.11.).
    handler = fc().AllowlistRedirects()
    doc = next(doc for doc in fc().DOCUMENTS if doc.name.startswith("BMBF"))
    target = "https://www.bundesbericht-forschung-innovation.de/wp-content/uploads/x.pdf"
    followed = handler.redirect_request(fc().request(doc), None, 301, "Moved", {}, target)
    assert followed.get_full_url() == target
    assert followed.get_header("User-agent") == fc().USER_AGENT


def test_the_user_agent_is_generic() -> None:
    agent = fc().USER_AGENT
    assert "python" not in agent.lower()
    assert "pii" not in agent.lower()
    assert "redaction" not in agent.lower()
    assert fc().request(fc().DOCUMENTS[0]).get_header("User-agent") == agent


# -- fetching ----------------------------------------------------------------------------


def test_positive_control_matching_files_land_with_a_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a, b = b"PK docx bytes", b"%PDF-1.7 bytes"
    docs = _table(monkeypatch, _doc("a.docx", a, "transparenz.schleswig-holstein.de"), _doc("b.pdf", b))
    opener = FakeOpener({docs[0].url: a, docs[1].url: b})

    assert fc().main([str(tmp_path)], opener) == 0

    assert (tmp_path / "a.docx").read_bytes() == a
    assert (tmp_path / "b.pdf").read_bytes() == b
    assert not list(tmp_path.glob("*.tmp"))
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert [entry["name"] for entry in manifest["files"]] == ["a.docx", "b.pdf"]
    assert manifest["files"][1] == {
        "name": "b.pdf",
        "url": docs[1].url,
        "size": len(b),
        "sha256": _sha(b),
        "licence": "test",
        "format": "pdf",
    }
    assert all(req.get_header("User-agent") == fc().USER_AGENT for req in opener.asked)


def test_a_wrong_hash_stops_the_run_and_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    good = b"good bytes"
    doc = _doc("a.pdf", good)
    _table(monkeypatch, doc, _doc("b.pdf", b"later"))
    opener = FakeOpener({doc.url: b"evil bytes"})

    assert fc().main([str(tmp_path)], opener) == 2

    assert sorted(path.name for path in tmp_path.iterdir()) == []
    assert len(opener.asked) == 1
    assert "refused" in capsys.readouterr().err


def test_a_download_larger_than_the_table_stops_early(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    good = b"x" * 10
    doc = _doc("a.pdf", good)
    _table(monkeypatch, doc)
    monkeypatch.setattr(fc(), "BLOCK", 4)
    opener = FakeOpener({doc.url: b"x" * 1000})

    assert fc().main([str(tmp_path)], opener) == 2

    assert not (tmp_path / "a.pdf").exists()
    assert not (tmp_path / "a.pdf.tmp").exists()
    # The reader stopped right after the limit, it did not take the rest.
    assert opener.responses[0].taken <= 12


def test_a_short_download_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    good = b"0123456789"
    doc = _doc("a.pdf", good)
    _table(monkeypatch, doc)
    assert fc().main([str(tmp_path)], FakeOpener({doc.url: good[:5]})) == 2
    assert not (tmp_path / "a.pdf").exists()


def test_a_final_url_on_a_foreign_host_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    good = b"bytes"
    doc = _doc("a.pdf", good)
    _table(monkeypatch, doc)
    opener = FakeOpener({doc.url: good}, final_url={doc.url: "https://evil.example/a.pdf"})
    assert fc().main([str(tmp_path)], opener) == 2
    assert not (tmp_path / "a.pdf").exists()


def test_a_table_url_outside_the_allowlist_is_never_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    good = b"bytes"
    doc = _doc("a.pdf", good, host="evil.example")
    _table(monkeypatch, doc)
    opener = FakeOpener({doc.url: good})
    assert fc().main([str(tmp_path)], opener) == 2
    assert opener.asked == []


def test_a_cached_file_with_the_right_hash_is_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    good = b"cached"
    doc = _doc("a.pdf", good)
    _table(monkeypatch, doc)
    opener = FakeOpener({doc.url: good})
    assert fc().main([str(tmp_path)], opener) == 0
    opener.asked.clear()
    assert fc().main([str(tmp_path)], opener) == 0
    assert opener.asked == []


def test_a_tampered_cached_file_is_fetched_again_and_replaced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    good = b"original"
    doc = _doc("a.pdf", good)
    _table(monkeypatch, doc)
    (tmp_path / "a.pdf").write_bytes(b"tampere")  # one byte short and different
    opener = FakeOpener({doc.url: good})
    assert fc().main([str(tmp_path)], opener) == 0
    assert len(opener.asked) == 1
    assert (tmp_path / "a.pdf").read_bytes() == good


def test_a_tampered_cache_that_cannot_be_repaired_is_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    good = b"original"
    doc = _doc("a.pdf", good)
    _table(monkeypatch, doc)
    (tmp_path / "a.pdf").write_bytes(b"evil!!!!")  # same size, other bytes
    assert fc().main([str(tmp_path)], FakeOpener({doc.url: b"still evil"})) == 2
    assert not (tmp_path / "a.pdf").exists()


def test_a_network_error_is_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _table(monkeypatch, _doc("a.pdf", b"x"))
    assert fc().main([str(tmp_path)], BrokenOpener()) == 2
    assert "could not be fetched (OSError)" in capsys.readouterr().err


def test_wrong_arguments_are_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert fc().main([]) == 2
    assert fc().main(["a", "b"]) == 2
    assert "usage" in capsys.readouterr().err
