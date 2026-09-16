from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from model_registry.loader import Registry, RegistryError, load_registry
from model_registry.policy import Tier

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
  review_by: 2027-09-16
"""


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / 'models.yaml'
    path.write_text(content)
    return path


def test_loads_and_derives_tiers(tmp_path: Path) -> None:
    registry = load_registry(_write(tmp_path, VALID_ENTRY), today=date(2026, 9, 16))
    assert isinstance(registry, Registry)
    resolved = registry.by_id('gemini-2.5-flash')
    assert resolved is not None
    assert Tier.BANK in resolved.tiers


def test_unknown_id_returns_none(tmp_path: Path) -> None:
    registry = load_registry(_write(tmp_path, VALID_ENTRY), today=date(2026, 9, 16))
    assert registry.by_id('nope') is None


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match='duplicate'):
        load_registry(_write(tmp_path, VALID_ENTRY + VALID_ENTRY), today=date(2026, 9, 16))


def test_overdue_review_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match='review_by'):
        load_registry(_write(tmp_path, VALID_ENTRY), today=date(2028, 1, 1))


def test_dangling_replacement_is_rejected(tmp_path: Path) -> None:
    content = VALID_ENTRY.replace('status: approved', 'status: deprecated\n  replacement: ghost-model')
    with pytest.raises(RegistryError, match='replacement'):
        load_registry(_write(tmp_path, content), today=date(2026, 9, 16))


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match='empty'):
        load_registry(_write(tmp_path, ''), today=date(2026, 9, 16))


def test_invalid_entry_reports_the_model_id(tmp_path: Path) -> None:
    content = VALID_ENTRY.replace('residency: canada', 'residency: mars')
    with pytest.raises(RegistryError, match=re.escape('gemini-2.5-flash')):
        load_registry(_write(tmp_path, content), today=date(2026, 9, 16))


def test_ids_returns_every_model(tmp_path: Path) -> None:
    registry = load_registry(_write(tmp_path, VALID_ENTRY), today=date(2026, 9, 16))
    assert registry.ids() == frozenset({'gemini-2.5-flash'})
