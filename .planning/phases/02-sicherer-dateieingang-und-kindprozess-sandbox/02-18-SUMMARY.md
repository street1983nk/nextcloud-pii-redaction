---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 18
subsystem: php-ui
tags: [job-05, ui, l10n, signature, macros]
requires: [02-01, 02-05, 02-11, 02-15]
provides: [Dateikarte mit neun Ablehnungsgründen, confirm-Karte mit Fortfahren/Abbrechen, Makro-Hinweis, Stufe checking, e2e-Toast, Statusfelder macrosRemoved/signatureConfirmed]
affects: [02-19, 02-20, 02-23]
tech-stack:
  added: []
  patterns: [Grundwort nur per switch auf feste t()-Texte, Antwort-Button nach requestCopy-Muster]
key-files:
  created: []
  modified:
    - php/src/ReviewPlaceholder.vue
    - php/src/startToast.ts
    - php/l10n/de.json
    - php/l10n/de_DE.json
    - php/l10n/en.json
    - php/l10n/fr.json
    - php/l10n/de.js
    - php/l10n/de_DE.js
    - php/l10n/en.js
    - php/l10n/fr.js
    - php/lib/Controller/JobController.php
    - php/lib/Controller/ReviewController.php
    - php/tests/Unit/JobControllerTest.php
    - php/tests/Unit/ReviewControllerTest.php
decisions:
  - "Status-Route und Startzustand der Prüfseite tragen macrosRemoved und signatureConfirmed (nur bool); ohne das erschiene der Makro-Hinweis erst nach Neuladen"
  - "confirm zählt als offen (OPEN), aber schedule und Sichtbarkeitswechsel pollen dabei nicht"
  - "cancelled mit signature_declined zeigt failure()-Texte als info-Karte mit Link auf die Datei statt 'Die Datei wurde gelöscht'"
  - "Commit-Reihenfolge Kataloge vor UI, damit jeder Commit die Text-Gates besteht"
metrics:
  completed: 2026-11-18
  tasks: "2/2"
---

# Phase 2 Plan 18: Dateikarte, Signatur-Bestätigung, Makro-Hinweis und E2E-Toast Summary

Die Prüfseite zeigt jetzt alle neuen Ablehnungsgründe mit Titel und Abhilfe, im Status `confirm` den Signatur-Hinweis mit Fortfahren und Abbrechen (POST `/review/{jobId}/confirm` bzw. `/decline`), bei `macrosRemoved` den Makro-Hinweis und für die Stufe `checking` eine eigene Zeile; der Start-Toast nennt `e2e_encrypted`. Alle 28 Texte stehen wortgleich zur Freigabe in de, de_DE, en und fr.

## Commits

| Schritt | Commit | Betreff |
|---|---|---|
| Statusfelder (Abweichung) | 4e70caa | fix(02-18): status route and review page carry the macro and signature flags |
| Task 2 Kataloge | 4269781 | feat(02-18): catalogues de, de_DE, en and fr carry the approved phase 2 texts |
| Task 1 Karte und Toast | fe749e9 | feat(02-18): file card shows refusal reasons, signature notice and macro notice |

## Prüfung

- `npm run typecheck` ohne Fehler, `npm run build` (Vite) ohne Fehler. Das Repo hat kein Lint- und kein JS-Test-Skript.
- `pytest tests/test_trilingual.py tests/test_ui_assets.py tests/test_public_texts.py`: 56 passed.
- Ganze Suite: 1330 passed, 44 skipped. ruff check, ruff format --check, pyright (latest) 0 Fehler, vulture grün.
- `scripts/l10n_js.py --check` grün.
- `grep -c "case 'confirm'"` = 1, `grep -c v-html` = 0, `grep -c "case 'e2e_encrypted'" startToast.ts` = 1.
- Gedankenstriche in `php/l10n/*.json`: 0 je Datei.
- PHPUnit (Feldliste der Status-Route, Makro-Flag in Status-Route und Startzustand) läuft erst in php.yml. Lokal gibt es kein PHP, die Syntax ist nur durch Lesen geprüft.

## Wortlaute (alle neuen Schlüssel, Abgleich mit 02-TEXTS.md)

de_DE ist wortgleich zu de (Freigabe Rückfrage 1, Test `test_de_and_de_DE_are_the_same_text`).

| Schlüssel (EN) | DE / de_DE | FR |
|---|---|---|
| The file is end-to-end encrypted | Die Datei ist Ende-zu-Ende-verschlüsselt | Le fichier est chiffré de bout en bout |
| The server cannot read it. If it may be stored unencrypted, analyse a copy from a normal folder. | Der Server kann sie nicht lesen. Darf sie unverschlüsselt liegen, eine Kopie aus einem normalen Ordner analysieren. | Le serveur ne peut pas le lire. S'il peut être stocké sans chiffrement, analysez une copie placée dans un dossier normal. |
| The PDF is password-protected | Die PDF ist passwortgeschützt | Le PDF est protégé par un mot de passe |
| Remove the password and analyse the file again. | Das Passwort entfernen und die Datei neu analysieren. | Supprimez le mot de passe et relancez l'analyse. |
| The document is password-protected | Das Dokument ist passwortgeschützt | Le document est protégé par un mot de passe |
| Save it without a password and analyse the file again. | Ohne Passwort speichern und die Datei neu analysieren. | Enregistrez-le sans mot de passe et relancez l'analyse. |
| The content does not match the file type | Der Inhalt passt nicht zum Dateityp | Le contenu ne correspond pas au type de fichier |
| Save the file again as PDF, DOCX or ODT and analyse that. | Die Datei neu als PDF, DOCX oder ODT speichern und diese analysieren. | Enregistrez à nouveau le fichier en PDF, DOCX ou ODT et analysez celui-ci. |
| The file is damaged | Die Datei ist beschädigt | Le fichier est endommagé |
| Open it in the original program, save it again and analyse that. | Im ursprünglichen Programm öffnen, neu speichern und diese analysieren. | Ouvrez-le dans son application d'origine, enregistrez-le à nouveau et analysez celui-ci. |
| The file is too large to analyse | Die Datei ist zu groß für die Analyse | Le fichier est trop volumineux pour l'analyse |
| It exceeds a safety limit. Split it into smaller files or reduce the images. | Sie überschreitet eine Sicherheitsgrenze. In kleinere Dateien aufteilen oder die Bilder verkleinern. | Il dépasse une limite de sécurité. Divisez-le en fichiers plus petits ou réduisez les images. |
| The document has more than 300 pages | Das Dokument hat mehr als 300 Seiten | Le document compte plus de 300 pages |
| Split it into parts of at most 300 pages and analyse each part. | In Teile mit höchstens 300 Seiten aufteilen und jeden Teil analysieren. | Divisez-le en parties de 300 pages au maximum et analysez chaque partie. |
| The file contains unsafe parts | Die Datei enthält unsichere Bestandteile | Le fichier contient des éléments dangereux |
| It was not analysed, for protection. Save it as PDF in the original program and analyse that. | Zum Schutz wurde sie nicht analysiert. Im ursprünglichen Programm als PDF speichern und diese analysieren. | Par sécurité, il n'a pas été analysé. Enregistrez-le en PDF dans son application d'origine et analysez celui-ci. |
| Analysis cancelled | Analyse abgebrochen | Analyse annulée |
| The signed PDF was not analysed. To redact it, analyse it again and confirm the notice. | Die signierte PDF wurde nicht analysiert. Zum Schwärzen neu analysieren und den Hinweis bestätigen. | Le PDF signé n'a pas été analysé. Pour le caviarder, relancez l'analyse et confirmez l'avertissement. |
| End-to-end encrypted files cannot be analysed on the server. | Ende-zu-Ende-verschlüsselte Dateien lassen sich auf dem Server nicht analysieren. | Les fichiers chiffrés de bout en bout ne peuvent pas être analysés sur le serveur. |
| The PDF is signed | Die PDF ist signiert | Le PDF est signé |
| The signature is lost when redacting. The original stays signed. Continue? | Die Signatur geht bei der Schwärzung verloren. Das Original bleibt signiert. Fortfahren? | La signature est perdue lors du caviardage. L'original reste signé. Continuer ? (U+00A0 vor ?) |
| Continue | Fortfahren | Continuer |
| Cancel | Abbrechen | Annuler |
| Saving… | Wird gespeichert… | Enregistrement… |
| The answer could not be saved. Try again. | Die Antwort ließ sich nicht speichern. Erneut versuchen. | La réponse n'a pas pu être enregistrée. Réessayez. |
| Macros were removed for the analysis. The original stays unchanged. | Makros wurden für die Analyse entfernt. Das Original bleibt unverändert. | Les macros ont été supprimées pour l'analyse. L'original reste inchangé. |
| Checking the file | Datei wird geprüft | Vérification du fichier |
| A safety check runs before the analysis. | Vor der Analyse läuft eine Sicherheitsprüfung. | Un contrôle de sécurité a lieu avant l'analyse. |

Die Texte wurden per Skript aus einer Tabelle eingetragen, die direkt aus 02-TEXTS.md übernommen ist. Das Skript bricht ab, wenn ein Schlüssel schon existiert oder das JSON-Layout abweicht. `unsupported_format` bestand schon und blieb unverändert.

## Deviations from Plan

**1. [Rule 2 - fehlende Funktion] Statusfelder für den Makro-Hinweis.**
- Gefunden in: Task 1
- Problem: `view()` liefert seit 02-11 `macrosRemoved` und `signatureConfirmed`, aber weder die Status-Route (`STATUS_FIELDS`) noch der Startzustand der Prüfseite gaben die Felder weiter. Die Karte hätte den Makro-Hinweis also nie gezeigt.
- Lösung: Beide Felder ergänzt (nur bool). PHPUnit zieht die Feldliste nach und prüft das Flag nach `recordAckFlags` in beiden Routen.
- Dateien: JobController.php, ReviewController.php, JobControllerTest.php, ReviewControllerTest.php (nicht in files_modified)
- Commit: 4e70caa
- Hinweis: Die Feldtabelle in 01-SKELETON.md (Phase 1) nennt die zwei neuen Felder noch nicht.

**2. Abbruchkarte bei `signature_declined`** (Notiz aus 02-01 und deferred-items.md): `cancelled` mit diesem Grund zeigt die Gruppe-1-Texte als info-Karte mit Link "In Dateien anzeigen" statt "Die Datei wurde gelöscht". Der Seitentitel bleibt ohne Dateinamen, wie bisher bei `cancelled` (der Server lässt den Namen dort weg).

**3. Commit-Reihenfolge:** Erst die Kataloge (Task 2), dann die UI (Task 1). Sonst wäre `test_every_text_the_php_app_uses_is_in_every_catalogue` beim Task-1-Commit rot gewesen.

**4. Zusätze im Antwortblock:** 401 führt zur Karte "Sitzung abgelaufen", 404 zu "nicht verfügbar". Ein 409 (anderer Status oder `original_changed`) fragt den Status einmal neu ab, `download_blocked` zeigt die Sperrkarte. Das folgt dem Muster der Abfrage.

## Offen (nur mit CI oder Playwright gegen einen echten Server belegbar)

- PHPUnit für die zwei neuen Fälle und die geänderte Feldliste läuft erst in php.yml nach einer Push-Freigabe.
- Sicht- und Bedienprüfung der confirm-Karte, des Makro-Hinweises und der Stufe `checking`: drei Breiten, hell und dunkel, gemeinsam mit dem Owner per Playwright (UI-Abnahme-Regel). Lokal wurde nichts gerendert.
- Ende-zu-Ende: Der Container sendet `ack confirm` und die Ablehnungsgründe erst ab 02-19. Bis dahin sind confirm-Karte und Gründe nur gegen den PHP-Vertrag gebaut.
- JOB-05 bleibt offen. Erkennung im Container (02-19) und Protokoll-Nachweis fehlen noch.

## Known Stubs

Keine. `signatureConfirmed` wird geladen und aktualisiert, die Karte zeigt es aber nicht an. Der Plan verlangt nur das Feld im Typ.

## Threat Flags

Keine neue Angriffsfläche. Die zwei neuen Statusfelder sind bool und geben keinen Inhalt preis (T-02-33). Grundwörter laufen nur über switch auf feste Texte, es gibt kein v-html und unbekannte Wörter bekommen den Standardtext (T-02-30). Die Antworten laufen über @nextcloud/axios mit requesttoken, und CSRF ist auf den Routen aktiv (T-02-18).

## Self-Check: PASSED
