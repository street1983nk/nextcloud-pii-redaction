---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 23
subsystem: ci
tags: [job-05, d-02-02, d-02-04, a6, deploy-harp, playwright, e2e]
requires: [02-07, 02-12, 02-18, 02-19, 02-20]
provides: [ci/refusals.sh, deploy-harp.yml Schritt refusals, Playwright-Fälle Ablehnungskarte und Signaturhinweis, test_workflows refusal_findings]
affects: [02-24, 02-25]
tech-stack:
  added: []
  patterns: [Sitzung per Anmeldeformular und Request-Token in curl, Spaltenprüfung an der echten Datenbank vor dem Schreiben, Zählung mit Positivkontrolle vor dem Negativurteil, Erwartungstexte aus dem Katalog der installierten App]
key-files:
  created:
    - ci/refusals.sh
  modified:
    - .github/workflows/deploy-harp.yml
    - backend/tests/test_workflows.py
    - backend/tests/test_playwright_contract.py
    - ci/playwright/review.spec.ts
    - .planning/phases/02-sicherer-dateieingang-und-kindprozess-sandbox/deferred-items.md
decisions:
  - "Korpus des E2E-Laufs liegt in ci/out/corpus; refusals.sh erzeugt ihn, Playwright liest ihn danach wieder"
  - "Bestätigung der Signatur läuft über eine echte Sitzung (Anmeldeformular, Cookies, Kopfzeile requesttoken), nicht über Basic Auth mit OCS-APIRequest"
  - "A6 wird im Skript an der Datenbank des Laufs geprüft (pragma_table_info bzw. information_schema); fehlt die Spalte encrypted, bricht der Schritt mit Meldung ab"
  - "Das Urteil zu D-02-02 steht am Ende des Skripts, damit ein Lauf alle anderen Beweise vorher zeigt"
  - "Produktcode nicht angefasst: der Widerspruch zwischen D-02-02 und toFailed geht als Entscheid an den Owner"
metrics:
  duration: "ca. 15 min"
  completed: 2026-11-18
  tasks: "2/2"
---

# Phase 2 Plan 23: Ablehnungen und Signaturbestätigung auf der echten Instanz Summary

`ci/refusals.sh` prüft in deploy-harp die vier Ablehnungsgründe der Vorprüfung, die Startablehnung im E2E-Ordner und den Bestätigungsfluss der signierten PDF mit echtem Request-Token; zwei Playwright-Fälle zeigen Ablehnungskarte und Signaturhinweis in allen zwölf Projekten. Nichts davon ist bisher gelaufen: Beleg erst in CI.

## Commits

| Schritt | Commit | Betreff |
|---|---|---|
| Task 1 | ee4e9a4 | test(02-23): refusals of the pre-check, E2E folder and signature confirmation on the real instance |
| Task 2 | 59d4d7a | test(02-23): Playwright cases for the refusal card and the signature notice |

## Was gebaut wurde

**ci/refusals.sh** (als alice, nach den flow-Läufen, vor rights.sh):

- (0) Kontrollen: `harmless.pdf` erreicht review, die Zählung sieht genau diese eine `review_ready` (API und Zeile in `oc_notifications`). `ext_image.docx` erreicht review mit Ereignis `external_links_removed`.
- (a) bis (d): `wrong_pdf_as_docx.docx` wrong_type, `pdf_301_pages.pdf` too_many_pages, `pdf_user_password.pdf` encrypted_pdf, `cfb_encrypted.docx` encrypted_document. Je Auftrag Zeitdeckel 180 s, erwartet wird Status failed mit genau diesem Grund.
- (e) E2E-Ordner: Spalte `encrypted` in `oc_filecache` wird an der Datenbank des Laufs abgefragt (Positivkontrolle mit `fileid`), sonst Abbruch "A6 does not hold". Flag auf den Ordner setzen und zurücklesen, Start ergibt 4xx mit `e2e_encrypted`, kein Auftrag in `oc_pii_jobs`. Gegenprobe: Flag zurück auf 0, dieselbe Datei startet und erreicht review.
- (f) Signierte PDF: Status confirm, Ereignis `signature_notice`, noch kein `signature_confirmed`, keine Benachrichtigung. bob bekommt 404. Die Sitzung von alice ohne Request-Token wird abgewiesen, der Auftrag bleibt in confirm. Mit `requesttoken` der Sitzung: 202 queued, dann review, `signatureConfirmed` in der Statusantwort, Ereignisse `signature_notice` vor `signature_confirmed`, letzteres genau einmal.
- (g) D-02-02: je abgelehntem Auftrag keine Benachrichtigung (API und `oc_notifications`), Zählung vor und nach den Ablehnungen gleich.
- Ausgabe nur Wörter der geschlossenen Listen, IDs und Zahlen.

**deploy-harp.yml:** ein Schritt `bash app-src/ci/refusals.sh` zwischen `flow.sh pdf greta` und `rights.sh`.

**test_workflows.py:** `ci/refusals.sh` in CHECK_ORDER; `refusal_findings()` liest aus dem Skript, dass jeder Grund an seiner Datei geprüft wird, dass die Spalte abgefragt wird und der Abbruch ein `fail` ist, dass mit Request-Token bestätigt wird und dass die Positivkontrolle der Zählung vor der ersten Ablehnung steht. Drei neue Tests, zwei davon Selbsttests mit sieben Mutationen.

**review.spec.ts:** zwei Fälle mit echten Läufen je Projekt.

- Ablehnung: `wrong_pdf_as_docx.docx` endet als failed wrong_type, die Karte zeigt Titel und Abhilfe-Satz. Bild `abgelehnt-wrong_type`.
- Signatur: `pdf_signed.pdf` wartet in confirm, Karte mit Hinweis, beide Knöpfe sichtbar und aktiv, kein Seitenbild. Tab und Umschalt+Tab wechseln zwischen den Knöpfen. Bild `signatur-bestaetigen`. Klick auf Fortfahren: Antwort 202, Fokus im Statusbereich, Knöpfe weg, Status queued, analyzing oder review. Danach folgt die offene Seite ohne Neuladen bis zum Seitenbild. Bild `signatur-bestaetigt-bereit`.
- Erwartungstexte stehen nicht im Spec: englischer Quelltext für englische Nutzer, sonst der Eintrag aus `apps/pii_redaction/l10n/<sprache>.json` der installierten App. Ein fehlender oder unübersetzter Eintrag wirft.

## Prüfung (lokal, ohne Docker)

- ruff check und ruff format --check (backend, ../scripts, ../ci): grün.
- pyright basic mit PYRIGHT_PYTHON_FORCE_VERSION=latest: 0 Fehler.
- vulture: grün.
- pytest `-m "not container"`: `1474 passed, 33 skipped, 37 deselected` (vorher 1471 passed; +3 Tests in test_workflows.py).
- `tests/test_workflows.py tests/test_ci_scripts.py`: 46 passed. `tests/test_playwright_contract.py`: 15 passed.
- shellcheck 0.9.0 (`uvx --offline --from shellcheck-py==0.9.0.6 shellcheck -x ci/*.sh`): sauber. `bash -n ci/refusals.sh`: ok. Datei 100755, LF.
- `npx tsc --noEmit -p tsconfig.json` in ci/playwright: 0 Fehler.
- `grep -c "ci/refusals.sh" .github/workflows/deploy-harp.yml`: 1. Wörter in refusals.sh: wrong_type 2, too_many_pages 2, encrypted_pdf 2, encrypted_document 2, e2e_encrypted 3, confirm 37.
- Kein U+2013 oder U+2014 in den geänderten Dateien (Skript mit Positivkontrolle).

Lokale Proben in Wegwerf-Skripten außerhalb des Repos, nicht Teil der Suite:

- `workers.precheck.judge` antwortet für die E2E-Dateien genau die erwarteten Wörter: wrong_type, too_many_pages, encrypted_pdf, encrypted_document; `pdf_signed.pdf` ok mit signed true; `harmless.pdf` und `ext_image.docx` ok. Ohne Jail und ohne Container.
- PyMuPDF rendert Seite 1 von `pdf_signed.pdf` und `harmless.pdf` als PNG.
- SQL und Python-Stücke des Skripts an einer leeren SQLite-Datei: `pragma_table_info` findet `encrypted` und `fileid`, nicht eine erfundene Spalte; das UPDATE wird festgeschrieben; ein UPDATE über den Leseweg von lib.sh geht verloren (darum `db_exec`). Zähler der Benachrichtigungen, Token-Auslese aus dem Seitenkopf und Reihenfolge der Ereignisse an Beispieldaten.

## Deviations from Plan

**1. [Rule 2] Strenger als der Plan.** Zusätzlich zur Zählung: zweiter Zeuge `oc_notifications` je Auftrag, Positivkontrolle der Zählung vor den Ablehnungen, Negativversuche am confirm-Weg (fremder Nutzer 404, Sitzung ohne Request-Token), Gegenprobe ohne E2E-Flag, kein Auftrag in `oc_pii_jobs` für die abgelehnte Datei.

**2. [Rule 1] Eigener Schreibweg `db_exec` im Skript.** `db_query` aus lib.sh schreibt auf SQLite nie fest; das Setzen des Flags wäre still verloren gegangen. lib.sh blieb unverändert.

**3. [Rule 1] Kein `grep -q` hinter einer Datenbankabfrage.** Unter pipefail kann ein früh endendes grep die Abfrage abbrechen und einen Treffer als Fehlschlag melden. Die Ereignisse werden erst gelesen, dann durchsucht.

**4. [Rule 2] Benachrichtigung der Kontrolle wird bis 20 s abgewartet.** Der Status wechselt im selben Request kurz vor dem Senden; ohne Warten wäre die Positivkontrolle ein Wettlauf.

**5. `ext_image.docx` als zweite Kontrolle.** Der Plan nennt die Datei nur in der E2E-Liste. Sie läuft jetzt bis review und muss `external_links_removed` im Protokoll haben.

**6. Drittes Bild `signatur-bestaetigt-bereit`.** Der Zustand direkt nach dem Klick ist ein Wettlauf (queued, analyzing oder schon review) und taugt nicht als Bild; das Bild nach Erreichen von review ist fest.

**7. `backend/tests/test_playwright_contract.py` außerhalb von files_modified.** Die drei neuen Zustände stehen im Raster, sonst hielte kein Gate die Bilder.

**8. HTTP-Code der E2E-Startablehnung nicht festgenagelt.** Geprüft wird 4xx plus Grund `e2e_encrypted`; der Code wird gedruckt. Begründung unter Befunde.

**9. Kopfkommentar von deploy-harp.yml nennt das Skript in Prosa ohne Pfad**, damit das Akzeptanzkriterium (genau eine Zeile mit `ci/refusals.sh`) hält.

## Befunde

- **D-02-02 gegen das Produkt, Owner-Entscheid nötig vor dem Push.** Laut Code sendet `JobService::toFailed` immer `job_failed`, auch wenn der Grund eine Ablehnung der Vorprüfung ist. Ohne Benachrichtigung sind nur die Startablehnung `e2e_encrypted`, confirm und `signature_declined`. Schritt (g) von refusals.sh ist nach Plan gebaut (Differenz 0) und wird deshalb im nächsten Lauf voraussichtlich mit vier Befunden rot. Das ist aus dem Code gelesen, nicht an einer laufenden Instanz gesehen. Produktcode nicht geändert: es ist eine Verhaltensfrage, sie berührt Phase 1 (`testFailedNotifiesAndGoesToPurge`, notification.spec.ts) und PHPUnit läuft lokal nicht. Wege A und B stehen in deferred-items.md.
- **notification.spec.ts erwartet `render_failed` für die kaputte PDF.** Die Vorprüfung antwortet lokal `damaged` für genau diese Bytes. Der Test wird im nächsten deploy-harp-Lauf voraussichtlich rot. Vorbestehend seit 02-19, nicht behoben.
- **`e2e_encrypted` hat keinen eigenen HTTP-Code.** `JobController::REFUSAL_STATUS` kennt den Grund nicht, die Antwort fällt auf 404 zurück. Der Toast liest den Grund aus dem Körper, für Nutzer ändert das nichts.

## Offen (nur in CI belegbar, nicht geraten)

- Der ganze Lauf von refusals.sh auf allen sieben Beinen, auch MariaDB (`information_schema`, `docker exec ... mariadb -e` für das UPDATE).
- A6: ob `oc_filecache.encrypted` auf stable33 bis stable35 existiert und ob das Flag am Ordner `Folder::isEncrypted()` wahr macht. Scheitert es, sagt der Schritt welches von beiden.
- Anmeldung per curl über das Formular: Status 302 oder 303, danach `data-user` und `data-requesttoken` im Seitenkopf. Lokal nur die Auslese an Beispiel-HTML geprüft.
- Antwort ohne Request-Token: erwartet wird nur "kein 2xx" und unveränderter Auftrag; der Code wird gedruckt (vermutlich 412).
- `ext_image.docx` durch Bereiniger und LibreOffice im echten Container mit Ereignis `external_links_removed`.
- Playwright: beide Fälle in zwölf Projekten, Bilder als Artefakt `playwright-<bein>`. Tab-Reihenfolge der beiden Knöpfe bei 375 px ist ungeprüft.
- PHPUnit und php.yml (Commit 2514ca5) bleiben wie bisher ohne Beleg bis zum Push.
- Requirement JOB-05 bleibt offen, bis deploy-harp grün ist.

## Known Stubs

Keine.

## Threat Flags

Keine neue Angriffsfläche im Produkt, nur Test- und CI-Code. refusals.sh schreibt in der Wegwerf-Instanz direkt in `oc_filecache` (ein Ordner, Flag hin und zurück) und legt eine Cookie-Datei in ci/out ab, die kein Artefakt wird (`*.cookies`). T-02-16 und T-02-18 haben jetzt ihren Test auf der echten Instanz; T-02-52 ist geprüft, aber nach Codelage nicht erfüllt (siehe Befunde).

## Self-Check: PASSED

- ci/refusals.sh, 02-23-SUMMARY.md vorhanden; Commits ee4e9a4 und 59d4d7a in `git log`.
