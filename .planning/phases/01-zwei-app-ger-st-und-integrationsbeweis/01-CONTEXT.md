# Phase 1: Zwei-App-Gerüst und Integrationsbeweis - Context

**Gathered:** 2026-11-07
**Status:** Ready for planning
**Source:** Owner-Antworten auf die offenen Fragen aus 01-RESEARCH.md (keine discuss-phase, Owner-Wahl)

<domain>
## Phase Boundary

Wie ROADMAP.md Phase 1: beide Apps installierbar (NC 33 bis 35, amd64 und arm64, HaRP), Dateiaktion startet einen Auftrag als Hintergrundarbeit, Platzhalter-Prüfseite mit Seite 1 als Bild über die PHP-App, Benachrichtigung, Platzhalter-Kopie per `newFile()` neben dem Original. Datenmodell, Etag-Bindung, Warteschlange und Logging-Regeln stehen, bevor eine Phase Klartext speichert.

</domain>

<decisions>
## Implementation Decisions

### Owner 07.11.2026
- LibreOffice headless kommt schon in Phase 1 ins Image; Seite 1 wird für PDF, DOCX und ODT als Bild gezeigt, die Image-Größe wird in Phase 1 gemessen.
- Kein Dateiname in Benachrichtigungen; die Benachrichtigung verlinkt nur auf die Prüfseite.
- Die Platzhalter-Kopie trägt schon den echten späteren Namenszusatz (Schwärzen und Pseudonymisieren getrennt), damit Ablage und Kollisionsregeln früh getestet werden.
- CI bekommt zusätzlich ein MariaDB-Bein (NC 35, amd64), damit Warteschlange und Lease-Claim unter MySQL-Semantik belegt sind.

### Claude's Discretion (Empfehlung aus der Recherche übernommen)
- Platzhalter-Weg ohne Debug-Schalter.
- Zusätzlich `de_DE` (Sie-Form) neben `de`, wie bei Audio & Video Search.

</decisions>

<canonical_refs>
## Canonical References

- `.planning/phases/01-zwei-app-ger-st-und-integrationsbeweis/01-RESEARCH.md` (Plattform, Fallen aus AVS, Validation Architecture)
- `.planning/PROJECT.md` (14 Owner-Entscheide)
- `.planning/research/ARCHITECTURE.md`, `PITFALLS.md`, `STACK.md`, `SUMMARY.md`
- Referenzimplementierung: `C:/Users/Student/nextcloud-audio-video-search` (Phase 1, grün auf NC 33 bis 35)

</canonical_refs>

<deferred>
## Deferred Ideas

None, Phase-Grenze wie ROADMAP.md.

</deferred>

---

*Phase: 01-zwei-app-ger-st-und-integrationsbeweis*
*Context gathered: 2026-11-07 aus Owner-Antworten*
