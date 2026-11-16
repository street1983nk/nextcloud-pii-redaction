# Phase 2: Sicherer Dateieingang und Kindprozess-Sandbox - Pattern Map

**Mapped:** 2026-11-16
**Files analyzed:** 41 (neu oder geändert)
**Analogs found:** 37 / 41

Grundlage: 02-CONTEXT.md (D-02-01 bis D-02-14), 02-RESEARCH.md (Projektstruktur, Pattern 1 bis 5, Erkennungstabelle, Wave-0-Lücken). Alle Pfade relativ zu `C:/Users/Student/nextcloud-pii-redaction`, sofern nicht als Findling (`C:/Users/Student/nextcloud-search/backend/src/findling/`) oder AV (`C:/Users/Student/nextcloud-audio-video-search/backend/src/audio_video_search_backend/`) gekennzeichnet.

## File Classification

### Backend: neue Module

| Neue/geänderte Datei | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/src/pii_redaction_backend/sandbox/__init__.py` | config | - | `backend/src/pii_redaction_backend/resources/__init__.py` | exact |
| `backend/src/pii_redaction_backend/sandbox/jail.py` | utility (Kind-Startprogramm) | process exec | `workers/render.py` (Kind-Einstieg `main(argv) -> int`) + Findling `extract/sandbox.py` (`_limit_address_space`, `_limit_malloc_arenas`) | role-match |
| `backend/src/pii_redaction_backend/sandbox/profiles.py` | config | - | `workers/child.py` (`SAFE_ENV`, `EXTRA_ALLOWED`, `PYTHON_CHILDREN` als `Final`-Konstanten) | role-match |
| `backend/src/pii_redaction_backend/sandbox/seccomp.py` | utility (ctypes) | - | Findling `extract/sandbox.py` Zeilen 126-153 (`ctypes.CDLL(None)`, mallopt) | partial |
| `backend/src/pii_redaction_backend/sandbox/landlock.py` | utility (ctypes) | - | wie seccomp.py | partial |
| `backend/src/pii_redaction_backend/sandbox/probe.py` | service | request-response (/status) | `runner/runner.py` `ChildRun`/`_LAST_CHILD`/`last_child()` Zeilen 66-81 | role-match |
| `backend/src/pii_redaction_backend/sandbox/reaper.py` | utility | process | `workers/child.py` `_kill_group` Zeilen 100-107 + RESEARCH "Reaper nach jedem Kind" | exact (Erweiterung) |
| `backend/src/pii_redaction_backend/intake/limits.py` | config | - | Findling `config.py` Zeilen 385-432 (Konstanten mit Begründungskommentar) + `backend/.../config.py` `MAX_SOURCE_BYTES` | exact |
| `backend/src/pii_redaction_backend/intake/magic.py` | utility | transform (Bytes zu Format) | `workers/sniff.py` (Nachfolger) | exact |
| `backend/src/pii_redaction_backend/intake/zipcheck.py` | utility | file-I/O | Findling `extract/archive.py` Zeilen 172-190, 289-482 | exact |
| `backend/src/pii_redaction_backend/intake/xmlcheck.py` | utility | transform | RESEARCH Pattern 3 Codebeispiel (kein Repo-Analog) | no analog |
| `backend/src/pii_redaction_backend/intake/pdfcheck.py` | utility | file-I/O | `workers/render.py` (Import des Parsers im Kind, alles in `try/except Exception`) | partial |
| `backend/src/pii_redaction_backend/intake/sanitize.py` | utility | transform (ZIP zu ZIP) | Findling `archive.py` `_copy` Zeilen 525-563 (gestreamtes Lesen mit Zähler); Regeln aus RESEARCH Pattern 4 | partial |
| `backend/src/pii_redaction_backend/workers/precheck.py` | worker (Kind-Einstieg) | file-I/O, schreibt verdict.json | `workers/render.py` | exact |
| `backend/src/pii_redaction_backend/workers/sanitize.py` | worker (Kind-Einstieg) | file-I/O | `workers/render.py` | exact |
| `backend/src/pii_redaction_backend/workers/lo_profile/registrymodifications.xcu` | config (Paketdaten) | - | keins | no analog |
| `backend/src/pii_redaction_backend/offline.py` | config | - | Findling `extract/sandbox.py` `_pin_native_thread_pools` Zeilen 321-336 (ENV vor Import setzen) | partial |

### Backend: geänderte Module

| Datei | Role | Data Flow | Analog / Ankerstelle | Match |
|---|---|---|---|---|
| `workers/child.py` | utility | process | sich selbst: `run_child` bekommt `profile=`, Argv immer über `python -I -m ...sandbox.jail`; `PYTHON_CHILDREN` um `precheck`, `sanitize` erweitern | exact |
| `workers/soffice.py` | worker | process | sich selbst: `command()` Zeilen 32-48 + Profilkopie vor `run_child`, `finally: rmtree` bleibt | exact |
| `workers/sniff.py` | utility | - | wird durch `intake/magic.py` ersetzt oder delegiert; `test_sniff.py` mitziehen | exact |
| `runner/runner.py` | service | request-response (Queue) | `_analyze` Zeilen 266-317: Vorprüfung nach `fetch`, vor `soffice`; neue `_Fail(Reason.…)`-Pfade | exact |
| `model.py` | model | - | `Reason`/`Stage`/`AckResult` StrEnum Zeilen 11-55 | exact |
| `nc.py` | service | request-response | `Claim` Zeilen 214-259 (Feld `expected`, `confirmed`), `_ack_body` Zeilen 371-403 (Ergebnis `confirm`, Signatur-/Makro-Flags) | exact |
| `api/status.py` | controller | request-response | sich selbst Zeilen 21-34: Feld `sandbox` mit festen Wörtern ergänzen | exact |
| `main.py` | config | - | `lifespan` Zeilen 80-106: `prctl(PR_SET_DUMPABLE,0)`, `PR_SET_CHILD_SUBREAPER`, Probe vor `Runner()` | exact |
| `config.py` | config | - | `MAX_SOURCE_BYTES` Zeile 28 (Kommentar "phase 2 hardens") nach `intake/limits.py` | exact |
| `logs.py` | utility | - | `ALLOWED_EXTRA` Zeilen 31-55 (neue Schlüssel nur falls nötig, gleichzeitig `test_log_calls.py`) | exact |
| `backend/pyproject.toml`, `backend/uv.lock` | config | - | bestehende exakte Pins; pikepdf, lxml, Erkennungsstapel (D-02-09) | exact |
| `backend/Dockerfile` | config | build | sich selbst: frpc-Zeile 50 `install -m 0755` zu `0711` (D-02-14), neue Stufe `test`, ENV-Block Zeilen 91-93 | exact |

### PHP-App

| Datei | Role | Data Flow | Analog | Match |
|---|---|---|---|---|
| `php/lib/Model/Reason.php` | model | - | sich selbst | exact |
| `php/lib/Model/Status.php` | model | - | sich selbst (`confirm` in `isOpen()`) | exact |
| `php/lib/Db/JobEventMapper.php` | model | CRUD | `ACTION_PLACEHOLDER_REQUESTED` Zeilen 20-21, `isAllowedAction` Zeilen 46-50 | exact |
| `php/lib/Service/JobService.php` | service | CRUD | `start()` Zeilen 69-119 (E2E-Prüfung), `toReview`/`toFailed` Zeilen 190-211 (neue `toConfirm`, `confirmSignature`) | exact |
| `php/lib/Service/FileAccess.php` | service | - | `resolve()`/`recheckForStart` Zeilen 109-135 (E2E-Ordnerprüfung hier, Pitfall 5) | exact |
| `php/lib/Controller/QueueController.php` | controller | request-response | `claim()` Zeilen 75-97 (`expected` aus MIME), `ack()` Zeilen 149-178 + `ackFailed` Zeilen 238-249 (neues Ergebnis `confirm`) | exact |
| `php/lib/Controller/ReviewController.php` | controller | request-response | `placeholder()` Zeilen 165-193 (Vorlage für POST `/review/{jobId}/confirm`) | exact |
| `php/src/ReviewPlaceholder.vue` | component | event-driven (Polling) | `failure()` Zeilen 276-293, `card` Zeilen 296-326, Aktionsblock Zeilen 85-104 | exact |
| `php/src/startToast.ts` | component | request-response | `refusal()` Zeilen 49-61 (Grund `e2e_encrypted` beim Start) | exact |
| `php/l10n/{de,de_DE,en,fr}.json` + `.js` | config (l10n) | - | bestehende Kataloge + `scripts/l10n_js.py` | exact |
| `php/tests/Unit/*` (JobServiceTest, QueueControllerTest, ReviewControllerTest, FileAccessTest, ModelTest) | test | - | bestehende Dateien gleichen Namens | exact |

### Tests, CI, Workflows

| Datei | Role | Data Flow | Analog | Match |
|---|---|---|---|---|
| `backend/tests/conftest.py` | test | - | sich selbst; Marker `container`/`linux` + Korpus-Fabrik | exact |
| `backend/tests/test_jail.py`, `test_jail_profiles.py`, `test_reaper.py` | test | - | `backend/tests/test_child.py` | exact |
| `backend/tests/test_intake_*.py`, `test_sanitize.py` | test | - | `backend/tests/test_sniff.py`, `test_child.py` | role-match |
| `backend/tests/test_offline.py` | test | - | `backend/tests/test_log_calls.py` (AST-Gate mit mutierter Probe) | role-match |
| `backend/tests/test_jail_container.py`, `test_lo_network.py`, `test_corpus.py` | test (container) | - | keins im Repo (erster `-m container`-Test) | no analog |
| `backend/tests/test_model.py`, `test_php_schema.py` | test | - | sich selbst (Lockstep-Listen) | exact |
| `backend/tests/test_dockerfile.py` | test | - | sich selbst (Regeln + mutierte Probe) | exact |
| `backend/tests/test_workflows.py`, `test_workflow_pins.py` | test | - | sich selbst | exact |
| `ci/make_corpus.py` | utility (CI) | batch | `ci/make_fixtures.py` | exact |
| `.github/workflows/docker.yml` | config (CI) | - | sich selbst, Schritt "Smoke test the pushed digest" Zeilen 88-119 | exact |

## Pattern Assignments

### `sandbox/jail.py` (Kind-Startprogramm, process exec)

**Analog 1:** `backend/src/pii_redaction_backend/workers/render.py` (Kind-Einstieg, nichts drucken, Exit-Codes)

```python
# render.py Zeilen 18-21, 33-41
def main(argv: list[str]) -> int:
    if len(argv) != 3 or not argv[2].isdigit() or not MIN_DPI <= int(argv[2]) <= MAX_DPI:
        return 2
    ...
    except Exception:
        out.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```
Übertragen: `main(argv)` parst `<profil> -- <befehl...>`, unbekanntes Profil = Exit 2, nie `print`, nie Logging (Gate `test_log_calls.py` Regel 4: `print(` verboten in `backend/src`). Am Ende `os.execv(ziel, argv)` mit `child_env()` (aus `workers/child.py` Zeilen 50-58), nicht `os.execvpe` mit geerbter Umgebung.

**Analog 2:** Findling `extract/sandbox.py` Zeilen 105-153 (rlimit und ctypes, Plattform-Guard)

```python
def _limit_address_space(cap: int) -> None:
    if sys.platform == "win32":
        return
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))

_M_ARENA_MAX: Final = -8
_CHILD_MALLOC_ARENAS: Final = 1

def _limit_malloc_arenas() -> None:
    if not sys.platform.startswith("linux"):
        return
    libc = ctypes.CDLL(None)
    mallopt = getattr(libc, "mallopt", None)
    if mallopt is None:
        return
    mallopt(_M_ARENA_MAX, _CHILD_MALLOC_ARENAS)
```
Übertragen: Reihenfolge laut RESEARCH Pattern 1 (rlimits mit `RLIMIT_CORE=(0,0)`, `PR_SET_NO_NEW_PRIVS`, Landlock, seccomp, `execv`). Kein `RLIMIT_NPROC` (Anti-Pattern). `mallopt` nur für Python-Kinder (Pitfall 8). Windows-Zweig: `resource` erst im Funktionskörper importieren, damit Tests unter Windows importieren können (gleiches Muster in `workers/child.py` Zeilen 110-116).

**Analog 3 (Geheimnisse):** Findling `extract/sandbox.py` Zeilen 274-286 `_shed_secrets` und AV `engine/child.py` Zeile 61 `SECRET_ENV`. Im PII-Repo ist das bereits stärker gelöst (leere Umgebung in `child_env`); das Jail ergänzt die /proc- und Dateiwege (Pitfall 1), nicht die Umgebung.

---

### `sandbox/profiles.py` (config)

**Analog:** `backend/src/pii_redaction_backend/workers/child.py` Zeilen 24-35

```python
SAFE_ENV: Final[dict[str, str]] = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/tmp",  # noqa: S108 - the child's home is a throwaway, its profile lives below the job folder
    "LANG": "C.UTF-8",
    "OMP_THREAD_LIMIT": "1",
}
EXTRA_ALLOWED: Final = frozenset({"TESSDATA_PREFIX", "SAL_USE_VCLPLUGIN"})
PYTHON_CHILDREN: Final = frozenset({"render", "placeholder"})
```
Übertragen: eine `@dataclass(frozen=True, slots=True)` je Profil (Muster `ChildRun` in `runner/runner.py` Zeilen 66-72) mit CPU, AS (None für `detect`), FSIZE, NOFILE, Wanduhr, Lese-/Schreibpfaden; ein `Final[Mapping[str, Profile]]`, Schlüssel `render`, `precheck`, `sanitize`, `soffice`, `ocr`, `detect`. Werte aus der Grenzwert-Tabelle in RESEARCH; Zeitdeckel aus `runner.py` Zeilen 51-53 (`RENDER_TIMEOUT_SECONDS`, `SOFFICE_TIMEOUT_SECONDS`) hierher ziehen.

---

### `sandbox/reaper.py` und Änderung `workers/child.py` (process)

**Analog:** `workers/child.py` Zeilen 69-107

```python
async def run_child(args: list[str], *, timeout_s: float, cwd: Path, extra_env: dict[str, str] | None = None) -> None:
    process = await asyncio.create_subprocess_exec(
        *args, cwd=cwd, env=child_env(extra_env),
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        code = await asyncio.wait_for(process.wait(), timeout=timeout_s)
    except TimeoutError:
        _kill_group(process.pid)
        await process.wait()
        raise ChildTimeout from None
    except asyncio.CancelledError:
        _kill_group(process.pid)
        await process.wait()
        raise
    if code != 0:
        raise ChildFailed(code)

def _kill_group(pid: int) -> None:
    if sys.platform == "win32":
        return
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
```
Übertragen (Pattern 2): nach `await process.wait()` IMMER (auch bei Erfolg, in `finally`) `reaper.reap_group(process.pid)` mit `killpg` + Schleife `os.waitpid(-pgid, os.WNOHANG)` bis `ChildProcessError` (Code in RESEARCH "Reaper nach jedem Kind"). Nie `waitpid(-1)`. `args` wird zu `jail_argv(profile, args)` = `[sys.executable, "-I", "-m", "pii_redaction_backend.sandbox.jail", profile, "--", *args]`; Muster `python_child` Zeilen 61-66. Exit-Code-Abbildung: `ChildFailed.exit_code` bleibt die einzige Rückinfo (kein stderr).

---

### `sandbox/probe.py` (service, Ergebnis für /status)

**Analog:** `runner/runner.py` Zeilen 66-81 und `api/status.py` Zeilen 21-34

```python
@dataclass(frozen=True, slots=True)
class ChildRun:
    kind: str
    rss_kb: int
    ms: int

_LAST_CHILD: dict[str, ChildRun] = {}

def last_child() -> ChildRun | None:
    return _LAST_CHILD.get("last")
```
```python
    return {
        "version": config.app_version(),
        "ready": ready,
        "companion": state.state,
        "busy": worker.busy if isinstance(worker, Runner) else False,
        "lastChild": None if last is None else {"kind": last.kind, "rssKb": last.rss_kb, "ms": last.ms},
    }
```
Übertragen: Probe-Ergebnis als Modul-Zustand mit Abfragefunktion, `/status` ergänzt `"sandbox": {"seccomp": "active"|"unavailable", "landlock": ..., "landlockAbi": int}` (nur feste Wörter und Zahlen, Kopfkommentar von status.py: "no name, no path"). Die PHP-Seite `ExAppService::status()` und `php/templates/admin.php`/`src/admin.ts` zeigen den Admin-Hinweis (D-02-11); Wortliste in PHP spiegeln.

---

### `intake/limits.py` (config, D-02-07/D-02-13)

**Analog:** Findling `config.py` Zeilen 396-432, eine Konstante je Block mit Messbegründung:

```python
# Central directory headers per ZIP file, counted by extract/archive.py itself
# before zipfile builds one ZipInfo per header; ... Measured: 10 000 headers cost
# ZipFile 5.5 MiB and 0.34 s, 100 000 cost 55.9 MiB and 3.3 s. ...
ARCHIVE_MAX_ENTRIES = 10_000
ARCHIVE_MAX_CENTRAL_DIRECTORY_BYTES = 8 * 1024 * 1024
ARCHIVE_MAX_RATIO = 100
ARCHIVE_RATIO_MIN_BYTES = 1024 * 1024
ARCHIVE_MALICIOUS_RATIO = 1000
```
Lokaler Stil: `Final`-Typisierung wie `backend/.../config.py` Zeile 28 (`MAX_SOURCE_BYTES: Final = 268435456` mit Kommentar). `MAX_SOURCE_BYTES` zieht nach `limits.py` (Kommentar "Provisional; phase 2 hardens the limits"), `config.py` importiert oder re-exportiert. `runner.py` Zeilen 61-62 (`MAX_PAGES = 100_000`, `MAX_SIDE`) und `QueueController::MAX_PAGES` Zeile 45 sind Plausibilitätsdeckel des Protokolls, nicht der 300-Seiten-Deckel; nicht verwechseln, aber im Kommentar auf `limits.MAX_PAGES` verweisen. Ein Test je Konstante auf Grenze und Grenze+1.

---

### `intake/magic.py` (Nachfolger von `workers/sniff.py`)

**Analog:** `backend/src/pii_redaction_backend/workers/sniff.py` (ganze Datei, 43 Zeilen)

```python
Format = Literal["pdf", "docx", "odt"]
PDF_MAGIC: Final = b"%PDF-"
ZIP_MAGIC: Final = b"PK\x03\x04"
ODT_MIMETYPE: Final = b"application/vnd.oasis.opendocument.text"

def detect(path: Path) -> Format | None:
    with path.open("rb") as handle:
        head = handle.read(8)
    if head.startswith(PDF_MAGIC):
        return "pdf"
    if not head.startswith(ZIP_MAGIC):
        return None
    try:
        with zipfile.ZipFile(path) as archive:
            ...
    except (zipfile.BadZipFile, OSError, EOFError, NotImplementedError):
        return None
```
Ändern: `ZipFile` erst NACH `zipcheck` (Findling-Befund "ZipFile baut je Header ein ZipInfo"); CFB-Signatur `D0 CF 11 E0 A1 B1 1A E1` mit `EncryptedPackage`-Suche ergänzen (Findling hat `extract/cfb.py` als Lesevorlage); Rückgabe statt `None` ein Wort der geschlossenen Liste (`encrypted_document`, `unsupported_format`, `wrong_type`). `runner._typed_source` Zeilen 410-418 ruft heute `sniff.detect` im Server-Prozess: das wandert ins Kind `precheck`.

---

### `intake/zipcheck.py` (file-I/O)

**Analog:** Findling `extract/archive.py`. Übernehmen (kopieren, nicht importieren, wie AV-Praxis):
- `_is_traversal` Zeilen 177-189 (NUL, führender Separator, Laufwerk, `..`-Segment auf `orig_filename`)
- `count_central_directory` Zeilen 289-315, `_central_directory` 339-347, `_end_record` 350-370, `_end_record64` 373-408, `_Window` 411-444, Konstanten Zeilen 108-141
- `_read_zip` Stufe 1+2 Zeilen 447-467 ohne Leseteil:

```python
    with path.open("rb") as handle:
        size = handle.seek(0, 2)
        _, length = _central_directory(handle, size)
        budget.take_directory(length)
        count = count_central_directory(handle, size, limit=budget.entries)
        budget.take_entries(count)

    with ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > count:
            raise OverLimit
        budget.take_declared(sum(info.file_size for info in members))
        _judge_ratios(members)
        for info in members:
            if _is_traversal(info.orig_filename):
                raise OverLimit(_ZIP_TRAVERSAL)
```
- `_judge_ratios` Zeilen 470-482, Overlap-Erkennung `_is_overlap` Zeile 172-174 und Warnungs-Fang aus `_copy` Zeilen 540-553.

Ergänzen (Pitfall 4): Namensnormalisierung (Backslash, `.`-Segmente, Doppelslash, NFC, `casefold()`) mit Kollisionsprüfung; Vorspann vor erstem Local Header ablehnen; Verschlüsselungsbit (`_ENCRYPTED_FLAG = 0x1`, Zeile 124) = `encrypted_document`; Verschachtelungstiefe 0. Fehlerklassen `CorruptDirectory` (= `damaged`), `OverLimit` mit `signature` (= `unsafe_content`) bzw. ohne (= `too_large`) wie Findling Zeilen 144-169.

---

### `intake/sanitize.py` + `workers/sanitize.py` (transform)

**Analog Lesen/Schreiben:** Findling `archive.py` `_copy` Zeilen 540-563 (blockweise mit Budget, `_READ_BLOCK = 64 * 1024`). Kind-Einstieg wie `workers/render.py`. Regeln (externe Rels, `attachedTemplate`, Feldcodes, `altChunk`, `vbaProject.bin`, ActiveX, ODF `xlink:href`, `Basic/`, `office:scripts`) aus RESEARCH Pattern 4; XML nur über `intake/xmlcheck.make_parser()`. Ergebnis-JSON trägt nur Zähler/Flags (`macros_removed: bool`, `external_links_removed: int`) für JobEvent-Aktionen (D-02-12). Gegenprobe: bereinigte Kopie erneut durch `zipcheck` + `xmlcheck`.

---

### `workers/precheck.py` (Kind-Einstieg, schreibt verdict.json)

**Analog:** `workers/render.py` (ganz) + Lesestelle `runner._read_meta` Zeilen 421-434:

```python
def _read_meta(path: Path) -> tuple[int, int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = "meta.json is not an object"
        raise ValueError(msg)
    values = []
    for key, ceiling in (("pages", MAX_PAGES), ("width", MAX_SIDE), ("height", MAX_SIDE)):
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= ceiling:
            msg = "meta.json value out of range"
            raise ValueError(msg)
        values.append(value)
```
Übertragen: `precheck <src> <expected> <out.json>`; verdict = `{"verdict": <Wort>, "pages": int, "signed": bool, "ownerProtected": bool}`; der Server liest es mit einer `_read_verdict` nach demselben Muster (Wort gegen `Reason`-Enum, Zahlen gegen Bereich, sonst `ValueError` = `render_failed`/`damaged`). pikepdf erst im Funktionskörper importieren (wie `import pymupdf` in render.py Zeile 24).

---

### `runner/runner.py` (Einbau der Vorprüfung)

**Analog:** sich selbst, `_analyze` Zeilen 288-312:

```python
            source = await asyncio.to_thread(_typed_source, folder)
            if source is None:
                raise _Fail(Reason.UNSUPPORTED_FORMAT)
            pdf = source
            if source.suffix != ".pdf":
                await self._report(job, stage, Stage.CONVERTING, None, None)
                pdf = await self._timed(
                    "soffice", self._convert(source, folder / "pdf", str(job.job_id), SOFFICE_TIMEOUT_SECONDS)
                )

            await self._report(job, stage, Stage.RENDERING, 0, None)
            args = child.python_child("render", str(pdf), str(folder / PAGE_FILE), str(RENDER_DPI))
            await self._timed("render", self._run_child(args, timeout_s=RENDER_TIMEOUT_SECONDS, cwd=folder))
        ...
        except _Fail as failure:
            await self._fail(job, failure.reason)
            return
        except (child.ChildTimeout, child.ChildFailed, soffice.ConversionFailed, ValueError, OSError) as exc:
            LOGGER.info("render step failed", extra={"job_id": job.job_id, "exc_type": type(exc).__name__})
            await self._fail(job, Reason.RENDER_FAILED)
```
Einbaupunkt: `_typed_source` ersetzen durch `await self._timed("precheck", self._run_child(child.python_child("precheck", ...), ...))` + `_read_verdict`; abgelehnt = `raise _Fail(Reason(<wort>))`; `signed and not job.confirmed` = neuer Abschluss `await self._close(job, AckResult.CONFIRM, ...)` und `return`; DOCX/ODT: `sanitize`-Kind vor `self._convert`, nach Konvertierung Seitenzahl gegen `limits.MAX_PAGES` (`too_many_pages`). Neue Stage-Wörter (falls `checking`) im Gleichschritt mit PHP `Stage` und `ReviewPlaceholder.vue` `line` Zeilen 264-273. Alle Außenwirkungen bleiben über den Konstruktor injizierbar (Zeilen 107-141), damit `test_runner.py` sie ersetzen kann.

---

### `workers/soffice.py` (gehärtetes Profil)

**Analog:** sich selbst Zeilen 62-70:

```python
async def convert(src: Path, outdir: Path, job_id: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> Path:
    profile = Path(PROFILE_ROOT) / f"lo-{_checked(job_id)}"
    _prepare(outdir)
    try:
        await run_child(command(src, outdir, job_id), timeout_s=timeout_s, cwd=outdir)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    return _single_pdf(outdir)
```
Ändern: vor `run_child` `<profile>/user/registrymodifications.xcu` aus Paketdaten kopieren (`importlib.resources.files("pii_redaction_backend.workers") / "lo_profile" / ...`), `run_child(..., profile="soffice")`. `_checked(job_id)` Zeilen 25-29 bleibt die Pfadsperre. Paketdaten müssen über `uv_build` ins Wheel (pyproject prüfen).

---

### `offline.py` (RES-02)

**Analog:** Findling `extract/sandbox.py` Zeilen 321-336 (Variablen vor dem Import setzen, Begründung im Kommentar):

```python
def _pin_native_thread_pools() -> None:
    for name in _NATIVE_THREAD_POOL_VARIABLES:
        os.environ[name] = "1"
```
Inhalt aus RESEARCH Code-Beispielen: `tldextract.tldextract.TLD_EXTRACTOR = TLDExtract(suffix_list_urls=(), cache_dir=None, fallback_to_snapshot=True)`, `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`, `HF_HUB_DISABLE_TELEMETRY`, Audit-Hook. ENV zusätzlich im Dockerfile-ENV-Block (Zeilen 91-93). Für das `detect`-Kind: Variablen über `EXTRA_ALLOWED` in `child.py` zulassen, nicht über geerbte Umgebung.

---

### `main.py` (Server-Härtung beim Start)

**Analog:** sich selbst `lifespan` Zeilen 80-96:

```python
    logs.configure(config.log_level())
    ...
    LOGGER.info("starting", extra={"version": config.app_version(), "binding": config.binding_mode()})
    checker = start_background(companion.run_periodic(), "companion")
    stop = asyncio.Event()
    worker = Runner()
```
Einbau: `prctl(PR_SET_DUMPABLE, 0)` als erste Handlung (Pitfall 1a, besser in `main()` vor `run_app`, Zeile 115-128), `PR_SET_CHILD_SUBREAPER` dort ebenfalls; `probe.run()` vor `Runner()`, Ergebnis per `LOGGER.info("sandbox probed", extra={...})` mit erlaubten Schlüsseln (neue Schlüssel in `logs.ALLOWED_EXTRA` UND `test_log_calls.ALLOWED_EXTRA`). Fehlerweg: `except Exception as exc: LOGGER.error(..., extra={"exc_type": type(exc).__name__})` wie Zeilen 73-75.

---

### `model.py` + `php/lib/Model/Reason.php` + `Status.php` (Lockstep)

**Analog Python:** `model.py` Zeilen 21-38 (`class Reason(StrEnum)`, Wörter klein mit Unterstrich). **Analog PHP:** `Reason.php` Zeilen 12-28 (`case EncryptedPdf = 'encrypted_pdf';`), `Status.php` Zeilen 14-48 (`isOpen()`, `isTerminal()`).

Neue Wörter (RESEARCH "Reason-Spalte hat 32 Zeichen"): `e2e_encrypted`, `encrypted_document`, `wrong_type`, `damaged`, `too_large`, `unsafe_content`; Status `confirm` (16 Zeichen, in `isOpen()`); `AckResult.CONFIRM`. Am Listenende anhängen, Reihenfolge ist Testinhalt.

Gleichzeitig ändern: `backend/tests/test_model.py` Zeilen 20-37, `backend/tests/test_php_schema.py` `CLOSED_LISTS` Zeilen 26-63, `php/tests/Unit/ModelTest.php`, `QueueController::RESULTS` Zeile 52.

---

### `php/lib/Db/JobEventMapper.php` (Protokoll JOB-05)

**Analog:** sich selbst Zeilen 20-50:

```php
	public const ACTION_PLACEHOLDER_REQUESTED = 'placeholder_requested';
	...
	public static function isAllowedAction(string $action): bool {
		return $action === self::ACTION_PLACEHOLDER_REQUESTED
			|| Status::tryFrom($action) !== null
			|| Subject::tryFrom($action) !== null;
	}
```
Neue Aktionen als Konstanten nach demselben Muster: `signature_notice`, `signature_confirmed`, `macros_removed`, `external_links_removed`, `owner_protection_dropped` (D-02-10); `isAllowedAction` um eine Konstantenliste erweitern (Spalte `action` prüfen: Länge in Migration). Aufruf wie `ReviewController::placeholder` Zeile 191: `$this->events->record($jobId, $uid, JobEventMapper::ACTION_…)`.

---

### `php/lib/Service/JobService.php` + `FileAccess.php` (E2E, Bestätigung)

**Analog Ablehnung beim Start:** `JobService::start` Zeilen 74-91:

```php
		[$verdict, $file] = $precheck ?? $this->files->recheckForStart($uid, $fileId);
		if ($verdict === Recheck::DownloadBlocked) {
			return self::refused(Reason::DownloadBlocked);
		}
		...
		if (!in_array($mime, self::ALLOWED_MIMES, true)) {
			return self::refused(Reason::UnsupportedFormat);
		}
```
E2E-Prüfung (Elternordner mit `getFileInfo()->isEncrypted()`, nur Ordner, Pitfall 5) als Methode in `FileAccess` (dort liegt laut Kopfkommentar Zeilen 15-33 jede Lesefrage; `test_php_gates.py` Regel 4 hält Knotensuche auf diese Datei), Aufruf in `start()` nach dem MIME-Check: `return self::refused(Reason::E2eEncrypted)`. Exceptions wie `downloadBlocked` Zeilen 81-84 fail-closed (Ausnahme = abgelehnt, Log nur `class`).

**Analog Übergang:** `toReview`/`toFailed` Zeilen 190-211 und `expect`/`finish` Zeilen 309-336. Neue `toConfirm(Job)` (aus `Analyzing`, Task null, Event `signature_notice`) und `confirmSignature(Job, uid)` (aus `Confirm` zurück nach `Queued`, Task `analyze`, Flag/Event `signature_confirmed`). Kein Notification-Subject (D-02-02: keine Nextcloud-Benachrichtigung je Ablehnung; `finish(..., null)` wie `toApproved` Zeile 238). `expected` (pdf/docx/odt) aus `ALLOWED_MIMES`-Index ableiten; wird in der Claim-Antwort mitgegeben, nicht gespeichert, falls MIME pro Claim neu gelesen wird (Job speichert bewusst keinen MIME, Kopfkommentar Zeilen 34-36).

---

### `php/lib/Controller/QueueController.php` (claim/ack)

**Analog:** `claim()` Zeilen 87-96 (Antwortfelder), `ack()` Zeilen 163-178 (`match ($result)`), `ackFailed` Zeilen 238-249:

```php
	private function ackFailed(Job $job, ?string $reason): DataResponse {
		$why = Reason::tryFrom($reason ?? '');
		if ($why === null) {
			return self::badRequest();
		}
		if (!in_array($job->getStatusEnum(), [Status::Analyzing, Status::Applying], true)) {
			return $this->conflict($job->getId());
		}
		$this->service->toFailed($job, $why);
		return new DataResponse(['ok' => true]);
	}
```
Neu: `'confirm' => $this->ackConfirm($job)` (nur aus `Analyzing`/`Analyze`, sonst 409), Makro-/Link-Flags als `?bool`/`?int` mit Bereichsprüfung (Muster `side()` Zeilen 291-293). Claim ergänzt `expected` und `confirmed` (bool). Python-Gegenstück `nc._parse_claim` Zeilen 227-259 (jedes Feld geprüft, sonst `LOGGER.warning("claim answer discarded", extra={"reason": "shape"})`).

---

### `php/lib/Controller/ReviewController.php` (POST Bestätigung)

**Analog:** `placeholder()` Zeilen 165-193 (Attribute, recheckMember, forMember, Statusprüfung, Event, `secured`):

```php
	#[\OCP\AppFramework\Http\Attribute\NoAdminRequired]
	#[\OCP\AppFramework\Http\Attribute\FrontpageRoute(verb: 'POST', url: '/review/{jobId}/placeholder', requirements: ['jobId' => '\d+'])]
	public function placeholder(int $jobId): JSONResponse {
		$uid = $this->uid();
		$verdict = $uid === null ? null : $this->jobs->recheckMember($jobId, $uid);
		if ($uid === null || $verdict === null || $verdict === Recheck::Missing) {
			return self::secured(new JSONResponse([], Http::STATUS_NOT_FOUND));
		}
		...
		if ($job->getStatusEnum() !== Status::Review) {
			return self::secured(new JSONResponse(['status' => $job->getStatus()], Http::STATUS_CONFLICT));
		}
		...
		$this->jobs->toApproved($job, $uid);
		$this->events->record($jobId, $uid, JobEventMapper::ACTION_PLACEHOLDER_REQUESTED);
		return self::secured(new JSONResponse(['status' => Status::Approved->value], Http::STATUS_ACCEPTED));
	}
```
Neu: `confirmSignature(int $jobId)` an `/review/{jobId}/confirm`, CSRF an (kein `NoCSRFRequired`), nur Initiator (V4), Status muss `confirm` sein. Gate `test_php_gates.py` Regel 12 verlangt den recheck-Aufruf in jeder Route.

---

### `php/src/ReviewPlaceholder.vue` (Dateikarte, D-02-02/D-02-04/D-02-12)

**Analog Ablehnungstext:** `failure()` Zeilen 276-293 (Titel + Abhilfe-Satz, passt exakt zu D-02-01):

```ts
function failure(reason: string | null): [string, string] {
	switch (reason) {
	case 'render_failed':
		return [t('pii_redaction', 'The file could not be displayed'), t('pii_redaction', 'It may be damaged. Save it as PDF and analyse that.')]
	...
	default:
		return [t('pii_redaction', 'The analysis failed'), t('pii_redaction', 'Analyse the file again. If it persists, tell your administrators.')]
	}
}
```
Je neuem Reason ein `case` (Wortlaut vor dem Bau zum Owner, D-02-03). Die Karte selbst: `card` Zeilen 319-322 (`case 'failed'`, `type: 'error'`).

**Analog Bestätigungsdialog:** Aktionsblock Zeilen 85-104 (`NcButton variant="primary"`, `posting`, `postFailed`-NoteCard) und `requestCopy()` Zeilen 424-445 (axios.post, Status übernehmen, `stateRegion.focus()`, `schedule(POLL_MS)`). Neuer `case 'confirm'` in `card` (`type: 'warning'`) plus Block `v-if="job.status === 'confirm'"` mit zwei Buttons. `isOpen`/`COPYING` und Polling (`schedule` Zeilen 368-379) müssen `confirm` als offen behandeln, aber nicht pollen müssen (wartet auf Nutzer). Makro-Hinweis (D-02-12): `NcNoteCard type="info"` im `isReady`-Block analog Zeilen 76-83, gespeist aus einem neuen View-Feld (`JobService::view` Zeilen 144-160 erweitern, Typannotation Zeile 126 mitziehen).

**Analog Start-Toast:** `php/src/startToast.ts` `refusal()` Zeilen 49-61, neuer `case 'e2e_encrypted'` mit `ToastType.ERROR`.

---

### l10n (`php/l10n/*.json` + `.js`)

**Analog:** bestehende Einträge, z. B. `php/l10n/de.json` Zeile 58 `"The file could not be displayed": "Die Datei ließ sich nicht darstellen"`. Schlüssel = englischer Quelltext im `t()`-Aufruf. `de.json` und `de_DE.json` identisch pflegen, danach `.js` mit `uv run python scripts/l10n_js.py` erzeugen (`--check` im Gate). `test_trilingual.py` (`catalogue_findings` Zeilen 57-66) und `test_ui_assets.py` prüfen Gleichstand und dass jeder `t()`-Schlüssel in allen Katalogen steht. Umlaute nur in Werten, keine Gedankenstriche.

---

### `backend/Dockerfile` (D-02-14, Teststufe, ENV)

**Analog:** sich selbst. Zeile 50:
```dockerfile
    install -m 0755 "/tmp/frp_${FRP_VERSION}_linux_${FRP_ARCH}/frpc" /usr/local/bin/frpc; \
```
wird `-m 0711`. Achtung: Zeile 83 `COPY --from=frpc /usr/local/bin/frpc /usr/local/bin/frpc` übernimmt den Modus; Zeile 51 `frpc --version` läuft noch als root, bleibt gültig. `docker/start.sh` byteweise unverändert (Zeile 68 `frpc -c /frpc.toml &`, Zeile 73 `exec "$@"`). Teststufe: nach `runtime` als `FROM runtime AS test` würde `test_the_build_is_multi_stage_with_a_runtime_stage_last` (test_dockerfile.py Zeilen 37-41) brechen; entweder Stufe VOR `runtime` nicht möglich (braucht runtime als Basis), also Regel anpassen auf "letzte Auslieferungsstufe runtime, build-push-action mit `target: runtime`", oder Teststufe in eigener Datei. Neue Regeln (frpc 0711, Teststufe nie Ziel des Push) mit mutierter Probe wie Zeilen 84-87, 122-130.

---

### `.github/workflows/docker.yml` (Container-Suite, `--network none`)

**Analog:** Schritt "Smoke test the pushed digest" Zeilen 88-119 (`docker run` mit den AppAPI-Variablen, Prüfungen mit `test`, Log-Gruppe). Neuer Schritt danach: Teststufe bauen (`docker/build-push-action` mit `target: test`, `push: false`, `load: true`, gleicher SHA-Pin Zeile 77) und `docker run --rm --network none <img>:test pytest -m container`. Host-Mitschnitt: separater Schritt mit `sudo tcpdump -i docker0`. Alle Actions per SHA pinnen (`test_workflow_pins.py`), Größe unter `CAP_BYTES` (test_workflows.py Zeile 27). RES-02-Modelle: `actions/cache` mit SHA-Pin, Schlüssel = sha256-Werte.

---

### `ci/make_corpus.py` (batch, nur Standardbibliothek)

**Analog:** `ci/make_fixtures.py` Zeilen 1-36 (Docstring mit `usage: python3 ci/make_corpus.py <outdir>`, Dateiliste im Docstring, nur stdlib, `Final`-Konstanten, `zipfile` und rohe PDF-Bytes von Hand). PDF-Bau über `_pdf_literal` Zeilen 87-90 als Vorlage. Korpusliste aus RESEARCH "Wave 0 Gaps". Gate: `test_ci_fixtures.py` als Vorlage für `test_ci_corpus.py`; ruff-Pfade in pyproject (`paths = [..., "../ci"]`) decken die Datei ab.

---

### Tests (Python)

**Analog Struktur:** `backend/tests/test_child.py`:

```python
POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX only")

@POSIX_ONLY
async def test_a_hanging_child_and_its_grandchild_are_killed(tmp_path: Path) -> None:
    ...
    with pytest.raises(child.ChildTimeout):
        await child.run_child([sys.executable, "-I", "-c", script], timeout_s=2, cwd=tmp_path)
    grandchild = int(pid_file.read_text(encoding="utf-8"))
    assert _gone_within(grandchild, seconds=5), "the grandchild survived the group kill"
```
`_alive` Zeilen 97-104 prüft bereits den Zombie-Zustand über `/proc/<pid>/stat`: direkt für `test_reaper.py` wiederverwenden. Async-Tests ohne Dekorator (`asyncio_mode = "auto"`, pyproject Zeile 83).

**Marker:** pyproject `[tool.pytest.ini_options]` Zeilen 81-90 hat noch keine `markers`; `container` und `linux` dort registrieren und in `python.yml` Zeile 93 `-m "not container"` ergänzen (sonst laufen sie lokal/CI ohne Image). Coverage `fail_under = 90` (Zeile 55): Container-only-Code ggf. mit Unit-Tests über Monkeypatch decken.

**Gate-Muster mit mutierter Probe** (Pflicht laut Kopfkommentaren von test_php_schema.py, test_log_calls.py, test_trilingual.py): jede neue Regel als Funktion `*_findings(source) -> list[str]`, ein Test auf die echte Quelle, ein `test_self_*`/`*_rule_fires`-Test auf eine verfälschte Probe (Beispiel test_dockerfile.py Zeilen 100-130).

## Shared Patterns

### Fail-closed mit geschlossener Wortliste
**Source:** `runner/runner.py` `_Fail` Zeilen 93-98, `nc._ack_body` Zeilen 381-383, `QueueController::ackFailed`.
**Apply to:** precheck, sanitize, runner, QueueController.
Jede Ablehnung ist ein `Reason`-Wort, nie ein Text; unbekanntes Wort = 400 bzw. `ValueError`; Kind-Ausgabe (verdict.json) wird wie `_read_meta` gegen Liste und Bereich geprüft.

### Logging-Härtung
**Source:** `backend/src/pii_redaction_backend/logs.py` `ALLOWED_EXTRA` Zeilen 31-55, Gate `backend/tests/test_log_calls.py` Zeilen 1-16.
**Apply to:** alle neuen Backend-Module.
```python
LOGGER.info("render step failed", extra={"job_id": job.job_id, "exc_type": type(exc).__name__})
```
Nur Literal-Meldungen, `extra` nur erlaubte Schlüssel, kein `.exception(`, kein `print(`. Kinder loggen gar nicht (stdout/stderr = DEVNULL). PHP: `['jobId' => ..., 'class' => $e::class]` wie FileAccess Zeile 82.

### Kind-Isolation (bestehend, jetzt über Jail)
**Source:** `workers/child.py` (SAFE_ENV, `start_new_session=True`, DEVNULL, `killpg`), Findling `extract/sandbox.py`, AV `engine/child.py` Zeilen 79-93 (`_kill_child_tree`) und 119-125 (`setsid`, `SECRET_ENV`).
**Apply to:** render, placeholder, precheck, sanitize, soffice, später ocr/detect.
Alle gehen über `run_child(..., profile=...)`; kein Kind ohne Profil (Test: `python_child`/`jail_argv` lehnt unbekannte Namen ab wie `test_a_python_child_runs_isolated`).

### Lockstep Python und PHP
**Source:** `model.py`, `php/lib/Model/*.php`, `backend/tests/test_php_schema.py` `CLOSED_LISTS`, `test_model.py`.
**Apply to:** Reason, Status, AckResult, Stage, JobEvent-Aktionen.
Jedes neue Wort in vier Stellen im selben Commit: Python-Enum, PHP-Enum, test_model.py, test_php_schema.py (+ ModelTest.php, Spaltenlänge 32/16 prüft test_php_schema Regel 3).

### Dreisprachigkeit
**Source:** `php/l10n/*.json`, `scripts/l10n_js.py`, `backend/tests/test_trilingual.py`.
**Apply to:** alle neuen Ablehnungs-, Bestätigungs-, Makro- und Admin-Texte. Wortlaute vor dem Bau zum Owner (D-02-03).

### Zustand im Container ohne Klartext
**Source:** `backend/src/pii_redaction_backend/store/schema.sql` (nur ids, hashes, Zahlen, Wörter), `test_store_schema.py`.
**Apply to:** falls Verdict oder Probe in `state.db` landen: nur Wörter/Zahlen, `schema_version` erhöhen; Landlock muss `state.db` für Kinder sperren (Pitfall 1).

### Injizierbare Außenwirkungen
**Source:** `Runner.__init__` Zeilen 107-141.
**Apply to:** neue Runner-Schritte (precheck, sanitize, probe) als Konstruktor-Parameter mit Standard, damit `test_runner.py` ohne Kindprozesse läuft.

## No Analog Found

| Datei | Role | Data Flow | Grund |
|---|---|---|---|
| `sandbox/seccomp.py` | utility | - | Kein seccomp in PII/Findling/AV; RESEARCH Pattern 1 (libseccomp per ctypes) nutzen, nur das ctypes-Muster von Findling `_limit_malloc_arenas` übernehmen |
| `sandbox/landlock.py` | utility | - | Kein Landlock im Bestand; kernel.org-Doku, ABI-Probe laut RESEARCH |
| `intake/xmlcheck.py` | utility | transform | Kein lxml-Parser im Repo; Fabrik aus RESEARCH Pattern 3 |
| `workers/lo_profile/registrymodifications.xcu` | config | - | Schlüssel aus RESEARCH Pattern 5, Format im CI-Schichtlauf (b) bestätigen (A3) |
| `tests/test_jail_container.py`, `test_lo_network.py`, `test_corpus.py` | test | - | Erste `-m container`-Tests; Struktur von test_child.py, Ablauf aus RESEARCH "Netzwerkbeweis in CI" |

## Metadata

**Analog search scope:** `backend/src/pii_redaction_backend/**`, `backend/tests/**`, `backend/Dockerfile`, `backend/docker/*.sh`, `php/lib/**`, `php/src/**`, `php/l10n/`, `ci/`, `scripts/`, `.github/workflows/`; Findling `extract/archive.py`, `extract/sandbox.py`, `config.py`; AV `engine/child.py`
**Files scanned:** ca. 40 gelesen, ca. 200 gelistet
**Pattern extraction date:** 2026-11-16
