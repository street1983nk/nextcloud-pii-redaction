# Contributing

Thanks for considering a contribution. PII Redaction is solo-maintained with hard
quality gates; small, focused pull requests get reviewed fastest.

## The shape of the repository

PII Redaction consists of two apps that always carry the same version:

- `php/`: the PHP app `pii_redaction` (file action, review page, permission
  checks, notifications, placing the copy, admin section). Store metadata in
  `php/appinfo/info.xml`, catalogues in `php/l10n/` (de, de_DE, en, fr),
  frontend sources in `php/src/`.
- `backend/`: the External App `pii_redaction_backend`, a Python container
  (FastAPI) that AppAPI deploys through HaRP. Code in
  `backend/src/pii_redaction_backend/`, store metadata in
  `backend/appinfo/info.xml`, catalogues in `backend/l10n/`.
- `ci/`: the scripts of the integration proof on real instances
  (`.github/workflows/deploy-harp.yml`).

## The gates

Green locally before you push:

```sh
cd backend
uv sync
uv run ruff check .
uv run ruff format --check .
PYRIGHT_PYTHON_FORCE_VERSION=latest uv run pyright
uv run vulture
uv run pytest -q
uv run python ../scripts/l10n_js.py --root ../php/l10n --check

cd ../php
npm ci --ignore-scripts
npm run typecheck
npm run build
```

The PHP unit tests run in CI (`.github/workflows/php.yml`) against a Nextcloud
server checkout.

## Pull requests

- One concern per pull request, with tests; a behaviour change without a test
  will be asked for one.
- Every user-visible text exists in German, English and French
  (`backend/tests/test_trilingual.py`).
- No content leaves the server: no external service receives file content.
- The store texts (`php/appinfo/info.xml`, `backend/appinfo/info.xml`) and the
  version travel with releases; do not change them in a feature pull request.
- Dependencies are locked in `backend/uv.lock` and `php/package-lock.json`;
  change them only through `uv` or `npm` and say why.

## Security problems

See [SECURITY.md](SECURITY.md); please do not open a public issue.
