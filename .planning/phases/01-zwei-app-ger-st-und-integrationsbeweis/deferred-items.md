# Deferred Items, Phase 1

Gefunden in Plan 01-01, außerhalb seines Umfangs, nicht behoben.

| Fund | Dateien | Grund | Zuständig |
|------|---------|-------|-----------|
| Release-Kette noch im Wurzel-Layout (`appinfo/info.xml`, `APP_ID: pii_redaction`, Archiv aus der Wurzel) | `.github/workflows/release.yml`, `.github/workflows/store-submit.yml`, `scripts/release/store-archive.sh` | Plan 01-01 stellt nur python/docker/deploy-harp/php um (AVS-Muster) | späterer Release-Plan der Phase (AVS: Plan 10) |
| Entwicklerdoku nennt alte Pfade (`src/pii_redaction/`, `appinfo/info.xml`, `l10n/`, `--cov=src/pii_redaction`) | `CONTRIBUTING.md` | reine Doku, kein Gate betroffen | Doku-Plan der Phase (AVS: Plan 13) |
| PHP-Dateien nur statisch geprüft (kein PHP lokal) | `php/**/*.php` | Owner-Regel: Laufbeweis in CI (`php.yml`) | CI beim ersten Push |
| Laufzeitabhängigkeit `numpy` steht über pymupdf/onnxruntime auf 2.5.4; Presidio verlangt später `<2.5.0` | `backend/uv.lock` | Konflikt erst mit Presidio; STACK.md pinnt dann `numpy==2.4.6` | Plan, der Presidio einführt |
