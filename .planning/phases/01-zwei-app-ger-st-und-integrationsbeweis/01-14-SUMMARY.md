---
phase: 01-zwei-app-ger-st-und-integrationsbeweis
plan: 14
subsystem: php-publish
tags: [notifier, suffix, publish, queued-job, listener, registration]
requires: [01-02, 01-04, 01-08, 01-12]
provides:
  - "Notification\\Notifier: vier Betreffe mit festen Katalogsätzen, Link nur auf die Prüfseite"
  - "Service\\Suffix::outputName(original, Mode, Lang)"
  - "Service\\PublishService::publish(Job) und BackgroundJob\\PublishJob (QueuedJob, ['jobId' => int])"
  - "Listener\\FileLifecycleListener (NodeWrittenEvent, BeforeNodeDeletedEvent), Listener\\LoadFilesScriptsListener"
  - "Application::register mit Notifier und drei Listener-Registrierungen"
  - "JobServiceFactory: output(), Elternordner mit isCreatable, getNonExistingName, newFile"
affects: [01-15, 01-16, 01-17]
tech-stack:
  added: []
  patterns:
    - "Ausgabe aus dem Container: gedeckelt in php://temp kopiert und dabei gehasht, erst nach sha256- und Größenabgleich geschrieben"
    - "Schreiben als Auftraggeber über ReaderContext, Übergänge danach außerhalb"
key-files:
  created:
    - php/lib/Notification/Notifier.php
    - php/lib/Service/Suffix.php
    - php/lib/Service/PublishService.php
    - php/lib/BackgroundJob/PublishJob.php
    - php/lib/Listener/FileLifecycleListener.php
    - php/lib/Listener/LoadFilesScriptsListener.php
    - php/tests/Unit/NotifierTest.php
    - php/tests/Unit/SuffixTest.php
    - php/tests/Unit/PublishServiceTest.php
    - php/tests/Unit/FileLifecycleListenerTest.php
  modified:
    - php/lib/AppInfo/Application.php
    - php/tests/Unit/JobServiceFactory.php
    - backend/tests/test_php_gates.py
key-decisions:
  - "Gate-Regel 17 lässt die von INotifier verlangte Deklaration getName() zu (App-Name, liest nichts); jeder Aufruf von getName( bleibt verboten (Selbsttest für beides)"
  - "Original geändert bei der Ablage ergibt stale (wie im Plan), NotPermittedException beim Schreiben ergibt target_not_writable, jede andere Ausnahme fängt PublishJob als check_error"
  - "Ein Strom, der weder endet noch liefert, bricht nach 1000 leeren Lesevorgängen als check_error ab"
requirements-completed: []  # JOB-02/JOB-04 erst mit CI-PHPUnit und dem echten Lauf (Plan 15) belegt
metrics:
  duration: "ca. 40 min"
  completed: 2026-11-07
  tasks: 3
  files: 13
---

# Phase 1 Plan 14: Benachrichtigung, Ablage und Lebenszyklus Summary

Der Auftrag lässt sich jetzt nach dem Container abschließen: Benachrichtigungen ohne Dateinamen in der Sprache des Empfängers, die Platzhalter-Kopie mit echtem Namenszusatz neben dem Original (als Hintergrundarbeit, erst nach Prüfsummenabgleich), und Schreib- oder Löschereignisse am Original beenden offene Aufträge.

## Ergebnis

- **Task 1 (`80506c3`):** `Notifier` mit `getID` `pii_redaction`, `getName` "PII Redaction"; `prepare` wirft `UnknownNotificationException` für fremde App und unbekannten Betreff, setzt Betreff und Nachricht als feste Katalogsätze ohne Parameter, den Link nur bei Objekt `job` mit numerischer ID (`linkToRouteAbsolute('pii_redaction.review.page')`) und das Icon absolut. `Suffix::outputName`: Stamm ohne letzte Endung (führender Punkt und fehlende Endung bleiben ganz), Zusatz nach Modus und Sprache, immer `.pdf`, NFC. `NotifierTest` (16 Datensätze je Betreff und Sprache mit den echten Katalogen, Link, Icon, ungültige Objekt-ID, beide Ausnahmen), `SuffixTest` (9 Datensätze, NFD nach NFC).
- **Task 2 (`71e0d08`):** `PublishService::publish` nur aus `verified`: Ausgabe null ergibt `failed(backend_unavailable)`; Strom in `php://temp/maxmemory:8388608` mit sha256, über 32 MiB oder Abweichung bei Prüfsumme/Größe `failed(check_error)`; dann als Auftraggeber: Original weg `cancelled(original_deleted)`, Etag anders `stale`, Sperre `failed(download_blocked)`, Ordner nicht anlegbar oder Schreiben verweigert `failed(target_not_writable)`, sonst `getNonExistingName` plus `newFile` und `toPublished`. Temp-Strom im `finally` geschlossen. `PublishJob extends QueuedJob`, prüft `jobId`, fängt jede Ausnahme mit Klasse im Log und beendet einen offenen Auftrag als `check_error`. `PublishServiceTest`: 13 Tests.
- **Task 3 (`a21e861`):** `FileLifecycleListener` und `LoadFilesScriptsListener`, `Application::register` mit `registerNotifierService` und drei `registerEventListener`. `FileLifecycleListenerTest`: 7 Tests (Schreiben, Endzustände, Löschen ohne Benachrichtigung, andere Datei, Ordner, fremdes Ereignis, Ausnahme).

Gates in `backend/` vor jedem Commit: ruff, ruff format --check, pyright latest 0 Fehler, vulture leer, pytest 413 passed / 3 skipped; `npm run typecheck` und `npm run build` grün. Akzeptanz-greps: `UnknownNotificationException` vorhanden, Zusätze 3, `FORM_C` 1, `newFile(` 1, `getNonExistingName` 1, `hash_equals` 1, `33554432` 1, `extends QueuedJob` 1, `registerEventListener` 3, `registerNotifierService` 1, `addInitScript(...)` 1, Testmethoden 13 und 7. Abweichung: `grep -cE "getName\(|..." Notifier.php` ergibt 1 (siehe unten).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3] Gate-Regel 17 gegen die Pflichtmethode von INotifier**
- **Issue:** `INotifier` verlangt `public function getName(): string`; Regel 17 und das Akzeptanz-grep verbieten jedes `getName(` im Ordner `Notification`. Beides zugleich ist nicht erfüllbar.
- **Fix:** Regel 17 nimmt nur die Deklaration `function getName(` heraus; Aufrufe wie `$node->getName()` schlagen weiter an. Zwei neue Selbsttest-Zeilen belegen beides. Das Akzeptanz-grep ergibt deshalb 1 (die Deklaration).
- **Commit:** 80506c3

**2. [Rule 2] Schutz gegen einen Strom ohne Ende und ohne Daten**
- **Fix:** nach 1000 leeren Lesevorgängen Abbruch als `check_error`.
- **Commit:** 71e0d08

**3. [Rule 2] Verweigertes Schreiben**
- **Issue:** Der Plan nennt nur `isCreatable()`; Quota oder eine Speicherregel können `newFile` trotzdem ablehnen.
- **Fix:** `NotPermittedException` ergibt `target_not_writable`, alles andere fängt `PublishJob`.
- **Commit:** 71e0d08

**4. Test "Ausnahme im Mapper"**
- `JobMapper` ist `final` und läuft gegen die echte CI-Datenbank; die Ausnahme wird deshalb über `File::getId()` ausgelöst (gleicher `try`-Block wie der Mapper-Aufruf).

## Known Stubs

Keine.

## Threat Flags

Keine neue Fläche außerhalb des Bedrohungsmodells. T-01-14-01 bis -06 mitigiert (Texte ohne Namen mit Gate 17 und Test je Sprache; sha256/Größe/Deckel; `getNonExistingName` plus `newFile`, nie Überschreiben; `actAs` mit Recheck, `isCreatable`, Sperre; Listener plus Etag-Prüfung vor der Ablage; Ablage als `QueuedJob`).

## Self-Check: PASSED

- Dateien vorhanden: Notifier.php, Suffix.php, PublishService.php, PublishJob.php, beide Listener, vier Testklassen
- Commits vorhanden: 80506c3, 71e0d08, a21e861
