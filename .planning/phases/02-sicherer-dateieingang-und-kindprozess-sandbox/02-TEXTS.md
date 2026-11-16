# Phase 2: Texte zur Freigabe (D-02-03)

Entwurf vom 2026-11-16. Alle neuen nutzersichtbaren Texte der Phase 2, Deutsch zuerst gedacht, Schlüssel = englischer Quelltext in `t('pii_redaction', ...)`.

Regeln für den Entwurf:

- Ton wie Phase 1: Titel kurz ohne Punkt, darunter ein Abhilfe-Satz (D-02-01). Deutsch unpersönlich im Infinitiv ("Die Datei neu analysieren."), Französisch mit "vous" im Imperativ.
- `de` und `de_DE` sind in Phase 1 wortgleich (Infinitiv passt zu Du- und Sie-Form). Der Entwurf hält das bei; die Spalte de_DE ist daher gleich DE.
- Texte nennen nur den Grund aus der geschlossenen Liste, nie Dateiname, Pfad oder Inhalt (T-02-33).
- Keine Benachrichtigung je Ablehnung (D-02-02); der Grund steht nur an der Dateikarte, beim Start zusätzlich im Toast.
- Keine Statuscodes, keine Kürzel wie ZIP, XML, DOCTYPE im Nutzertext. Fachwörter nur im Admin-Text in Klammern.
- Französisch: U+00A0 vor `: ; ? !`.

## Gruppe 1: Ablehnungsgründe an der Dateikarte (`failure()` in ReviewPlaceholder.vue)

Je Grund zwei Zeilen: T = Titel, A = Abhilfe-Satz.

| Grund / Zeile | EN (Quelltext) | DE | de_DE | FR |
|---|---|---|---|---|
| `e2e_encrypted` T | The file is end-to-end encrypted | Die Datei ist Ende-zu-Ende-verschlüsselt | Die Datei ist Ende-zu-Ende-verschlüsselt | Le fichier est chiffré de bout en bout |
| `e2e_encrypted` A | The server cannot read it. If it may be stored unencrypted, analyse a copy from a normal folder. | Der Server kann sie nicht lesen. Darf sie unverschlüsselt liegen, eine Kopie aus einem normalen Ordner analysieren. | Der Server kann sie nicht lesen. Darf sie unverschlüsselt liegen, eine Kopie aus einem normalen Ordner analysieren. | Le serveur ne peut pas le lire. S'il peut être stocké sans chiffrement, analysez une copie placée dans un dossier normal. |
| `encrypted_pdf` T | The PDF is password-protected | Die PDF ist passwortgeschützt | Die PDF ist passwortgeschützt | Le PDF est protégé par un mot de passe |
| `encrypted_pdf` A | Remove the password and analyse the file again. | Das Passwort entfernen und die Datei neu analysieren. | Das Passwort entfernen und die Datei neu analysieren. | Supprimez le mot de passe et relancez l'analyse. |
| `encrypted_document` T | The document is password-protected | Das Dokument ist passwortgeschützt | Das Dokument ist passwortgeschützt | Le document est protégé par un mot de passe |
| `encrypted_document` A | Save it without a password and analyse the file again. | Ohne Passwort speichern und die Datei neu analysieren. | Ohne Passwort speichern und die Datei neu analysieren. | Enregistrez-le sans mot de passe et relancez l'analyse. |
| `wrong_type` T | The content does not match the file type | Der Inhalt passt nicht zum Dateityp | Der Inhalt passt nicht zum Dateityp | Le contenu ne correspond pas au type de fichier |
| `wrong_type` A | Save the file again as PDF, DOCX or ODT and analyse that. | Die Datei neu als PDF, DOCX oder ODT speichern und diese analysieren. | Die Datei neu als PDF, DOCX oder ODT speichern und diese analysieren. | Enregistrez à nouveau le fichier en PDF, DOCX ou ODT et analysez celui-ci. |
| `damaged` T | The file is damaged | Die Datei ist beschädigt | Die Datei ist beschädigt | Le fichier est endommagé |
| `damaged` A | Open it in the original program, save it again and analyse that. | Im ursprünglichen Programm öffnen, neu speichern und diese analysieren. | Im ursprünglichen Programm öffnen, neu speichern und diese analysieren. | Ouvrez-le dans son application d'origine, enregistrez-le à nouveau et analysez celui-ci. |
| `too_large` T | The file is too large to analyse | Die Datei ist zu groß für die Analyse | Die Datei ist zu groß für die Analyse | Le fichier est trop volumineux pour l'analyse |
| `too_large` A | It exceeds a safety limit. Split it into smaller files or reduce the images. | Sie überschreitet eine Sicherheitsgrenze. In kleinere Dateien aufteilen oder die Bilder verkleinern. | Sie überschreitet eine Sicherheitsgrenze. In kleinere Dateien aufteilen oder die Bilder verkleinern. | Il dépasse une limite de sécurité. Divisez-le en fichiers plus petits ou réduisez les images. |
| `too_many_pages` T | The document has more than 300 pages | Das Dokument hat mehr als 300 Seiten | Das Dokument hat mehr als 300 Seiten | Le document compte plus de 300 pages |
| `too_many_pages` A | Split it into parts of at most 300 pages and analyse each part. | In Teile mit höchstens 300 Seiten aufteilen und jeden Teil analysieren. | In Teile mit höchstens 300 Seiten aufteilen und jeden Teil analysieren. | Divisez-le en parties de 300 pages au maximum et analysez chaque partie. |
| `unsafe_content` T | The file contains unsafe parts | Die Datei enthält unsichere Bestandteile | Die Datei enthält unsichere Bestandteile | Le fichier contient des éléments dangereux |
| `unsafe_content` A | It was not analysed, for protection. Save it as PDF in the original program and analyse that. | Zum Schutz wurde sie nicht analysiert. Im ursprünglichen Programm als PDF speichern und diese analysieren. | Zum Schutz wurde sie nicht analysiert. Im ursprünglichen Programm als PDF speichern und diese analysieren. | Par sécurité, il n'a pas été analysé. Enregistrez-le en PDF dans son application d'origine et analysez celui-ci. |
| `unsupported_format` T (besteht, geprüft) | Format not supported | Format nicht unterstützt | Format nicht unterstützt | Format non pris en charge |
| `unsupported_format` A (besteht, geprüft) | Only PDF, DOCX and ODT can be analysed. | Nur PDF, DOCX und ODT lassen sich analysieren. | Nur PDF, DOCX und ODT lassen sich analysieren. | Seuls les PDF, DOCX et ODT peuvent être analysés. |
| `signature_declined` T | Analysis cancelled | Analyse abgebrochen | Analyse abgebrochen | Analyse annulée |
| `signature_declined` A | The signed PDF was not analysed. To redact it, analyse it again and confirm the notice. | Die signierte PDF wurde nicht analysiert. Zum Schwärzen neu analysieren und den Hinweis bestätigen. | Die signierte PDF wurde nicht analysiert. Zum Schwärzen neu analysieren und den Hinweis bestätigen. | Le PDF signé n'a pas été analysé. Pour le caviarder, relancez l'analyse et confirmez l'avertissement. |

Hinweise:

- `unsupported_format`: bestehende Phase-1-Texte unverändert übernommen; Prüfung ergab keinen Änderungsbedarf.
- `too_many_pages`: Die Zahl 300 steht fest im Satz (feste Konstante nach D-02-07/D-02-08, kein Platzhalter), in Ziffern für bessere Lesbarkeit.
- Wortlaut "neu analysieren" statt "erneut starten" aus dem Beispiel D-02-01, damit der Ton zu den Phase-1-Texten passt ("Die Datei neu analysieren.").

## Gruppe 2: Start-Toast (`refusal()` in startToast.ts)

| Grund | EN (Quelltext) | DE | de_DE | FR |
|---|---|---|---|---|
| `e2e_encrypted` | End-to-end encrypted files cannot be analysed on the server. | Ende-zu-Ende-verschlüsselte Dateien lassen sich auf dem Server nicht analysieren. | Ende-zu-Ende-verschlüsselte Dateien lassen sich auf dem Server nicht analysieren. | Les fichiers chiffrés de bout en bout ne peuvent pas être analysés sur le serveur. |

Toast-Typ: Fehler, bleibt stehen bis zum Schließen (wie die übrigen Ablehnungen aus Phase 1).

## Gruppe 3: Signatur-Bestätigung an der Dateikarte (D-02-04, Status `confirm`)

| Ort | EN (Quelltext) | DE | de_DE | FR |
|---|---|---|---|---|
| Kartentitel | The PDF is signed | Die PDF ist signiert | Die PDF ist signiert | Le PDF est signé |
| Kartentext | The signature is lost when redacting. The original stays signed. Continue? | Die Signatur geht bei der Schwärzung verloren. Das Original bleibt signiert. Fortfahren? | Die Signatur geht bei der Schwärzung verloren. Das Original bleibt signiert. Fortfahren? | La signature est perdue lors du caviardage. L'original reste signé. Continuer ? |
| Knopf bestätigen | Continue | Fortfahren | Fortfahren | Continuer |
| Knopf abbrechen | Cancel | Abbrechen | Abbrechen | Annuler |
| Knopf während des Sendens | Saving… | Wird gespeichert… | Wird gespeichert… | Enregistrement… |
| Fehlerhinweis | The answer could not be saved. Try again. | Die Antwort ließ sich nicht speichern. Erneut versuchen. | Die Antwort ließ sich nicht speichern. Erneut versuchen. | La réponse n'a pas pu être enregistrée. Réessayez. |

Bestätigung und Hinweis stehen im Protokoll (JOB-05); dort keine Nutzertexte, nur feste Ereigniswörter.

## Gruppe 4: Makro-Hinweis an der Dateikarte (D-02-12)

| Ort | EN (Quelltext) | DE | de_DE | FR |
|---|---|---|---|---|
| Hinweis (Info) | Macros were removed for the analysis. The original stays unchanged. | Makros wurden für die Analyse entfernt. Das Original bleibt unverändert. | Makros wurden für die Analyse entfernt. Das Original bleibt unverändert. | Les macros ont été supprimées pour l'analyse. L'original reste inchangé. |

## Gruppe 5: Stufenzeile `checking` (`line` in ReviewPlaceholder.vue)

| Ort | EN (Quelltext) | DE | de_DE | FR |
|---|---|---|---|---|
| Titel | Checking the file | Datei wird geprüft | Datei wird geprüft | Vérification du fichier |
| Text | A safety check runs before the analysis. | Vor der Analyse läuft eine Sicherheitsprüfung. | Vor der Analyse läuft eine Sicherheitsprüfung. | Un contrôle de sécurité a lieu avant l'analyse. |

## Gruppe 6: Admin-Hinweis geminderter Schutz (D-02-11, Admin-Einstellungen)

| Zeile (`data-layer`) | EN (Quelltext) | DE | de_DE | FR |
|---|---|---|---|---|
| `seccomp` | Network block for helper processes not available (seccomp). Analyses run with reduced protection. | Netzsperre für Hilfsprozesse nicht verfügbar (seccomp). Analysen laufen mit geminderter Schutzwirkung. | Netzsperre für Hilfsprozesse nicht verfügbar (seccomp). Analysen laufen mit geminderter Schutzwirkung. | Blocage réseau des processus auxiliaires indisponible (seccomp). Les analyses fonctionnent avec une protection réduite. |
| `landlock` | File access restriction for helper processes not available (Landlock). Analyses run with reduced protection. | Dateizugriffssperre für Hilfsprozesse nicht verfügbar (Landlock). Analysen laufen mit geminderter Schutzwirkung. | Dateizugriffssperre für Hilfsprozesse nicht verfügbar (Landlock). Analysen laufen mit geminderter Schutzwirkung. | Restriction d'accès aux fichiers des processus auxiliaires indisponible (Landlock). Les analyses fonctionnent avec une protection réduite. |
| `jail` | The protection layer for helper processes could not be loaded. Analyses fail until this is fixed. | Die Schutzschicht für Hilfsprozesse ließ sich nicht laden. Bis zur Behebung schlagen Analysen fehl. | Die Schutzschicht für Hilfsprozesse ließ sich nicht laden. Bis zur Behebung schlagen Analysen fehl. | La couche de protection des processus auxiliaires n'a pas pu être chargée. Les analyses échouent jusqu'à la correction. |
| Abhilfe zu `seccomp`/`landlock` | Run the container with seccomp and Landlock enabled (current Linux kernel, default security profile of the container runtime). | Den Container mit aktiviertem seccomp und Landlock betreiben (aktueller Linux-Kernel, Standard-Sicherheitsprofil der Container-Laufzeit). | Den Container mit aktiviertem seccomp und Landlock betreiben (aktueller Linux-Kernel, Standard-Sicherheitsprofil der Container-Laufzeit). | Exécutez le conteneur avec seccomp et Landlock activés (noyau Linux récent, profil de sécurité par défaut de l'environnement de conteneurs). |
| Abhilfe zu `jail` | Restart the backend container and check its log. | Den Backend-Container neu starten und sein Protokoll prüfen. | Den Backend-Container neu starten und sein Protokoll prüfen. | Redémarrez le conteneur du backend et consultez son journal. |

"Hilfsprozesse" steht für die Kindprozesse, in denen Prüfung, Umwandlung und Darstellung laufen.

## Freigabe

Freigabe: erteilt am 2026-11-16

Der Owner hat alle Texte wie entworfen freigegeben. Antworten auf die sechs Rückfragen:

1. `de_DE` bleibt unpersönlich im Infinitiv wie in Phase 1, keine Sie-Form; Spalte de_DE bleibt gleich DE.
2. Der Abhilfe-Rat zu `e2e_encrypted` bleibt auf der Dateikarte; der Start-Toast bleibt ohne Rat.
3. Die Seitengrenze steht in Ziffern: "300".
4. "neu analysieren" bleibt (statt "erneut starten").
5. "Hilfsprozesse" bleibt als Wort für die Kindprozesse im Admin-Hinweis.
6. "Das Original bleibt signiert." bleibt im Kartentext der Signatur-Bestätigung.

Hinweis für Plan 02-18: Eine abgebrochene Analyse mit Grund `signature_declined` (Status `cancelled`) darf nicht den allgemeinen Abbruch-Text "Die Datei wurde gelöscht" zeigen, sondern die Texte aus Gruppe 1 (`signature_declined` T/A).
