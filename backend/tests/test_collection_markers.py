"""The skip rule for the container and linux markers, and the measurement helper (plan 02-07)."""

import json
from pathlib import Path

import pytest

from tests.conftest import pytest_collection_modifyitems, record_measurement, skip_reason


@pytest.mark.parametrize(
    ("markers", "platform", "env", "expected"),
    [
        (frozenset({"container"}), "linux", {}, "container only"),
        (frozenset({"container"}), "linux", {"PII_IN_CONTAINER": "0"}, "container only"),
        (frozenset({"container"}), "linux", {"PII_IN_CONTAINER": "1"}, None),
        (frozenset({"linux"}), "win32", {}, "linux only"),
        (frozenset({"linux"}), "linux", {}, None),
        (frozenset({"container", "linux"}), "win32", {"PII_IN_CONTAINER": "1"}, "linux only"),
        (frozenset(), "win32", {}, None),
        (frozenset({"parametrize"}), "win32", {}, None),
    ],
)
def test_skip_reason(markers: frozenset[str], platform: str, env: dict[str, str], expected: str | None) -> None:
    assert skip_reason(markers, platform, env) == expected


def test_inside_the_container_nothing_is_swallowed() -> None:
    # Positive control: in the image (Linux, variable set) a test with both markers runs.
    assert skip_reason(frozenset({"container", "linux"}), "linux", {"PII_IN_CONTAINER": "1"}) is None


class FakeItem:
    """Just what the hook touches: iter_markers and add_marker."""

    def __init__(self, *names: str) -> None:
        self.marks = [getattr(pytest.mark, name).mark for name in names]
        self.added: list[pytest.MarkDecorator] = []

    def iter_markers(self) -> list[pytest.Mark]:
        return list(self.marks)

    def add_marker(self, marker: pytest.MarkDecorator) -> None:
        self.added.append(marker)


def test_the_hook_skips_exactly_the_marked_item(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PII_IN_CONTAINER", raising=False)
    marked = FakeItem("container")
    plain = FakeItem()
    pytest_collection_modifyitems(None, [marked, plain])  # type: ignore[arg-type]
    assert [mark.mark.name for mark in marked.added] == ["skip"]
    assert marked.added[0].mark.kwargs == {"reason": "container only"}
    assert plain.added == []


def test_record_measurement_merges_keys_atomically(tmp_path: Path) -> None:
    record_measurement("rss_kb", 1234, out_dir=tmp_path)
    record_measurement("frpc_environ_readable", False, out_dir=tmp_path)
    record_measurement("rss_kb", 2345, out_dir=tmp_path)
    data = json.loads((tmp_path / "measurements.json").read_text(encoding="utf-8"))
    assert data == {"frpc_environ_readable": False, "rss_kb": 2345}
    assert sorted(path.name for path in tmp_path.iterdir()) == ["measurements.json"]
