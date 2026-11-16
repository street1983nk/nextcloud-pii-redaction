# Abgleich mit den Nextcloud-Sicherheitsrichtlinien (PII Redaction)

Anhang zum Sicherheitsdossier. Stand: 16.11.2026, geprüft gegen die
Security guidelines des Nextcloud 35 Developer Manual
(developer_manual/prologue/security.html) und die App-Store-Regeln
(app_publishing_maintenance/publishing.html). Prüfweg: Code-Sweep über
php/ und backend/src am 16.11.2026 (shell_exec, proc_open, passthru,
eval, rohes SQL, print_unescaped, innerHTML, os.system: 0 Treffer) plus
das Phase-1-Security-Audit (01-SECURITY.md, 103 Threats, 0 offen).

## Developer-Guidelines

| Regel | Stand | Beleg |
|---|---|---|
| SQL-Injection: nur vorbereitete Abfragen | erfüllt | IQueryBuilder in allen Mappers; kein rohes SQL im Sweep; Backend-Store mit parametrisierten sqlite-Abfragen |
| XSS: Templates und DOM sanieren | erfüllt | Prüfseite als Vue-App mit Template-Escaping, CSP ohne Inline-Skripte; kein innerHTML mit Nutzerdaten (Sweep) |
| Clickjacking | erfüllt | Standard-Header unangetastet |
| Code execution / file inclusion | erfüllt | Sweep 0 Treffer; Dokumente nur im ExApp-Volume, nie im Webroot |
| Directory traversal: Files API | erfüllt | Dateizugriffe über IRootFolder nach Rechteprüfung; Ausgabe schreibt PHP als Nutzer über die Files API, der Container hat keinen Schreibzugriff auf Nutzerdateien |
| Shell injection | erfüllt | PHP ruft keine Shell (Sweep); LibreOffice/Tesseract als Kindprozess mit Argumentliste ohne Shell (Phase-2-Pläne: Jail mit geleerter Umgebung) |
| Auth bypass / privilege escalation | erfüllt | Dateiaktion/Prüfseite/Protokoll prüfen Rechte in PHP; Phase-1-Audit verified |
| Sensitive data exposure | erfüllt | Logging-Härtung (kein Exception-Text, LOG_CONTEXT_KEYS-Gate mit Selbsttest, kein Pfad/Name im Log); Geheimnis-Lesewege aus dem Container sind Gegenstand der Phase-2-Pläne (prctl DUMPABLE=0, Landlock, frpc 0711) |
| CSRF | erfüllt | App-Framework-Standard; POSTs mit requesttoken |
| Unvalidated redirects | n. a. | Keine Weiterleitungen |
| CORS | n. a. | Keine CORS-Freigaben |

## Store-Regeln (Auszug)

| Regel | Stand | Beleg |
|---|---|---|
| AGPL-3.0-or-later | erfüllt | LICENSE, info.xml; PyMuPDF AGPL passt; fr_core_news_lg LGPL-LR-Prüfung dokumentiert (CLAUDE.md) |
| Kein "Nextcloud" im Namen | erfüllt | pii_redaction / pii_redaction_backend |
| Zeitnahe Reaktion auf Sicherheitsmeldungen | erfüllt | SECURITY.md (GitHub private reporting + Mail, 7 Tage); Praxisbeleg: pip-audit-Gate auf main + CVE-Fix-Prozess |
| Sauberes Auf-/Abräumen, Up-/Downgrade | erfüllt | Migrationen mit Tests, enabled-Handler räumt Altzustände (Push 11) |
| Keine Daten an Dritte, Datenschutz | erfüllt | Kein Dokumentinhalt/Fund/Telemetrie verlässt den Server; Modell-Downloads mit festem sha256; Netzabschaltung der Bibliotheken (tldextract/Presidio/GLiNER2) ist Phase-2-Kriterium mit --network-none-Beweis am echten Image |
| Kontaktweg | erfüllt | GitHub Issues, SECURITY.md |

## Über die Richtlinien hinaus

- Threat-Audit je Phase (01-SECURITY.md verified, 103 Threats); Phase 2 IST die Härtungsphase (Kindprozess-Sandbox, Vorprüfung fail-closed, Korpus in CI)
- Workflow-Pins, pip-audit über den Lock, composer.lock erzwungen
- Fail-closed als Grundlinie: Ablehnung ist der sichere Pfad

## Offene Punkte

- Der Abgleich wird nach dem Phase-2-Security-Audit (02-SECURITY.md) um die Sandbox-Belege ergänzt (seccomp/Landlock-Probe, frpc-0711-Messung A1, Netzbeweis).
