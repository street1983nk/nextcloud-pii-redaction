---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 15
subsystem: php-queue
tags: [job-05, claim, ack, signature]
requires: [02-05, 02-11]
provides: [claim expected/confirmed, ack confirm, ack review flags, ReviewController confirmSignature/declineSignature, JobService::formatOf/claimFacts]
affects: [02-18, 02-19, 02-20]
key-files:
  modified:
    - php/lib/Controller/QueueController.php
    - php/lib/Controller/ReviewController.php
    - php/lib/Service/JobService.php
    - php/tests/Unit/QueueControllerTest.php
    - php/tests/Unit/ReviewControllerTest.php
decisions:
  - "expected und confirmed nur in Claims der Aufgabe analyze; expected ist null, wenn die Datei weg ist oder inzwischen einen anderen MIME hat (der Container entscheidet dann unsupported_format, Plan 02-19)"
  - "Die drei Ack-Flags sind untypisierte Parameter (mixed), weil das Framework sonst 'yes' zu true und '7' zu 7 machen würde; angenommen wird nur echtes JSON-bool bzw. int 0 bis 10000"
  - "Flags werden erst nach allen Prüfungen und direkt vor toReview protokolliert"
  - "confirm/decline: recheckMember in der Route selbst (Gate-Regel 12), gemeinsame Auswertung in decideSignature; Changed/DownloadBlocked wie beim Platzhalter 409 mit Grund"
metrics:
  completed: 2026-11-17
  tasks: "2/2"
---

# Phase 2 Plan 15: Claim/Ack-Vertrag und Signatur-Routen Summary

Der Claim einer Analyse nennt `expected` (pdf/docx/odt aus dem MIME, sonst null) und `confirmed` (Event signature_confirmed); `ack confirm` führt aus analyzing in den Zustand confirm; `ack review` nimmt die Bereinigungs-Flags nur streng typisiert an; `POST /review/{jobId}/confirm` und `/decline` erlauben nur dem Auftraggeber die Entscheidung.

## Commits

| Schritt | Commit |
|---|---|
| Task 1 Tests | d445a25 |
| Task 1 Umsetzung | 961c64b |
| Task 2 Tests | f536ede |
| Task 2 Umsetzung | ed3374a |

## Prüfung

- Suite 1008 passed, 18 skipped; PHP-Gates (Regel 12 Recheck je Route, CSRF unverändert: 2 NoCSRFRequired wie vorher) grün.
- PHPUnit (laufen in php.yml nach dem Push-Tor 02-16): Format je MIME, null bei fremdem MIME, confirmed erst nach Bestätigung, Apply-Claims ohne die Felder, confirm aus analyzing 200 und aus applying 409, sieben falsche Flag-Formen 400, gültige Flags drei Events, keine Flags keine Events, fünf Vorprüfungsgründe bei failed; Routen: bestätigen 202 queued, ablehnen 202 cancelled ohne Benachrichtigung, fremder Nutzer/unbekannter Auftrag/unlesbare Datei 404, anderer Status 409 mit Status.

## Deviations from Plan

- JobService (Datei nicht in files_modified) bekommt `formatOf` und `claimFacts`, damit der Controller ohne neuen Konstruktor-Parameter auskommt und die MIME-Liste nur an einer Stelle steht.
- Der alte Test "confirm noch nicht behandelt" wurde durch die echten confirm-Fälle ersetzt.

## Threat Flags

Keine neuen Endpunkte ausserhalb des Plans.

## Self-Check: PASSED
