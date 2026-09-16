from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from model_registry.schema import Hosting, ModelEntry, Provider, Residency, Status, UseCase


def _entry(**overrides: object) -> ModelEntry:
    base: dict[str, object] = {
        'id': 'gemini-2.5-flash',
        'display_name': 'Gemini 2.5 Flash',
        'provider': Provider.GOOGLE,
        'hosting': Hosting.VERTEX,
        'region': 'northamerica-northeast1',
        'residency': Residency.CANADA,
        'open_weights': False,
        'trains_on_customer_data': False,
        'use_cases': [UseCase.OCR],
        'status': Status.APPROVED,
        'approved_on': date(2026, 9, 16),
        'approval_ref': 'https://github.com/damienxie-nesto/model-registry/pull/1',
        'review_by': date(2027, 9, 16),
    }
    base.update(overrides)
    return ModelEntry(**base)  # type: ignore[arg-type]


def test_valid_entry_parses() -> None:
    entry = _entry()
    assert entry.id == 'gemini-2.5-flash'
    assert entry.residency is Residency.CANADA


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _entry(bank_approved=True)


def test_deprecated_without_replacement_is_rejected() -> None:
    with pytest.raises(ValidationError, match='requires a replacement'):
        _entry(status=Status.DEPRECATED)


def test_deprecated_with_replacement_parses() -> None:
    entry = _entry(status=Status.DEPRECATED, replacement='gemini-3.5-flash')
    assert entry.replacement == 'gemini-3.5-flash'


def test_empty_use_cases_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _entry(use_cases=[])


def test_entry_is_frozen() -> None:
    entry = _entry()
    with pytest.raises(ValidationError):
        entry.id = 'other'
