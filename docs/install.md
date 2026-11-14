Deutsch | [English](install.en.md) | [Français](install.fr.md)

# PII Redaction installieren

PII Redaction besteht aus zwei Apps. Beide sind nötig und müssen dieselbe Version haben:

- `pii_redaction_backend`: External App (Python-Container), wandelt DOCX und ODT in PDF um, erstellt das Seitenbild und die Platzhalter-PDF
- `pii_redaction`: PHP-App, bringt Dateiaktion, Prüfseite, Rechteprüfung, Benachrichtigungen, Ablage der Kopie und den Statusbereich

Stand 0.1.0: Die Prüfseite zeigt eine Vorschau ohne Erkennung, die Kopie ist ein Platzhalter. Personenbezogene Daten werden noch nicht gesucht und nicht geschwärzt.

## Reihenfolge

1. AppAPI aktivieren und den Deploy-Daemon HaRP einrichten.
2. Die External App „PII Redaction Backend“ (`pii_redaction_backend`) installieren und warten, bis sie aktiviert ist.
3. Die App „PII Redaction“ (`pii_redaction`) in derselben Version installieren und aktivieren.
4. Die App Notifications aktiviert lassen, sonst erscheinen keine Benachrichtigungen.
5. Unter Verwaltungseinstellungen, Grundeinstellungen die Hintergrundjobs auf Cron stellen (siehe Abschnitt Hintergrundjobs).
6. Unter Verwaltungseinstellungen, PII Redaction den Zustand prüfen: Erwartet ist „Beide Apps sind verbunden.“

## Gleiche Version (Lockstep)

- Beide Apps tragen immer dieselbe Versionsnummer. Nach einem Update beide Apps auf dieselbe Version bringen.
- Unterscheiden sich die Versionen nur in der letzten Stelle (zum Beispiel 0.1.0 und 0.1.1), laufen Analysen weiter.
- Unterscheiden sie sich in der ersten oder zweiten Stelle, startet keine neue Analyse und auf der Prüfseite lässt sich keine Kopie anlegen, bis beide Apps zusammenpassen.
- Ist die PHP-App deaktiviert, nimmt das Backend keine Aufträge an.

## Zustände im Statusbereich

Der Statusbereich unter Verwaltungseinstellungen, PII Redaction zeigt genau einen Zustand, darunter die Versionen beider Apps, die Zeit der letzten Prüfung und den Knopf „Erneut prüfen“:

- **Erfolg, „Beide Apps sind verbunden.“** Alles in Ordnung, nichts zu tun.
- **Hinweis, „Kleiner Versionsunterschied.“** Die Versionen unterscheiden sich in der letzten Stelle. Analysen laufen; beim nächsten Update beide Apps angleichen.
- **Fehler, „Die Versionen passen nicht zusammen.“** Die Versionen unterscheiden sich in der ersten oder zweiten Stelle. Beide Apps auf dieselbe Version bringen.
- **Fehler, „Das Backend ist nicht installiert.“** `pii_redaction_backend` fehlt. Die External App installieren.
- **Fehler, „Das Backend ist deaktiviert.“** `pii_redaction_backend` ist installiert, aber aus. Unter Apps aktivieren.
- **Fehler, „Das Backend antwortet nicht.“** Der Container läuft nicht oder HaRP ist nicht erreichbar. Unter Apps und in den AppAPI-Einstellungen prüfen.
- **Fehler, „AppAPI ist nicht aktiviert.“** Ohne AppAPI läuft das Backend nicht. AppAPI aktivieren und HaRP einrichten.
- **Warnung, „Der Zustand konnte nicht neu geprüft werden.“** „Erneut prüfen“ kam nicht durch; angezeigt bleibt der Stand beim Laden der Seite. Später erneut prüfen.

Bei jedem Fehler führt der Link „Apps öffnen“ zur App-Verwaltung. Solange ein Fehler besteht, startet keine Analyse und auf der Prüfseite lässt sich keine Kopie anlegen. Nutzer sehen beim Start „PII Redaction ist gerade nicht bereit. Die Verwaltung informieren.“

## Hintergrundjobs

Die Kopie neben dem Original legt ein Hintergrundjob von Nextcloud an. Im Modus AJAX läuft er erst, wenn jemand eine Seite öffnet; die Kopie erscheint dann verzögert. Empfohlen ist der Modus Cron.

## Hinweise

- Analysiert werden PDF, DOCX und ODT, immer genau eine Datei. Die Dateiaktion fehlt bei Mehrfachauswahl, im Papierkorb, auf öffentlichen Freigabeseiten und bei Ordnern.
- Es läuft immer nur ein Auftrag. Weitere warten in der Warteschlange.
- **Geänderte Datei:** Beim Start merkt sich die App den Stand der Datei (Etag). Ändert er sich danach, gilt die Prüfung als veraltet: Die Prüfseite meldet „Die Datei wurde geändert“, die Datei muss neu analysiert werden. Externe Speicher können den Etag auch ohne Änderung am Inhalt neu setzen, etwa beim erneuten Einlesen. Auch dann verlangt die App eine neue Analyse. Das ist Absicht: Lieber einmal mehr analysieren als eine Kopie aus einem anderen Stand anlegen.
- **Download-Sperre:** Erlaubt eine Freigabe kein Herunterladen, startet keine Analyse, ohne Ausnahme. Wird die Sperre nachträglich gesetzt, zeigt die Prüfseite kein Seitenbild mehr und es entsteht keine Kopie.
- **Gelöschtes Original:** Die Analyse endet, es kommt keine Benachrichtigung.
- Die Kopie ist immer eine PDF und überschreibt nie eine vorhandene Datei. Ist der Name belegt, bekommt sie ` (2)` angehängt.
