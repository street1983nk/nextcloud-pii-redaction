---
quick_id: 261118-hs4
date: 2026-11-18
---

# Keine Benachrichtigung je Ablehnung der Vorprüfung (D-02-02, Owner-Entscheid A)

Owner-Entscheid vom 18.11.2026, Weg A aus deferred-items.md der Phase 02: Eine Ablehnung der Vorprüfung erzeugt keine Nextcloud-Benachrichtigung. Der Grund steht schon an der Karte der Prüfseite. Echte Fehler benachrichtigen weiter.

Ausgangslage: `JobService::toFailed` sendet immer `job_failed`; Ablehnungen der Vorprüfung kommen über `QueueController::ackFailed` dorthin.

1. Die Ablehnungsgründe an einer Stelle im Produkt: `Reason::isPrecheckRefusal()`. Maßstab ist die geschlossene Liste der Urteile der Vorprüfung (`backend/src/pii_redaction_backend/intake/verdict.py`) und 02-TEXTS.md Gruppe 1. Ein Grund, der dort nicht steht, bleibt ein Fehler.
2. `toFailed` sendet für diese Gründe nichts. Statusübergang, Ereignis `failed`, Rückgabe des Lease und Purge-Aufgabe bleiben. Der Pfad "erster Leser sendet job_failed einmal" (`catchUpGiveUp`) darf für eine Ablehnung nichts nachsenden.
3. PHPUnit: je Ablehnungsgrund "failed, Purge, keine Benachrichtigung" und je Fehler "benachrichtigt einmal", als DataProvider mit ausgeschriebenen Gründen. `testFailedNotifiesAndGoesToPurge` bleibt.
4. `ci/playwright/notification.spec.ts`: `job_failed` aus einem echten Fehler, dazu der Beleg, dass die kaputte PDF keine Benachrichtigung erzeugt.
5. `ci/refusals.sh` Schritt (g) und die Gates in backend/tests gegen das Produkt lesen, nur bei Bedarf ändern.
6. STATE.md (Blocker), deferred-items.md (Punkt 1 und 2 erledigt, Punkt 3 bleibt).
7. Kataloge DE/EN/FR: prüfen, ob ein Text unbenutzt oder falsch wird.

PHPUnit und Playwright laufen nur in CI (kein PHP, kein Docker lokal). Kein Push.
