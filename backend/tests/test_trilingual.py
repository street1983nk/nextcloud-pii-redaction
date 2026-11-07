"""Owner rule: everything user facing exists in German, English and French.

German comes first (README.md is German). The rule covers, and this module holds:

- the READMEs: README.md (de), README.en.md, README.fr.md
- every user document under docs/: <name>.md (de) with <name>.en.md and
  <name>.fr.md beside it, in both directions
- the store texts: name, summary and description of backend/appinfo/info.xml in the
  English default, lang="de" and lang="fr"
- the l10n catalogues: backend/l10n/de.json, en.json, fr.json with exactly the
  same keys, no empty value, and every string of the settings page among them
- the PHP app catalogues php/l10n/{de,de_DE,en,fr}.json (section at the end)

Each rule has a mutated sample that has to make it fire, so a gate whose body
was deleted cannot stay green.
"""

import json
import re
from pathlib import Path
from xml.etree import ElementTree

from pii_redaction_backend import settings
from tests.conftest import BACKEND_ROOT, REPO_ROOT

LANGUAGES = ("de", "en", "fr")
README_FILES = {"de": "README.md", "en": "README.en.md", "fr": "README.fr.md"}
DOCS = REPO_ROOT / "docs"
L10N = BACKEND_ROOT / "l10n"
INFO_XML = BACKEND_ROOT / "appinfo" / "info.xml"
STORE_ELEMENTS = ("name", "summary", "description")


def missing_doc_languages(names: list[str]) -> list[str]:
    """The language editions missing from a list of markdown file names."""
    bases = set()
    for name in names:
        stem = name.removesuffix(".md")
        bases.add(stem.removesuffix(".en").removesuffix(".fr"))
    missing = []
    for base in sorted(bases):
        for name in (f"{base}.md", f"{base}.en.md", f"{base}.fr.md"):
            if name not in names:
                missing.append(name)
    return missing


def store_languages_missing(source: str) -> list[str]:
    """Every store element whose de, en (default) or fr edition is missing or empty."""
    info = ElementTree.fromstring(source)  # noqa: S314 - our own file
    findings = []
    for kind in STORE_ELEMENTS:
        present = {element.get("lang", "en"): (element.text or "").strip() for element in info.findall(kind)}
        findings += [f"{kind} lang={language}" for language in LANGUAGES if not present.get(language)]
    return findings


def catalogue_findings(catalogues: dict[str, dict[str, str]]) -> list[str]:
    """Missing languages, keys that exist in one catalogue only, and empty values."""
    findings = [f"l10n/{language}.json is missing" for language in LANGUAGES if language not in catalogues]
    every_key = set().union(*(set(table) for table in catalogues.values())) if catalogues else set()
    for language, table in sorted(catalogues.items()):
        findings += [f"l10n/{language}.json lacks {key!r}" for key in sorted(every_key - set(table))]
        findings += [
            f"l10n/{language}.json has an empty value for {key!r}" for key, value in table.items() if not value
        ]
    return findings


def load_catalogues() -> dict[str, dict[str, str]]:
    """Every l10n/<lang>.json as language -> translations."""
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))["translations"] for path in sorted(L10N.glob("*.json"))
    }


# -- the real tree -------------------------------------------------------------


def test_the_three_readmes_exist_and_link_each_other() -> None:
    for language, name in README_FILES.items():
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        others = [other for key, other in README_FILES.items() if key != language]
        assert all(f"({other})" in text for other in others), name


def test_every_user_document_exists_in_three_languages() -> None:
    names = sorted(path.name for path in DOCS.glob("*.md"))

    assert names, "docs/ carries no user document, so this gate would judge nothing"
    assert missing_doc_languages(names) == []


def test_the_store_texts_exist_in_three_languages() -> None:
    assert store_languages_missing(INFO_XML.read_text(encoding="utf-8")) == []


def test_the_catalogues_carry_the_same_keys_in_three_languages() -> None:
    assert catalogue_findings(load_catalogues()) == []


def test_every_string_of_the_settings_page_is_translated() -> None:
    catalogues = load_catalogues()

    for text in settings.user_visible_strings(settings.admin_form()):
        for language in LANGUAGES:
            assert text in catalogues[language], f"{text!r} missing in l10n/{language}.json"


# -- self tests: every rule has to be able to fire ------------------------------


def test_a_missing_document_edition_is_reported_in_both_directions() -> None:
    assert missing_doc_languages(["a.md", "a.en.md", "a.fr.md"]) == []
    assert missing_doc_languages(["a.md", "a.en.md"]) == ["a.fr.md"]
    assert missing_doc_languages(["b.en.md", "b.fr.md"]) == ["b.md"]


def test_a_missing_store_language_is_reported() -> None:
    sample = (
        "<info><name>N</name><name lang='de'>N</name><name lang='fr'>N</name>"
        "<summary>S</summary><summary lang='de'>S</summary>"
        "<description>D</description><description lang='de'>D</description><description lang='fr'> </description>"
        "</info>"
    )

    assert store_languages_missing(sample) == ["summary lang=fr", "description lang=fr"]


def test_a_key_in_one_catalogue_only_is_reported() -> None:
    catalogues = {"de": {"A": "A-de", "B": "B-de"}, "en": {"A": "A"}, "fr": {"A": ""}}

    assert catalogue_findings(catalogues) == [
        "l10n/en.json lacks 'B'",
        "l10n/fr.json lacks 'B'",
        "l10n/fr.json has an empty value for 'A'",
    ]
    assert catalogue_findings({"de": {}, "en": {}}) == ["l10n/fr.json is missing"]


# -- the PHP app catalogues (plan 01-03) -------------------------------------------
#
# php/l10n carries de, de_DE, en and fr. de and de_DE hold the same impersonal
# text (UI-SPEC: correct in both registers). Rules on top of the key parity:
# placeholders survive translation, French has U+00A0 before : ; ? ! and inside
# guillemets, every value has at most three sentences and 240 characters (the
# hard limit; the guide value of two sentences is the owner's review in plan
# 20), admin banners carry no version placeholder, and every text the PHP app
# sends through t() or n() is a key of every catalogue.

PHP_ROOT = REPO_ROOT / "php"
PHP_L10N = PHP_ROOT / "l10n"
PHP_LANGUAGES = ("de", "de_DE", "en", "fr")
NBSP = chr(0x00A0)
NARROW_NBSP = chr(0x202F)
ELLIPSIS = chr(0x2026)
GUILLEMET_OPEN = chr(0x00AB)
GUILLEMET_CLOSE = chr(0x00BB)
MAX_SENTENCES = 3
MAX_CHARACTERS = 240
PLACEHOLDER = re.compile(r"%(?:\d+\$)?[sd]|%n")
URL = re.compile(r"https?://\S+")
SENTENCE_END = re.compile("[.?!" + ELLIPSIS + r"](?=\s|$)")
# The admin banners of the seven backend states plus the failed recheck.
ADMIN_BANNER_KEYS = (
    "Both apps are connected.",
    "Minor version difference. Analyses run; align both apps at the next update.",
    "The versions do not match. No analysis starts until both are the same.",
    "The backend is not installed. Without it, no analysis starts.",
    "The backend is disabled. No analysis starts until it is enabled again.",
    "The backend does not respond. Check that it is running and that the deploy daemon can be reached.",
    "AppAPI is not enabled. The backend only runs through AppAPI.",
    "The state could not be checked again. Shown is the state from when the page was loaded.",
)
_Q = r"""(['"])(.*?)(?<!\\)"""
_TS_T = re.compile(r"\bt\(\s*'pii_redaction'\s*,\s*" + _Q + r"\1", re.DOTALL)
_TS_N = re.compile(r"\bn\(\s*'pii_redaction'\s*,\s*" + _Q + r"\1\s*,\s*" + r"""(['"])(.*?)(?<!\\)\3""", re.DOTALL)
_PHP_T = re.compile(r"\$(?:this->)?l(?:10n)?->t\(\s*" + _Q + r"\1", re.DOTALL)
_PHP_N = re.compile(r"\$(?:this->)?l(?:10n)?->n\(\s*" + _Q + r"\1\s*,\s*" + r"""(['"])(.*?)(?<!\\)\3""", re.DOTALL)

type Value = str | list[str]


def load_php_catalogues() -> dict[str, dict[str, Value]]:
    return {
        language: json.loads((PHP_L10N / f"{language}.json").read_text(encoding="utf-8"))["translations"]
        for language in PHP_LANGUAGES
        if (PHP_L10N / f"{language}.json").is_file()
    }


def forms(value: Value) -> list[str]:
    return value if isinstance(value, list) else [value]


def placeholder_findings(catalogues: dict[str, dict[str, Value]], reference: str = "en") -> list[str]:
    """Placeholders of the reference value that a translation dropped or added."""
    findings = []
    for key, value in catalogues.get(reference, {}).items():
        wanted = sorted(set(PLACEHOLDER.findall(" ".join(forms(value)))))
        for language, table in sorted(catalogues.items()):
            for text in forms(table.get(key, "")):
                found = sorted(set(PLACEHOLDER.findall(text)))
                if found != wanted:
                    findings.append(f"{language}: {key!r} has {found}, expected {wanted}")
    return findings


def french_spacing_findings(text: str) -> list[str]:
    """French typography: U+00A0 before : ; ? ! and inside guillemets."""
    stripped = URL.sub("", PLACEHOLDER.sub("X", text))
    spaces = (NBSP, NARROW_NBSP)
    findings = []
    for match in re.finditer(r"[:;?!]", stripped):
        if stripped[match.start() - 1 : match.start()] not in spaces:
            findings.append(f"{match.group(0)!r} without U+00A0 in {text!r}")
    for match in re.finditer(GUILLEMET_OPEN, stripped):
        if stripped[match.end() : match.end() + 1] not in spaces:
            findings.append(f"opening guillemet without U+00A0 in {text!r}")
    for match in re.finditer(GUILLEMET_CLOSE, stripped):
        if stripped[match.start() - 1 : match.start()] not in spaces:
            findings.append(f"closing guillemet without U+00A0 in {text!r}")
    return findings


def brevity_findings(text: str) -> list[str]:
    """The hard limit of the brevity rule: three sentences, 240 characters."""
    findings = []
    sentences = len(SENTENCE_END.findall(PLACEHOLDER.sub("X", text)))
    if sentences > MAX_SENTENCES:
        findings.append(f"{sentences} sentences in {text[:60]!r}")
    if len(text) > MAX_CHARACTERS:
        findings.append(f"{len(text)} characters in {text[:60]!r}")
    return findings


def used_texts(source: str, *, php: bool) -> set[str]:
    """Keys a source sends through t() or n() of the PHP app."""
    single, plural = (_PHP_T, _PHP_N) if php else (_TS_T, _TS_N)
    keys = {match.group(2) for match in single.finditer(source)}
    keys |= {f"_{match.group(2)}_::_{match.group(4)}_" for match in plural.finditer(source)}
    return keys


def _ui_sources() -> list[tuple[Path, bool]]:
    found: list[tuple[Path, bool]] = []
    for pattern in ("src/**/*.ts", "src/**/*.vue"):
        found += [(path, False) for path in sorted(PHP_ROOT.glob(pattern))]
    for pattern in ("lib/**/*.php", "templates/*.php"):
        found += [(path, True) for path in sorted(PHP_ROOT.glob(pattern))]
    return found


def test_the_php_catalogues_carry_the_same_keys_in_four_language_codes() -> None:
    catalogues = load_php_catalogues()
    assert set(catalogues) == set(PHP_LANGUAGES)
    reference = set(catalogues["en"])
    assert all(set(table) == reference for table in catalogues.values())
    assert len(reference) >= 60
    empty = [key for table in catalogues.values() for key, value in table.items() if not all(forms(value))]
    assert empty == []


def test_de_and_de_DE_are_the_same_text() -> None:
    catalogues = load_php_catalogues()
    assert catalogues["de"] == catalogues["de_DE"]


def test_the_plural_forms_fit_the_languages() -> None:
    for language in PHP_LANGUAGES:
        plural = json.loads((PHP_L10N / f"{language}.json").read_text(encoding="utf-8"))["pluralForm"]
        assert plural == ("nplurals=2; plural=(n > 1);" if language == "fr" else "nplurals=2; plural=(n != 1);")


def test_every_placeholder_survives_translation() -> None:
    assert placeholder_findings(load_php_catalogues()) == []
    backend: dict[str, dict[str, Value]] = {language: dict(table) for language, table in load_catalogues().items()}
    assert placeholder_findings(backend) == []


def test_french_values_carry_the_narrow_spacing() -> None:
    values = [text for value in load_php_catalogues()["fr"].values() for text in forms(value)]
    values += list(load_catalogues()["fr"].values())
    assert any(NBSP in text for text in values), "positive control: no U+00A0 at all in French"
    assert [finding for text in values for finding in french_spacing_findings(text)] == []


def test_every_value_stays_within_three_sentences_and_240_characters() -> None:
    values = [text for table in load_php_catalogues().values() for value in table.values() for text in forms(value)]
    values += [text for table in load_catalogues().values() for text in table.values()]
    assert [finding for text in values for finding in brevity_findings(text)] == []


def test_no_admin_banner_names_a_version() -> None:
    for language, table in load_php_catalogues().items():
        for key in ADMIN_BANNER_KEYS:
            assert key in table, f"{language} lacks the banner {key!r}"
            assert not PLACEHOLDER.search(" ".join(forms(table[key]))), f"{language}: {key!r} has a placeholder"


def test_every_text_the_php_app_uses_is_in_every_catalogue() -> None:
    catalogues = load_php_catalogues()
    missing = []
    for path, php in _ui_sources():
        for key in used_texts(path.read_text(encoding="utf-8"), php=php):
            missing += [f"{path.name}: {key!r} not in {lang}" for lang, table in catalogues.items() if key not in table]
    assert missing == []


def test_self_placeholders_fire_on_a_dropped_one() -> None:
    good: dict[str, dict[str, Value]] = {"en": {"Review: %s": "Review: %s"}, "de": {"Review: %s": "Prüfung: %s"}}
    assert placeholder_findings(good) == []
    dropped: dict[str, dict[str, Value]] = {**good, "fr": {"Review: %s": "Vérification"}}
    assert placeholder_findings(dropped) == ["fr: 'Review: %s' has [], expected ['%s']"]
    plural: dict[str, dict[str, Value]] = {
        "en": {"_%n job_::_%n jobs_": ["%n job", "%n jobs"]},
        "de": {"_%n job_::_%n jobs_": ["%d Auftrag", "%n Aufträge"]},
    }
    assert placeholder_findings(plural) == ["de: '_%n job_::_%n jobs_' has ['%d'], expected ['%n']"]


def test_self_french_spacing_fires_on_a_plain_space_and_a_missing_one() -> None:
    assert french_spacing_findings("Vérification" + NBSP + ": %s") == []
    assert french_spacing_findings("Vérification : %s") != []
    assert french_spacing_findings("Vraiment?") != []
    assert french_spacing_findings(GUILLEMET_OPEN + "PII Redaction" + GUILLEMET_CLOSE) != []
    assert french_spacing_findings(GUILLEMET_OPEN + NBSP + "PII" + NBSP + GUILLEMET_CLOSE) == []
    assert french_spacing_findings("Voir https://example.org/a?b=c") == []
    assert french_spacing_findings("%1$s sur %2$s pages") == []


def test_self_brevity_fires_on_four_sentences_and_241_characters() -> None:
    four_sentences = "Eins. Zwei. Drei. Vier."
    assert brevity_findings(four_sentences) == [f"4 sentences in {four_sentences!r}"]
    assert brevity_findings("a" * 241) == ["241 characters in " + repr("a" * 60)]
    three_at_limit = "Eins. Zwei. " + "x" * 227 + "."
    assert len(three_at_limit) == MAX_CHARACTERS
    assert brevity_findings(three_at_limit) == []
    assert brevity_findings("Wird angelegt" + ELLIPSIS) == []


def test_self_the_text_extraction_finds_t_and_n_calls() -> None:
    ts = "t('pii_redaction', 'Open review page') + n('pii_redaction', '%n job is ahead.', '%n jobs are ahead.', k)"
    assert used_texts(ts, php=False) == {"Open review page", "_%n job is ahead._::_%n jobs are ahead._"}
    php = "$this->l->t('A review is ready'); $l->t(\"Review: %s\", [$n]);"
    assert used_texts(php, php=True) == {"A review is ready", "Review: %s"}
    assert used_texts("t('other_app', 'Foreign')", php=False) == set()
