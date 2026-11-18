---
quick_id: 261118-k0t
date: 2026-11-18
---

# ci/refusals.sh: Formular-Login mit Origin-Kopf, CSRF-Ablehnung beim Namen

CI-Lauf "Deploy through HaRP" 44310663659 zu d93bf13: Auf allen sieben deploy-harp-Beinen bestehen 10 von 12 Beweisen. Rot sind überall gleich nur die zwei Beweise mit Browser-Sitzung:

    FAIL: the login form sent alice back to /index.php/login (HTTP 303): the login was refused
    PROOF FAILED: signed_refuses
    PROOF FAILED: signed_confirms

Ursache (Skript, nicht Produkt), am Quelltext von Nextcloud Server belegt: `core/Controller/LoginController.php`, `tryLogin`, Zeilen 307 bis 314 (stable33, stable34 und stable35 im Abschnitt wortgleich) weist ein Formular ohne Kopfzeile `Origin` oder mit einem nicht vertrauten Origin als `invalidOrigin` ab, bevor Passwort oder Request-Token geprüft werden. curl sendet bei einem POST keinen `Origin`, ein Browser schon.

1. `session_login` sendet `Origin` (Schema, Host und Port aus `NC_URL`), sonst bleibt der Weg wie er ist: Login-Seite für Sitzungscookie, die beiden SameSite-Cookies und das Request-Token, dann das Formular. Kein Basic-Auth, kein `OCS-APIRequest`.
2. Der Negativfall wird schärfer statt schwächer: Die Bestätigung ohne Request-Token und mit einem erfundenen Token muss genau `412` mit `CSRF check failed` antworten (`SecurityMiddleware` wirft `CrossSiteRequestForgeryException`). "Alles außer 2xx" hätte auch eine nicht angemeldete Sitzung (401) durchgelassen.
3. Positivkontrolle in derselben Sitzung: `signed_confirms` bestätigt in der Sitzung, die der Server gerade abgewiesen hat, mit deren Token. Der einzige Unterschied zum abgewiesenen Versuch ist das Token.
4. Fehlermeldungen des Login-Teils nennen die echten Werte: Statuscode je Schritt, Namen der gesetzten Cookies, ob ein Token gefunden wurde, `Location` ohne Query, das Grundwort des Servers aus seiner geschlossenen Liste. Nie Passwort, Token oder Cookie-Werte.
5. Gates in `backend/tests/test_workflows.py` mitziehen, mit Selbsttests.
6. Produktcode bleibt unverändert. Kein Push.

Beweis nur in CI: Docker und PHP laufen lokal nicht. Lokal: Gates und ein Lauf der Sitzungsfunktionen und der beiden Beweise gegen eine Attrappe von curl mit eingebauten Fehlern.
