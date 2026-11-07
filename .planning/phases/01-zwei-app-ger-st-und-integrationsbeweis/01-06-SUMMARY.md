---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 06
subsystem: backend-core
tags: [logging, allowlist, strenum, httpx, queue-client, gateway, companion, memory-guard]
requires: [01-01, 01-03, 01-05]
provides:
  - "logs.py: ALLOWED_EXTRA (SKELETON-Menge), JsonFormatter ohne Traceback und ohne Formatierungsargumente, exc_type plus where (modul:zeile), uvicorn.access aus"
  - "model.py: StrEnums Stage, Reason, Task, AckResult nach SKELETON"
  - "config.py: storage_root, work_dir(job_id), state_db_path, MAX_SOURCE_BYTES = 268435456, FALLBACK_STORAGE_DIRNAME"
  - "nc.py: Claim, claim, progress, ack, FetchResult, fetch_source, fetch_handshake, new_client, app_api_headers"
  - "companion.py: ok/missing/unknown, may_work, check_once, refresh_if_stale, run_periodic"
  - "resources/memory_guard.py: NEED, RESERVE, headroom_bytes, admits, admit, anon_bytes, memory_events; resources/hardware.py: detect"
affects: [01-10, 01-15, 01-17]
tech-stack:
  added: []
  patterns:
    - "Antworten der PHP-App feldweise prüfen (Findling _mapping/_positive_int), sonst verwerfen"
    - "Ausgehende Werte nur aus den Enums; Wert außerhalb wirft vor dem Senden"
    - "Download über <target>.part und os.replace erst bei Erfolg"
    - "Logzeile: Literal plus Allowlist-Skalare, Ausnahme nur als Typ und Ort"
key-files:
  created:
    - backend/src/pii_redaction_backend/model.py
    - backend/src/pii_redaction_backend/companion.py
    - backend/src/pii_redaction_backend/resources/__init__.py
    - backend/src/pii_redaction_backend/resources/hardware.py
    - backend/src/pii_redaction_backend/resources/memory_guard.py
    - backend/tests/test_model.py
    - backend/tests/test_nc.py
    - backend/tests/test_companion.py
    - backend/tests/test_handshake.py
    - backend/tests/test_memory_guard.py
  modified:
    - backend/src/pii_redaction_backend/logs.py
    - backend/src/pii_redaction_backend/config.py
    - backend/src/pii_redaction_backend/nc.py
    - backend/src/pii_redaction_backend/store/repo.py
    - backend/tests/test_logs.py
    - backend/tests/test_config.py
    - backend/tests/test_boundary.py
key-decisions:
  - "Handshake läuft über httpx (fetch_handshake(client=None)) statt über nc_py_api, damit alle Aufrufe in die PHP-App einen Client, eine Kopfzeilen-Funktion und denselben Redirect-Schutz haben"
  - "403 beim Handshake gilt wie 404 als missing (die PHP-App hält diesen Container nicht für ihr Backend)"
  - "companion.may_work() ist nur bei ok wahr; unknown (auch 412 vor der Aktivierung) lässt den Runner nicht arbeiten"
  - "fetch_source ohne gültigen X-Pii-Etag ist nicht ok (fail closed), weil ack den gesehenen Etag braucht"
  - "Formatter schreibt record.msg als Literal, nie getMessage(); nicht skalare Extras werden verworfen statt als repr geschrieben"
requirements-completed: []  # PLAT-02 und JOB-06 erst mit Runner (Plan 10) und CI-Lauf belegt
metrics:
  duration: "ca. 10 min"
  completed: 2026-11-07
  tasks: 3
  files: 17
---

# Phase 1 Plan 06: Container-Kern Summary

Der Container hat jetzt seinen Kern für den Runner aus Plan 10. Logzeilen tragen nur Allowlist-Felder und bei Ausnahmen nur Typ und Ort, nie Text oder Traceback. `nc.py` ist der einzige HTTP-Ort: Claim, Fortschritt, Abschluss, Handshake und der auftragsgebundene Quelldownload mit sha256 im Strom, Größendeckel, `X-Pii-Etag` und 409 als stale. Dazu kommen der Gegen-App-Zustand und der RAM-Wächter aus Findling.

## Ergebnis

- **Task 1 (TDD, RED `dfb6e9a`, GREEN `e8c376b`):** `ALLOWED_EXTRA` ist genau die SKELETON-Menge, `test_log_calls.py` gleicht sie jetzt aktiv ab. Ein `ValueError("PIIKANARIE7Q4XZ9")` aus Paketcode ergibt `exc_type` und `where` (z. B. `config:123`), aber weder Kanarie noch "Traceback". Ein Test ersetzt `formatException` durch eine Falle. Formatierungsargumente (auch von uvicorn) erreichen die Zeile nie. `uvicorn.access` ist abgeschaltet, `uvicorn`, `uvicorn.error` und `starlette` laufen über den JSON-Formatter. `model.py` hat die vier StrEnums, `repo.py` prüft gegen sie. `config.work_dir(7)` liegt unter `APP_PERSISTENT_STORAGE/work/7`; 0, negative Zahlen und `True` werfen.
- **Task 2 (TDD, RED `f863cb7`, GREEN `a0a172e`):** `claim` verwirft leere Antworten, `task: delete`, negative oder boolsche IDs, fehlendes oder nicht hexadezimales Token, Etag über 40 Zeichen, leere oder zu lange Nutzer-IDs mit Steuerzeichen und `leaseSeconds: 0`. Zahlen als Strings (OCS) werden angenommen. `progress` und `ack` senden nur Enum-Werte und prüfen sha256, Bildmaß und Zählwerte vor dem Senden; 409 ergibt False. `fetch_source` schreibt über `src.part`, ersetzt das Ziel nur bei Erfolg und löscht die Teildatei in jedem anderen Fall (409, 403/404/500, 302, fehlender Etag, Deckel überschritten, Kurzlesen, abgebrochener Strom). Jede Anfrage setzt `follow_redirects=False` zusätzlich zum Client. Kopfzeilen: `EX-APP-ID` aus der Umgebung, `AUTHORIZATION-APP-API` mit leerem Nutzer. Companion: 200 mit gültiger Version `ok`, 403/404 `missing`, 412 `unknown` ohne Fehlerzählung, drei Netzfehler in Folge `missing`. `test_boundary.py` bewacht zusätzlich `urllib` und `http.client`.
- **Task 3 (TDD, RED `1cc5c67`, GREEN `1e92e58`):** `hardware.py` und `memory_guard.py` aus Findling mit neuem Importpfad, alle Findling-Tests übernommen. Neu: `NEED = {"render": 512 MiB, "soffice": 1 GiB}`, `RESERVE = 256 MiB`, beide mit "vorläufig, nach Messung Phase 1/2 festschreiben". `admit("soffice")` ist bei 900 MiB False, ab 1280 MiB True; unlesbarer Kopfraum lässt nichts zu; eine unbekannte Art wirft `KeyError`. Das SKELETON-Beispiel (2 GiB Grenze, 1 GiB anon, 3 GiB verfügbar) ergibt 1 GiB.

Gates in `backend/` vor jedem Commit: ruff (inkl. `../scripts`), ruff format --check, pyright latest 0 Fehler, vulture leer, pytest seriell. Endstand: 361 passed, 3 skipped (POSIX-Tests aus Plan 05). Neue Pakete: keine (httpx 0.28.1 war schon Laufzeit-Pin).

## TDD Gate Compliance

Bei allen drei Tasks liegt der `test(...)`-Commit vor dem `feat(...)`-Commit. Die RED-Läufe scheiterten wie erwartet (fehlende Module beziehungsweise 16 rote Tests in Task 1).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2] Handshake über httpx statt nc_py_api**
- **Issue:** AVS fragt den Handshake über `nc._session.ocs`. Damit gäbe es zwei Wege in die PHP-App mit unterschiedlichem Redirect- und Fehlerverhalten.
- **Fix:** `fetch_handshake(client=None)` nutzt denselben httpx-Client und dieselben Kopfzeilen wie die Queue; Statuscodes (404, 412) kommen direkt aus der Antwort.
- **Commit:** a0a172e

**2. [Rule 2] Fehlender oder kaputter `X-Pii-Etag` ist kein Erfolg**
- **Issue:** Der Plan nennt den Header, aber nicht den Fall ohne Header. Ohne Etag kann `ack` die Etag-Bindung (JOB-04) nicht belegen.
- **Fix:** `ok=False`, Teildatei gelöscht.
- **Commit:** a0a172e

**3. [Rule 2] Grenz-Gate um `urllib` und `http.client` ergänzt**
- **Issue:** Die Plan-Liste nennt `urllib`, die alte `test_boundary.py` hatte nur `urllib3`. `http.client` ist ebenfalls ein Client. `from http import HTTPStatus` bleibt erlaubt.
- **Commit:** f863cb7

**4. [Rule 2] Nicht skalare Extras werden verworfen**
- **Issue:** Der alte Formatter schrieb `repr(value)`, darüber könnte eine Liste mit Inhalt in die Zeile gelangen.
- **Fix:** Nur `str`, `int`, `float`, `bool` aus der Allowlist kommen in die Zeile.
- **Commit:** e8c376b

Kleinere Ergänzungen: `companion.may_work()` als Abfrage für den Runner, `memory_events` und `anon_bytes` aus Findling mitkopiert (Plan 10 unterscheidet damit `out_of_memory`), `config.storage_root()`.

## Hinweise für spätere Pläne

- **Plan 10 (Runner):** `nc.progress`/`nc.ack` liefern False sowohl bei 409 als auch bei Netzfehlern. Ein Netzfehler beim `ack` sollte wiederholt werden, solange der Lease läuft; ein 409 beendet die Arbeit am Auftrag. Wer das unterscheiden muss, ergänzt einen Rückgabewert, ohne die Signatur aus `<interfaces>` zu brechen.
- **Plan 10:** `claim` loggt Netzfehler nur auf debug; der Runner zählt Fehlrunden und entscheidet über Log und Rückoff (Findling-Muster).
- **Plan 10/11 (/status):** `companion.current().version` gegen `config.app_version()` vergleichen (Lockstep Major.Minor).
- **Plan 07 (Gateway PHP):** Der Container erwartet `X-Pii-Etag` mit höchstens 40 sichtbaren ASCII-Zeichen ohne Leerzeichen und Query `token` als 16 bis 64 Kleinbuchstaben-Hex (heute 32 aus `bin2hex(random_bytes(16))`).

## Known Stubs

Keine.

## Threat Flags

Keine neue Fläche außerhalb des Bedrohungsmodells. T-01-06-01 bis -05 sind mitigiert: Allowlist und Kanarien-Test (01), Feldprüfung (02), Deckel plus `.part` plus keine Weiterleitung (03), APP_SECRET nur in `app_api_headers` und nie geloggt (04), `admit` mit fail closed (05).

## Self-Check: PASSED

- Dateien vorhanden: model.py, companion.py, resources/{__init__,hardware,memory_guard}.py, test_model.py, test_nc.py, test_companion.py, test_handshake.py, test_memory_guard.py
- Commits vorhanden: dfb6e9a, e8c376b, f863cb7, a0a172e, 1cc5c67, 1e92e58
