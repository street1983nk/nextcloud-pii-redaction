---
phase: 02-sicherer-dateieingang-und-kindprozess-sandbox
plan: 10
subsystem: offline
tags: [res-02, tldextract, huggingface, gliner2, audit-hook]
requires: [02-02]
provides: [offline.configure, offline.install_network_tripwire, offline.OFFLINE_ENV, offline.NETWORK_EVENTS]
affects: [02-22]
key-files:
  created:
    - backend/src/pii_redaction_backend/offline.py
    - backend/tests/test_offline.py
decisions:
  - "Positivkontrolle mit zusätzlichem Aufzeichnungs-Hook statt Exit-Code: tldextract fängt den PermissionError (urllib3 macht daraus einen ConnectionError) und fällt auf den Snapshot zurück; der Versuch steht aber im Protokoll"
  - "Kindprozesse der Tests mit leerem TLDEXTRACT_CACHE, damit ein vorhandener Benutzer-Cache den Netzversuch nicht verdeckt"
metrics:
  completed: 2026-11-17
  tasks: "2/2"
---

# Phase 2 Plan 10: Netzabschaltung der Bibliotheken Summary

`offline.configure()` setzt HF_HUB_OFFLINE, TRANSFORMERS_OFFLINE, HF_HUB_DISABLE_TELEMETRY und TLDEXTRACT_PUBLIC_SUFFIX_LIST_URLS="" hart und ersetzt `tldextract.tldextract.TLD_EXTRACTOR` durch einen Extraktor ohne URLs und Cache; `install_network_tripwire()` beendet jeden Python-Netzschritt; ein AST-Gate verbietet die Netz-APIs von gliner2, huggingface_hub, spaCy und `from_pretrained` mit Repo-ID.

## Commits

| Schritt | Commit |
|---|---|
| Tests (Task 1 und Gate Task 2) | 452f40d |
| offline.py | 5b6c656 |

## Prüfung

- Suite 929 passed, 14 skipped; ruff, Format, pyright (latest) 0, vulture grün.
- RED belegt (Sammelfehler ohne offline.py).
- Presidio-EmailRecognizer findet `max@example.org` mit 0 Netzereignissen; Positivkontrolle ohne configure zeigt aufgezeichnete Netzereignisse.
- Gate: alle Quellen in backend/src, scripts, ci ohne Fund; 12 Proben feuern; absoluter Pfad bei from_pretrained erlaubt.

## Deviations from Plan

- Test- und Gate-Tests in einem Test-Commit (Task 2 ist reiner Test), danach der Implementierungs-Commit.
- Behavior "Positivkontrolle endet mit PermissionError" angepasst: tldextract schluckt den Fehler und nutzt den Snapshot; gemessen wird deshalb über einen Aufzeichnungs-Hook (aussagekräftiger, unabhängig vom Fehlerpfad der Bibliothek).

## Threat Flags

Keine.

## Self-Check: PASSED
