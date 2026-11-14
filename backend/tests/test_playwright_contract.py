"""The acceptance suite under ci/playwright/ holds the UI-SPEC test contract.

Read as text, no browser:

- playwright.config.ts names exactly the twelve projects of the grid (English
  375/768/1280 light and dark plus high contrast at 1280, German de_DE and
  French at 375 light and 1280 dark, German "de" at 375 light).
- @playwright/test is pinned exactly, in package.json and in the lock file.
- Every surface of the screenshot grid has screenshot() calls, and every state
  of the grid that has a fixed name appears as that name in the spec of its
  surface.
- admin.spec.ts carries the six tags of the drift steps (plan 18), and the
  main Playwright step of deploy-harp.yml leaves exactly those out.
- The closed lists the specs may forge from mirror php/lib/Model value by
  value, so page.route can never show a state the server does not know.
- No fixed waits (waitForTimeout) and no test.only in the specs.

Each check is a function that returns its problems; the self tests feed it a
broken copy and expect it to complain.
"""

import json
import re
from pathlib import Path

from tests.conftest import REPO_ROOT

SUITE = REPO_ROOT / "ci" / "playwright"
MODEL = REPO_ROOT / "php" / "lib" / "Model"
DEPLOY = REPO_ROOT / ".github" / "workflows" / "deploy-harp.yml"
PLAYWRIGHT_VERSION = "1.65.0"

PROJECTS = (
    "en-w375-light",
    "en-w375-dark",
    "en-w768-light",
    "en-w768-dark",
    "en-w1280-light",
    "en-w1280-dark",
    "en-w1280-contrast",
    "de-w375-light",
    "de-w1280-dark",
    "fr-w375-light",
    "fr-w1280-dark",
    "de-du-w375-light",
)

# The screenshot grid of the UI-SPEC: surface -> spec file and the states with
# a fixed name. States built from a list (ready per format, failure per
# reason) are covered by the list checks below.
GRID: dict[str, tuple[str, tuple[str, ...]]] = {
    "dateien": (
        "fileaction.spec.ts",
        (
            "menue-pdf",
            "menue-download-gesperrt",
            "toast-als-naechstes",
            "toast-n-davor",
            "toast-laeuft-schon",
            "toast-backend-nicht-bereit",
            "toast-download-gesperrt",
            "toast-nicht-verfuegbar",
            "toast-format",
            "toast-allgemein",
            "kopie-in-liste",
        ),
    ),
    "pruefseite": (
        "review.spec.ts",
        (
            "warteschlange-als-naechstes",
            "warteschlange-n-davor",
            "warteschlange-backend-nicht-bereit",
            "lauf-waiting",
            "lauf-fetching",
            "lauf-converting",
            "lauf-rendering",
            "seite-nicht-abrufbar",
            "kopie-wird-angelegt",
            "kopie-angelegt",
            "original-geaendert",
            "original-geloescht",
            "download-gesperrt",
            "abgelaufen",
            "nicht-verfuegbar-fremd",
            "nicht-verfuegbar-acl",
            "nicht-verfuegbar-freigabe-entzogen",
            "stand-nicht-aktualisiert",
            "sitzung-abgelaufen",
            "bereit-backend-nicht-bereit",
        ),
    ),
    "benachrichtigung": ("notification.spec.ts", ("popover",)),
    "kopie": ("review.spec.ts", ("erste-seite",)),
    "admin": (
        "admin.spec.ts",
        (
            "ok",
            "pruefung-laeuft",
            "neupruefung-gescheitert",
            "version_patch_differs",
            "version_drift",
        ),
    ),
}

# Lists inside the specs that expand into states of the grid.
EXPANDED: dict[str, tuple[str, ...]] = {
    "review.spec.ts": (
        "render_failed",
        "out_of_memory",
        "repeatedly_stuck",
        "backend_state_lost",
        "target_not_writable",
        "'pdf'",
        "'docx'",
        "'odt'",
    ),
    "admin.spec.ts": ("backend_missing", "backend_disabled", "backend_unreachable", "no_app_api"),
    "notification.spec.ts": ("review_ready", "job_failed", "job_stale", "copy_created"),
}

DRIFT_TAGS = ("@patch", "@drift", "@missing", "@disabled", "@unreachable", "@noappapi")


def read(name: str) -> str:
    return (SUITE / name).read_text(encoding="utf-8")


def specs() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(SUITE.glob("*.spec.ts"))}


# -- checks ----------------------------------------------------------------------


def project_problems(config: str) -> list[str]:
    names = re.findall(r"\bname: '([^']+)'", config)
    problems = [f"project {name} is missing" for name in PROJECTS if name not in names]
    problems += [f"project {name} is not in the grid" for name in names if name not in PROJECTS]
    if len(names) != len(PROJECTS):
        problems.append(f"{len(names)} projects instead of {len(PROJECTS)}")
    if not re.search(r"\bworkers: 1\b", config):
        problems.append("more than one worker")
    return problems


def pin_problems(package: str, lock: str) -> list[str]:
    problems = []
    wanted = json.loads(package).get("devDependencies", {}).get("@playwright/test")
    if wanted != PLAYWRIGHT_VERSION:
        problems.append(f"@playwright/test is {wanted!r}, not exactly {PLAYWRIGHT_VERSION}")
    locked = json.loads(lock).get("packages", {}).get("node_modules/@playwright/test", {}).get("version")
    if locked != PLAYWRIGHT_VERSION:
        problems.append(f"the lock file holds @playwright/test {locked!r}")
    return problems


def grid_problems(texts: dict[str, str]) -> list[str]:
    problems = []
    for surface, (spec, states) in GRID.items():
        text = texts.get(spec, "")
        if not re.search(rf"screenshot\(page, '{surface}',", text):
            problems.append(f"surface {surface} has no screenshot() in {spec}")
        problems += [f"state {surface}/{state} is missing in {spec}" for state in states if f"'{state}'" not in text]
    for spec, needles in EXPANDED.items():
        text = texts.get(spec, "")
        problems += [f"{needle} is missing in {spec}" for needle in needles if needle not in text]
    return problems


def tag_problems(admin: str, workflow: str) -> list[str]:
    titles = re.findall(r"^test\('([^']*)'|tag: '(@\w+)'", admin, re.MULTILINE)
    seen = {tag for title in titles for part in title for tag in re.findall(r"@\w+", part)}
    problems = [f"tag {tag} is not on any test of admin.spec.ts" for tag in DRIFT_TAGS if tag not in seen]
    invert = re.search(r'npx playwright test --grep-invert "([^"]*)"', workflow)
    if invert is None:
        problems.append("deploy-harp.yml has no main Playwright step with --grep-invert")
    elif set(invert.group(1).split("|")) != set(DRIFT_TAGS):
        problems.append(f"the main step leaves out {invert.group(1)}, not the drift tags")
    return problems


def php_cases(name: str) -> list[str]:
    return re.findall(r"^\s*case \w+ = '([a-z_]+)';", (MODEL / name).read_text(encoding="utf-8"), re.MULTILINE)


def ts_list(helpers: str, name: str) -> list[str]:
    match = re.search(rf"export const {name} = \[(.*?)\] as const;", helpers, re.DOTALL)
    return re.findall(r"'([a-z_]+)'", match.group(1)) if match else []


def closed_list_problems(helpers: str) -> list[str]:
    problems = []
    for ts_name, php_file in (("STATUSES", "Status.php"), ("STAGES", "Stage.php"), ("REASONS", "Reason.php")):
        if ts_list(helpers, ts_name) != php_cases(php_file):
            problems.append(f"{ts_name} in helpers.ts differs from php/lib/Model/{php_file}")
    return problems


def hygiene_problems(texts: dict[str, str]) -> list[str]:
    problems = []
    for name, text in texts.items():
        if "waitForTimeout" in text:
            problems.append(f"{name} waits a fixed time")
        if re.search(r"\b(test|describe)\.only\(", text):
            problems.append(f"{name} narrows the run with .only")
    return problems


# -- the suite as it is -----------------------------------------------------------------


def test_the_config_names_the_twelve_projects() -> None:
    assert project_problems(read("playwright.config.ts")) == []


def test_playwright_is_pinned_exactly() -> None:
    assert pin_problems(read("package.json"), read("package-lock.json")) == []


def test_every_surface_and_state_of_the_grid_has_a_picture() -> None:
    assert grid_problems(specs()) == []


def test_the_drift_tags_are_there_and_left_out_of_the_main_run() -> None:
    assert tag_problems(read("admin.spec.ts"), DEPLOY.read_text(encoding="utf-8")) == []


def test_the_forged_values_come_from_the_closed_lists_of_the_server() -> None:
    assert closed_list_problems(read("helpers.ts")) == []
    # Positive control: the PHP enums were read at all.
    assert "review" in php_cases("Status.php")
    assert "render_failed" in php_cases("Reason.php")


def test_no_fixed_waits_and_no_only() -> None:
    assert hygiene_problems({**specs(), "helpers.ts": read("helpers.ts")}) == []


def test_every_spec_writes_pictures_through_the_one_helper() -> None:
    for name, text in specs().items():
        assert "page.screenshot(" not in text, name
    assert "__${surface}__${state}.png" in read("helpers.ts")


# -- self tests: each check complains about a broken copy -----------------------------


def test_self_project_check_finds_a_removed_project() -> None:
    config = read("playwright.config.ts")
    broken = re.sub(r"^.*name: 'fr-w1280-dark'.*\n", "", config, flags=re.MULTILINE)
    assert broken != config
    problems = project_problems(broken)
    assert "project fr-w1280-dark is missing" in problems
    assert "11 projects instead of 12" in problems


def test_self_project_check_finds_a_second_worker() -> None:
    assert "more than one worker" in project_problems(read("playwright.config.ts").replace("workers: 1", "workers: 2"))


def test_self_pin_check_finds_a_range() -> None:
    package = read("package.json").replace(
        f'"@playwright/test": "{PLAYWRIGHT_VERSION}"', f'"@playwright/test": "^{PLAYWRIGHT_VERSION}"'
    )
    assert pin_problems(package, read("package-lock.json")) != []


def test_self_grid_check_finds_a_missing_surface_and_state() -> None:
    texts = specs()
    texts["notification.spec.ts"] = texts["notification.spec.ts"].replace(
        "screenshot(page, 'benachrichtigung',", "noShot(page, 'x',"
    )
    texts["review.spec.ts"] = texts["review.spec.ts"].replace("'nicht-verfuegbar-acl'", "'x'")
    problems = grid_problems(texts)
    assert "surface benachrichtigung has no screenshot() in notification.spec.ts" in problems
    assert "state pruefseite/nicht-verfuegbar-acl is missing in review.spec.ts" in problems


def test_self_tag_check_finds_a_missing_tag_and_a_wrong_invert() -> None:
    admin = read("admin.spec.ts").replace("tag: '@noappapi'", "tag: ''")
    workflow = DEPLOY.read_text(encoding="utf-8").replace('|@noappapi"', '"')
    problems = tag_problems(admin, workflow)
    assert "tag @noappapi is not on any test of admin.spec.ts" in problems
    assert any(problem.startswith("the main step leaves out") for problem in problems)


def test_self_closed_list_check_finds_an_extra_value() -> None:
    helpers = read("helpers.ts").replace("\t'expired',\n] as const;", "\t'expired',\n\t'invented',\n] as const;")
    assert closed_list_problems(helpers) == ["STATUSES in helpers.ts differs from php/lib/Model/Status.php"]


def test_self_hygiene_check_finds_a_fixed_wait_and_only() -> None:
    problems = hygiene_problems({"x.spec.ts": "await page.waitForTimeout(500);\ntest.only('a', () => {});"})
    assert problems == ["x.spec.ts waits a fixed time", "x.spec.ts narrows the run with .only"]


def test_self_specs_are_found() -> None:
    assert set(specs()) == {"admin.spec.ts", "fileaction.spec.ts", "notification.spec.ts", "review.spec.ts"}
    assert Path(SUITE / "helpers.ts").is_file()
