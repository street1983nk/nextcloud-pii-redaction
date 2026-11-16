# Phase 2: Zurückgestellte Befunde

- ERLEDIGT d0f2849 (EN/FR-Fassung angelegt, Owner-Ok): 2026-11-16 (bei 02-01): `backend/tests/test_trilingual.py::test_every_user_document_exists_in_three_languages` war rot, weil `docs/security-guidelines-abgleich.md` (Commit e1f7c0b) ohne `.en.md` und `.fr.md` liegt. Nicht durch 02-01 verursacht. Abhilfe: EN/FR-Fassung nachziehen oder die Datei als internes Dokument aus `docs/` herausnehmen (Owner-Entscheid).
- 2026-11-16 (bei 02-01, Notiz für 02-18): Karte im Status `cancelled` mit Grund `signature_declined` darf nicht den allgemeinen Abbruch-Text "Die Datei wurde gelöscht" zeigen, sondern die freigegebenen Texte `signature_declined` T/A aus 02-TEXTS.md Gruppe 1.
