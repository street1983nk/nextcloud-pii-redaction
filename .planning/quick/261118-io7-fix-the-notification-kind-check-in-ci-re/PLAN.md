---
quick_id: 261118-io7
date: 2026-11-18
---

# ci/refusals.sh: Meldungsart sprachunabhängig erkennen, Beweise einzeln führen

CI-Lauf "Deploy through HaRP" 44300061301 zu c025b96: alle sieben deploy-harp-Beine rot im Schritt "Refusals with their reason, E2E folder, signed PDF after the confirmation", überall an derselben Stelle:

    job 13 has 1 notifications (A review is ready), expected one review_ready
    FAIL: positive control failed: the API shows no review_ready for job 13

Ursache (Skript, nicht Produkt): `seen_notification` vergleicht das Feld `subject` der OCS-API der Notifications-App mit dem Schlüsselwort. Die API liefert dort den gerenderten Titel (`Notifier::prepare` setzt `setParsedSubject`), das Schlüsselwort steht nur in `oc_notifications.subject` (`NotificationSender::notify`). `ci/stale.sh` liest es deshalb schon aus der Tabelle.

1. `seen_notification` mit zwei Zeugen: Die API sagt, was der Nutzer sieht (genau eine Meldung des Auftrags, mit Titel und Link zur Prüfseite), die Tabelle nennt das Schlüsselwort (genau `review_ready`). Keine Annahme über die Sprache des Kontos. Die Positivkontrolle prüft dadurch mehr, nicht weniger.
2. Den Rest des Skripts Zeile für Zeile gegen den Produktcode lesen (Routen, HTTP-Codes, JSON-Felder, Ereignisnamen, SQL für SQLite und MariaDB, Sitzungsanmeldung, Request-Token) und gleichartige Fehler vorab beheben.
3. Jeden Beweis einzeln führen (`proof`): Ein Fehlschlag wird benannt, die übrigen laufen weiter, am Ende ist der Lauf rot. Fehlermeldungen nennen die tatsächlichen Werte (Antwort gekürzt, Request-Token geschwärzt).
4. Gates in `backend/tests/test_workflows.py` mitziehen, mit Selbsttests.
5. Produktcode bleibt unverändert. Kein Push.

Beweis nur in CI: Docker und PHP laufen lokal nicht. Lokal: Gates und ein Lauf des Skripts gegen eine Attrappe von `ci/lib.sh` mit eingebauten Fehlern.
