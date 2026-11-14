"""Gates over the check scripts of the integration proof (plan 17).

The scripts run only in CI against a real instance; what can be decided by
reading them is decided here, on every local test run:

1. Every ``ci/*.sh`` that ``deploy-harp.yml`` calls exists, starts with
   ``#!/usr/bin/env bash`` and carries ``set -euo pipefail``.
2. A script and the ``ci/lib.sh`` it sources redirect only to ``/dev/null`` or
   into ``ci/out/``: the target of every ``>`` and ``>>`` starts with
   ``${CI_OUT}`` or with a variable whose every assignment does.
3. ``ci/canary.sh`` runs its positive control before the first negative
   search for the canary (order in the text).
4. ``ci/queue.sh`` checks both "at most 1" for every sample and "exactly 1 at
   least once" (the positive control of the query).

Each rule has a self test with a mutated sample that makes it fire.
"""

import re

from tests.conftest import REPO_ROOT

CI = REPO_ROOT / "ci"
DEPLOY = REPO_ROOT / ".github" / "workflows" / "deploy-harp.yml"
SHEBANG = "#!/usr/bin/env bash\n"
STRICT = "set -euo pipefail"
OUT_ROOT = "${CI_OUT}"

# A hyphen belongs to a script name (ci/admin-state.sh, plan 18); without it the
# rules would not see that script at all.
_SCRIPT_CALL = re.compile(r"\bci/([a-z_-]+\.sh)\b")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_]+)\1")
# A redirection after a blank, a ";", "}" or ")" with an optional descriptor;
# "->" inside a message and ">&2" are no redirection into a file.
_REDIRECT = re.compile(r"(?:^|(?<=[\s;})]))\d?>{1,2}(?!&)\s*(\"[^\"]*\"|'[^']*'|[^\s;|&)]+)")
_ASSIGNMENT = re.compile(r"(?<![\w$-])([A-Za-z_]\w*)=(\"[^\"]*\"|'[^']*'|\S*)")
_VARIABLE_HEAD = re.compile(r"\A\"?\$\{([A-Za-z_]\w*)\}")
_FUNCTION = re.compile(r"^\s*([A-Za-z_]\w*)\s*\(\)\s*\{")


def code_lines(source: str) -> list[str]:
    """The lines a shell runs: no comment lines, no heredoc bodies (Python)."""
    lines: list[str] = []
    end: str | None = None
    for line in source.splitlines():
        if end is not None:
            if line.strip() == end:
                end = None
            continue
        if line.lstrip().startswith("#"):
            continue
        lines.append(line)
        heredoc = _HEREDOC.search(line)
        if heredoc:
            end = heredoc.group(2)
    return lines


def called_scripts(workflow: str) -> list[str]:
    """The ci/*.sh names deploy-harp.yml calls, in order, without comments."""
    lines = [line for line in workflow.splitlines() if not line.lstrip().startswith("#")]
    names: list[str] = []
    for line in lines:
        for name in _SCRIPT_CALL.findall(line):
            if name not in names:
                names.append(name)
    return names


def header_problems(source: str) -> list[str]:
    """Rule 1 for one script."""
    problems = []
    if not source.startswith(SHEBANG):
        problems.append("no #!/usr/bin/env bash in the first line")
    if not any(line.strip() == STRICT for line in code_lines(source)):
        problems.append("no set -euo pipefail")
    return problems


def out_variables(sources: list[str]) -> set[str]:
    """The variables every assignment of which points into ci/out/."""
    assignments: dict[str, list[str]] = {}
    for source in sources:
        for line in code_lines(source):
            for name, value in _ASSIGNMENT.findall(line):
                assignments.setdefault(name, []).append(value)
    found = {"CI_OUT"}
    while True:
        grown = {
            name
            for name, values in assignments.items()
            if name not in found and values and all(_points_into(value, found) for value in values)
        }
        if not grown:
            return found
        found |= grown


def _points_into(target: str, out: set[str]) -> bool:
    head = _VARIABLE_HEAD.match(target)
    return head is not None and head.group(1) in out


def _masked(line: str) -> str:
    """The line with the inside of every quoted string blanked out (same length).

    A ">" inside a string (an SQL comparison, a message) is no redirection.
    """
    masked: list[str] = []
    quote: str | None = None
    escaped = False
    for char in line:
        if escaped:
            masked.append("_")
            escaped = False
        elif char == "\\" and quote != "'":
            masked.append("_")
            escaped = True
        elif quote is None and char in "\"'":
            quote = char
            masked.append(char)
        elif char == quote:
            quote = None
            masked.append(char)
        else:
            masked.append("_" if quote is not None else char)
    return "".join(masked)


def redirect_targets(line: str) -> list[str]:
    """The targets of the redirections of one line, read from the line itself."""
    targets = []
    for found in _REDIRECT.finditer(_masked(line)):
        original = _REDIRECT.match(line, found.start())
        if original is not None:
            targets.append(original.group(1))
    return targets


def foreign_redirects(source: str, out: set[str]) -> list[str]:
    """Rule 2: redirection targets outside /dev/null and ci/out/."""
    found = []
    for line in code_lines(source):
        for target in redirect_targets(line):
            if target == "/dev/null" or _points_into(target, out):
                continue
            found.append(target)
    return found


def _searching_functions(lines: list[str]) -> set[str]:
    """Functions of the script whose body runs grep."""
    names: set[str] = set()
    current: str | None = None
    for line in lines:
        start = _FUNCTION.match(line)
        if start:
            current = start.group(1)
            continue
        if current is not None:
            if line.startswith("}"):
                current = None
            elif "grep" in line:
                names.add(current)
    return names


def canary_order_problems(source: str) -> list[str]:
    """Rule 3: every positive canary search comes before the first negative one.

    A canary search is a code line naming ``${CANARY`` with ``grep`` or with a
    call of a function of the script that greps. It is positive when it or its
    continuation line says "positive control".
    """
    lines = code_lines(source)
    searchers = _searching_functions(lines)
    positive: list[int] = []
    negative: list[int] = []
    for index, line in enumerate(lines):
        if "${CANARY" not in line:
            continue
        if "grep" not in line and not any(re.search(rf"(?:^|\s){name}\s", line) for name in searchers):
            continue
        statement = line
        if line.rstrip().endswith("\\") and index + 1 < len(lines):
            statement += lines[index + 1]
        (positive if "positive control" in statement else negative).append(index)
    problems = []
    if not positive:
        problems.append("no positive control of the canary")
    if not negative:
        problems.append("no negative search of the canary")
    if positive and negative and max(positive) > min(negative):
        problems.append("a negative search runs before the positive control")
    return problems


def queue_problems(source: str) -> list[str]:
    """Rule 4: at most one active lease per sample, exactly one at least once."""
    code = "\n".join(code_lines(source))
    problems = []
    if "lease_until" not in code:
        problems.append("the samples do not ask lease_until")
    if not re.search(r"\$\{count\}\"?\s+-le\s+1\b", code):
        problems.append("no sample is checked for at most 1")
    if not re.search(r"active 1\$", code) or not re.search(r"-ge\s+1\b", code):
        problems.append("no check that a sample saw exactly 1")
    return problems


def _read(name: str) -> str:
    return (CI / name).read_text(encoding="utf-8")


# -- the real tree -------------------------------------------------------------------


def test_deploy_harp_calls_the_six_check_scripts_of_plan_17() -> None:
    names = called_scripts(DEPLOY.read_text(encoding="utf-8"))
    for name in ("rights.sh", "stale.sh", "queue.sh", "routes.sh", "measure.sh", "canary.sh"):
        assert name in names, f"deploy-harp.yml does not call ci/{name}"


def test_rule1_every_called_script_exists_and_is_strict() -> None:
    names = called_scripts(DEPLOY.read_text(encoding="utf-8"))
    assert names
    missing = [name for name in names if not (CI / name).is_file()]
    assert missing == []
    findings = {name: found for name in names if (found := header_problems(_read(name)))}
    assert findings == {}


def test_rule2_scripts_redirect_into_ci_out_only() -> None:
    names = [*called_scripts(DEPLOY.read_text(encoding="utf-8")), "lib.sh"]
    sources = {name: _read(name) for name in names}
    out = out_variables(list(sources.values()))
    findings = {name: found for name, text in sources.items() if (found := foreign_redirects(text, out))}
    assert findings == {}
    # Anti vacuum: the rule did see redirections into ci/out/.
    assert sum(len(_REDIRECT.findall("\n".join(code_lines(text)))) for text in sources.values()) >= 20


def test_rule3_canary_runs_the_positive_control_first() -> None:
    assert canary_order_problems(_read("canary.sh")) == []


def test_rule4_queue_checks_at_most_one_and_exactly_one() -> None:
    assert queue_problems(_read("queue.sh")) == []


# -- the self tests --------------------------------------------------------------------

SAMPLE_SCRIPT = """#!/usr/bin/env bash
# A comment may say set -euo pipefail > /tmp/x without counting.
set -euo pipefail
OUT="${CI_OUT}/x.json"
echo "a -> b" >&2
echo ok > "${OUT}"
echo ok >> "${CI_OUT}/y.log" 2> /dev/null
python3 - <<'PY'
print(1 > 2)
PY
"""


def test_self_rule1_fires_on_a_missing_shebang_or_strict_mode() -> None:
    assert header_problems(SAMPLE_SCRIPT) == []
    assert header_problems(SAMPLE_SCRIPT.replace("#!/usr/bin/env bash", "#!/bin/sh")) == [
        "no #!/usr/bin/env bash in the first line"
    ]
    assert header_problems(SAMPLE_SCRIPT.replace("set -euo pipefail\nOUT", "set -eu\nOUT")) == ["no set -euo pipefail"]
    workflow = "run: bash app-src/ci/rights.sh\n# bash app-src/ci/ghost.sh\nrun: bash app-src/ci/canary.sh\n"
    assert called_scripts(workflow) == ["rights.sh", "canary.sh"]


def test_self_rule2_fires_on_a_redirect_outside_ci_out() -> None:
    out = out_variables([SAMPLE_SCRIPT])
    assert foreign_redirects(SAMPLE_SCRIPT, out) == []
    assert foreign_redirects(SAMPLE_SCRIPT + 'echo x > "${NC_ROOT}/data/x"\n', out) == ['"${NC_ROOT}/data/x"']
    assert foreign_redirects(SAMPLE_SCRIPT + "echo x >> ../leak.log\n", out) == ["../leak.log"]
    # A variable that points elsewhere once is not trusted any more.
    twice = SAMPLE_SCRIPT + 'OUT="${RUNNER_TEMP}/x"\n'
    assert foreign_redirects(twice, out_variables([twice])) == ['"${OUT}"']


def test_self_rule3_fires_on_a_negative_search_before_the_positive_control() -> None:
    good = """#!/usr/bin/env bash
set -euo pipefail
hits_in() {
\tgrep -c "$1" "$2"
}
grep -aqF "${CANARY}" original.pdf \\
\t|| fail "positive control failed: not in the original"
hits_in "${CANARY}" dump.sql
"""
    assert canary_order_problems(good) == []
    swapped = good.replace('hits_in "${CANARY}" dump.sql\n', "")
    swapped = swapped.replace("grep -aqF", 'hits_in "${CANARY}" early.sql\ngrep -aqF', 1)
    assert canary_order_problems(swapped) == ["a negative search runs before the positive control"]
    without = good.replace('|| fail "positive control failed: not in the original"', "|| true")
    assert canary_order_problems(without) == ["no positive control of the canary"]


def test_self_rule4_fires_without_either_queue_check() -> None:
    good = """#!/usr/bin/env bash
set -euo pipefail
count=$(db_query "SELECT COUNT(*) FROM oc_pii_jobs WHERE lease_until > 1")
[ "${count}" -le 1 ] || fail "too many"
exactly_one=$(grep -c '^sample [0-9]* active 1$' log)
[ "${exactly_one}" -ge 1 ] || fail "none"
"""
    assert queue_problems(good) == []
    assert queue_problems(good.replace('[ "${count}" -le 1 ]', "true")) == ["no sample is checked for at most 1"]
    assert queue_problems(good.replace('[ "${exactly_one}" -ge 1 ]', "true")) == [
        "no check that a sample saw exactly 1"
    ]
    assert queue_problems(good.replace("lease_until", "status")) == ["the samples do not ask lease_until"]


def test_the_scripts_of_plan_18_are_seen_by_the_rules() -> None:
    # Positive control of the call pattern: the drift scripts, one of them with
    # a hyphen, are in the list the rules check.
    names = called_scripts(DEPLOY.read_text(encoding="utf-8"))
    assert "redeploy.sh" in names
    assert "admin-state.sh" in names
    assert called_scripts("bash app-src/ci/admin-state.sh x.json\n# bash ci/hidden.sh\n") == ["admin-state.sh"]
