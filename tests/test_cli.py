from __future__ import annotations

import io
from pathlib import Path

import pytest

from model_registry.cli import main

VALID_ENTRY = """
- id: gemini-2.5-flash
  display_name: Gemini 2.5 Flash
  provider: google
  hosting: vertex
  region: northamerica-northeast1
  residency: canada
  open_weights: false
  trains_on_customer_data: false
  use_cases: [ocr]
  status: approved
  approved_on: 2026-09-16
  approval_ref: https://github.com/OWNER/model-registry/pull/1
  review_by: 2099-01-01
"""


def test_validate_passes_on_good_registry(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY)
    assert main(['validate', '--registry', str(registry)]) == 0
    assert 'gemini-2.5-flash' not in capsys.readouterr().err


def test_validate_fails_on_bad_registry(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY.replace('residency: canada', 'residency: mars'))
    assert main(['validate', '--registry', str(registry)]) == 1
    assert 'gemini-2.5-flash' in capsys.readouterr().err


def test_render_writes_the_table(tmp_path: Path) -> None:
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY)
    readme = tmp_path / 'README.md'
    readme.write_text('# x\n<!-- BEGIN MODELS -->\n<!-- END MODELS -->\n')

    assert main(['render', '--registry', str(registry), '--readme', str(readme)]) == 0
    assert '`gemini-2.5-flash`' in readme.read_text()


def test_render_check_fails_when_readme_is_stale(tmp_path: Path) -> None:
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY)
    readme = tmp_path / 'README.md'
    readme.write_text('# x\n<!-- BEGIN MODELS -->\n<!-- END MODELS -->\n')

    assert main(['render', '--registry', str(registry), '--readme', str(readme), '--check']) == 1


def test_render_check_passes_when_readme_is_current(tmp_path: Path) -> None:
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY)
    readme = tmp_path / 'README.md'
    readme.write_text('# x\n<!-- BEGIN MODELS -->\n<!-- END MODELS -->\n')

    main(['render', '--registry', str(registry), '--readme', str(readme)])
    assert main(['render', '--registry', str(registry), '--readme', str(readme), '--check']) == 0


def test_scan_blocks_on_banned_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY.replace('status: approved', 'status: banned'))
    diff = "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1,0 +1,1 @@\n+MODEL = 'gemini-2.5-flash'\n"
    monkeypatch.setattr('sys.stdin', io.StringIO(diff))

    assert main(['scan', '--registry', str(registry)]) == 1
    assert 'banned' in capsys.readouterr().err


def test_scan_warn_only_exits_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY)
    diff = "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1,0 +1,1 @@\n+MODEL = 'gpt-9-ultra'\n"
    monkeypatch.setattr('sys.stdin', io.StringIO(diff))

    assert main(['scan', '--registry', str(registry)]) == 0


def test_scan_block_unknown_exits_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY)
    diff = "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1,0 +1,1 @@\n+MODEL = 'gpt-9-ultra'\n"
    monkeypatch.setattr('sys.stdin', io.StringIO(diff))

    assert main(['scan', '--registry', str(registry), '--block-unknown']) == 1


def test_scan_rejects_input_with_no_recognizable_diff_header(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY)
    monkeypatch.setattr('sys.stdin', io.StringIO('not a unified diff\njust some noise\n'))

    assert main(['scan', '--registry', str(registry)]) == 1
    assert 'diff' in capsys.readouterr().err.lower()


def test_scan_on_genuinely_empty_diff_is_clean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY)
    monkeypatch.setattr('sys.stdin', io.StringIO(''))

    assert main(['scan', '--registry', str(registry)]) == 0
    assert capsys.readouterr().out == '0 warning(s), no blocking model usage\n'


def test_registry_flag_before_subcommand_is_honoured(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY.replace('residency: canada', 'residency: mars'))

    assert main(['--registry', str(registry), 'validate']) == 1
    assert 'gemini-2.5-flash' in capsys.readouterr().err


def test_registry_flag_before_subcommand_is_honoured_for_render(tmp_path: Path) -> None:
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY.replace('id: gemini-2.5-flash', 'id: zzz-pre-subcommand-registry-flag'))
    readme = tmp_path / 'README.md'
    readme.write_text('# x\n<!-- BEGIN MODELS -->\n<!-- END MODELS -->\n')

    assert main(['--registry', str(registry), 'render', '--readme', str(readme)]) == 0
    assert '`zzz-pre-subcommand-registry-flag`' in readme.read_text()


def test_registry_flag_before_subcommand_is_honoured_for_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY.replace('status: approved', 'status: banned'))
    diff = "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1,0 +1,1 @@\n+MODEL = 'gemini-2.5-flash'\n"
    monkeypatch.setattr('sys.stdin', io.StringIO(diff))

    assert main(['--registry', str(registry), 'scan']) == 1
    assert 'banned' in capsys.readouterr().err


def test_registry_flag_precedence_prefers_the_post_subcommand_value(tmp_path: Path) -> None:
    before_registry = tmp_path / 'before.yaml'
    before_registry.write_text(VALID_ENTRY.replace('residency: canada', 'residency: mars'))
    after_registry = tmp_path / 'after.yaml'
    after_registry.write_text(VALID_ENTRY)

    assert main(['--registry', str(before_registry), 'validate', '--registry', str(after_registry)]) == 0


def test_registry_flag_after_subcommand_works_for_all_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = tmp_path / 'models.yaml'
    registry.write_text(VALID_ENTRY)
    readme = tmp_path / 'README.md'
    readme.write_text('# x\n<!-- BEGIN MODELS -->\n<!-- END MODELS -->\n')

    assert main(['validate', '--registry', str(registry)]) == 0
    assert main(['render', '--registry', str(registry), '--readme', str(readme)]) == 0

    monkeypatch.setattr('sys.stdin', io.StringIO(''))
    assert main(['scan', '--registry', str(registry)]) == 0
