---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 21
subsystem: sandbox
tags: [safe-01, safe-04, container-proof, corpus, a1, a2, rlimit-as]
requires: [02-07, 02-12, 02-14, 02-19]
provides: [tests/test_jail_container.py, tests/test_corpus.py, tests/probes/read_secrets.py, conftest mounted_corpus/load_mounted_corpus, sandbox.yml Korpus unter /corpus]
affects: [02-22, 02-24, 02-25]
tech-stack:
  added: []
  patterns: [Probe im Jail antwortet nur in Wörtern, Kanarienwerte über Datei statt Umgebung, Logzeilen als Tor (JAIL-READ, CORPUS-JAIL-SUM)]
key-files:
  created:
    - backend/tests/test_jail_container.py
    - backend/tests/test_jail_container_helpers.py
    - backend/tests/test_corpus.py
    - backend/tests/probes/read_secrets.py
  modified:
    - backend/tests/conftest.py
    - backend/tests/test_workflows.py
    - .github/workflows/sandbox.yml
    - .planning/phases/02-sicherer-dateieingang-und-kindprozess-sandbox/deferred-items.md
decisions:
  - "Das Test-Image hat kein ci/: sandbox.yml erzeugt den Korpus auf dem Runner mit ci/make_corpus.py und hängt ihn read-only unter /corpus ein (PII_CORPUS); fehlt er, scheitert der Test laut, kein Skip"
  - "Grenzen im Kind über getrlimit, nicht /proc/self/limits: Landlock gibt /proc nicht frei; der Leseversuch wird nur als Wort gemeldet, kein Recht geöffnet"
  - "missing ist im Jail nur erlaubt, wo die Datei auch außerhalb fehlt; sonst muss denied kommen. Positivkontrolle: uid 10001 ohne Jail liest /frpc.toml, client.key und die fremde Datei"
  - "Zombies werden je uid 10001 nach bis zu 5 s gezählt (Server und Tests laufen als 10001), Tor 0"
  - "Eine unlesbare Kindantwort im Korpuslauf ist ein Befund (answer-refused), keine stille damaged-Abbildung"
metrics:
  duration: "ca. 15 min"
  completed: 2026-11-18
  tasks: "2/2"
---

# Phase 2 Plan 21: Container-Beweise Jail und Korpus Summary

Zwei Container-Tests für sandbox.yml: `test_jail_container.py` prüft in jedem der sechs Profile die Lesewege aus Pitfall 1 (/proc/1/environ, /proc/<frpc>/environ, /frpc.toml, /certs/frp/client.key, state.db, fremder Auftragsordner), Umgebung, rlimits, Sockets, Schutzschichten, Gruppen-Kill und Zombies nach echter LibreOffice-Umwandlung mit VmPeak/VmHWM-Messung. `test_corpus.py` schickt den ganzen Korpus durch die echten Kinder precheck und sanitize mit der Fehlerabbildung des Runners.

## Commits

| Schritt | Commit | Betreff |
|---|---|---|
| Task 1 | 0be8589 | test(02-21): container proof that no jailed child reads a secret, keeps its limits and leaves no zombie |
| Task 2 | de8f787 | test(02-21): the whole corpus through the real precheck and sanitize children, the container lives |

## Prüfung (lokal, ohne Docker)

- Gates grün: ruff check, ruff format --check, pyright (latest) 0 Fehler, vulture, shellcheck (die neuen Shell-Zeilen der Workflow-Schritte als Datei geprüft).
- Ganze Suite: `1444 passed, 58 skipped` (vorher 1434 passed, 44 skipped; +10 Hilfstests, +14 Container-Skips).
- `pytest --collect-only -m "not container"` listet weder test_jail_container.py noch test_corpus.py; in der Vollsuite werden beide mit "container only" übersprungen (5 + 6 Profile bzw. 1).
- Akzeptanz: `pytestmark = [pytest.mark.container, pytest.mark.linux]` in beiden Dateien; die vier Pfade wörtlich; `a1_frpc_environ` 4 Treffer, in `test_a1_frpc_environ_is_only_measured` kein assert; `python_child("precheck"` in test_corpus.py; Fehlerwort nur über `runner._child_failure_reason`, Antworten über `runner._read_verdict` und `runner._read_sanitize`.
- `test_jail_container_helpers.py` (läuft überall): Probe liest und sieht den Kanarienwert (Positivkontrolle), antwortet nur in Wörtern, schreibt keinen Wert, sieht einen Kanarienwert in der Umgebung und nennt nur den Schlüssel, weist falsche Argumente ab; 300-Seiten-DOCX hat 299 Seitenumbrüche; `vm_values`; `expected_limits` gegen die Profilwerte; `load_mounted_corpus` scheitert ohne Variable und ohne manifest.json.
- Trockenlauf von test_corpus.py nur im Scratchpad (Kinder im Prozess, ohne Jail, Windows): 47 Dateien, 47 bestanden, 34 abgewiesen, Kontrollen ok, sieben sanitize-Fälle ok/ok, pdf_signed confirm. Das prüft nur die Testlogik, nicht das Jail.

## Neue Logzeilen (Gate statt Diagnose)

- `A1-FRPC-ENVIRON unjailed=<word>` (nur Messung), `DUMPABLE-SERVER-ENVIRON unjailed=<word>` (Tor denied)
- `JAIL-READ profile=<p> control= server_environ= frpc_environ= frpc_toml= client_key= state_db= foreign_file= foreign_listing= env_ok= canary_seen=` (Tor)
- `JAIL-LIMITS profile=<p> ok= proc_self_limits=`, `JAIL-SOCKET profile=<p> inet= unix=`, `JAIL-LAYERS seccomp= landlock= abi=`
- `JAIL-GROUP-KILL timeout= left= grandchild=`, `JAIL-ZOMBIES after=<group-kill|soffice> n=`
- `SOFFICE-MEMORY doc=<harmless_docx|docx_300_pages> pages= vmpeak_kb= vmhwm_kb= samples= ms=`
- `CORPUS-JAIL file=... precheck= sanitize= again= ms= ok=` je Datei, `CORPUS-JAIL-SUM ...` (Tor)
- measurements.json: `a1_frpc_environ`, `dumpable_server_environ`, `jail_reads_<profil>`, `a2_landlock`, `soffice_vmpeak_kb`, `soffice_vmhwm_kb`, `corpus_jail`

## Deviations from Plan

**1. [Rule 3 - blockierend] Korpus im Container.** Das Test-Image enthält kein `ci/` (conftest-Kommentar, 02-16), die Fixture `corpus` ginge dort ins Leere. sandbox.yml bekommt den Schritt "Make the attack corpus" (`python3 ci/make_corpus.py`, nur Standardbibliothek), den Mount `-v "${CORPUS}:/corpus:ro"` und `-e PII_CORPUS=/corpus`; conftest die Fixture `mounted_corpus` (scheitert laut, kein Skip); test_workflows.py verlangt die drei Stellen. Dateien außerhalb von files_modified.

**2. Grenzen über getrlimit statt /proc/self/limits.** Landlock gibt keinem Profil /proc frei, der Plan-Weg würde in jedem Kind `denied` liefern. Die Probe liest die Grenzen per `getrlimit` (dieselben Kernelwerte) und meldet den Leseversuch auf /proc/self/limits nur als Wort. Kein Jail-Recht geöffnet.

**3. Heartbeat über den HaRP-Socket.** Der Plan nennt `http://127.0.0.1:<APP_PORT>/heartbeat`; in sandbox.yml lauscht der Server hinter HaRP nur auf `/tmp/exapp.sock`. Der Test nimmt wie der Smoke-Test den Socket, ohne HaRP den Port.

**4. Strenger als der Plan.** `missing` nur, wo die Datei auch ohne Jail fehlt; Positivkontrolle, dass uid 10001 ohne Jail /frpc.toml, client.key und die fremde Datei liest; fremder Ordner auch per Listing; Seitenzahl 300 der Umwandlung geprüft; Sampler muss soffice.bin gesehen haben; jedes Kind unter Profil-Wanduhr plus 5 s; Anzahl Abweisungen gleich Zahl der Bombenfälle im Manifest.

**5. Zombies je uid 10001 statt global.** Server und Tests laufen als 10001; andere uids gibt es im Container nicht als Arbeitsprozesse. Tor 0 nach bis zu 5 s.

**6. Zusätzliche Datei `test_jail_container_helpers.py`** mit den lokal prüfbaren Teilen (Probe, Hilfsfunktionen, Fixture), damit eine kaputte Probe das Jail nicht dicht aussehen lässt.

## Offen (nur in CI belegbar, nicht geraten)

- Der echte Lauf beider Container-Tests in sandbox.yml auf amd64 und arm64 steht aus. Er kommt mit dem nächsten Push nach Owner-Freigabe (Plan 02-24).
- A1: Ergebnis `a1_frpc_environ` erst aus dem Lauf; bei `read` entscheidet 02-24 nach D-02-14.
- A2: `JAIL-LAYERS` muss auf beiden Architekturen `active/active` zeigen, sonst AR (02-25).
- RLIMIT_AS soffice (D-02-13): Grundlage sind `soffice_vmpeak_kb`/`soffice_vmhwm_kb` aus dem Lauf.
- Mögliche rote Stellen, die Befunde wären und kein Grund, Rechte zu öffnen: eine Datei, die im Jail `read` liefert; ein precheck-/sanitize-Kind, das unter Landlock eine Bibliothek nicht lädt (Exit 71, Wort render_failed); Zombies nach soffice. Erst der Lauf zeigt es.
- Requirements SAFE-01 und SAFE-04 bleiben offen, bis der Container-Beleg da ist.
- Nebenbefund (deferred-items.md): test_soffice_risks.py einmal lokal flackernd, nicht behoben.

## Known Stubs

Keine.

## Threat Flags

Keine neue Angriffsfläche; nur Testcode und ein read-only Mount von Testdaten in den Testcontainer. T-02-01, T-02-02, T-02-03, T-02-06 und T-02-08 haben jetzt ihren Container-Test.

## Self-Check: PASSED
