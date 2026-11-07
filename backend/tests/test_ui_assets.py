"""Static gates over the browser assets of the PHP app (templates, sources, CSS).

Taken over from Audio & Video Search and moved to the Vite build: the sources
live in php/src (TypeScript and Vue), php/js is build output and not judged.
The development machine runs no browser in the local suite, so what the UI
contract (01-UI-SPEC.md) forbids in so many words is checked by reading files:

* templates: no inline script (CSP), no style attribute (theme), no printer
  that skips escaping (only p() prints a value), every class carries the app
  prefix pii- or is one of the few server classes the UI-SPEC names;
* sources: no markup from a string (innerHTML and friends, v-html, isHTML),
  no eval;
* CSS: server variables only, so no hex, rgb or hsl colour, no !important,
  no removed focus outline, no shadow, no gradient;
* every script a PHP file adds as pii_redaction-<name> is an entry of
  vite.config.ts, so no page asks for a bundle the build never makes.

Every rule has a staged violation that has to make it fire, and the real tree
is held to a floor (the three entries and the review sheet exist), so the
gates cannot pass on an empty directory.
"""

import re
from pathlib import Path

from tests.conftest import REPO_ROOT

PHP_ROOT = REPO_ROOT / "php"
TEMPLATES = PHP_ROOT / "templates"
SOURCES = PHP_ROOT / "src"
STYLES = PHP_ROOT / "css"
LIB = PHP_ROOT / "lib"
VITE_CONFIG = PHP_ROOT / "vite.config.ts"

ALLOWED_SERVER_CLASSES = frozenset(
    {"section", "settings-hint", "checkbox", "primary", "icon-loading-small", "hidden-visually"}
)
CLASS_PREFIX = "pii-"
BUILT_STYLE = re.compile(r"^pii_redaction-.*\.css$|\.chunk\.css$")

INLINE_SCRIPT = re.compile(r"<script", re.IGNORECASE)
STYLE_ATTRIBUTE = re.compile(r"\sstyle\s*=", re.IGNORECASE)
UNESCAPED_PRINTER = re.compile(r"<\?=|<\?php\s+echo\b|\becho\s|\bprint_unescaped\s*\(|\bprint\s*\(")
MARKUP_FROM_STRING = re.compile(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|v-html|isHTML")
EVAL_CALL = re.compile(r"\beval\s*\(|new\s+Function\s*\(")
HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b")
FUNCTIONAL_COLOUR = re.compile(r"\b(?:rgb|hsl)a?\(", re.IGNORECASE)
IMPORTANT = re.compile(r"!\s*important", re.IGNORECASE)
NO_OUTLINE = re.compile(r"outline\s*:\s*(?:none|0)\b", re.IGNORECASE)
SHADOW = re.compile(r"box-shadow|text-shadow", re.IGNORECASE)
GRADIENT = re.compile(r"gradient", re.IGNORECASE)
ADD_SCRIPT = re.compile(r"Util::add(?:Init)?Script\(\s*'pii_redaction'\s*,\s*'pii_redaction-([\w-]+)'")
VITE_ENTRY = re.compile(r"^\s*([A-Za-z_][\w]*)\s*:\s*'src/[\w/.-]+\.ts'", re.MULTILINE)

_CLASS_ATTRIBUTE = re.compile(r"\bclass=\"([^\"]*)\"")
_PHP_BLOCK = re.compile(r"<\?php.*?\?>", re.DOTALL)


def files(folder: Path, *suffixes: str) -> list[Path]:
    """The files below one asset folder with one of the suffixes, sorted."""
    if not folder.is_dir():
        return []
    return sorted(path for path in folder.rglob("*") if path.is_file() and path.suffix in suffixes)


def findings(pattern: re.Pattern[str], text: str) -> list[str]:
    """Every match of pattern in text."""
    return [match.group(0) for match in pattern.finditer(text)]


def foreign_classes(template: str) -> list[str]:
    """Class names that neither carry the app prefix nor are allowed server classes.

    A PHP block inside a class value is removed first; the literal text in
    front of it ("pii-banner--") is what the rule judges.
    """
    found = []
    for match in _CLASS_ATTRIBUTE.finditer(template):
        value = _PHP_BLOCK.sub("", match.group(1))
        for name in value.split():
            if not name.startswith(CLASS_PREFIX) and name not in ALLOWED_SERVER_CLASSES:
                found.append(name)
    return found


def vite_entries(config: str) -> set[str]:
    """The entry names of createAppConfig in vite.config.ts."""
    return set(VITE_ENTRY.findall(config))


def scripts_without_entry(php_sources: dict[str, str], entries: set[str]) -> list[str]:
    """pii_redaction-<name> scripts added in PHP whose <name> the build never makes."""
    return sorted(
        f"{name}: {script}"
        for name, text in php_sources.items()
        for script in ADD_SCRIPT.findall(text)
        if script not in entries
    )


def _read(paths: list[Path]) -> dict[str, str]:
    return {path.relative_to(REPO_ROOT).as_posix(): path.read_text(encoding="utf-8") for path in paths}


def _templates() -> dict[str, str]:
    return _read(files(TEMPLATES, ".php"))


def _sources() -> dict[str, str]:
    return _read(files(SOURCES, ".ts", ".vue"))


def _styles() -> dict[str, str]:
    # Only the hand written sheets: a local build may leave bundle styles here.
    return _read([path for path in files(STYLES, ".css") if not BUILT_STYLE.search(path.name)])


def _php_sources() -> dict[str, str]:
    return _read(files(LIB, ".php") + files(TEMPLATES, ".php"))


def _hits(sources: dict[str, str], pattern: re.Pattern[str]) -> dict[str, list[str]]:
    return {name: found for name, text in sources.items() if (found := findings(pattern, text))}


# -- the real tree ------------------------------------------------------------------


def test_the_tree_carries_the_three_entries_and_the_review_sheet() -> None:
    for path in (
        SOURCES / "init.ts",
        SOURCES / "review.ts",
        SOURCES / "admin.ts",
        SOURCES / "ReviewPlaceholder.vue",
        STYLES / "review.css",
        VITE_CONFIG,
    ):
        assert path.is_file(), f"{path.relative_to(REPO_ROOT)} is missing"
    assert vite_entries(VITE_CONFIG.read_text(encoding="utf-8")) == {"init", "review", "admin"}


def test_templates_have_no_inline_script() -> None:
    assert _hits(_templates(), INLINE_SCRIPT) == {}


def test_templates_have_no_style_attribute() -> None:
    assert _hits(_templates(), STYLE_ATTRIBUTE) == {}


def test_templates_print_only_through_p() -> None:
    assert _hits(_templates(), UNESCAPED_PRINTER) == {}


def test_template_classes_carry_the_prefix_or_are_server_classes() -> None:
    found = {name: names for name, text in _templates().items() if (names := foreign_classes(text))}
    assert found == {}


def test_sources_build_no_markup_from_strings() -> None:
    assert _hits(_sources(), MARKUP_FROM_STRING) == {}


def test_sources_have_no_eval() -> None:
    assert _hits(_sources(), EVAL_CALL) == {}


def test_styles_use_no_colour_values() -> None:
    styles = _styles()
    assert _hits(styles, HEX_COLOUR) == {}
    assert _hits(styles, FUNCTIONAL_COLOUR) == {}


def test_styles_do_not_force_or_remove() -> None:
    styles = _styles()
    assert _hits(styles, IMPORTANT) == {}
    assert _hits(styles, NO_OUTLINE) == {}


def test_styles_stay_flat() -> None:
    styles = _styles()
    assert _hits(styles, SHADOW) == {}
    assert _hits(styles, GRADIENT) == {}


def test_the_page_image_is_never_inverted() -> None:
    sources = {**_styles(), **_sources()}
    assert _hits(sources, re.compile(r"background-invert-if-dark")) == {}


def test_every_added_script_is_a_vite_entry() -> None:
    entries = vite_entries(VITE_CONFIG.read_text(encoding="utf-8"))
    assert scripts_without_entry(_php_sources(), entries) == []


def test_the_review_page_keeps_its_dom_contract() -> None:
    page = (SOURCES / "ReviewPlaceholder.vue").read_text(encoding="utf-8")
    assert 'id="pii-review-state"' in page
    assert 'role="status"' in page
    assert 'aria-live="polite"' in page
    assert 'id="pii-placeholder"' in page
    assert "pii-review__page" in page
    assert "visibilityState" in page
    assert "/page/1" in page
    assert "#pii-review [hidden]" in (STYLES / "review.css").read_text(encoding="utf-8")


def test_the_admin_script_keeps_its_dom_contract() -> None:
    script = (SOURCES / "admin.ts").read_text(encoding="utf-8")
    for needle in ("pii-admin", "pii-backend-state", "pii-recheck", "pii-recheck-failed", "admin/state"):
        assert needle in script, needle
    assert "aria-busy" in script
    assert "stateArea.focus()" in script


def test_the_admin_section_keeps_its_contract() -> None:
    template = (TEMPLATES / "admin.php").read_text(encoding="utf-8")
    style = (STYLES / "admin.css").read_text(encoding="utf-8")
    # One state area, announced politely and the focus target after a recheck.
    assert template.count('id="pii-backend-state"') == 1
    assert 'role="status" aria-live="polite" tabindex="-1"' in template
    # The seven states and the recheck warning, rendered on the server.
    for state in (
        "ok",
        "version_patch_differs",
        "version_drift",
        "backend_missing",
        "backend_disabled",
        "backend_unreachable",
        "no_app_api",
    ):
        assert f"'{state}' =>" in template, state
    assert 'id="pii-recheck-failed"' in template
    assert 'id="pii-recheck"' in template
    assert 'id="pii-recheck-label"' in template
    assert 'id="pii-checked-at"' in template
    # Orchestrator decision 3: the AVS form of the link to the app management.
    assert template.count("linkToRoute('appstore.page.viewApps')") == 1
    assert template.count("linkToRoute('settings.AppSettings.viewApps')") == 1
    assert "Util::addScript('pii_redaction', 'pii_redaction-admin')" in template
    assert "Util::addStyle('pii_redaction', 'admin')" in template
    assert "debug" not in template.lower()
    assert "#pii-admin [hidden]" in style
    assert "pointer: coarse" in style


# -- the self tests: every rule has to fire on a staged violation --------------------


def test_self_inline_script_and_style_attribute_fire() -> None:
    assert findings(INLINE_SCRIPT, '<SCRIPT nonce="x">go()</SCRIPT>') == ["<SCRIPT"]
    assert findings(STYLE_ATTRIBUTE, '<div style="color: red">') == [" style="]
    assert findings(STYLE_ATTRIBUTE, '<div class="pii-style">') == []


def test_self_unescaped_printers_fire() -> None:
    for staged in ("<?= $name ?>", "<?php echo $name; ?>", "<?php print_unescaped($name); ?>", "<?php print($x); ?>"):
        assert findings(UNESCAPED_PRINTER, staged), staged
    assert findings(UNESCAPED_PRINTER, "<?php p($name); ?>") == []


def test_self_foreign_classes_fire_and_php_values_pass() -> None:
    assert foreign_classes('<div class="pii-banner pii-banner--<?php p($kind); ?>">') == []
    assert foreign_classes('<button class="primary"><p class="settings-hint">') == []
    assert foreign_classes('<div class="card pii-x">') == ["card"]


def test_self_source_rules_fire() -> None:
    assert findings(MARKUP_FROM_STRING, "node.innerHTML = text") == ["innerHTML"]
    assert findings(MARKUP_FROM_STRING, '<p v-html="name" />') == ["v-html"]
    assert findings(MARKUP_FROM_STRING, "showMessage(text, { isHTML: true })") == ["isHTML"]
    assert findings(EVAL_CALL, "eval (code)") == ["eval ("]
    assert findings(EVAL_CALL, "node.textContent = value") == []


def test_self_colour_rules_fire() -> None:
    assert findings(HEX_COLOUR, "color: #fff;") == ["#fff"]
    assert findings(FUNCTIONAL_COLOUR, "background: rgba(0, 0, 0, .5)") == ["rgba("]
    assert findings(HEX_COLOUR, "color: var(--color-main-text);") == []


def test_self_force_remove_and_flat_rules_fire() -> None:
    assert findings(IMPORTANT, "display: none !important;") == ["!important"]
    assert findings(NO_OUTLINE, "outline: none;") == ["outline: none"]
    assert findings(NO_OUTLINE, "outline: 2px solid var(--color-main-text);") == []
    assert findings(SHADOW, "box-shadow: 0 2px 8px") == ["box-shadow"]
    assert findings(GRADIENT, "background: linear-gradient(red, blue)") == ["gradient"]


def test_self_a_script_without_an_entry_fires() -> None:
    config = (
        "createAppConfig({\n\tinit: 'src/init.ts',\n\treview: 'src/review.ts',\n}, {\n\tappName: 'pii_redaction',\n})"
    )
    assert vite_entries(config) == {"init", "review"}
    php = {"a.php": "\\OCP\\Util::addScript('pii_redaction', 'pii_redaction-admin');"}
    assert scripts_without_entry(php, vite_entries(config)) == ["a.php: admin"]
    php_ok = {"a.php": "\\OCP\\Util::addInitScript('pii_redaction', 'pii_redaction-init');"}
    assert scripts_without_entry(php_ok, vite_entries(config)) == []
