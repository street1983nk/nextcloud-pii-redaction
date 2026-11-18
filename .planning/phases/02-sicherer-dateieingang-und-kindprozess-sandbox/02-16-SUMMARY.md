---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 16
subsystem: ci
tags: [push-gate, sandbox, soffice, detect, arm64, harp]
requires: [02-02, 02-03, 02-04, 02-05, 02-06, 02-07, 02-08, 02-09, 02-10, 02-11, 02-12, 02-13, 02-14, 02-15]
provides: [phase-02 auf origin grün bei c1b6f5f, Profilvorlage für LibreOffice aus dem Image-Bau, deny_connect für soffice/render/precheck/sanitize, detect ohne OMP_THREAD_LIMIT, Tor test_detect_finds_the_name_in_time_on_every_architecture, Wächter test_torch_threads_guard.py]
affects: [02-17, 02-19, 02-22, Phase 8]
key-files:
  modified:
    - backend/src/pii_redaction_backend/workers/soffice.py
    - backend/src/pii_redaction_backend/sandbox/profiles.py
    - backend/src/pii_redaction_backend/sandbox/seccomp.py
    - backend/src/pii_redaction_backend/workers/child.py
    - backend/src/pii_redaction_backend/resources/hardware.py
    - backend/Dockerfile
    - backend/tests/test_container_soffice.py
    - backend/tests/test_soffice_profile.py
    - backend/tests/test_torch_threads_guard.py
    - backend/tests/profile_work.py
    - ci/seed.sh
    - .planning/phases/02-sicherer-dateieingang-und-kindprozess-sandbox/deferred-items.md
decisions:
  - "Push nur nach Owner-Freigabe je SHA, Ziel ausschließlich origin/phase-02, main unverändert"
  - "LibreOffice startet aus einer Profilvorlage des Image-Baus, kein Init-Lauf zur Laufzeit (Owner 17.11.)"
  - "soffice, render, precheck und sanitize bekommen connect() -> EACCES (Owner 17.11.); detect und ocr behalten connect() bis zur Messung"
  - "detect läuft ohne OMP_THREAD_LIMIT; OMP_NUM_THREADS aus hardware.worker_threads() (Deckel 2), vom Elternprozess gerechnet (Owner-Freigabe acf73d9)"
  - "ocr behält OMP_THREAD_LIMIT=1, die übrigen Kinder bleiben unverändert"
metrics:
  completed: 2026-11-18
  tasks: "2/2"
---

# Phase 2 Plan 16: Push-Tor und CI auf phase-02 Summary

phase-02 steht bei c1b6f5f auf origin, alle Workflows grün; auf dem Weg wurden der soffice-Startzähler, die Zombies im Testaufbau und der Hänger von detect auf arm64 (Ursache `OMP_THREAD_LIMIT=1`) belegt und behoben, main blieb unberührt.

## Freigaben

- Owner-Freigaben für jeden gepushten SHA liegen vor; letzter freigegebener und gepushter SHA: c1b6f5f.
- Ziel jeweils `git push origin HEAD:phase-02`, kein Force, kein PR, kein Merge, kein Kommentar.

## Commits (letzte Runde, in Reihenfolge)

| Commit | Betreff |
|---|---|
| 279e152 | docs(02-16): zombies of 335a80f, reaper finding and the detect variants |
| 87f5744 | test(02-16): detect variants without OMP_THREAD_LIMIT, stack lines every 30 s and torch facts per architecture |
| ea315a9 | docs(02-16): arm64 detect hang after c2ac178, next measurement and a gate before release |
| acf73d9 | fix(02-16): detect child without OMP_THREAD_LIMIT, thread count from cpu.max |
| 43afd81 | docs(02-16): root cause of the arm64 detect hang and the product fix |
| ad36464 | test(02-16): guard that every torch module applies the worker threads |
| c1b6f5f | ci(02-16): groupfolders tarball fallback for stable35 |

Frühere Korrekturen dieses Plans (Profilvorlage, deny_connect, Zähler, ruff in ci/) sind in deferred-items.md mit Commit und Plan-Bezug beschrieben (98c6324, 11207fd, 66e39c0, 8a9b7e4, 97707ea, 6e1d6e1, 47ad882, 4486922, 914d939, 54d8bf8, 335a80f, c2ac178, 8a0c6b2, 9ca6bb4, 3804cf6, b7f14cb, ba141fa, 7e3c909, b79b2f0).

## CI-Beleg zu c1b6f5f

Läufe (Logs lokal im Scratchpad `pii-0216o`):

- Python-Gates: https://github.com/street1983nk/nextcloud-pii-redaction/actions/runs/44248082841 , ruff, format, pyright, vulture, pytest, shellcheck grün, `1298 passed, 5 skipped, 13 deselected`.
- Sandbox: https://github.com/street1983nk/nextcloud-pii-redaction/actions/runs/44248082571 , Container suite amd64 und arm64 je `13 passed`, Notice `bridge test absent, smoke only` auf beiden Architekturen (erwartet bis 02-22).
- deploy-harp: https://github.com/street1983nk/nextcloud-pii-redaction/actions/runs/44248082614 , 11/11 Jobs grün (deploy-harp stable33/34/35 auf amd64 und arm64, stable35 mariadb, upgrade stable33/34/35, upgrade stable35 arm64); groupfolders in allen 11 Jobs aus dem Store (`groupfolders came from the app store`), der Tarball-Rückfall griff nicht.
- php.yml und security.yml für c1b6f5f grün (Angabe Owner-Session "CI komplett grün"; Logs dazu nicht im Scratchpad).

Messwerte aus dem Sandbox-Lauf:

| Zeile | amd64 | arm64 |
|---|---|---|
| SOFFICE-STARTS product | n=1 | n=1 |
| SOFFICE-STARTS control-fresh-unjailed | n=2 | n=2 |
| ZOMBIES after_job | 0 | 0 |
| SOCKET-CONNECT soffice/render/precheck/sanitize | refused EACCES | refused EACCES |
| SOCKET-CONNECT detect/ocr | ok | ok |
| PROFILE-WORK render, placeholder, precheck, sanitize | product_ok=ja | product_ok=ja |
| DETECT-VARIANT unjailed ms_extract | 247 ms (AVX2) | 354 ms (SVE128) |
| DETECT-VARIANT jailed-product ms_extract | 244 ms | 370 ms |
| DETECT-VARIANT control-omp-limit-1 (Negativkontrolle) | ok=ja 397 ms | ok=nein (hängt in score_queries) |
| TORCH-FACTS aten_threads / omp_max_threads | 2 / 2 | 2 / 2 |

Landlock-ABI und seccomp-Zustand stehen nicht als eigene Zeilen in diesem Log; die Werte aus den früheren Sandbox-Läufen gelten unverändert (Jail-Regeln in dieser Runde nicht geändert, nur deny_connect ergänzt).

## Befunde und Korrekturen (Plan-Bezug)

1. **soffice-Startzähler (Testaufbau, 02-14/02-16):** n=4 bis 7 kam von Forks und Zombies, nicht von Neustarts. Gezählt wird nur noch ein lebender soffice.bin mit Programm-Identität (cmdline und exe). Beleg: product n=1, control n=2 auf beiden Architekturen.
2. **Zombies (Testaufbau):** pytest per `docker exec` war nicht Subreaper; der Produkttest macht pytest jetzt zum Subreaper. Im Produkt ist der Server PID 1 und Subreaper, `reap_group` sammelt ein. Beleg: `ZOMBIES after_job=0`.
3. **detect hängt auf arm64 (Produkt, 02-08 child.py):** Ursache `OMP_THREAD_LIMIT=1` aus SAFE_ENV, torch/ATen plant trotzdem mit mehreren Threads; auf arm64 (libgomp) hängt `score_queries`, auch ohne Jail. Fix acf73d9: `child_env(profile="detect")` ohne die Grenze, dafür `OMP_NUM_THREADS` aus `hardware.worker_threads()` (Deckel 2), im Kind `apply_worker_threads(torch)`.
4. **Neues Tor** `test_detect_finds_the_name_in_time_on_every_architecture`: unjailed und jailed-product, fertig in 60 s, Name gefunden, Extraktion <= 5000 ms. Grün auf beiden Architekturen.
5. **Wächter** `backend/tests/test_torch_threads_guard.py`: kein Modul, das torch/gliner2/transformers importiert, ohne `apply_worker_threads` (AST, ohne torch).
6. **groupfolders stable35 (ci/seed.sh):** Rückfall auf den Release-Tarball v23.0.1, wenn der Store die App nicht liefert. Im grünen Lauf nicht gebraucht.

## Deviations from Plan

- Mehrere Korrekturrunden statt einer, jede mit eigener Owner-Freigabe je SHA; Produkt-Fixes nur mit Owner-Entscheid (Profilvorlage, deny_connect, detect-Umgebung).
- Korrekturen lagen teils in Dateien außerhalb der Pläne 02-02 bis 02-15 (Dockerfile, ci/seed.sh, hardware.py); Bezug in deferred-items.md.

## Offen

- R3: `SOFFICE-GATE` und `LO-PACKAGE` laufen nur in docker.yml (main, Tags, Monatslauf), Beleg erst beim ersten docker.yml-Lauf.
- detect und ocr behalten connect(); Messung ohne connect() und eigener Owner-Entscheid stehen aus. ocr wartet auf Tesseract im Image.
- Security-Notiz `/tmp/exapp.sock` für secure-phase (deferred-items.md).

## Threat Flags

Keine neue Angriffsfläche über den Plan hinaus; deny_connect verkleinert sie für vier Kinder.

## Self-Check: PASSED
