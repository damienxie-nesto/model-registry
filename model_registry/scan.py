from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from fnmatch import fnmatch

from model_registry.loader import Registry
from model_registry.schema import Status

#: Paths where naming a model is legitimate rather than a usage decision:
#: evaluation notebooks and reports name rejected models on purpose.
DEFAULT_EXCLUDES: tuple[str, ...] = (
    '*.ipynb',
    'accuracy/*',
    '*/accuracy/*',
    'docs/*',
    '*/docs/*',
    'CHANGELOG*',
    '*.lock',
)

#: Deliberately loose: it is better to warn on a non-model string than to miss a
#: real model ID. False positives are silenced with the ignore comment.
#:
#: This prefix pattern alone misses models registered under other providers
#: (e.g. `mistral-large`, `o3-mini`); `_build_candidate_pattern` unions it with
#: exact matches on every ID the registry knows about so those are not
#: silently unenforceable.
_PREFIX_CANDIDATE = r'(?:gemini|gpt|text-embedding|claude)[-\w.]*'
_IGNORE = re.compile(r'model-registry:\s*ignore')
_HUNK = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')
_TARGET_FILE = re.compile(r'^\+\+\+ b/(.+)$')


def has_file_header(diff_text: str) -> bool:
    """Return whether `diff_text` contains at least one recognizable `+++ b/...` header.

    Used to distinguish a genuinely empty diff (nothing changed) from input that is
    not a parseable unified diff at all, so the latter is never reported as clean.
    """
    return any(_TARGET_FILE.match(line) for line in diff_text.splitlines())


def _build_candidate_pattern(registry: Registry) -> re.Pattern[str]:
    """Build the per-scan regex: the loose prefix pattern plus every registry ID.

    Registry IDs are word-bounded via lookaround on `[-\\w.]` (not `\\b`) so that
    a registered ID never matches as a substring inside a longer, unrelated
    hyphenated identifier.
    """
    known_ids = sorted(registry.ids(), key=len, reverse=True)
    alternatives = [_PREFIX_CANDIDATE, *(re.escape(model_id) for model_id in known_ids)]
    pattern = r'(?<![-\w.])(?:' + '|'.join(alternatives) + r')(?![-\w.])'
    return re.compile(pattern, re.IGNORECASE)


class Severity(StrEnum):
    BLOCK = 'block'
    WARN = 'warn'


@dataclass(frozen=True)
class Finding:
    path: str
    line_no: int
    model_id: str
    reason: str
    severity: Severity

    def format(self) -> str:
        return f'{self.path}:{self.line_no}: {self.severity.value}: {self.model_id} is {self.reason}'


def _is_excluded(path: str, excluded_globs: tuple[str, ...]) -> bool:
    return any(fnmatch(path, pattern) for pattern in excluded_globs)


def _classify(
    model_id: str,
    registry: Registry,
    unknown_severity: Severity,
) -> tuple[str, Severity] | None:
    resolved = registry.by_id(model_id)
    if resolved is None:
        return ('unknown', unknown_severity)
    if resolved.entry.status is Status.DEPRECATED:
        return ('deprecated', Severity.BLOCK)
    if resolved.entry.status is Status.BANNED:
        return ('banned', Severity.BLOCK)
    return None


def scan_diff(
    diff_text: str,
    registry: Registry,
    excluded_globs: tuple[str, ...] = DEFAULT_EXCLUDES,
    unknown_severity: Severity = Severity.WARN,
) -> list[Finding]:
    """Report model IDs introduced by added lines in a unified diff.

    Only added lines are examined, so adopting the check does not require a repo to
    first clean up model IDs it already contains.
    """
    findings: list[Finding] = []
    path = ''
    skip_file = True
    line_no = 0
    candidate_pattern = _build_candidate_pattern(registry)

    for raw_line in diff_text.splitlines():
        target = _TARGET_FILE.match(raw_line)
        if target:
            path = target.group(1)
            skip_file = _is_excluded(path, excluded_globs)
            continue

        hunk = _HUNK.match(raw_line)
        if hunk:
            line_no = int(hunk.group(1))
            continue

        if raw_line.startswith('-'):
            continue

        if not raw_line.startswith('+'):
            line_no += 1
            continue

        content = raw_line[1:]
        if not skip_file and not _IGNORE.search(content):
            findings.extend(_scan_line(content, path, line_no, registry, unknown_severity, candidate_pattern))
        line_no += 1

    return findings


def _scan_line(
    content: str,
    path: str,
    line_no: int,
    registry: Registry,
    unknown_severity: Severity,
    candidate_pattern: re.Pattern[str],
) -> list[Finding]:
    found: list[Finding] = []
    for match in candidate_pattern.finditer(content):
        model_id = match.group(0)
        classification = _classify(model_id, registry, unknown_severity)
        if classification is None:
            continue
        reason, severity = classification
        found.append(
            Finding(path=path, line_no=line_no, model_id=model_id, reason=reason, severity=severity),
        )
    return found
