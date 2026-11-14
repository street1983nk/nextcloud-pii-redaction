"""Owner rules over every public text: no em or en dash, no emoji, real umlauts.

- Dashes and emoji: every tracked text file, code included, because comments and
  strings end up in logs, archives and screenshots. The licence texts are third
  party and exempt.
- Umlauts: German prose must not spell ä, ö, ü, ß as ae, oe, ue, ss. A general
  pattern would hit correct words (Quelle, aktuell, Masse), so the gate holds a
  list of transcribed words that never occur in correct German. Code is exempt
  (identifiers stay ASCII), so the scan covers the German texts only: README.md,
  German docs, l10n/de.json, the German store texts and the project documents.

The forbidden characters are written as escapes, so this file passes itself.
"""

import json
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree

import pytest

from tests.conftest import BACKEND_ROOT, REPO_ROOT

EM_DASH = "\u2014"
EN_DASH = "\u2013"
EMOJI = re.compile("[\U0001f000-\U0001faff\u2600-\u27bf\ufe0f]")
EXEMPT = frozenset({"LICENSE", "LICENSES/AGPL-3.0-or-later.txt", "backend/uv.lock"})
# The GSD planning documents carry the status marks of the planning tool (check
# mark, cross, warning sign in VALIDATION.md and RESEARCH.md); the tool reads
# them back, so they stay. Nothing under .planning/ ships in an archive or image.
EXEMPT_PREFIXES = (".planning/",)
BINARY_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".gz", ".zip"})

# Transcribed spellings that are never correct German. Lowercase stems; a match
# needs a word boundary in front, so "Quelle" or "aktuell" never match.
TRANSCRIBED = (
    "fuer",
    "ueber",
    "koenn",
    "moeglich",
    "muess",
    "waehl",
    "waehrend",
    "wuerd",
    "groess",
    "aender",
    "aenderung",
    "geloescht",
    "loesch",
    "pruef",
    "schwaerz",
    "schluessel",
    "spaeter",
    "zurueck",
    "hoechst",
    "naechst",
    "gemaess",
    "laeuft",
    "oeffn",
    "oeffentlich",
    "benoetig",
    "verfuegbar",
    "unterstuetz",
    "ausfuehr",
    "eingefuegt",
    "hinzufueg",
    "schliess",
    "gross",
    "strasse",
    "massnahme",
    "regelmaessig",
    "faehig",
    "zusaetzlich",
    "ueberpruef",
    "veroeffentlich",
)
TRANSCRIBED_PATTERN = re.compile(r"(?i)\b(?:" + "|".join(TRANSCRIBED) + r")\w*")
# SKELETON.md exists only in the skeleton; new_app.py does not copy it.
GERMAN_DOCUMENTS = ("README.md", "SKELETON.md", "DESIGN.md", "PRODUCT.md", "CHANGELOG.md")


def tracked_files() -> list[Path]:
    """Every file git tracks or would track, so a new file is checked from its first day."""
    output = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],  # noqa: S607 - git from PATH
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO_ROOT / line for line in output.splitlines() if line and (REPO_ROOT / line).is_file()]


def dash_and_emoji_findings(name: str, source: str) -> list[str]:
    findings = []
    if EM_DASH in source:
        findings.append(f"{name}: em dash")
    if EN_DASH in source:
        findings.append(f"{name}: en dash")
    if EMOJI.search(source):
        findings.append(f"{name}: emoji")
    return findings


def transcription_findings(name: str, source: str) -> list[str]:
    return [f"{name}: {match.group(0)!r} instead of a real umlaut" for match in TRANSCRIBED_PATTERN.finditer(source)]


def german_texts() -> list[tuple[str, str]]:
    """(name, text) of every German public text."""
    texts = [
        (name, (REPO_ROOT / name).read_text(encoding="utf-8"))
        for name in GERMAN_DOCUMENTS
        if name != "SKELETON.md" or (REPO_ROOT / name).is_file()
    ]
    texts += [
        (f"docs/{path.name}", path.read_text(encoding="utf-8"))
        for path in sorted((REPO_ROOT / "docs").glob("*.md"))
        if not path.name.endswith((".en.md", ".fr.md"))
    ]
    catalogue = json.loads((BACKEND_ROOT / "l10n" / "de.json").read_text(encoding="utf-8"))
    texts.append(("backend/l10n/de.json", "\n".join(catalogue["translations"].values())))
    for name in ("de", "de_DE"):
        php = json.loads((REPO_ROOT / "php" / "l10n" / f"{name}.json").read_text(encoding="utf-8"))["translations"]
        values = [text for value in php.values() for text in (value if isinstance(value, list) else [value])]
        texts.append((f"php/l10n/{name}.json", "\n".join(values)))
    texts += store_texts("de")
    return texts


# The store metadata of both apps: the ExApp and the PHP app.
STORE_FILES = (("backend", BACKEND_ROOT / "appinfo" / "info.xml"), ("php", REPO_ROOT / "php" / "appinfo" / "info.xml"))


def store_texts(language: str) -> list[tuple[str, str]]:
    """(name, text) of every store text of both apps in one language."""
    texts = []
    for app, info_xml in STORE_FILES:
        info = ElementTree.fromstring(info_xml.read_text(encoding="utf-8"))  # noqa: S314 - own repo file
        texts += [(f"{app} info.xml {el.tag} {language}", el.text or "") for el in info if el.get("lang") == language]
    return texts


def test_no_tracked_text_carries_a_dash_or_an_emoji() -> None:
    files = tracked_files()
    assert len(files) > 30

    findings = []
    for path in files:
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative in EXEMPT or relative.startswith(EXEMPT_PREFIXES) or path.suffix in BINARY_SUFFIXES:
            continue
        findings += dash_and_emoji_findings(relative, path.read_text(encoding="utf-8"))

    assert findings == []


def test_german_texts_use_real_umlauts() -> None:
    texts = german_texts()
    assert len(texts) >= 8

    findings = [finding for name, source in texts for finding in transcription_findings(name, source)]

    assert findings == []


def test_the_german_texts_really_contain_umlauts() -> None:
    # The positive control: a gate over texts without a single umlaut would be
    # green for the wrong reason.
    joined = "".join(source for _, source in german_texts())

    assert all(letter in joined for letter in "äöüß")


@pytest.mark.parametrize(
    ("sample", "count"),
    [
        ("Gr" + "oesse und f" + "uer alle", 2),
        ("Die Quelle ist aktuell, die Masse stimmt.", 0),
        ("Größe für alle", 0),
    ],
)
def test_the_umlaut_rule_fires_on_transcriptions_only(sample: str, count: int) -> None:
    assert len(transcription_findings("sample", sample)) == count


def test_the_dash_rule_fires() -> None:
    assert dash_and_emoji_findings("s", "a \u2014 b \u2013 c \U0001f600") == ["s: em dash", "s: en dash", "s: emoji"]
    assert dash_and_emoji_findings("s", "a - b, c: d") == []


# The places the owner rule names explicitly (plan 01-03): the scan above
# covers every tracked file, this holds that these really are among them.
DASH_SCOPE = ("php/", "backend/l10n/", "README.md", "README.en.md", "README.fr.md", "docs/", "CHANGELOG.md")


def test_the_dash_scan_reaches_every_place_the_owner_rule_names() -> None:
    scanned = [path.relative_to(REPO_ROOT).as_posix() for path in tracked_files()]
    assert all(any(name.startswith(scope) for name in scanned) for scope in DASH_SCOPE)


def test_the_php_catalogues_are_among_the_german_texts() -> None:
    names = [name for name, _ in german_texts()]
    assert "php/l10n/de.json" in names
    assert "php/l10n/de_DE.json" in names


def test_self_the_transcription_list_covers_the_app_words() -> None:
    for word in ("Pr" + "uefung", "Schw" + "aerzen", "gel" + "oescht", "Ae" + "nderung", "f" + "uer", "Str" + "asse"):
        assert transcription_findings("sample", word), word
    assert transcription_findings("sample", "Prüfung Schwärzen gelöscht Änderung für Straße") == []


# -- French typography in the documents and store texts (plan 01-19) ---------------
#
# test_trilingual.py holds the catalogues to U+00A0 before : ; ? ! and inside
# guillemets. The audit of plan 01-19 found the French README without a single
# one (six plain spaces), so the documents and the French store texts of both
# apps get the same rule here. Code spans, fenced blocks, link targets and URLs
# are no prose; "![" is markdown image syntax and a colon between digits a time.

NBSP = chr(0x00A0)
NARROW_NBSP = chr(0x202F)
_FRENCH_NO_PROSE = (
    re.compile(r"```.*?```", re.DOTALL),
    re.compile(r"`[^`\n]*`"),
    re.compile(r"\]\([^)]*\)"),
    re.compile(r"https?://\S+"),
)
_FRENCH_MARK = re.compile("[:;?!\u00bb]")
_OPEN_GUILLEMET_BARE = re.compile("\u00ab(?![\u00a0\u202f])")


def french_prose_findings(name: str, source: str) -> list[str]:
    prose = source
    for pattern in _FRENCH_NO_PROSE:
        prose = pattern.sub(" ", prose)
    findings = []
    for match in _FRENCH_MARK.finditer(prose):
        before = prose[match.start() - 1 : match.start()]
        after = prose[match.end() : match.end() + 1]
        if match.group(0) == "!" and after == "[":
            continue
        if match.group(0) == ":" and before.isdigit() and after.isdigit():
            continue
        if before not in (NBSP, NARROW_NBSP):
            findings.append(f"{name}: {match.group(0)!r} without U+00A0 before it")
    findings += [f"{name}: opening guillemet without U+00A0 after it" for _ in _OPEN_GUILLEMET_BARE.finditer(prose)]
    return findings


def french_texts() -> list[tuple[str, str]]:
    texts = [("README.fr.md", (REPO_ROOT / "README.fr.md").read_text(encoding="utf-8"))]
    documents = sorted((REPO_ROOT / "docs").glob("*.fr.md"))
    texts += [(f"docs/{path.name}", path.read_text(encoding="utf-8")) for path in documents]
    return texts + store_texts("fr")


def test_french_documents_and_store_texts_carry_the_narrow_spacing() -> None:
    texts = french_texts()
    assert len(texts) >= 8
    assert any(NBSP in source for _, source in texts), "positive control: no U+00A0 at all in French"

    assert [finding for name, source in texts for finding in french_prose_findings(name, source)] == []


def test_self_the_french_rule_fires_on_plain_and_missing_spaces() -> None:
    plain = "Statut : en cours ; pr\u00eat ? Oui ! \u00ab x \u00bb"
    assert len(french_prose_findings("s", plain)) == 6
    assert len(french_prose_findings("s", "Statut: x")) == 1
    clean = f"Statut{NBSP}: x{NBSP}; \u00ab{NBSP}y{NBSP}\u00bb ![b](https://a.b/c:d) `a:b` 0:00"
    assert french_prose_findings("s", clean) == []


def test_self_the_german_texts_include_both_store_files() -> None:
    names = {name.split(" ")[0] for name, _ in german_texts() if "info.xml" in name}
    assert names == {"backend", "php"}
