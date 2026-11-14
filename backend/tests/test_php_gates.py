"""Static gates over the PHP app, the local stand-in for a PHP toolchain.

The development machine has no PHP, so ``php -l`` and phpunit run in CI only
(``.github/workflows/php.yml``). What can be decided by reading the sources is
decided here, on every local test run. Taken over from Audio & Video Search
(rules 1 to 11) and extended by the rules of PII Redaction (12 to 21):

1. Every method carrying ``ExAppRequired`` opens with
   ``$foreign = $this->rejectForeignCaller();``.
2. No ``PublicPage`` anywhere in ``php/lib``.
3. ``exAppRequest(`` appears exactly once, in ``php/lib/Service/ExAppService.php``.
4. ``->getById(`` and ``->getFirstNodeById(`` appear in ``FileAccess.php`` only.
5. No ``error_log``, ``var_dump`` or ``print_r`` in ``php/lib``.
6. A logger call never carries ``getPath()``, ``getName()`` or ``$path``.
7. Every ``.php`` file starts with ``<?php`` and ``declare(strict_types=1);``.
8. No U+2013 or U+2014 anywhere under ``php/``.
9. ``php/composer.json`` is valid JSON and maps both app namespaces.
10. No helper in ``php/tests`` is named like a final method of PHPUnit's TestCase.
11. Every ``[hidden]`` rule under ``php/css`` hangs off ``#pii-admin`` or ``#pii-review``.
12. Recheck: every ``FrontpageRoute`` method of ``JobController.php`` and
    ``ReviewController.php`` and every ``ApiRoute`` method of
    ``GatewayController.php`` calls something starting with ``recheck``.
13. No migration column name contains ``name``, ``path``, ``mime``, ``text``,
    ``value``, ``snippet``, ``title``, ``comment`` or ``content``.
14. A logger call opens with a literal starting ``PII Redaction: `` and its
    context keys come from ``jobId, fileId, status, reason, app, exception, class``.
15. No ``getMessage()`` in ``php/lib``.
16. No ``#[\\Override]`` under ``php/`` (PHP 8.2 floor).
17. ``php/lib/Notification`` never calls ``getName(``, ``getPath(`` or ``getInternalPath(``.
18. ``newFile(`` appears in ``php/lib/Service/PublishService.php`` only.
19. No ``shareapi_allow_view_without_download`` and no ``ViewOnly`` in
    ``php/lib``: the download block fails closed and knows no exception.
20. No ``time()`` call in ``php/lib/Db`` and ``php/lib/Service``: the only
    clock is ``ITimeFactory``.
21. An idle claim reads only: ``JobMapper::claimNext`` calls no write before
    its read-only ``nextCandidate(`` check (``claimPurge`` writes only after
    its own read), and ``QueueController::claim`` writes nothing itself.

The gates judge the files that exist (later plans add controllers and
services); plan 17 adds the check that every file of phase 1 is present. Each
rule has a self test with a mutated sample that makes it fire and one that
passes.
"""

import json
import re
from pathlib import Path

from tests.conftest import REPO_ROOT

PHP_ROOT = REPO_ROOT / "php"
LIB = PHP_ROOT / "lib"
# php/js/ is the build output of php/src (git ignored); the sources are judged.
SKIPPED_DIRECTORIES = {"vendor", "node_modules", ".phpunit.cache", "js"}

GUARD_STATEMENT = "$foreign = $this->rejectForeignCaller();"
EXAPP_ATTRIBUTE = "ExAppRequired"
FORBIDDEN_ATTRIBUTE = "PublicPage"
PROXY_CALL = "exAppRequest("
PROXY_HOME = "php/lib/Service/ExAppService.php"
LOOKUP_CALLS = ("->getById(", "->getFirstNodeById(")
LOOKUP_HOME = "FileAccess.php"
DEBUG_OUTPUT = ("error_log", "var_dump", "print_r")
LEAKING_LOG_ARGUMENTS = re.compile(r"getPath\(\)|getName\(\)|\$path\b")
DASHES = ("\u2013", "\u2014")
PHP_HEADER = re.compile(r"\A<\?php\r?\n(?:\r?\n)*declare\(strict_types=1\);")
HIDDEN_ROOTS = ("#pii-admin", "#pii-review")
RECHECK_FILES = {
    "JobController.php": "FrontpageRoute",
    "ReviewController.php": "FrontpageRoute",
    "GatewayController.php": "ApiRoute",
}
RECHECK_CALL = re.compile(r"recheck\w*\(")
FORBIDDEN_COLUMN_PARTS = ("name", "path", "mime", "text", "value", "snippet", "title", "comment", "content")
_ADD_COLUMN = re.compile(r"addColumn\(\s*'([^']+)'")
LOG_PREFIX = "PII Redaction: "
LOG_CONTEXT_KEYS = frozenset({"jobId", "fileId", "status", "reason", "app", "exception", "class"})
OVERRIDE_ATTRIBUTE = "#[\\Override]"
NOTIFIER_FORBIDDEN = ("getName(", "getPath(", "getInternalPath(")
_NOTIFIER_NAME_DECLARATION = re.compile(r"\bfunction\s+getName\s*\(")
NEW_FILE_CALL = "newFile("
NEW_FILE_HOME = "php/lib/Service/PublishService.php"
DOWNLOAD_EXCEPTIONS = ("shareapi_allow_view_without_download", "ViewOnly")
_TIME_CALL = re.compile(r"(?<![\w>:$])time\(\)")

_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_HIDDEN_RULE = re.compile(r"([^{}]*\[hidden\])\s*\{")
_FUNCTION = re.compile(r"^\s*(?:public|protected|private)\s+(?:static\s+)?function\s+(\w+)\s*\(")
_LOGGER_CALL = re.compile(r"->logger->(?:debug|info|notice|warning|error|critical|alert|emergency|log)\(")
_CONTEXT_KEY = re.compile(r"""(['"])(\w+)\1\s*=>""")
_NOT_A_STATEMENT = ("//", "/*", "*", "#")


def php_files(root: Path) -> list[Path]:
    """Every .php file below root, without dependency and cache directories."""
    if not root.is_dir():
        return []
    return sorted(
        path for path in root.rglob("*.php") if not SKIPPED_DIRECTORIES.intersection(path.relative_to(root).parts)
    )


def text_files(root: Path) -> list[Path]:
    """Every file below root that reads as UTF-8 text, same exclusions."""
    found = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or SKIPPED_DIRECTORIES.intersection(path.relative_to(root).parts):
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        found.append(path)
    return found


def _sources(root: Path) -> dict[str, str]:
    return {path.relative_to(REPO_ROOT).as_posix(): path.read_text(encoding="utf-8") for path in php_files(root)}


def _lib_sources() -> dict[str, str]:
    return _sources(LIB)


# -- helpers shared by several rules ------------------------------------------------


def _attributes_above(lines: list[str], index: int) -> list[str]:
    """The attribute lines directly above a method; the docblock is the wall."""
    collected = []
    cursor = index - 1
    while cursor >= 0 and lines[cursor].strip().startswith("#["):
        collected.append(lines[cursor].strip())
        cursor -= 1
    return collected


def _first_statement(lines: list[str], index: int) -> str:
    """The first line inside the body of the method declared at index."""
    start = len(lines)
    for cursor in range(index, len(lines)):
        if lines[cursor].rstrip().endswith("{"):
            start = cursor + 1
            break
    for line in lines[start:]:
        stripped = line.strip()
        if stripped and not stripped.startswith(_NOT_A_STATEMENT):
            return stripped
    return ""


def _method_body(lines: list[str], index: int) -> str:
    """The text of the method declared at index, up to its closing brace."""
    depth = 0
    opened = False
    body = []
    for line in lines[index:]:
        body.append(line)
        depth += line.count("{") - line.count("}")
        if "{" in line:
            opened = True
        if opened and depth <= 0:
            break
    return "\n".join(body)


def _methods_with(source: str, attribute: str) -> list[tuple[str, str]]:
    """(name, body) of every method that carries the attribute."""
    lines = source.splitlines()
    return [
        (match.group(1), _method_body(lines, index))
        for index, line in enumerate(lines)
        if (match := _FUNCTION.match(line)) is not None
        and any(attribute in above for above in _attributes_above(lines, index))
    ]


def _call_arguments(source: str, open_paren: int) -> str:
    """The text between an opening parenthesis and its partner, strings respected."""
    depth = 0
    quote = ""
    index = open_paren
    while index < len(source):
        char = source[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return source[open_paren + 1 : index]
        index += 1
    return source[open_paren + 1 :]


def misplaced(sources: dict[str, str], needle: str, home: str) -> list[str]:
    """Files other than home (a repo path or a bare file name) that contain needle."""
    return sorted(name for name, text in sources.items() if needle in text and home not in (name, Path(name).name))


# -- rules 1 to 11 -------------------------------------------------------------------


def unguarded_exapp_methods(source: str) -> list[str]:
    """Methods with ExAppRequired whose first statement is not the guard."""
    lines = source.splitlines()
    findings = []
    for index, line in enumerate(lines):
        match = _FUNCTION.match(line)
        if match is None:
            continue
        if not any(EXAPP_ATTRIBUTE in attribute for attribute in _attributes_above(lines, index)):
            continue
        if _first_statement(lines, index) != GUARD_STATEMENT:
            findings.append(match.group(1))
    return findings


def proxy_problems(sources: dict[str, str]) -> list[str]:
    """Rule 3: one call, in ExAppService.php, nowhere else."""
    problems = misplaced(sources, PROXY_CALL, PROXY_HOME)
    home = sources.get(PROXY_HOME)
    if home is not None and home.count(PROXY_CALL) != 1:
        problems.append(f"{PROXY_HOME} calls {PROXY_CALL} {home.count(PROXY_CALL)} times")
    return problems


def debug_output_calls(source: str) -> list[str]:
    return [name for name in DEBUG_OUTPUT if re.search(rf"\b{name}\s*\(", source)]


def leaking_log_calls(source: str) -> list[str]:
    findings = []
    for match in _LOGGER_CALL.finditer(source):
        arguments = _call_arguments(source, match.end() - 1)
        if LEAKING_LOG_ARGUMENTS.search(arguments):
            findings.append(" ".join(arguments.split())[:120])
    return findings


def lacks_strict_header(source: str) -> bool:
    return PHP_HEADER.match(source) is None


def dashes_in(source: str) -> list[str]:
    return [f"U+{ord(dash):04X}" for dash in DASHES if dash in source]


COMPOSER_NAMESPACES = {"OCA\\PiiRedaction\\": "lib/"}
COMPOSER_TEST_NAMESPACES = {"OCA\\PiiRedaction\\Tests\\": "tests/"}


def composer_namespaces(text: str) -> tuple[dict[str, str], dict[str, str]]:
    data = json.loads(text)
    return data["autoload"]["psr-4"], data["autoload-dev"]["psr-4"]


# Final methods of PHPUnit\Framework\TestCase (11.5): a helper with one of these
# names is a fatal error the moment phpunit loads the class.
FINAL_TESTCASE_METHODS = frozenset(
    {
        "count",
        "dataName",
        "dataSetAsString",
        "groups",
        "name",
        "nameWithDataSet",
        "numberOfAssertionsPerformed",
        "providedData",
        "result",
        "run",
        "size",
        "status",
        "usesDataProvider",
        "valueObjectForEvents",
    }
)


def helpers_shadowing_final_methods(source: str) -> list[str]:
    return [
        match.group(1)
        for line in source.splitlines()
        if (match := _FUNCTION.match(line)) and match.group(1) in FINAL_TESTCASE_METHODS
    ]


def weak_hidden_rules(source: str) -> list[str]:
    rules = _CSS_COMMENT.sub("", source)
    return [
        selector.strip()
        for selector in _HIDDEN_RULE.findall(rules)
        if not any(root in selector for root in HIDDEN_ROOTS)
    ]


# -- rules 12 to 21 ------------------------------------------------------------------


def routes_without_recheck(source: str, attribute: str) -> list[str]:
    """Rule 12: route methods whose body never calls recheck*()."""
    return [name for name, body in _methods_with(source, attribute) if RECHECK_CALL.search(body) is None]


def forbidden_columns(source: str) -> list[str]:
    """Rule 13: column names of a migration that could carry clear text."""
    return [
        column
        for column in _ADD_COLUMN.findall(source)
        if any(part in column.lower() for part in FORBIDDEN_COLUMN_PARTS)
    ]


def log_contract_problems(source: str) -> list[str]:
    """Rule 14: message prefix and context keys of every logger call."""
    problems = []
    for match in _LOGGER_CALL.finditer(source):
        arguments = _call_arguments(source, match.end() - 1).strip()
        literal = re.match(r"""(['"])(.*?)(?<!\\)\1""", arguments, re.DOTALL)
        if literal is None or not literal.group(2).startswith(LOG_PREFIX):
            problems.append("message is not a literal with the prefix")
            continue
        rest = arguments[literal.end() :]
        problems += [f"context key {key}" for _, key in _CONTEXT_KEY.findall(rest) if key not in LOG_CONTEXT_KEYS]
    return problems


def message_calls(source: str) -> int:
    """Rule 15."""
    return source.count("getMessage()")


def notifier_leaks(source: str) -> list[str]:
    """Rule 17."""
    # INotifier itself demands a method getName() (the app name); declaring it
    # reads nothing, so only the declaration is taken out before the search.
    source = _NOTIFIER_NAME_DECLARATION.sub("", source)
    return [needle for needle in NOTIFIER_FORBIDDEN if needle in source]


def download_exceptions(source: str) -> list[str]:
    """Rule 19."""
    return [needle for needle in DOWNLOAD_EXCEPTIONS if needle in source]


def time_calls(source: str) -> int:
    """Rule 20: a bare time() call (getTime() and $this->time() do not count)."""
    return len(_TIME_CALL.findall(source))


# Rule 21: an idle claim reads only. Before the read-only candidate check in
# JobMapper::claimNext only claimPurge may run (it writes after its own read
# found a purge job); the claim route leaves the slot row to claimNext.
CANDIDATE_CHECK = "nextCandidate("
IDLE_WRITE_CALLS = (
    "ensureSlot(",
    "takeSlot(",
    "freeSlot(",
    "claimJob(",
    "giveUp(",
    "->update(",
    "->insert(",
    "->delete(",
    "executeStatement(",
)


def _method_named(source: str, name: str) -> str:
    lines = source.splitlines()
    for index, line in enumerate(lines):
        match = _FUNCTION.match(line)
        if match is not None and match.group(1) == name:
            return _method_body(lines, index)
    return ""


def idle_claim_writes(mapper: str, controller: str) -> list[str]:
    """Rule 21: write calls an idle claim reaches before any candidate was found."""
    found = []
    claim_next = _method_named(mapper, "claimNext")
    if not claim_next:
        return ["JobMapper::claimNext missing"]
    check = claim_next.find(CANDIDATE_CHECK)
    if check < 0:
        found.append("claimNext has no candidate check")
        check = len(claim_next)
    found.extend(f"claimNext: {call}" for call in IDLE_WRITE_CALLS if -1 < claim_next.find(call) < check)
    route = _method_named(controller, "claim")
    found.extend(f"QueueController::claim: {call}" for call in IDLE_WRITE_CALLS if call in route)
    return found


# -- the real tree -------------------------------------------------------------------


def test_the_tree_is_not_empty() -> None:
    """Anti vacuum: the gates below need PHP sources to judge."""
    assert (LIB / "AppInfo" / "Application.php").is_file()
    assert php_files(LIB / "Migration"), "no migration to judge"


# Every PHP file of phase 1 (01-SKELETON.md): controllers, services, mappers,
# notifier, background job, listeners, migration, models and settings. A gate
# over a file that is gone would pass on nothing (plan 17).
PHASE1_FILES = (
    "AppInfo/Application.php",
    "BackgroundJob/PublishJob.php",
    "Controller/GatewayController.php",
    "Controller/HandshakeController.php",
    "Controller/JobController.php",
    "Controller/QueueController.php",
    "Controller/ReviewController.php",
    "Controller/SettingsController.php",
    "Db/Job.php",
    "Db/JobEvent.php",
    "Db/JobEventMapper.php",
    "Db/JobMapper.php",
    "Listener/FileLifecycleListener.php",
    "Listener/LoadFilesScriptsListener.php",
    "Migration/Version000100Date20261107000000.php",
    "Model/Lang.php",
    "Model/Mode.php",
    "Model/Reason.php",
    "Model/Recheck.php",
    "Model/Stage.php",
    "Model/Status.php",
    "Model/Subject.php",
    "Model/Task.php",
    "Notification/Notifier.php",
    "Service/ExAppService.php",
    "Service/FileAccess.php",
    "Service/JobService.php",
    "Service/NotificationSender.php",
    "Service/PublishService.php",
    "Service/ReaderContext.php",
    "Service/Suffix.php",
    "Settings/Admin.php",
    "Settings/Section.php",
)


def missing_phase1_files(lib: Path) -> list[str]:
    """The files of PHASE1_FILES that are not under ``lib``."""
    return [name for name in PHASE1_FILES if not (lib / name).is_file()]


def tree_problems(lib: Path) -> list[str]:
    """Anti vacuum: every phase 1 file is there and the rules have their subjects."""
    problems = [f"{name} is missing" for name in missing_phase1_files(lib)]
    for name, attribute in RECHECK_FILES.items():
        path = lib / "Controller" / name
        if path.is_file() and not _methods_with(path.read_text(encoding="utf-8"), attribute):
            problems.append(f"{name} has no {attribute} method for rule 12 to judge")
    publish = lib / "Service" / "PublishService.php"
    if publish.is_file() and NEW_FILE_CALL not in publish.read_text(encoding="utf-8"):
        problems.append("PublishService.php has no newFile( for rule 18 to judge")
    proxy = lib / "Service" / "ExAppService.php"
    if proxy.is_file() and proxy.read_text(encoding="utf-8").count(PROXY_CALL) != 1:
        problems.append("ExAppService.php does not call exAppRequest( exactly once")
    return problems


def test_the_tree_carries_the_files_the_gates_are_about() -> None:
    """Anti vacuum: rules 12 and 18 and the rest must have something to judge."""
    assert tree_problems(LIB) == []


def test_self_the_tree_rule_fires_on_a_missing_file(tmp_path: Path) -> None:
    for name in PHASE1_FILES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((LIB / name).read_text(encoding="utf-8"), encoding="utf-8")
    assert tree_problems(tmp_path) == []
    (tmp_path / "Controller" / "QueueController.php").unlink()
    assert tree_problems(tmp_path) == ["Controller/QueueController.php is missing"]
    publish = tmp_path / "Service" / "PublishService.php"
    publish.write_text(publish.read_text(encoding="utf-8").replace(NEW_FILE_CALL, "newFolder("), encoding="utf-8")
    assert "PublishService.php has no newFile( for rule 18 to judge" in tree_problems(tmp_path)
    review = tmp_path / "Controller" / "ReviewController.php"
    review.write_text(review.read_text(encoding="utf-8").replace("FrontpageRoute", "Route"), encoding="utf-8")
    assert "ReviewController.php has no FrontpageRoute method for rule 12 to judge" in tree_problems(tmp_path)


def test_rule1_every_exapp_route_opens_with_the_foreign_caller_guard() -> None:
    findings = {name: unguarded_exapp_methods(text) for name, text in _lib_sources().items()}
    assert {name: methods for name, methods in findings.items() if methods} == {}


def test_rule2_no_public_page_in_lib() -> None:
    assert [name for name, text in _lib_sources().items() if FORBIDDEN_ATTRIBUTE in text] == []


def test_rule3_the_container_is_called_from_exapp_service_only() -> None:
    assert proxy_problems(_lib_sources()) == []


def test_rule4_the_node_lookup_lives_in_file_access_only() -> None:
    sources = _lib_sources()
    assert [name for needle in LOOKUP_CALLS for name in misplaced(sources, needle, LOOKUP_HOME)] == []


def test_rule5_no_debug_output_in_lib() -> None:
    findings = {name: debug_output_calls(text) for name, text in _lib_sources().items()}
    assert {name: calls for name, calls in findings.items() if calls} == {}


def test_rule6_no_path_or_file_name_in_a_log_call() -> None:
    findings = {name: leaking_log_calls(text) for name, text in _lib_sources().items()}
    assert {name: calls for name, calls in findings.items() if calls} == {}


def test_rule7_every_php_file_is_strict() -> None:
    files = php_files(PHP_ROOT)
    assert files, "no PHP file found"
    assert [
        path.relative_to(REPO_ROOT).as_posix()
        for path in files
        if lacks_strict_header(path.read_text(encoding="utf-8"))
    ] == []


def test_rule8_no_dash_characters_under_php() -> None:
    findings = {
        path.relative_to(REPO_ROOT).as_posix(): dashes_in(path.read_text(encoding="utf-8"))
        for path in text_files(PHP_ROOT)
    }
    assert {name: found for name, found in findings.items() if found} == {}


def test_rule9_composer_json_parses_and_maps_the_app_namespaces() -> None:
    autoload, autoload_dev = composer_namespaces((PHP_ROOT / "composer.json").read_text(encoding="utf-8"))
    assert autoload == COMPOSER_NAMESPACES
    assert autoload_dev == COMPOSER_TEST_NAMESPACES


def test_rule10_no_test_helper_shadows_a_final_testcase_method() -> None:
    findings = {
        name: found
        for name, text in _sources(PHP_ROOT / "tests").items()
        if (found := helpers_shadowing_final_methods(text))
    }
    assert findings == {}


def test_rule11_every_hidden_rule_hangs_off_an_app_root_id() -> None:
    sheets = sorted((PHP_ROOT / "css").glob("*.css")) if (PHP_ROOT / "css").is_dir() else []
    findings = {path.name: found for path in sheets if (found := weak_hidden_rules(path.read_text(encoding="utf-8")))}
    assert findings == {}


def test_rule12_every_route_rechecks() -> None:
    findings = {}
    for name, text in _lib_sources().items():
        attribute = RECHECK_FILES.get(Path(name).name)
        if attribute and "/Controller/" in name and (missing := routes_without_recheck(text, attribute)):
            findings[name] = missing
    assert findings == {}


def test_rule13_no_migration_column_could_carry_clear_text() -> None:
    findings = {name: found for name, text in _sources(LIB / "Migration").items() if (found := forbidden_columns(text))}
    assert findings == {}


def test_rule14_log_calls_carry_the_prefix_and_allowed_context_only() -> None:
    findings = {name: found for name, text in _lib_sources().items() if (found := log_contract_problems(text))}
    assert findings == {}


def test_rule15_no_get_message_in_lib() -> None:
    assert [name for name, text in _lib_sources().items() if message_calls(text)] == []


def test_rule16_no_override_attribute_under_php() -> None:
    assert [name for name, text in _sources(PHP_ROOT).items() if OVERRIDE_ATTRIBUTE in text] == []


def test_rule17_the_notifier_never_reads_a_name_or_a_path() -> None:
    findings = {name: found for name, text in _sources(LIB / "Notification").items() if (found := notifier_leaks(text))}
    assert findings == {}


def test_rule18_new_file_lives_in_publish_service_only() -> None:
    assert misplaced(_lib_sources(), NEW_FILE_CALL, NEW_FILE_HOME) == []


def test_rule19_no_download_exception_in_lib() -> None:
    findings = {name: found for name, text in _lib_sources().items() if (found := download_exceptions(text))}
    assert findings == {}


def test_rule20_no_bare_time_call_in_db_and_service() -> None:
    sources = {**_sources(LIB / "Db"), **_sources(LIB / "Service")}
    assert sources, "no Db or Service source to judge"
    assert [name for name, text in sources.items() if time_calls(text)] == []


def test_rule21_an_idle_claim_reads_only() -> None:
    mapper = (LIB / "Db" / "JobMapper.php").read_text(encoding="utf-8")
    controller = (LIB / "Controller" / "QueueController.php").read_text(encoding="utf-8")
    assert idle_claim_writes(mapper, controller) == []


# -- the self tests: every rule has to fire on a staged violation --------------------

GUARDED_ROUTE = """
	#[\\OCP\\AppFramework\\Http\\Attribute\\ExAppRequired]
	#[\\OCP\\AppFramework\\Http\\Attribute\\NoCSRFRequired]
	public function get(int $jobId): DataResponse {
		// a comment first is fine
		$foreign = $this->rejectForeignCaller();
		if ($foreign !== null) {
			return $foreign;
		}
		return new DataResponse([]);
	}
"""


def test_self_rule1_fires_on_a_route_without_the_guard() -> None:
    assert unguarded_exapp_methods(GUARDED_ROUTE) == []
    late = GUARDED_ROUTE.replace("// a comment first is fine", "$this->logger->info('PII Redaction: before');")
    assert unguarded_exapp_methods(late) == ["get"]
    assert unguarded_exapp_methods(GUARDED_ROUTE.replace(GUARD_STATEMENT, "$x = 1;")) == ["get"]
    plain = GUARDED_ROUTE.replace("#[\\OCP\\AppFramework\\Http\\Attribute\\ExAppRequired]\n", "")
    assert unguarded_exapp_methods(plain.replace(GUARD_STATEMENT, "$x = 1;")) == []


def test_self_rule2_fires_on_a_public_page_attribute() -> None:
    assert FORBIDDEN_ATTRIBUTE in "#[PublicPage]\npublic function x(): void {}"
    assert FORBIDDEN_ATTRIBUTE not in "#[NoAdminRequired]\npublic function x(): void {}"


def test_self_rule3_fires_on_a_second_caller_and_on_a_second_call() -> None:
    good = {PROXY_HOME: "$api->exAppRequest($id);"}
    assert proxy_problems(good) == []
    assert proxy_problems({**good, "php/lib/Service/Other.php": "$api->exAppRequest($id);"}) == [
        "php/lib/Service/Other.php"
    ]
    assert proxy_problems({PROXY_HOME: "$a->exAppRequest(1); $a->exAppRequest(2);"}) == [
        f"{PROXY_HOME} calls {PROXY_CALL} 2 times"
    ]


def test_self_rule4_fires_on_a_lookup_outside_file_access() -> None:
    sources = {
        "php/lib/Service/FileAccess.php": "$folder->getFirstNodeById($id); $root->getById($id);",
        "php/lib/Service/JobService.php": "$root->getById($id);",
    }
    assert [name for needle in LOOKUP_CALLS for name in misplaced(sources, needle, LOOKUP_HOME)] == [
        "php/lib/Service/JobService.php"
    ]


def test_self_rule5_fires_on_each_debug_printer() -> None:
    for name in DEBUG_OUTPUT:
        assert debug_output_calls(f"{name}($value);") == [name]
    assert debug_output_calls("$this->logger->debug('PII Redaction: fine');") == []


def test_self_rule6_fires_on_a_path_or_a_name_in_a_log_call() -> None:
    for source in (
        "$this->logger->warning('x', ['file' => $file->getPath()]);",
        "$this->logger->info('x', [\n\t'n' => $node->getName(),\n]);",
        "$this->logger->error('x', ['p' => $path]);",
    ):
        assert len(leaking_log_calls(source)) == 1, source
    assert leaking_log_calls("$this->logger->warning('x (y)', ['fileId' => $fileId]); $path = 1;") == []


def test_self_rule7_fires_on_a_missing_or_late_strict_declaration() -> None:
    assert not lacks_strict_header("<?php\n\ndeclare(strict_types=1);\n\nnamespace X;\n")
    assert lacks_strict_header("<?php\n\nnamespace X;\n")
    assert lacks_strict_header("<?php\nnamespace X;\ndeclare(strict_types=1);\n")


def test_self_rule8_fires_on_both_dashes() -> None:
    assert dashes_in("a \u2013 b \u2014 c") == ["U+2013", "U+2014"]
    assert dashes_in("a - b \u00b7 c \u2026") == []


def test_self_rule9_fires_on_a_lost_backslash() -> None:
    broken = r'{"autoload": {"psr-4": {"OCA\PiiRedaction\\": "lib/"}}, "autoload-dev": {"psr-4": {}}}'
    try:
        composer_namespaces(broken)
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("a single backslash before a letter has to be rejected")


def test_self_rule10_fires_on_a_helper_named_status() -> None:
    assert helpers_shadowing_final_methods("\tprivate function status(array $v): int {") == ["status"]
    assert helpers_shadowing_final_methods("\tprivate function statusOf(array $v): int {") == []


def test_self_rule11_fires_on_a_hidden_rule_without_the_root_id() -> None:
    assert weak_hidden_rules(".pii-admin [hidden] {\n\tdisplay: none;\n}") == [".pii-admin [hidden]"]
    assert weak_hidden_rules("#other [hidden] {\n\tdisplay: none;\n}") == ["#other [hidden]"]
    assert weak_hidden_rules("#pii-review [hidden] {\n\tdisplay: none;\n}") == []


RECHECKED_ROUTE = """
	#[NoAdminRequired]
	#[FrontpageRoute(verb: 'GET', url: '/review/{jobId}')]
	public function show(int $jobId): TemplateResponse {
		$check = $this->access->recheck($job, $uid);
		return $this->render($check);
	}

	private function render(Recheck $check): TemplateResponse {
		return new TemplateResponse('pii_redaction', 'review');
	}
"""


def test_self_rule12_fires_on_a_route_without_recheck() -> None:
    assert routes_without_recheck(RECHECKED_ROUTE, "FrontpageRoute") == []
    assert routes_without_recheck(RECHECKED_ROUTE.replace("recheck(", "lookup("), "FrontpageRoute") == ["show"]
    assert routes_without_recheck(RECHECKED_ROUTE.replace("recheck(", "recheckForStart("), "FrontpageRoute") == []
    # The body ends at the method's own brace: a recheck in the next method does not count.
    moved = RECHECKED_ROUTE.replace("$this->access->recheck($job, $uid);", "1;").replace(
        "return new TemplateResponse", "$this->access->recheck($j, $u); return new TemplateResponse"
    )
    assert routes_without_recheck(moved, "FrontpageRoute") == ["show"]


def test_self_rule13_fires_on_a_name_column() -> None:
    assert forbidden_columns("$t->addColumn('file_etag', Types::STRING);") == []
    assert forbidden_columns("$t->addColumn('file_name', Types::STRING);") == ["file_name"]
    assert forbidden_columns("$t->addColumn('Snippet_X', Types::TEXT);") == ["Snippet_X"]


def test_self_rule14_fires_on_a_missing_prefix_and_a_foreign_key() -> None:
    good = "$this->logger->warning('PII Redaction: job failed', ['jobId' => $id, 'exception' => $e]);"
    assert log_contract_problems(good) == []
    assert log_contract_problems(good.replace("PII Redaction: ", "")) == ["message is not a literal with the prefix"]
    assert log_contract_problems(good.replace("'jobId'", "'file'")) == ["context key file"]
    assert log_contract_problems("$this->logger->error($message);") == ["message is not a literal with the prefix"]


def test_self_rule15_fires_on_get_message() -> None:
    assert message_calls("$x = $e->getMessage();") == 1
    assert message_calls("$x = $e::class;") == 0


def test_self_rule16_fires_on_the_override_attribute() -> None:
    assert OVERRIDE_ATTRIBUTE in "\t#[\\Override]\n\tpublic function prepare() {}"
    assert OVERRIDE_ATTRIBUTE not in "\t/** @inheritDoc */\n\tpublic function prepare() {}"


def test_self_rule17_fires_on_a_name_in_the_notifier() -> None:
    assert notifier_leaks("$subject = $node->getName();") == ["getName("]
    assert notifier_leaks("$n->getInternalPath();") == ["getInternalPath("]
    assert notifier_leaks("$n->setParsedSubject($l->t('A review is ready'));") == []
    # The interface method may be declared, but nothing may call a getName().
    assert notifier_leaks("public function getName(): string { return 'PII Redaction'; }") == []
    assert notifier_leaks("public function getName(): string { return $file->getName(); }") == ["getName("]


def test_self_rule18_fires_on_new_file_outside_publish_service() -> None:
    sources = {NEW_FILE_HOME: "$folder->newFile($n, $s);", "php/lib/Service/JobService.php": "$f->newFile($n);"}
    assert misplaced(sources, NEW_FILE_CALL, NEW_FILE_HOME) == ["php/lib/Service/JobService.php"]
    assert misplaced({NEW_FILE_HOME: "$folder->newFile($n, $s);"}, NEW_FILE_CALL, NEW_FILE_HOME) == []


def test_self_rule19_fires_on_a_download_exception() -> None:
    assert download_exceptions("$c->getValueBool('core', 'shareapi_allow_view_without_download')") == [
        "shareapi_allow_view_without_download"
    ]
    assert download_exceptions("use OCA\\Files_Sharing\\ViewOnly;") == ["ViewOnly"]
    assert download_exceptions("$attributes->getAttribute('permissions', 'download')") == []


def test_self_rule20_fires_on_a_bare_time_call() -> None:
    assert time_calls("$now = time();") == 1
    assert time_calls("$now = \\time();") == 1
    assert time_calls("$now = $this->time->getTime(); $x = microtime(true);") == 0


READ_FIRST_CLAIM = """
	public function claimNext(): ?array {
		$now = $this->time->getTime();
		$purge = $this->claimPurge($now, $token);
		if ($purge !== null) {
			return $purge;
		}
		if ($this->nextCandidate($now) === null) {
			return null;
		}
		$this->ensureSlot();
		if (!$this->takeSlot($now, $token)) {
			return null;
		}
		$this->freeSlot($token);
		return null;
	}
"""
QUIET_ROUTE = """
	public function claim(): DataResponse {
		$claim = $this->jobs->claimNext();
		return new DataResponse([]);
	}
"""


def test_self_rule21_fires_on_a_write_before_the_candidate_check() -> None:
    assert idle_claim_writes(READ_FIRST_CLAIM, QUIET_ROUTE) == []
    slot_first = READ_FIRST_CLAIM.replace(
        "\t\tif ($this->nextCandidate($now) === null) {\n\t\t\treturn null;\n\t\t}\n\t\t$this->ensureSlot();",
        "\t\t$this->ensureSlot();\n\t\tif ($this->nextCandidate($now) === null) {\n\t\t\treturn null;\n\t\t}",
    )
    assert slot_first != READ_FIRST_CLAIM
    assert idle_claim_writes(slot_first, QUIET_ROUTE) == ["claimNext: ensureSlot("]
    no_check = READ_FIRST_CLAIM.replace("$this->nextCandidate($now) === null", "false")
    assert idle_claim_writes(no_check, QUIET_ROUTE) == [
        "claimNext has no candidate check",
        "claimNext: ensureSlot(",
        "claimNext: takeSlot(",
        "claimNext: freeSlot(",
    ]
    slot_route = QUIET_ROUTE.replace("$claim =", "$this->jobs->ensureSlot();\n\t\t$claim =")
    assert idle_claim_writes(READ_FIRST_CLAIM, slot_route) == ["QueueController::claim: ensureSlot("]
    assert idle_claim_writes("", QUIET_ROUTE) == ["JobMapper::claimNext missing"]
