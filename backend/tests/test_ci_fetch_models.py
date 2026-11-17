"""ci/fetch_models.py without the network: fixed table, host allowlist, checksum, zip slip, nothing in the image."""

import hashlib
import importlib.util
import io
import re
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.conftest import BACKEND_ROOT, REPO_ROOT


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ci_fetch_models", REPO_ROOT / "ci" / "fetch_models.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fm = _module()


class Response(io.BytesIO):
    def __init__(self, data: bytes, url: str) -> None:
        super().__init__(data)
        self.url = url

    def geturl(self) -> str:
        return self.url


class FakeOpener:
    """Answers every URL with the bytes in files; remembers what was asked."""

    def __init__(self, files: dict[str, bytes], final_url: dict[str, str] | None = None) -> None:
        self.files = files
        self.final_url = final_url or {}
        self.asked: list[str] = []

    def open(self, url: str, timeout: float) -> Response:
        assert timeout > 0
        self.asked.append(url)
        return Response(self.files[url], self.final_url.get(url, url))


def _wheel(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# -- the table -------------------------------------------------------------------------


def test_the_table_holds_exactly_the_six_files_of_claude_md() -> None:
    claude = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert len(fm.MODELS) == 6
    for model in fm.MODELS:
        assert re.fullmatch(r"[0-9a-f]{64}", model.sha256)
        assert model.sha256 in claude, model.target
        assert fm.host_allowed(model.url), model.url
    names = sorted(model.target.rsplit("/", 1)[-1] for model in fm.MODELS)
    assert names == sorted(
        [
            "de_core_news_lg-3.8.0-py3-none-any.whl",
            "model.safetensors",
            "tokenizer.json",
            "config.json",
            "config.json",
            "tokenizer_config.json",
        ]
    )
    assert all(fm.GLINER_COMMIT in model.url for model in fm.MODELS[1:])
    assert fm.GLINER_COMMIT in claude


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("https://huggingface.co/x", True),
        ("https://us.aws.cdn.hf.co/x", True),
        ("https://release-assets.githubusercontent.com/x", True),
        ("https://github.com/x", True),
        ("http://huggingface.co/x", False),
        ("https://evil.example/x", False),
        ("https://huggingface.co.evil.example/x", False),
        ("https://cdn.hf.co.evil.example/x", False),
        ("https://xcdn.hf.co/x", False),
    ],
)
def test_the_host_allowlist(url: str, allowed: bool) -> None:
    assert fm.host_allowed(url) is allowed


def test_a_redirect_to_a_foreign_host_is_refused() -> None:
    handler = fm.AllowlistRedirects()
    with pytest.raises(fm.Refused):
        handler.redirect_request(None, None, 302, "Found", {}, "https://evil.example/model")


# -- fetching ---------------------------------------------------------------------------


def _small_table(monkeypatch: pytest.MonkeyPatch, data: bytes, wheel: bytes) -> tuple[Any, ...]:
    table = (
        fm.Model(url="https://github.com/w.whl", sha256=_sha(wheel), target=f"spacy/{fm.SPACY_WHEEL}"),
        fm.Model(url="https://huggingface.co/a/config.json", sha256=_sha(data), target="gliner2/c/config.json"),
    )
    monkeypatch.setattr(fm, "MODELS", table)
    return table


GOOD_WHEEL = _wheel(
    {
        "de_core_news_lg/__init__.py": b"",
        "de_core_news_lg/de_core_news_lg-3.8.0/meta.json": b"{}",
        "de_core_news_lg/de_core_news_lg-3.8.0/ner/model": b"weights",
        "de_core_news_lg-3.8.0.dist-info/METADATA": b"x",
    }
)


def test_positive_control_matching_files_land_and_the_wheel_is_unpacked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = _small_table(monkeypatch, b'{"a": 1}', GOOD_WHEEL)
    opener = FakeOpener({table[0].url: GOOD_WHEEL, table[1].url: b'{"a": 1}'})

    assert fm.main([str(tmp_path)], opener) == 0

    assert (tmp_path / "gliner2/c/config.json").read_bytes() == b'{"a": 1}'
    model = tmp_path / fm.SPACY_TARGET
    assert (model / "meta.json").read_bytes() == b"{}"
    assert (model / "ner/model").read_bytes() == b"weights"
    assert not (model / "__init__.py").exists()
    assert not list(tmp_path.rglob("*.tmp"))


def test_a_cached_file_with_the_right_hash_is_not_fetched_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = _small_table(monkeypatch, b"cfg", GOOD_WHEEL)
    opener = FakeOpener({table[0].url: GOOD_WHEEL, table[1].url: b"cfg"})
    assert fm.main([str(tmp_path)], opener) == 0
    opener.asked.clear()
    assert fm.main([str(tmp_path)], opener) == 0
    assert opener.asked == []


def test_a_wrong_checksum_leaves_nothing_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    table = _small_table(monkeypatch, b"expected", GOOD_WHEEL)
    opener = FakeOpener({table[0].url: GOOD_WHEEL, table[1].url: b"tampered"})

    assert fm.main([str(tmp_path)], opener) == 2

    assert not (tmp_path / "gliner2/c/config.json").exists()
    assert not list(tmp_path.rglob("*.tmp"))


def test_a_response_that_ended_on_a_foreign_host_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    table = _small_table(monkeypatch, b"cfg", GOOD_WHEEL)
    opener = FakeOpener(
        {table[0].url: GOOD_WHEEL, table[1].url: b"cfg"},
        final_url={table[0].url: "https://evil.example/w.whl"},
    )
    assert fm.main([str(tmp_path)], opener) == 2
    assert not (tmp_path / "spacy" / fm.SPACY_WHEEL).exists()


@pytest.mark.parametrize(
    "bad_name",
    [
        "../escape.txt",
        "de_core_news_lg/de_core_news_lg-3.8.0/../../../escape.txt",
        "/etc/escape.txt",
        "de_core_news_lg\\..\\escape.txt",
        "C:/escape.txt",
    ],
)
def test_a_wheel_with_a_zip_slip_name_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_name: str
) -> None:
    wheel = _wheel({"de_core_news_lg/de_core_news_lg-3.8.0/meta.json": b"{}", bad_name: b"evil"})
    table = _small_table(monkeypatch, b"cfg", wheel)
    opener = FakeOpener({table[0].url: wheel, table[1].url: b"cfg"})

    assert fm.main([str(tmp_path)], opener) == 2

    assert not (tmp_path.parent / "escape.txt").exists()
    assert not (tmp_path / fm.SPACY_TARGET).exists()


def test_the_usage_error() -> None:
    assert fm.main([]) == 2


# -- the image ---------------------------------------------------------------------------


def test_no_model_goes_into_the_image() -> None:
    dockerfile = (BACKEND_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "fetch_models" not in dockerfile
    assert "safetensors" not in dockerfile
    assert "de_core_news_lg" not in dockerfile
