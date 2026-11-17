"""The test-only partial jail of the soffice diagnosis (tests/jail_layers.py, plan 02-16).

It must switch off exactly the layers above the one named and keep the code
of the product for the rest, or the diagnosis would measure something else.
"""

from dataclasses import replace

import pytest

from pii_redaction_backend.sandbox import jail
from tests import jail_layers


def test_limits_switches_off_landlock_and_seccomp_only() -> None:
    ops = jail_layers.layered_ops("limits")
    product = jail.system_ops()
    assert ops.landlock_abi() == 0
    assert ops.seccomp_available() is False
    assert (ops.setrlimit, ops.prctl, ops.execv) == (product.setrlimit, product.prctl, product.execv)


def test_landlock_switches_off_seccomp_only() -> None:
    ops = jail_layers.layered_ops("landlock")
    product = jail.system_ops()
    assert ops.landlock_abi is product.landlock_abi
    assert ops.landlock_restrict is product.landlock_restrict
    assert ops.seccomp_available() is False


def test_an_unknown_layer_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown layer"):
        jail_layers.layered_ops("seccomp")
    assert jail_layers.main(["layers", "seccomp", "soffice", "--", "/usr/bin/soffice"]) == jail.EXIT_USAGE
    assert jail_layers.main(["layers", "limits", "nonsense"]) == jail.EXIT_USAGE
    assert jail_layers.main([]) == jail.EXIT_USAGE


def test_the_partial_jail_applies_its_layers_in_product_order() -> None:
    calls: list[str] = []
    base = jail_layers.layered_ops("landlock")
    ops = replace(
        base,
        setrlimit=lambda name, _value: calls.append(name),
        prctl=lambda _option, _value: calls.append("prctl"),
        landlock_abi=lambda: 6,
        landlock_restrict=lambda *_paths: calls.append("landlock"),
        execv=lambda path, _args: calls.append(f"exec {path}"),
    )
    call = jail.parse(["soffice", "--", "/usr/bin/soffice"])
    assert call is not None
    assert jail.run(call, ops) == jail.EXIT_LAYER_FAILED  # a fake execv returns
    assert calls[-3:] == ["prctl", "landlock", "exec /usr/bin/soffice"]
    assert "seccomp" not in calls
