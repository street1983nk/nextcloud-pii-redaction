---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 12
subsystem: php-queue
tags: [queue, gateway, lease, token, etag, ocs]
requires: [01-02, 01-04, 01-08]
provides:
  - "QueueController: OCS POST queue/claim, queue/{jobId}/progress, queue/{jobId}/ack"
  - "GatewayController: OCS GET files/{jobId}?token= mit X-Pii-Etag"
  - "JobServiceFactory: fopen-Doppel für Datei 42 ($content, $openedAs), getId 42"
affects: [01-14, 01-15, 01-17]
tech-stack:
  added: []
  patterns:
    - "Container-Werte: falsche Liste oder Bereich 400, nicht (mehr) der eigene Auftrag 409"
    - "ack nur über das Claim-Token (hash_equals); der nächste Claim ersetzt es nach Lease-Ablauf"
    - "Ergebnis gelesen, aber nicht übernommen (stale/failed beim ack review): 409 mit {reason}"
key-files:
  created:
    - php/lib/Controller/QueueController.php
    - php/lib/Controller/GatewayController.php
    - php/tests/Unit/QueueControllerTest.php
    - php/tests/Unit/GatewayControllerTest.php
  modified:
    - php/tests/Unit/JobServiceFactory.php
key-decisions:
  - "ack prüft nur das Claim-Token, nicht den Lease: ein späteres ack mit noch gültigem Token ist harmlos, nach einem neuen Claim ist das Token ein anderes"
  - "ack review mit abweichendem oder geändertem Etag bzw. gescheitertem Recheck antwortet 409 mit {reason}, nachdem der Auftrag stale/failed wurde"
  - "Gateway: Datei nicht zu öffnen (Ausnahme oder kein Strom) ergibt 503 ohne Zustandswechsel; der Lease regelt die Wiederholung (passt zum Runner: 5xx ergibt kein ack)"
requirements-completed: []  # JOB-02/03/04/06 erst mit CI-PHPUnit und dem Container-Lauf (Plan 15) belegt
metrics:
  duration: "ca. 30 min"
  completed: 2026-11-07
  tasks: 2
  files: 5
---

# Phase 1 Plan 12: Warteschlange und Gateway Summary

Die Container-Seite der PHP-App steht: claim, progress und ack sind an Token, Lease und geschlossene Listen gebunden, und das Gateway liefert nur die Datei des gerade geleasten Auftrags, als Auftraggeber gelesen und nur in der Version, auf die der Auftrag gestartet wurde.

## Ergebnis

- **Task 1 (`3d63bfc`):** `QueueController` mit drei `ExAppRequired`-Routen, jede beginnt mit dem Fremd-App-Wächter. `claim` ruft `ensureSlot` und `claimNext` und antwortet mit den sieben SKELETON-Feldern oder `[]`. `progress` prüft `Stage::tryFrom`, Zähler (nicht negativ, `done <= total`, `total <= 100000`) mit 400, dann Token (`hash_equals`), Zustand `analyzing`/`applying` und Lease mit 409, verlängert den Lease und speichert Stufe und Zähler. `ack`: `review` verlangt Seitenzahl, Bildmaß als ganze Zahlen 1 bis 20000 und `etagSeen`; abweichender gesehener Etag oder `Recheck::Changed` ergibt `toStale`, Missing/Sperre `toFailed(not_readable|download_blocked)`, sonst `toReview`. `verified` verlangt 64 Kleinbuchstaben-Hex und Größe 1 bis 33554432, dann `toVerified` und `IJobList::add(PublishJob::class, ['jobId' => …])`. `failed` nur mit `Reason::tryFrom`. `purged` nur bei Aufgabe purge. Den Lease gibt `JobService` bei jedem Übergang zurück. `QueueControllerTest`: 20 Tests.
- **Task 2 (`03241bb`):** `GatewayController::file(jobId, token)` nach dem AVS-Gerüst: Auftrag mit passendem Token, Zustand `analyzing` und lebendem Lease, sonst 404 ohne Unterscheidung. Recheck als Auftraggeber; Missing 404 plus `failed(not_readable)`, Sperre 403 plus `failed(download_blocked)`, Etag geändert 409 plus `stale`. Bei Ok `fopen('rb')` und `StreamResponse` mit `Content-Type: application/octet-stream`, `X-Pii-Etag`, `Cache-Control: no-store`, ohne Dateinamen-Kopfzeile. `GatewayControllerTest`: 10 Tests.

Gates in `backend/` vor jedem Commit: ruff (inkl. `../scripts`), ruff format --check, pyright latest 0 Fehler, vulture leer, pytest 413 passed / 3 skipped. PHP-Gates 1 bis 20 grün (Regel 1 Wächter in allen vier OCS-Methoden, Regel 12 `recheck(` im Gateway). Akzeptanz-greps: Wächter 3, `hash_equals` 2, `Stage::tryFrom|Reason::tryFrom` 2, `PublishJob::class` 1, `X-Pii-Etag` 1, `Content-Disposition` 0, `recheck(` 1. PHP lokal nur statisch; PHPUnit nach dem nächsten Owner-freigegebenen Push in CI.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2] `image` als Parameter von `ack`**
- **Issue:** Die Plan-Signatur nennt kein `image`, der Vertrag (SKELETON, `nc.py`) schickt das Bildmaß als `image: {width, height}`.
- **Fix:** `?array $image = null` zusätzlich; geprüft wie im Plan beschrieben.
- **Commit:** 3d63bfc

**2. [Rule 2] Gateway 503 für nicht zu öffnende Dateien**
- **Issue:** Der Plan nennt nur 404/403/409. Ein gesperrter oder kurz nicht erreichbarer Speicher wäre sonst ein falscher Endzustand.
- **Fix:** Ausnahme oder fehlender Strom ergibt 503 ohne Übergang, Log nur mit Klasse.
- **Commit:** 03241bb

**3. [Rule 3] fopen im Test-Trait**
- **Issue:** Das Gateway liest den Inhalt; der gemeinsame Datei-Doppel hatte kein `fopen`.
- **Fix:** `JobServiceFactory` liefert `$content` und merkt sich die Modi in `$openedAs`; dazu `getId() = 42` für Plan 14.
- **Commit:** 03241bb

**4. [Rule 1] Testhelfer `status()` verletzte Gate-Regel 10**
- **Fix:** in `jobStatus()` umbenannt (TestCase::status ist final).
- **Commit:** 03241bb

## Hinweise für spätere Pläne

- **Plan 14:** `PublishJob` bekommt `['jobId' => int]`; der Klassenname ist `OCA\PiiRedaction\BackgroundJob\PublishJob`.
- **Plan 15:** Ein ack review nach Etag-Wechsel antwortet 409; der Runner behandelt das als Ablehnung (kein erneutes ack), der purge räumt danach.

## Known Stubs

Keine.

## Threat Flags

Keine neue Fläche außerhalb des Bedrohungsmodells. T-01-12-01 bis -06 mitigiert (Wächter je Route plus Test; Gateway nur mit Token, Lease, Zustand, Recheck als Auftraggeber und gleichem Etag; Listen und Bereiche mit 400; sha256-Form und Größendeckel, Abgleich gegen den Strom in Plan 14; keine Namenskopfzeile; Etag an Gateway und ack).

## Self-Check: PASSED

- Dateien vorhanden: php/lib/Controller/QueueController.php, php/lib/Controller/GatewayController.php, beide Testklassen
- Commits vorhanden: 3d63bfc, 03241bb
