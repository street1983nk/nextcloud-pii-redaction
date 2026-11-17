"""The models of the network proof, fetched on the runner and checked, never baked into the image.

usage: python3 ci/fetch_models.py <outdir>

Six files with a fixed URL and the sha256 from CLAUDE.md (D-02-09: models only
in the CI cache): the de_core_news_lg 3.8.0 wheel and the five files of
GLiNER2 fastino/gliner2-privacy-filter-PII-multi at commit 1cb41660. Every
host on the way, redirects included, has to be on the allowlist; a file is
written to <name>.tmp while it is hashed and moved into place only when the
hash matches. A file that is already there with the right hash is kept (the
cache of sandbox.yml). The wheel is unpacked to its model folder only, after
every member name was checked against zip slip.

Layout: <out>/spacy/de_core_news_lg-3.8.0/ and <out>/gliner2/<commit>/...
Standard library only. Errors go to stderr, exit 2.
"""

import hashlib
import os
import sys
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Final

GLINER_REPO: Final = "fastino/gliner2-privacy-filter-PII-multi"
GLINER_COMMIT: Final = "1cb4166094dc58fa8d836429f060d6c95f62b495"
SPACY_WHEEL: Final = "de_core_news_lg-3.8.0-py3-none-any.whl"
SPACY_MODEL_DIR: Final = "de_core_news_lg/de_core_news_lg-3.8.0/"
SPACY_TARGET: Final = "spacy/de_core_news_lg-3.8.0"
BLOCK: Final = 1024 * 1024

ALLOWED_HOSTS: Final = frozenset({"github.com", "release-assets.githubusercontent.com", "huggingface.co"})
# The Hugging Face CDN host depends on the region (CLAUDE.md "Host-Allowlist").
ALLOWED_SUFFIXES: Final = (".cdn.hf.co",)


@dataclass(frozen=True, slots=True)
class Model:
    url: str
    sha256: str
    target: str


def _hf(name: str, sha256: str) -> Model:
    return Model(
        url=f"https://huggingface.co/{GLINER_REPO}/resolve/{GLINER_COMMIT}/{name}",
        sha256=sha256,
        target=f"gliner2/{GLINER_COMMIT}/{name}",
    )


MODELS: Final = (
    Model(
        url=f"https://github.com/explosion/spacy-models/releases/download/de_core_news_lg-3.8.0/{SPACY_WHEEL}",
        sha256="36fda650e476b54d5e87803635e36dadd1e8e034c4b5962088586d684f4c9fed",
        target=f"spacy/{SPACY_WHEEL}",
    ),
    _hf("model.safetensors", "0280f6f39f6012da50b6640bad438d9b7e763a1b0102094115d1b710c4dd79b6"),
    _hf("tokenizer.json", "f6df10ec83bea993035b2dd7c39345a3d4fcf23421c2adb6cb4ffc1e6d1bc4b5"),
    _hf("config.json", "164f17362bcf9d114067d3465e7374bfdd79ce6b605acb745de5a49dabb9595c"),
    _hf("encoder_config/config.json", "f27dd63cc43a248d2566f0b6ad7a115db353676ce0561dcbca45bac766464c1a"),
    _hf("tokenizer_config.json", "233beed1f1095cccfc7907cde31a8d90a0c6aa4fdfaf6493f8e55fd162e81ae6"),
)


class Refused(Exception):
    """A host, a hash or a member name that is not allowed."""


def host_allowed(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https":
        return False
    return host in ALLOWED_HOSTS or any(host.endswith(suffix) for suffix in ALLOWED_SUFFIXES)


class AllowlistRedirects(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only to a host on the allowlist."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        if not host_allowed(newurl):
            raise Refused
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def default_opener() -> Any:
    return urllib.request.build_opener(AllowlistRedirects())


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(BLOCK):
            digest.update(block)
    return digest.hexdigest()


def _copy_hashed(source: BinaryIO, target: Path) -> str:
    digest = hashlib.sha256()
    with target.open("wb") as handle:
        while block := source.read(BLOCK):
            digest.update(block)
            handle.write(block)
    return digest.hexdigest()


def fetch(model: Model, outdir: Path, opener: Any) -> None:
    """One file into place, or Refused with nothing left behind."""
    target = outdir / model.target
    if target.is_file() and sha256_of(target) == model.sha256:
        return
    if not host_allowed(model.url):
        raise Refused
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".tmp")
    try:
        with opener.open(model.url, timeout=60) as response:
            if not host_allowed(response.geturl()):
                raise Refused
            digest = _copy_hashed(response, partial)
        if digest != model.sha256:
            raise Refused
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def _safe_member(name: str) -> bool:
    if not name or name.startswith(("/", "\\")) or "\\" in name or ":" in name:
        return False
    return ".." not in PurePosixPath(name).parts


def unpack_wheel(wheel: Path, outdir: Path) -> Path:
    """The model folder of the wheel under <out>/spacy/, checked member by member."""
    destination = outdir / SPACY_TARGET
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if not all(_safe_member(name) for name in names):
            raise Refused
        members = [name for name in names if name.startswith(SPACY_MODEL_DIR) and not name.endswith("/")]
        if not members:
            raise Refused
        for name in members:
            target = destination / name[len(SPACY_MODEL_DIR) :]
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, target.open("wb") as handle:
                while block := source.read(BLOCK):
                    handle.write(block)
    return destination


def main(argv: list[str], opener: Any = None) -> int:
    if len(argv) != 1:
        sys.stderr.write("usage: python3 ci/fetch_models.py <outdir>\n")
        return 2
    outdir = Path(argv[0])
    opener = opener if opener is not None else default_opener()
    try:
        for model in MODELS:
            fetch(model, outdir, opener)
        unpack_wheel(outdir / MODELS[0].target, outdir)
    except Refused:
        sys.stderr.write("a model file was refused (host, checksum or member name)\n")
        return 2
    except OSError as error:
        sys.stderr.write(f"a model file could not be fetched ({type(error).__name__})\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
