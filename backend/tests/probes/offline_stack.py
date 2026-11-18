"""Probe of RES-02 (plan 02-22): the detection stack loads and finds offline, with a tripwire that counts.

usage: python -I offline_stack.py <count|raise|control> <out.json> [<models root>]

count    a counting audit hook (NET_EVENTS, a module variable, so the number
         can be written out), offline.configure(), then the stack: spaCy
         de_core_news_lg from its absolute folder as the SpacyNlpEngine of
         Presidio (model_name is the absolute path, language de), the analyzer
         on SENTENCE must find EMAIL_ADDRESS; GLiNER2 from its absolute local
         folder must find a person.
raise    the same, with offline.install_network_tripwire() on top of the
         counting hook: every Python network step raises. The run must still
         end with exit 0.
control  the positive control: no configure, an empty TLDEXTRACT_CACHE in the
         folder of out.json, the counting hook and the tripwire, then one
         tldextract lookup. It must count at least one network event (the
         tripwire stops the step, tldextract falls back to its snapshot).

out.json holds email, person (bools), net_events (int), event_names (the
distinct audit event names, no arguments) and error (a word, - when none).
Nothing goes to stdout; exit 0 with out.json written, 1 when the stack failed
(out.json says where), 2 for wrong arguments.

The counting hook is not the product list (offline.NETWORK_EVENTS): it counts
every step that names a peer or resolves a name (connect, sendto, sendmsg,
the lookups), a bind to an address other than loopback, and the URL openers
of the standard library. Creating a socket is no network step: urllib3 makes
throwaway sockets at import (urllib3/_constant.py reads the default options,
util/connection.py binds ::1 port 0 to test IPv6), seen locally; those name no
peer and send nothing.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Final

SENTENCE: Final = "Bitte melden Sie sich bei Erika Mustermann unter erika.mustermann@example.org."
PERSON: Final = "Mustermann"
SPACY_FOLDER: Final = ("spacy", "de_core_news_lg-3.8.0")
GLINER_FOLDER: Final = ("gliner2", "1cb4166094dc58fa8d836429f060d6c95f62b495")
MODES: Final = ("count", "raise", "control")
# Every audit event of the standard library that names a peer or resolves a name.
PEER_EVENTS: Final = frozenset(
    {
        "socket.connect",
        "socket.sendto",
        "socket.sendmsg",
        "socket.getaddrinfo",
        "socket.gethostbyname",
        "socket.gethostbyaddr",
        "socket.getnameinfo",
        "urllib.Request",
        "http.client.connect",
        "http.client.send",
        "ftplib.connect",
        "smtplib.connect",
    }
)
LOOPBACK_HOSTS: Final = frozenset({"::1", "localhost"})

NET_EVENTS: list[str] = []


def is_network_event(event: str, args: tuple[object, ...]) -> bool:
    """A step with a peer or a name lookup, or a bind beyond loopback (a Unix socket path is no network)."""
    if event == "socket.bind":
        address = args[1] if len(args) > 1 else None
        if not isinstance(address, tuple) or not address:
            return False
        host = str(address[0])
        return not (host.startswith("127.") or host in LOOPBACK_HOSTS)
    return event in PEER_EVENTS


def _count(event: str, args: tuple[object, ...]) -> None:
    if is_network_event(event, args):
        NET_EVENTS.append(event)


def _write(out: Path, answer: dict[str, object]) -> None:
    temporary = out.with_name(f"{out.name}.tmp")
    temporary.write_text(json.dumps(answer, sort_keys=True), encoding="utf-8")
    os.replace(temporary, out)


def _temp_in(folder: Path) -> None:
    """tempfile and torch's caches go to the folder of out.json, the only folder the jail lets the probe write.

    The same reason as tests/profile_work.py use_work_folder_as_temp: torch._dynamo
    makes a cache folder at import, and the jail grants no write right on /tmp.
    """
    os.environ["TMPDIR"] = str(folder)
    os.environ["TORCHINDUCTOR_CACHE_DIR"] = str(folder / "torchinductor")
    tempfile.tempdir = str(folder)


def _email(models: Path) -> bool:
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import SpacyNlpEngine

    spacy_path = models.joinpath(*SPACY_FOLDER)
    # A model_name that is no folder makes Presidio call spacy.cli.download, which asks GitHub (seen locally).
    if not spacy_path.is_absolute() or not spacy_path.is_dir():
        raise FileNotFoundError("spacy model folder")
    engine = SpacyNlpEngine(models=[{"lang_code": "de", "model_name": str(spacy_path)}])
    engine.load()
    analyzer = AnalyzerEngine(nlp_engine=engine, supported_languages=["de"])
    found = analyzer.analyze(SENTENCE, language="de", entities=["EMAIL_ADDRESS"])
    return any(item.entity_type == "EMAIL_ADDRESS" for item in found)


def _threads() -> None:
    """The thread count of the child environment to torch, as the detection child does it (arm64, plan 02-16)."""
    import torch

    from pii_redaction_backend.resources import hardware

    hardware.apply_worker_threads(torch)


def _person(models: Path) -> bool:
    from gliner2 import GLiNER2

    folder = models.joinpath(*GLINER_FOLDER)
    if not folder.is_absolute() or not folder.is_dir():
        raise FileNotFoundError("gliner2 model folder")
    model = GLiNER2.from_pretrained(str(folder))
    result = model.extract_entities(SENTENCE, ["person"])
    entities = result.get("entities", {}) if isinstance(result, dict) else {}
    people = entities.get("person", []) if isinstance(entities, dict) else []
    return any(PERSON in str(person) for person in people)


def _stack(mode: str, models: Path, answer: dict[str, object]) -> None:
    from pii_redaction_backend import offline

    # The counting hook comes first, so configure itself is counted as well.
    sys.addaudithook(_count)
    step = "configure"
    try:
        offline.configure()
        if mode == "raise":
            offline.install_network_tripwire()
        step = "threads"
        _threads()
        step = "presidio"
        answer["email"] = _email(models)
        step = "gliner2"
        answer["person"] = _person(models)
        step = "-"
    except (Exception, SystemExit) as exc:
        # SystemExit too: spaCy's download helper ends the process with sys.exit.
        answer["error"] = f"{step}:{type(exc).__name__}"


def _control(folder: Path, answer: dict[str, object]) -> None:
    cache = folder / "tldextract-cache"
    cache.mkdir(exist_ok=True)
    os.environ["TLDEXTRACT_CACHE"] = str(cache)
    os.environ.pop("TLDEXTRACT_PUBLIC_SUFFIX_LIST_URLS", None)
    from pii_redaction_backend import offline

    sys.addaudithook(_count)
    offline.install_network_tripwire()
    try:
        import tldextract

        tldextract.extract("mail.example.org")
    except Exception as exc:
        answer["error"] = f"tldextract:{type(exc).__name__}"


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3) or argv[0] not in MODES or (argv[0] != "control") != (len(argv) == 3):
        return 2
    mode, out = argv[0], Path(argv[1])
    models = Path(argv[2]) if mode != "control" else None
    if models is not None and not models.is_absolute():
        return 2
    answer: dict[str, object] = {"email": False, "person": False, "net_events": 0, "event_names": [], "error": "-"}
    _temp_in(out.parent)
    if models is None:
        _control(out.parent, answer)
    else:
        _stack(mode, models, answer)
    answer["net_events"] = len(NET_EVENTS)
    answer["event_names"] = sorted(set(NET_EVENTS))
    _write(out, answer)
    return 0 if answer["error"] == "-" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
