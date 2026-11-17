"""Switch off the hidden network calls of the detection libraries (RES-02).

Three libraries reach the internet on their own (RESEARCH Pitfalls 6 and 7):

- tldextract, called by the Presidio e-mail recognizer, fetches the Public
  Suffix List from publicsuffix.org and GitHub on its first use;
- huggingface_hub and transformers look for updates and send telemetry when a
  model is named by repository id;
- gliner2 always imports its cloud client (GLiNER2API); only its use can be
  forbidden, which an AST gate in the tests does.

configure() must run before the first Presidio, transformers or gliner2
import in a process: it sets the offline variables hard (not setdefault) and
replaces the module level extractor of tldextract by one without URLs and
without cache, which reads the snapshot that ships inside the package.

install_network_tripwire() adds an audit hook that ends every Python level
network step with PermissionError. It sees Python only; C code (LibreOffice,
libxml2) is covered by seccomp in the jail and by the --network none run of
plan 02-22. It is never installed in the server process: the server talks to
Nextcloud. It belongs in detection children and tests. Nothing is logged.
"""

import os
import sys
import types
from collections.abc import Mapping
from typing import Final

OFFLINE_ENV: Final[Mapping[str, str]] = types.MappingProxyType(
    {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        # An empty value is an empty URL list in tldextract 5.4.0.
        "TLDEXTRACT_PUBLIC_SUFFIX_LIST_URLS": "",
    }
)

NETWORK_EVENTS: Final = frozenset(
    {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.sendto", "urllib.Request"}
)


def configure() -> None:
    """Offline variables and a tldextract without URLs and cache; safe to call twice."""
    for key, value in OFFLINE_ENV.items():
        os.environ[key] = value
    import tldextract.tldextract as extractor_module

    extractor_module.TLD_EXTRACTOR = extractor_module.TLDExtract(
        suffix_list_urls=(), cache_dir=None, fallback_to_snapshot=True
    )


def _tripwire(event: str, _args: tuple[object, ...]) -> None:
    if event in NETWORK_EVENTS:
        msg = "network access is not allowed in this process"
        raise PermissionError(msg)


def install_network_tripwire() -> None:
    """From now on every Python network step of this process fails. Cannot be undone."""
    sys.addaudithook(_tripwire)
