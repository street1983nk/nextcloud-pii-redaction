---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: "02-23 abgeschlossen; Quick-Task 261118-hs4 setzt Owner-Entscheid A zu D-02-02 um (lokal, ungepusht: a2a5d59, bb328c5); nächster Schritt 02-24"
last_updated: "2026-11-18T11:27:54.750Z"
last_activity: 2026-11-18 -- Quick-Task 261118-k0t: ci/refusals.sh sendet beim Formular-Login den Origin-Kopf, CSRF-Ablehnung 412 beim Namen (CI-Lauf offen)
progress:
  total_phases: 15
  completed_phases: 1
  total_plans: 46
  completed_plans: 44
  percent: 7
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-11-07)

**Core value:** Eine Datei aus Nextcloud wird mit einem Klick lokal auf personenbezogene Daten geprüft; nach menschlicher Prüfung entsteht neben dem Original eine geschwärzte oder pseudonymisierte Kopie, in der nachweislich nichts Geschwärztes mehr steckt. Kein Inhalt verlässt den Server.
**Current focus:** Phase 2: Sicherer Dateieingang und Kindprozess-Sandbox

## Current Position

Phase: 2 of 15 (Sicherer Dateieingang und Kindprozess-Sandbox)
Plan: 23 of 25 in current phase (02-01 bis 02-23 abgeschlossen; origin/phase-02 bei 5a1edd2, 02-19 bis 02-23 lokal ungepusht; Container-Läufe von 02-21 und 02-22 und der deploy-harp-Lauf von 02-23 offen bis zum nächsten Push; Owner-Entscheid A zu D-02-02 vom 18.11. umgesetzt in Quick-Task 261118-hs4; nächster Schritt 02-24)
Status: Ready to execute
Last activity: 2026-11-18 -- 02-23 abgeschlossen

Progress: [██████████] 96%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: -
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P02 | 35 min | 2 tasks | 16 files |
| Phase 01 P03 | 45 min | 3 tasks | 15 files |
| Phase 01 P04 | 35 min | 3 tasks | 10 files |
| Phase 01 P05 | 40 min | 3 tasks | 18 files |
| Phase 01 P06 | 10 min | 3 tasks | 17 files |
| Phase 01 P07 | 25 min | 3 tasks | 3 files |
| Phase 01 P08 | 30 min | 2 tasks | 7 files |
| Phase 01 P09 | 55 min | 3 tasks | 15 files |
| Phase 01 P10 | 45 min | 2 tasks | 12 files |
| Phase 01 P11 | 25 min | 2 tasks | 10 files |
| Phase 01 P12 | 30 min | 2 tasks | 5 files |
| Phase 01 P13 | 30 min | 1 tasks | 8 files |
| Phase 01 P14 | 40 min | 3 tasks | 13 files |
| Phase 01 P15 | 45 min | 3 tasks | 14 files |
| Phase 02 P02 | 60 min | 2 tasks | 5 files |
| Phase 02 P08 | 50 min | 2 tasks | 10 files |
| Phase 02 P09 | 40 min | 2 tasks | 4 files |
| Phase 02 P10 | 25 min | 2 tasks | 2 files |
| Phase 02 P11 | 35 min | 2 tasks | 7 files |
| Phase 02 P12 | 35 min | 2 tasks | 4 files |
| Phase 02 P13 | 45 min | 2 tasks | 4 files |
| Phase 02 P14 | 30 min | 2 tasks | 9 files |
| Phase 02 P15 | 30 min | 2 tasks | 5 files |
| Phase 02 P16 | 1 Tag | 2 tasks | 12 files |
| Phase 02 P17 | 60 min | 2 tasks | 9 files |
| Phase 02 P19 | ca. 60 min | 2 tasks | 6 files |
| Phase 02 P20 | ca. 15 min | 3 tasks | 17 files |
| Phase 02 P21 | 15 min | 2 tasks | 8 files |
| Phase 02 P22 | 75 min | 2 tasks | 8 files |
| Phase 02 P23 | 15 min | 2 tasks | 6 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Projektmodus standard, Schichten mit Sicherheit zuerst; Sandbox vor Formaten, Positionsindex vor Markieren, Leck-Zoo und unabhängiger Prüfer vor echter Schwärzung
- [Roadmap]: "Workflow, Ablage, Rechtsgrundlagen, Protokoll" aus der Recherche in Phase 10 (Freigabe und Ablage) und Phase 11 (Rechtsgrundlagen und Protokoll) geteilt
- [Roadmap]: Phase 4 (Testsatz, Leck-Zoo) läuft begleitend ab Phase 1, fertig vor Abschluss von Phase 6
- [01-01]: Owner-Paketfreigabe 07.11.: alles wie gelistet, aber vue 3.5.44 und @playwright/test 1.64.1 (Cool-down); pymupdf 2.1 samt Pflichtabhängigkeiten und @nextcloud/dialogs 8.0.0 freigegeben
- [01-01]: Backend ohne Browser-Routen (leeres routes-Element), deploy-harp prüft unsignierten Zugriff auf /status negativ
- [01-01]: Env-Präfix bleibt PII_REDACTION_ (config.ENV_PREFIX); httpx nur einmal als Laufzeit-Pin
- [01-02]: Ein Auftrag zur Zeit über Sperrzeile pii_slot (bedingte UPDATE, Token-Rücklesen); QueueMapperTest gegen echte CI-DB, php.yml aktiviert die App vorher
- [01-03]: Kataloge php/l10n stehen (94 Einträge); PHP-Gates 1 bis 20 und Log-AST-Gate gelten ab jetzt für alle Pläne
- [01-04]: Download-Sperre fail closed in FileAccess; backendState prüft unter dem ersten aktiven Admin, ohne Admin kein Start
- [01-05]: Kindprozesse mit SAFE_ENV, eigener Gruppe und killpg; LibreOffice ungepinnt über trixie-security im Image
- [01-06]: nc.py ist einziger HTTP-Ort (auch Handshake über httpx); Antworten feldweise geprüft, ohne X-Pii-Etag kein Erfolg
- [01-06]: RAM-Bedarf render 512 MiB, soffice 1 GiB, Reserve 256 MiB vorläufig bis zur Messung
- [01-07]: Ganzzahlspalten NOT NULL, die mit dem Entity-Default 0 geschrieben werden, brauchen einen DB-Default (Entity-Setter überspringt gleiche Werte); phase-01 CI grün auf a1ace24
- [01-08]: Alle Zustandswechsel über JobService (Ereignis, Lease-Freigabe, Benachrichtigung ohne Parameter, purge nach Endzustand); erster Leser holt job_failed für repeatedly_stuck nach
- [01-09]: Frontend nur mit Owner-freigegebenen npm-Pins (keine direkte typescript-Abhängigkeit), npm immer mit --ignore-scripts; Admin-Banner serverseitig, admin.ts schaltet nur hidden
- [01-10]: Runner unterscheidet abgelehnten Bericht (Auftrag endet) von fehlender Antwort (ack bis dreimal); Gateway ohne Antwort ergibt kein ack, der Lease regelt die Wiederholung
- [01-11]: Admin-Sektion serverseitig mit sieben Bannern; Apps-Link nach AVS-Form (Orchestrator-Entscheid 3) in Template und admin/state gleich
- [Phase 01-12]: ack nur über Claim-Token; ack review mit Etag-Abweichung wird stale und antwortet 409 {reason}; Gateway 503 bei nicht zu öffnender Datei ohne Zustandswechsel
- [Phase 01-13]: Status-Route meldet recheck, Prüfseite wechselt bei nachträglicher Download-Sperre in die Sperrkarte; cancelled(original_deleted) zeigt 200 ohne Namen trotz Recheck Missing
- [Phase 01-14]: Gate-Regel 17 erlaubt die INotifier-Deklaration getName(), Aufrufe bleiben verboten; Ablage: NotPermittedException ergibt target_not_writable, sonstige Ausnahme check_error über PublishJob
- [Phase 01-15]: ci/lib.sh ist der gemeinsame Skriptvertrag; deploy-harp auf sieben Beinen (MariaDB nur stable35/amd64); php-Build mit --configLoader runner gegen die tsconfig-Warnung
- [Phase 02-01]: Phase-2-Texte am 16.11. wie entworfen freigegeben; de_DE unpersönlich, e2e-Rat nur an der Karte, Ziffern 300
- [Phase 02-04]: Raten wie Findling streng über 100/1000; CFB-Verzeichnis über die FAT-Kette (4 MiB); verborgene Daten vor dem ersten Mitglied und Overlap = unsafe_content
- [Phase 02-05]: ack confirm antwortet bis 02-15 mit 400, expliziter purged-Arm statt default
- [Phase 02-06]: tests/ wieder im Build-Kontext nur für die Teststufe; runtime kopiert nie tests, Push nur target runtime
- [Phase 02-07]: zip_lying_size und XML/PDF-Strukturfälle bestehen Stufe A/B; 02-09 muss sie ablehnen (Querprobe)
- [Phase 02-02]: transformers 5.22.1, hub 2.4.0, tokenizers 0.23.3 statt 4.57.6 (Owner-Freigabe 1); Lock mit exclude-newer 2026-11-03 für alle Pakete inkl. torch aus dem CPU-Index (Owner-Freigabe 2, Option B); pip-audit mit +cpu-Strip
- [Phase 02-16]: detect-Kind ohne OMP_THREAD_LIMIT, OMP_NUM_THREADS aus hardware.worker_threads (Deckel 2); ocr behält die Grenze
- [Phase 02-17]: LibreOffice-Härtung wird in die registrymodifications.xcu der Vorlagenkopie eingefügt, nicht kopiert; conflict/malformed fail-closed
- [Phase 02-18]: Status-Route und Startzustand der Prüfseite tragen macrosRemoved/signatureConfirmed (nur bool); confirm gilt als offen, wird aber nicht gepollt
- [Phase 02-19]: expected null im analyze-Claim endet ohne Download als unsupported_format; fehlender Schlüssel oder fremdes Wort verwirft den Claim
- [Phase 02-19]: andere Abstürze von precheck/sanitize sind damaged; Exit 71 markiert den Jail an jeder Kindstelle (auch soffice, Platzhalter)
- [Phase 02-20]: sandboxDegraded nur aus festen Wörtern (seccomp, landlock, jail), bei jedem Recheck frisch; seccomp/Landlock teilen eine Abhilfe, Schutzschicht eigenes Fehlerbanner
- [Phase 02-21]: Korpus im Container kommt vom Runner (ci/make_corpus.py, Mount /corpus:ro, PII_CORPUS), das Test-Image hat kein ci/
- [Phase 02-21]: Grenzen im Jail-Kind per getrlimit; /proc/self/limits bleibt gesperrt, kein Recht geöffnet
- [Phase 02-22]: Netzbeweis LibreOffice mit Kanarienserver und Schichtläufen a bis d; Korpus per retarget auf den Kanarienport, auch im Bridge-Container
- [Phase 02-22]: Presidio lädt bei falschem spaCy-Pfad per spacy.cli.download aus dem Netz; Erkennungs-Kind muss Modellordner vorher prüfen
- [Phase 02-23]: E2E-Korpus des deploy-harp-Laufs liegt in ci/out/corpus (refusals.sh erzeugt, Playwright liest); Signaturbestätigung im CI über echte Sitzung mit Request-Token; A6 prüft refusals.sh selbst an der Datenbank des Laufs

### Pending Todos

None yet.

### Blockers/Concerns

- Owner hat am 07.11. alle 14 Empfehlungen aus research/SUMMARY.md übernommen; offen bleibt nur die Messung für den OCR-Zweitkanal je Seite (bei Leckgewinn an)
- FAU/ALeKS-Goldstandard am 07.11. angefragt (Mail an Evert, CC Adrian); ABGELEHNT am 07.11. (Prof. Adrian: "können Ihrer Bitte nicht nachkommen", ohne Begründung). Owner 07.11.: eigener Goldstandard (öffentliche Urteile/Ratsvorlagen), Holdout durch Gemini 3.1 Pro + GPT-6.1-sol über API (nicht Claude), Widersprüche entscheidet der Owner; Nutzungsbedingungen (Training V2-01) vor Plan Phase 4 prüfen, Phase 4
- Container-Messwerte (RSS des Stapels, LibreOffice-Spitze, Image-Größe, Kaltstart) fehlen; RAM-Schwellen erst nach Messung in Phase 1/2 festschreiben
- Zertifikat `pii_redaction_backend` beantragt (#1419), noch nicht erteilt
- Scans und arm64-Tempo ungemessen (Phase 12, 15)
- Länder-Label-Sätze brauchen juristisches Gegenlesen vor Store (Phase 11)
- GELÖST 18.11. (Quick-Task 261118-hs4, a2a5d59, bb328c5): Owner-Entscheid A zu D-02-02. JobService::toFailed sendet für die acht Ablehnungsgründe der Vorprüfung (Reason::isPrecheckRefusal) keine Benachrichtigung mehr, echte Fehler benachrichtigen weiter; notification.spec.ts holt job_failed aus target_not_writable und belegt, dass die kaputte PDF (damaged) keine Meldung erzeugt. Beleg erst in CI (PHPUnit, deploy-harp). Zweifelsfälle für den Owner im SUMMARY des Quick-Tasks

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-11-18T11:27:45.415Z
Stopped at: Completed 02-23-PLAN.md
Resume file: None

## Quick Tasks Completed

| ID | Date | Task | Status |
|----|------|------|--------|
| 261118-gbl | 2026-11-18 | Fix two broken assertions in ExAppServiceTest (CI eb46ef4 PHP gates red) | done, CI proof pending |
| 261118-hs4 | 2026-11-18 | No notification for a refusal of the pre-check (D-02-02, owner decision A) | done, CI proof pending |
| 261118-io7 | 2026-11-18 | ci/refusals.sh: subject word from the database, every proof on its own (CI run 44300061301 red on all seven legs) | done, CI proof pending |
| 261118-k0t | 2026-11-18 | ci/refusals.sh: Origin header with the login form, CSRF refusal 412 by name, confirmation in the refused session (CI run 44310663659: 10 of 12 proofs green on all seven legs) | done, CI proof pending |
| 261118-lie | 2026-11-18 | Security scans (CodeQL, REUSE, pip-audit) also on phase branches | done, CI proof pending |
