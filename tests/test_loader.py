from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from model_registry.loader import Registry, RegistryError, check_reviews_current, load_registry
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
    registry = load_registry(_write(tmp_path, VALID_ENTRY))
    assert isinstance(registry, Registry)
    resolved = registry.by_id('gemini-2.5-flash')
    assert resolved is not None
    assert Tier.BANK in resolved.tiers


def test_unknown_id_returns_none(tmp_path: Path) -> None:
    registry = load_registry(_write(tmp_path, VALID_ENTRY))
    assert registry.by_id('nope') is None


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match='duplicate'):
        load_registry(_write(tmp_path, VALID_ENTRY + VALID_ENTRY))


def test_overdue_review_still_loads(tmp_path: Path) -> None:
    """A lapsed review is a governance signal, not a structural defect.

    `load_registry` runs in every consumer repo's PR check and in the drift routine, so
    a rule that fires here fires everywhere the day the dates pass. `validate` — this
    repo's own CI gate — is where the lapse is caught; see
    `test_lapsed_review_loads_for_consumers_but_fails_validate` in `test_cli.py`.
    """
    registry = load_registry(_write(tmp_path, VALID_ENTRY))
    assert registry.ids() == frozenset({'gemini-2.5-flash'})


def test_overdue_review_is_rejected_by_check_reviews_current(tmp_path: Path) -> None:
    registry = load_registry(_write(tmp_path, VALID_ENTRY))
    with pytest.raises(RegistryError, match='review_by'):
        check_reviews_current(registry, today=date(2028, 1, 1))


def test_current_review_passes_check_reviews_current(tmp_path: Path) -> None:
    registry = load_registry(_write(tmp_path, VALID_ENTRY))
    check_reviews_current(registry, today=date(2026, 9, 16))


def test_bank_tier_with_an_unverified_region_is_rejected(tmp_path: Path) -> None:
    content = VALID_ENTRY.replace('region: northamerica-northeast1', 'region: unverified')
    with pytest.raises(RegistryError, match=re.escape('region is')):
        load_registry(_write(tmp_path, content))


def test_bank_tier_with_an_empty_region_is_rejected(tmp_path: Path) -> None:
    content = VALID_ENTRY.replace('region: northamerica-northeast1', "region: ''")
    with pytest.raises(RegistryError, match=re.escape('region is')):
        load_registry(_write(tmp_path, content))


def test_unverified_region_is_fine_when_the_facts_do_not_grant_bank(tmp_path: Path) -> None:
    content = VALID_ENTRY.replace('region: northamerica-northeast1', 'region: unverified').replace(
        'status: approved',
        'status: trial',
    )
    registry = load_registry(_write(tmp_path, content))
    resolved = registry.by_id('gemini-2.5-flash')
    assert resolved is not None
    assert Tier.BANK not in resolved.tiers


def test_dangling_replacement_is_rejected(tmp_path: Path) -> None:
    content = VALID_ENTRY.replace('status: approved', 'status: deprecated\n  replacement: ghost-model')
    with pytest.raises(RegistryError, match='replacement'):
        load_registry(_write(tmp_path, content))


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match='empty'):
        load_registry(_write(tmp_path, ''))


def test_invalid_entry_reports_the_model_id(tmp_path: Path) -> None:
    content = VALID_ENTRY.replace('residency: canada', 'residency: mars')
    with pytest.raises(RegistryError, match=re.escape('gemini-2.5-flash')):
        load_registry(_write(tmp_path, content))


def test_ids_returns_every_model(tmp_path: Path) -> None:
    registry = load_registry(_write(tmp_path, VALID_ENTRY))
    assert registry.ids() == frozenset({'gemini-2.5-flash'})


def test_non_list_top_level_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match=re.escape('must contain a list')):
        load_registry(_write(tmp_path, 'models: []'))


def test_malformed_yaml_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match=re.escape('not valid YAML')):
        load_registry(_write(tmp_path, '- id: [unclosed'))
