"""The removed admin page and the l10n catalogue pair (.json and .js)."""

import subprocess
import sys
from types import SimpleNamespace
from typing import Any

from pii_redaction_backend import APP_ID, settings
from tests.conftest import BACKEND_ROOT, REPO_ROOT


async def test_unregister_removes_the_form_of_earlier_builds_by_its_old_id() -> None:
    removed: list[str] = []

    async def unregister_form(form_id: str) -> None:
        removed.append(form_id)

    nc: Any = SimpleNamespace(ui=SimpleNamespace(settings=SimpleNamespace(unregister_form=unregister_form)))
    await settings.unregister(nc)

    assert removed == [f"{APP_ID}_admin"]


def test_the_js_catalogues_match_their_json_source() -> None:
    result = subprocess.run(  # noqa: S603 - fixed arguments
        [sys.executable, str(REPO_ROOT / "scripts" / "l10n_js.py"), "--check", "--root", str(BACKEND_ROOT / "l10n")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout
