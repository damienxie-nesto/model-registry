from __future__ import annotations

from datetime import date

import pytest

from model_registry.loader import Registry, ResolvedModel
from model_registry.policy import Tier
from model_registry.scan import Severity, has_file_header, scan_diff
from model_registry.schema import Hosting, ModelEntry, Provider, Residency, Status, UseCase


def _resolved(model_id: str, status: Status) -> ResolvedModel:
    entry = ModelEntry(
        id=model_id,
        display_name=model_id,
        provider=Provider.GOOGLE,
        hosting=Hosting.VERTEX,
        region='northamerica-northeast1',
        residency=Residency.CANADA,
        open_weights=False,
        trains_on_customer_data=False,
        use_cases=[UseCase.OCR],
        status=status,
        approved_on=date(2026, 9, 16),
        approval_ref='https://github.com/damienxie-nesto/model-registry/pull/1',
        review_by=date(2099, 1, 1),
        replacement='gemini-3.5-flash' if status is Status.DEPRECATED else None,
    )
    return ResolvedModel(entry=entry, tiers=frozenset({Tier.STANDARD}))


@pytest.fixture
def registry() -> Registry:
    return Registry(
        models=(
            _resolved('gemini-3.5-flash', Status.APPROVED),
            _resolved('gemini-2.5-pro', Status.DEPRECATED),
            _resolved('gpt-4o', Status.BANNED),
            _resolved('mistral-large', Status.BANNED),
        ),
    )


def _diff(path: str, *added: str) -> str:
    body = '\n'.join(f'+{line}' for line in added)
    return f'diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1,0 +1,{len(added)} @@\n{body}\n'


def test_approved_model_produces_no_finding(registry: Registry) -> None:
    assert scan_diff(_diff('app.py', "MODEL = 'gemini-3.5-flash'"), registry) == []


def test_deprecated_model_blocks(registry: Registry) -> None:
    findings = scan_diff(_diff('app.py', "MODEL = 'gemini-2.5-pro'"), registry)
    assert len(findings) == 1
    assert findings[0].severity is Severity.BLOCK
    assert findings[0].reason == 'deprecated'


def test_banned_model_blocks(registry: Registry) -> None:
    findings = scan_diff(_diff('app.py', "MODEL = 'gpt-4o'"), registry)
    assert findings[0].severity is Severity.BLOCK
    assert findings[0].reason == 'banned'


def test_unknown_model_warns_by_default(registry: Registry) -> None:
    findings = scan_diff(_diff('app.py', "MODEL = 'gemini-9.9-turbo'"), registry)
    assert findings[0].severity is Severity.WARN
    assert findings[0].reason == 'unknown'


def test_unknown_model_can_be_escalated_to_block(registry: Registry) -> None:
    findings = scan_diff(
        _diff('app.py', "MODEL = 'gemini-9.9-turbo'"),
        registry,
        unknown_severity=Severity.BLOCK,
    )
    assert findings[0].severity is Severity.BLOCK


def test_ignore_comment_suppresses_the_finding(registry: Registry) -> None:
    diff = _diff('app.py', "MODEL = 'gemini-2.5-pro'  # model-registry: ignore benchmarking only")
    assert scan_diff(diff, registry) == []


def test_excluded_paths_are_skipped(registry: Registry) -> None:
    assert scan_diff(_diff('accuracy/report.py', "M = 'gemini-2.5-pro'"), registry) == []
    assert scan_diff(_diff('notebook.ipynb', "M = 'gemini-2.5-pro'"), registry) == []
    assert scan_diff(_diff('docs/models.md', "M = 'gemini-2.5-pro'"), registry) == []


def test_removed_lines_are_ignored(registry: Registry) -> None:
    diff = (
        'diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n'
        "@@ -1,1 +1,1 @@\n-MODEL = 'gemini-2.5-pro'\n+MODEL = 'gemini-3.5-flash'\n"
    )
    assert scan_diff(diff, registry) == []


def test_line_numbers_come_from_the_hunk_header(registry: Registry) -> None:
    diff = (
        "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -40,0 +42,2 @@\n+# comment\n+MODEL = 'gpt-4o'\n"
    )
    findings = scan_diff(diff, registry)
    assert findings[0].line_no == 43


def test_multiple_models_on_one_line_each_report(registry: Registry) -> None:
    diff = _diff('app.py', "PAIR = ('gemini-2.5-pro', 'gpt-4o')")
    assert {finding.model_id for finding in scan_diff(diff, registry)} == {'gemini-2.5-pro', 'gpt-4o'}


def test_non_prefix_registry_id_is_still_classified(registry: Registry) -> None:
    diff = _diff('app.py', "MODEL = 'mistral-large'")
    findings = scan_diff(diff, registry)
    assert len(findings) == 1
    assert findings[0].model_id == 'mistral-large'
    assert findings[0].severity is Severity.BLOCK
    assert findings[0].reason == 'banned'


def test_multi_file_diff_resets_state_between_files(registry: Registry) -> None:
    diff = (
        'diff --git a/accuracy/report.py b/accuracy/report.py\n'
        '--- a/accuracy/report.py\n+++ b/accuracy/report.py\n'
        "@@ -1,0 +1,1 @@\n+MODEL = 'gemini-2.5-pro'\n"
        'diff --git a/app.py b/app.py\n'
        '--- a/app.py\n+++ b/app.py\n'
        "@@ -1,0 +1,1 @@\n+MODEL = 'gemini-2.5-pro'\n"
    )
    findings = scan_diff(diff, registry)
    assert len(findings) == 1
    assert findings[0].path == 'app.py'


def test_multi_file_diff_resets_state_between_files_reverse_order(registry: Registry) -> None:
    diff = (
        'diff --git a/app.py b/app.py\n'
        '--- a/app.py\n+++ b/app.py\n'
        "@@ -1,0 +1,1 @@\n+MODEL = 'gemini-2.5-pro'\n"
        'diff --git a/accuracy/report.py b/accuracy/report.py\n'
        '--- a/accuracy/report.py\n+++ b/accuracy/report.py\n'
        "@@ -1,0 +1,1 @@\n+MODEL = 'gemini-2.5-pro'\n"
    )
    findings = scan_diff(diff, registry)
    assert len(findings) == 1
    assert findings[0].path == 'app.py'


def test_banned_model_blocks_regardless_of_casing(registry: Registry) -> None:
    """A capitalisation difference must not turn a BLOCK into a WARN.

    The candidate pattern has always matched case-insensitively while `Registry.by_id`
    resolved case-sensitively, so `GPT-4o` came back *unknown* — exit 0 — for a model
    the registry bans.
    """
    findings = scan_diff(_diff('app.py', "MODEL = 'GPT-4o'"), registry)
    assert len(findings) == 1
    assert findings[0].severity is Severity.BLOCK
    assert findings[0].reason == 'banned'


def test_mixed_case_deprecated_model_blocks(registry: Registry) -> None:
    findings = scan_diff(_diff('app.py', "MODEL = 'Gemini-2.5-Pro'"), registry)
    assert len(findings) == 1
    assert findings[0].severity is Severity.BLOCK
    assert findings[0].reason == 'deprecated'


def test_finding_reports_the_model_id_as_written(registry: Registry) -> None:
    """Report the string the developer actually typed so the message is actionable."""
    findings = scan_diff(_diff('app.py', "MODEL = 'GPT-4o'"), registry)
    assert findings[0].model_id == 'GPT-4o'


def test_approved_model_produces_no_finding_in_any_casing(registry: Registry) -> None:
    assert scan_diff(_diff('app.py', "MODEL = 'Gemini-3.5-Flash'"), registry) == []


def test_added_line_starting_with_plus_plus_b_does_not_hijack_the_file_header(registry: Registry) -> None:
    """Added content that looks like a header must not stop the scan.

    A file quoting a diff (docs fixture, changelog, test data) can add a line whose
    content begins `++ b/`. That used to be consumed as a `+++ b/<path>` header: the
    scanner switched to a made-up path, and the rest of the real file went unscanned
    with no diagnostic and exit 0 — a scan that did not scan, reported as clean.
    """
    diff = _diff(
        'app.py',
        '++ b/docs/quoted-patch.txt',
        'SAMPLE = "unchanged"',
        "MODEL = 'gpt-4o'",
    )
    findings = scan_diff(diff, registry)
    assert [finding.model_id for finding in findings] == ['gpt-4o']
    assert findings[0].path == 'app.py'
    assert findings[0].severity is Severity.BLOCK


def test_added_line_starting_with_plus_plus_b_does_not_redirect_to_an_excluded_path(registry: Registry) -> None:
    """The same hijack aimed at an excluded glob, which is the silent-skip version."""
    diff = _diff('app.py', '++ b/docs/anything.md', "MODEL = 'gpt-4o'")
    assert [finding.model_id for finding in scan_diff(diff, registry)] == ['gpt-4o']


def test_has_file_header_ignores_a_hijacked_header() -> None:
    assert has_file_header(_diff('app.py', '++ b/docs/quoted-patch.txt')) is True
    assert has_file_header('+++ b/docs/quoted-patch.txt\n') is False
