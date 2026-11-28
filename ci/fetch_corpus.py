"""Real public authority documents for the LibreOffice memory measurement, fetched on the runner with fixed hashes.

usage: python3 ci/fetch_corpus.py <outdir>

Owner rule 28.11.2026: the address space cap of soffice (D-02-13, plan 02-24,
"Nachtrag Task 3") is measured with real public documents, not only with made
ones. The table holds ten files with a fixed URL, size and sha256 (hashed on
28.11.2026): seven DOCX of the Schleswig-Holstein transparency portal
(cc-by-nd/4.0) and three PDFs of the Bundestag and of the federal research
report BuFI 2024.

Test corpora never go into the repository (CLAUDE.md): the files live only in
the runner cache of sandbox.yml and in the container that measures them;
nothing here copies them into the tree, an artifact or the image. The licence
of the three PDFs is not settled (an official work under section 5 UrhG has to
be checked file by file, and for the BuFI report it is unclear): they are
downloaded at run time only and never redistributed, not even as a derived
file (sandbox.yml keeps the DOCX and ODT made from them in RUNNER_TEMP).

Every host on the way, redirects included, has to be https on port 443 and
on the allowlist. Checked on 28.11.2026: the BuFI URL answers 301 with a path
on the same host, the other nine answer 200 directly. The BuFI host refuses
the default user agent of urllib (403), so every request names a generic one.
A download stops as soon as it grows past the fixed size; it is written to
<name>.tmp while it is hashed and moved into place only when size and hash
match. A file that is already there with the right hash is kept (the cache of
sandbox.yml); sandbox.yml calls the script on every run, so a cached file is
hashed again each time. manifest.json lists the table for the container test.

Standard library only. A refusal or an error names the file and the reason on
stderr (of a URL only its host, never path or query), exit 2.
"""

import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO, Final

BLOCK: Final = 1024 * 1024
TIMEOUT_S: Final = 60
MANIFEST: Final = "manifest.json"
# Generic on purpose: names no project and no person (the BuFI host answers 403 to Python-urllib).
USER_AGENT: Final = "Mozilla/5.0"

ALLOWED_HOSTS: Final = frozenset(
    {
        "transparenz.schleswig-holstein.de",
        "dserver.bundestag.de",
        "www.bundesbericht-forschung-innovation.de",
    }
)
# A redirect may stay within the domain of its source (checked 28.11.: none leaves its host).
ALLOWED_SUFFIXES: Final = (".schleswig-holstein.de", ".bundestag.de", ".bundesbericht-forschung-innovation.de")

CC_BY_ND: Final = "cc-by-nd/4.0"
# The PDFs: not settled, see the module text. Runtime download only, never distributed.
OFFICIAL_WORK: Final = "amtliches Werk nach § 5 UrhG prüfen; nur Laufzeit-Download, nicht verteilt"
SH: Final = "https://transparenz.schleswig-holstein.de/dataset"


@dataclass(frozen=True, slots=True)
class Document:
    name: str
    url: str
    size: int
    sha256: str
    licence: str

    @property
    def format(self) -> str:
        return self.name.rsplit(".", 1)[-1]


DOCUMENTS: Final = (
    Document(
        "sh-1.docx",
        f"{SH}/32d3de61-677f-4f9e-896c-dec8172f1da9/resource/d7ecda94-5ebd-409b-b66d-bd7eeb14bbfe/download/"
        "20210325-antragvordruck_2021_wertgrnland-grnlandlebensru.docx",
        46088,
        "83acc7a8428d3ece2be04857d1b4d04d6c098a69923023063e12bfb1f100f414",
        CC_BY_ND,
    ),
    Document(
        "sh-2.docx",
        f"{SH}/0b73e692-3c0a-49ba-b60d-f40cd8151a45/resource/4af93653-e723-4094-bc4d-ff802398e352/download/"
        "20210325-vns-antrag-2021_-online_barrierefrei.docx",
        53862,
        "50b39b954c348c2472a981d76a05e3f167c1e64a9a5a94fbe304bc564823796a",
        CC_BY_ND,
    ),
    Document(
        "sh-3.docx",
        f"{SH}/4fe97191-83f4-4fec-bce2-5b7bb2a5be1b/resource/dc893e9d-ed4b-4fdb-87eb-b91850b015a7/download/"
        "richtlinie-zur-forderung-des-internationalen7909188318303235339.docx",
        29612,
        "ebba462053daa2f907268c86041f2853c04c933598617de9d7c2c54440d3768d",
        CC_BY_ND,
    ),
    Document(
        "sh-4.docx",
        f"{SH}/69f72ee1-09d9-47bd-9a2c-083cba62880d/resource/6428d404-2a0e-45b3-8e86-4a782bc08661/download/"
        "rl-anerkennung-ab-2020-gesamtfassung9066038611978143929.docx",
        28530,
        "e55ea5ecbd9d98e64ced51f60cc26d482bf5295dd932470a0d635936adf8e590",
        CC_BY_ND,
    ),
    Document(
        "sh-5.docx",
        f"{SH}/1e4013db-6dd0-4eb2-9a3e-1ce988b9ec8a/resource/c9cf13c7-8b38-464b-9512-886f5004ab8f/download/"
        "rl_barrierefrei-neu8796571456658981455.docx",
        29240,
        "b89da05d80bfcb4cd79d9ae5e43aaa49e2c91e2f7bb9f13b60433e11f970fe9e",
        CC_BY_ND,
    ),
    Document(
        "sh-6.docx",
        f"{SH}/b1343bfa-29c4-4d2f-8f84-2307690968ea/resource/61817310-0e6e-429d-bb99-0258ab450e12/download/"
        "2020_01_anfrage-externe-projekte7978262383865973361.docx",
        44166,
        "e63a7ab7d28dabccaf41afc1c2b7fea1bac9cb78ef737c23eba97f68d39c3f09",
        CC_BY_ND,
    ),
    Document(
        "sh-7.docx",
        f"{SH}/103dcbc4-7037-4ac1-8042-ec9b9fc6876a/resource/04f1a58b-e8b1-4d15-8eff-250158b81fc6/download/"
        "20200113_schriftenliste1965049653079296351.docx",
        37201,
        "e9201a4cd48994c48c9489b401aed132b3ddbce092a71103624d71666bc684ff",
        CC_BY_ND,
    ),
    # Licence unclear: runtime download only, never distributed (owner 28.11.).
    Document(
        "BMBF_BuFI-2024_Hauptband.pdf",
        "https://www.bundesbericht-forschung-innovation.de/files/BMBF_BuFI-2024_Hauptband.pdf",
        42379911,
        "531eb1088761403da79d0307fc851f9b001b55963c1d2b221d37770010c52620",
        OFFICIAL_WORK,
    ),
    Document(
        "1913500.pdf",
        "https://dserver.bundestag.de/btd/19/135/1913500.pdf",
        3890344,
        "b8f2d39b00cb4a81d02b77bf519c20fa035edb0833a2c039d20df4df6a16caa2",
        OFFICIAL_WORK,
    ),
    Document(
        "1800107.pdf",
        "https://dserver.bundestag.de/btd/18/001/1800107.pdf",
        24991580,
        "756ca21fbcf248f6c5d7f0064b961fe5eaf81b6dc0d14b768750c7752f8a857a",
        OFFICIAL_WORK,
    ),
)


class Refused(Exception):
    """A host, a size or a hash that is not allowed; str() is the reason, safe for a public log."""


def host_of(url: str) -> str:
    """Only the host of url, lowercased.

    Path and query can carry tokens of a login page a redirect points to, and
    stderr ends up in a public CI log, so a message never prints more than the host.
    """
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return "?"


def host_allowed(url: str) -> bool:
    """https, port 443, no user part, and a host of the allowlist or below one of its domains."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.username is not None or parts.password is not None:
        return False
    try:
        port = parts.port
    except ValueError:
        return False
    if port not in {None, 443}:
        return False
    host = (parts.hostname or "").lower()
    return host in ALLOWED_HOSTS or any(host.endswith(suffix) for suffix in ALLOWED_SUFFIXES)


class AllowlistRedirects(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only to a URL host_allowed accepts."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        if not host_allowed(newurl):
            raise Refused(f"redirect to host {host_of(newurl)}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def default_opener() -> Any:
    return urllib.request.build_opener(AllowlistRedirects())


def request(document: Document) -> urllib.request.Request:
    # https only: every table URL and every redirect passes host_allowed before it is opened.
    return urllib.request.Request(document.url, headers={"User-Agent": USER_AGENT})  # noqa: S310


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(BLOCK):
            digest.update(block)
    return digest.hexdigest()


def copy_limited(source: BinaryIO, target: Path, limit: int) -> tuple[str, int]:
    """Copy and hash source into target; Refused as soon as more than limit bytes arrive."""
    digest = hashlib.sha256()
    size = 0
    with target.open("wb") as handle:
        while block := source.read(BLOCK):
            size += len(block)
            if size > limit:
                raise Refused(f"larger than {limit} bytes")
            digest.update(block)
            handle.write(block)
    return digest.hexdigest(), size


def cached(document: Document, outdir: Path) -> bool:
    target = outdir / document.name
    return target.is_file() and target.stat().st_size == document.size and sha256_of(target) == document.sha256


def fetch(document: Document, outdir: Path, opener: Any) -> None:
    """One file into place, or Refused with nothing of it left behind."""
    if cached(document, outdir):
        return
    if not host_allowed(document.url):
        raise Refused(f"host {host_of(document.url)}")
    target = outdir / document.name
    target.unlink(missing_ok=True)
    partial = target.with_name(target.name + ".tmp")
    try:
        with opener.open(request(document), timeout=TIMEOUT_S) as response:
            if not host_allowed(response.geturl()):
                raise Refused(f"final host {host_of(response.geturl())}")
            digest, size = copy_limited(response, partial, document.size)
        if size != document.size:
            raise Refused(f"size {size} of {document.size} bytes")
        if digest != document.sha256:
            raise Refused("checksum")
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def manifest(documents: tuple[Document, ...]) -> dict[str, object]:
    """What the container test reads: every file with its format, size, hash, licence and source."""
    return {
        "files": [{**asdict(document), "format": document.format} for document in documents],
    }


def write_manifest(outdir: Path, documents: tuple[Document, ...]) -> None:
    target = outdir / MANIFEST
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(manifest(documents), indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, target)


def main(argv: list[str], opener: Any = None) -> int:
    if len(argv) != 1:
        sys.stderr.write("usage: python3 ci/fetch_corpus.py <outdir>\n")
        return 2
    outdir = Path(argv[0])
    opener = opener if opener is not None else default_opener()
    current = "outdir"  # what a message names: the file being worked on
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        for document in DOCUMENTS:
            current = document.name
            fetch(document, outdir, opener)
        current = MANIFEST
        write_manifest(outdir, DOCUMENTS)
    except Refused as refusal:
        sys.stderr.write(f"{current} was refused ({refusal})\n")
        return 2
    except OSError as error:
        sys.stderr.write(f"{current} could not be fetched ({type(error).__name__})\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
