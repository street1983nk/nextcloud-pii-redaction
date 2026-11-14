# Deferred Items, Phase 1

Gefunden in Plan 01-01, außerhalb seines Umfangs, nicht behoben.

| Fund | Dateien | Grund | Zuständig |
|------|---------|-------|-----------|
| Release-Kette noch im Wurzel-Layout (`appinfo/info.xml`, `APP_ID: pii_redaction`, Archiv aus der Wurzel) | `.github/workflows/release.yml`, `.github/workflows/store-submit.yml`, `scripts/release/store-archive.sh` | Plan 01-01 stellt nur python/docker/deploy-harp/php um (AVS-Muster) | späterer Release-Plan der Phase (AVS: Plan 10) |
| Entwicklerdoku nennt alte Pfade (`src/pii_redaction/`, `appinfo/info.xml`, `l10n/`, `--cov=src/pii_redaction`) | `CONTRIBUTING.md` | reine Doku, kein Gate betroffen | erledigt in 01-19 (3301f8e) |
| PHP-Dateien nur statisch geprüft (kein PHP lokal) | `php/**/*.php` | Owner-Regel: Laufbeweis in CI (`php.yml`) | CI beim ersten Push |
| Laufzeitabhängigkeit `numpy` steht über pymupdf/onnxruntime auf 2.5.4; Presidio verlangt später `<2.5.0` | `backend/uv.lock` | Konflikt erst mit Presidio; STACK.md pinnt dann `numpy==2.4.6` | Plan, der Presidio einführt |

Gefunden in Plan 01-19 (Text-Audit), außerhalb seines Umfangs, nicht behoben.

| Fund | Dateien | Grund | Zuständig |
|------|---------|-------|-----------|
| Store-Beschreibung beider Apps (DE/EN/FR) verspricht Erkennung, echte Schwärzung und Vorschau vor dem Schwärzen; 0.1.0 hat nichts davon | `php/appinfo/info.xml`, `backend/appinfo/info.xml` | Produkttext, Owner-Regel: Entwurf vor Release zeigen | Owner-Entscheid vor dem ersten Store-Release |
| Deklaratives Formular der ExApp unter Weitere Einstellungen zeigt „Neue Dateien automatisch verarbeiten“ und „Größte Datei in MB“; beide Werte liest kein Code (nur `settings.py` und `test_settings.py`) | `backend/src/pii_redaction_backend/settings.py`, `backend/l10n/*.json` | Skelett-Rest, sichtbar für Admins; Entfernen ändert Formular und Tests | Owner-Entscheid, dann eigener Plan |
| Katalogsatz „Prüfungen werden nach 14 Tagen gelöscht.“ (Zustand abgelaufen), Phase 1 setzt keine Frist durch (`JobMapper`: „Phase 1 enforces no retention yet“) | `php/l10n/*.json`, `php/src/ReviewPlaceholder.vue` | Zustand nur per gefälschtem Startzustand erreichbar; UI-SPEC: Durchsetzung ab Phase 10 | Phase 10 oder Textänderung nach Owner-Entscheid |
| Symbole aus Material Design Icons (Apache-2.0) ohne `LICENSES/Apache-2.0.txt` und ohne REUSE-Eintrag; `REUSE.toml` führt alles als AGPL | `php/src/icon.svg`, `php/templates/admin.php`, `REUSE.toml`, `LICENSES/` | AVS hat Lizenztext und Hinweis; README nennt die Lizenz jetzt | Release-Vorbereitung |
