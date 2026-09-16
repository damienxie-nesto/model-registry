from __future__ import annotations

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
