---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 22
subsystem: sandbox
tags: [safe-03, res-02, container-proof, canary, a3, a8, tripwire]
requires: [02-07, 02-10, 02-12, 02-17, 02-19, 02-21]
provides: [tests/test_lo_network.py, tests/test_offline_container.py, tests/probes/offline_stack.py, sandbox.yml Korpus auch im Bridge-Container]
affects: [02-24, 02-25]
tech-stack:
  added: []
  patterns: [Kanarienserver zählt in setup(), Schichtläufe mit je einer Schutzschicht, eigener Zählhaken statt Produktliste]
key-files:
  created:
    - backend/tests/test_lo_network.py
    - backend/tests/test_lo_network_helpers.py
    - backend/tests/test_offline_container.py
    - backend/tests/test_offline_stack_probe.py
    - backend/tests/probes/offline_stack.py
  modified:
    - .github/workflows/sandbox.yml
    - backend/tests/test_workflows.py
    - backend/tests/test_offline.py
decisions:
  - "Kanarien-Korpus: der eingehängte Korpus (Adresse http://127.0.0.1:9/) wird je Kandidat mit retarget() auf den Port des Kanarienservers umgeschrieben; das Image hat kein ci/, make_corpus.py kann dort nicht laufen"
  - "Bridge-Container bekommt den Korpus ebenfalls (Mount + PII_CORPUS), sonst hätte test_bridge_full_chain keine Datei"
  - "Läufe a, b und c verlangen 0 Verbindungen UND ein PDF: ein Lauf, der nichts rendert, zählte 0 aus dem falschen Grund"
  - "Makro-Markierung liegt im Ausgabeordner des Laufs (im Jail schreibbar), damit Landlock das Ergebnis von Lauf a nicht verdeckt"
  - "Zählhaken der Probe zählt Schritte mit Gegenstelle oder Namensauflösung und bind außerhalb Loopback, nicht das Anlegen eines Sockets: urllib3 legt beim Import Wegwerf-Sockets an und bindet ::1 Port 0"
metrics:
  duration: "ca. 75 min"
  completed: 2026-11-18
  tasks: "2/2"
---

# Phase 2 Plan 22: Netzbeweise LibreOffice und Erkennungsstapel Summary

Zwei Container-Tests für sandbox.yml. `test_lo_network.py` zählt mit einem Kanarienserver auf 127.0.0.1 jede Verbindung, während die fünf Dokumente mit externem Bezug, die zwei Makro-Dateien des Korpus und ein eigenes OnLoad-Basic-ODT in vier getrennten Schichtläufen durch LibreOffice gehen. `test_offline_container.py` lässt Presidio und GLiNER2 mit `--network none` ohne Jail und im Jail-Profil detect laufen, mit Zählhaken und werfendem Tripwire.

## Commits

| Schritt | Commit | Betreff |
|---|---|---|
| Task 1 | 044c895 | test(02-22): LibreOffice network proof with a canary, layer runs and a positive control |
| Task 2 | 2e6d2ab | test(02-22): RES-02 proof of the detection stack offline in the real image |

## Prüfung (lokal, ohne Docker)

- Gates grün: ruff check, ruff format --check, pyright (latest) 0 Fehler, vulture, shellcheck (geänderte Shell-Zeilen des Bridge-Schritts als Datei, `uvx --offline --from shellcheck-py`).
- Ganze Suite: `1471 passed, 70 skipped` (vorher 1444 passed, 58 skipped; +27 lokale Tests, +12 Container-Skips).
- `pytest --collect-only -m "not container" tests/test_lo_network.py`: nichts gesammelt (5 deselected). test_offline_container.py ebenso nur mit `container`.
- Hilfstests mit Positivkontrolle (laufen überall):
  - Kanarie zählt einen nackten connect und eine Anfrage mit Pfad (`GET:/img.png`), vorher 0.
  - retarget: jeder der fünf Kandidaten hat danach die Kanarienadresse und nicht mehr die Korpusadresse, Namen, Reihenfolge und Kompression gleich; harmless.odt bleibt unverändert, mimetype erst und gespeichert.
  - Makro-ODT: dom:load-Ereignis, Module1 mit dem Markierungspfad, Manifest vollständig; der echte Bereiniger nimmt es an (ok, macrosRemoved true) und entfernt Basic/ und den Listener.
  - Schichttabelle a bis d, `positive_control_word`, `closed_problems` feuert auf Verbindung, fehlendes PDF, gelaufenes Makro und Zombies.
  - Probe: falsche Argumente Exit 2; Ereignisfilter mit Positiv- und Negativfällen; Kontrolllauf ohne configure zählt mindestens ein Netzereignis (lokal, Tripwire stoppt den Abruf); Stapellauf ohne Modelle endet mit `presidio:FileNotFoundError` und 0 Netzereignissen nach den Importen von torch und Presidio.
  - AST-Gate aus 02-10 liest jetzt auch tests/probes und meldet für offline_stack.py nichts.

## Neue Logzeilen

- `LO-NET layer=<a|b|c|d|a-bridge> file= connections= pdf= outcome= macro= asked=` je Datei, `LO-NET-ZOMBIES layer= n=` (Tor 0)
- `LO-NET-CONTROL connections= positive_control=<triggered|not_triggered>` (Messwert)
- `OFFLINE-STACK run=<unjailed|jailed|jailed-raise|control> exit= email= person= net_events= events= error= ms=`
- measurements.json: `lo_network_a`, `lo_network_b`, `lo_network_c`, `lo_network_d`, `positive_control`, `positive_control_connections`, `positive_control_macro`, `offline_stack_unjailed`, `offline_stack_jailed`, `offline_stack_jailed_raise`, `offline_positive_control`

## Deviations from Plan

**1. [Rule 3 - blockierend] Korpus mit Kanarienport.** Das Image hat kein ci/, make_corpus.py kann im Container nicht laufen. Der Test schreibt die Kandidaten aus dem eingehängten Korpus mit `retarget()` auf den Port um (nur die Adresse, Mitglied für Mitglied). Positivkontrolle im Fixture: mindestens ein geändertes Mitglied je Kandidat.

**2. [Rule 3 - blockierend] sandbox.yml: Korpus auch im Bridge-Container.** Der Bridge-Lauf hatte weder Mount noch PII_CORPUS. Neu: `-v "${CORPUS}:/corpus:ro"` am Bridge-Container und `-e PII_CORPUS=/corpus` am Bridge-pytest. test_workflows.py prüft beides mit Selbsttest. Datei außerhalb von files_modified.

**3. [Rule 2] Strenger als der Plan.** a, b und c verlangen zusätzlich ein PDF je Datei. Die Kanarie muss im Container vor jedem Lauf einen nackten connect zählen (Fixture), sonst bricht der Test ab. Zombies nach jeder Schicht, nicht nur nach a.

**4. Makro-Markierung im Ausgabeordner statt /tmp/<job>.** Im Jail ist /tmp nicht schreibbar; dort hätte Landlock die Datei verhindert, nicht die Härtung. Der Ausgabeordner ist in allen Läufen schreibbar. Das Korpus-ODT odt_basic.odt hat einen leeren `Sub Main` und einen Listener im Textkörper; deshalb baut der Test ein eigenes ODT mit `office:scripts`, vollständiger Basic-Bibliothek und Manifest.

**5. Lauf c über `soffice.convert` mit abgeschaltetem `harden_profile`.** So läuft genau der Produktweg (Jail, Vorlagenkopie, Socket-Aufräumen), nur ohne die Härtung. Läufe b und d starten soffice mit `soffice.command`, `prepare_profile`/`seed_profile` und `child_env`, ohne Jail.

**6. Zählhaken der Probe enger als zuerst gebaut.** Erster Entwurf zählte jedes Socket-Ereignis und schlug lokal an: urllib3 legt beim Import Sockets an (`_constant.py`) und bindet `::1` Port 0 (`util/connection.py`). Gezählt werden jetzt Ereignisse mit Gegenstelle oder Namensauflösung (connect, sendto, sendmsg, getaddrinfo, gethostbyname, gethostbyaddr, getnameinfo, urllib/http.client/ftplib/smtplib) und bind außerhalb Loopback. Das ist weiter breiter als `offline.NETWORK_EVENTS` (Gegenprobe nicht mit dem Muster der Umsetzung).

**7. Ausgabe der Probe um `event_names` und `error` erweitert.** Nur Ereignisnamen und ein Schrittwort, kein Inhalt; ohne sie wäre ein roter CI-Lauf nicht zu deuten.

**8. Zusätzliche Dateien** `test_lo_network_helpers.py` und `test_offline_stack_probe.py` mit den lokal prüfbaren Teilen (Muster aus 02-21). `test_offline.py`: GATED_ROOTS um tests/probes erweitert (Akzeptanzkriterium des Plans).

## Befunde

- **Presidio lädt bei falschem Modellpfad aus dem Netz.** Lokaler Lauf der Probe mit nicht vorhandenem spaCy-Ordner im Zählmodus: `SpacyNlpEngine.load()` rief den spaCy-Download auf ("No compatible package found ..."), der Prozess endete per `sys.exit`. Dabei ging einmal eine Kompatibilitätsabfrage von diesem Rechner an GitHub (kein Dokumentinhalt; der Test lief ohne werfenden Tripwire). Folgen: Die Probe prüft jetzt vor dem Laden, dass beide Modellordner existieren, fängt auch `SystemExit`, und der lokale Test läuft im Modus raise. **Für den Erkennungs-Kind in Phase 3:** Modellordner vor `SpacyNlpEngine` prüfen, sonst Download-Versuch (im Container durch `--network none`/seccomp gestoppt, aber nicht verlassen).
- urllib3 legt beim Import Wegwerf-Sockets an (AF_INET, AF_INET6 mit bind auf `::1`). Im Jail verweigert seccomp diese Sockets; die früheren detect-Läufe im Jail liefen trotzdem durch, urllib3 fängt das also ab. Kein Recht geöffnet.

## Offen (nur in CI belegbar, nicht geraten)

- Echter Lauf beider Container-Tests in sandbox.yml auf amd64 und arm64, mit Mitschnitt-Schritt (0 Pakete) für `-k bridge`. Kommt mit dem nächsten Push nach Owner-Freigabe (Plan 02-24).
- A3 (xcu wird gelesen und wirkt) ist nur dann belegt, wenn die Positivkontrolle d `triggered` zeigt und b 0 bleibt. Zeigt d `not_triggered`, ist b nicht unterscheidbar; dann legt 02-24 das dem Owner vor.
- A8 (LibreOffice braucht kein AF_INET): Lauf c muss ein PDF je Kandidat liefern.
- Makro-Positivkontrolle: Ob das OnLoad-Basic ohne Härtung überhaupt liefe, steht nur als Messwert `positive_control_macro` (LibreOffice blockiert Dokumentmakros auch im Standard meist).
- Mögliche rote Stellen, die Befunde wären und kein Grund, Rechte zu öffnen: ein Netzereignis in der Probe im Jail detect (zum Beispiel ein Cache-Zugriff von transformers), ein Kandidat ohne PDF in b oder c, eine Verbindung in a bis c.
- Requirements SAFE-03 und RES-02 bleiben offen, bis der Container-Beleg da ist.

## Known Stubs

Keine.

## Threat Flags

Keine neue Angriffsfläche im Produkt; nur Testcode, ein Kanarienserver auf Loopback im Testcontainer und ein read-only Mount von Testdaten in den Bridge-Container. T-02-13, T-02-14, T-02-21, T-02-22 und T-02-51 haben jetzt ihren Container-Test.

## Self-Check: PASSED
