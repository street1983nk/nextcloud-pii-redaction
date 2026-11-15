"""The admin settings page: none, until a setting actually does something.

Earlier builds registered a declarative AppAPI form with two fields that no
code read ("Process new files automatically", "Largest file in MB"). The form
is gone, but an instance that enabled such a build still carries it in
AppAPI's table, so enabling and disabling both remove it by its old id.
"""

from typing import Final

from pii_redaction_backend import APP_ID
from pii_redaction_backend.nc import AsyncNextcloudApp

# The id earlier builds registered the form under.
FORM_ID: Final = f"{APP_ID}_admin"


async def unregister(nc: AsyncNextcloudApp) -> None:
    """Remove the admin form of earlier builds; a form that is already gone is not an error."""
    await nc.ui.settings.unregister_form(FORM_ID)
